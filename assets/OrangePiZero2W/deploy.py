# -*- coding: utf-8 -*-
"""Safely update the MBT03 client on an already reachable Orange Pi."""

import argparse
import getpass
import hashlib
import os
import posixpath
import shlex
import sys
import uuid
import time

import paramiko


LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(LOCAL_DIR, "..", ".."))
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")
COMMON_DIR = os.path.join(ASSETS_DIR, "server_client")
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
if ASSETS_DIR not in sys.path:
    sys.path.insert(0, ASSETS_DIR)

DEPLOY_FILES = {
    os.path.join(LOCAL_DIR, "r_client.py"): "r_client.py",
    os.path.join(LOCAL_DIR, "connection_led.py"): "connection_led.py",
    os.path.join(LOCAL_DIR, "wifi_defaults.json"): "wifi_defaults.json",
    os.path.join(LOCAL_DIR, "wifi_sync.py"): "wifi_sync.py",
    os.path.join(LOCAL_DIR, "wifi_manager.py"): "wifi_manager.py",
    os.path.join(COMMON_DIR, "__init__.py"): "server_client/__init__.py",
    os.path.join(COMMON_DIR, "client_core.py"): "server_client/client_core.py",
    os.path.join(COMMON_DIR, "protocol.py"): "server_client/protocol.py",
    os.path.join(COMMON_DIR, "discovery.py"): "server_client/discovery.py",
}


def _run(client, command, *, check=True):
    _stdin, stdout, stderr = client.exec_command(command)
    output = stdout.read().decode("utf-8", "ignore")
    error = stderr.read().decode("utf-8", "ignore")
    status = stdout.channel.recv_exit_status()
    if check and status != 0:
        raise RuntimeError(
            f"Remote command failed ({status}): {command}\n{error or output}"
        )
    return output.strip(), status


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_install(client, source, destination):
    """Never truncate a live runtime file, including on a failed copy."""
    script = (
        "import os,shutil,tempfile; "
        f"src={source!r}; dst={destination!r}; "
        "parent=os.path.dirname(dst); "
        "fd,tmp=tempfile.mkstemp(prefix='.mbt03-install-',dir=parent); "
        "os.close(fd); shutil.copyfile(src,tmp); os.chmod(tmp,0o600); "
        "f=open(tmp,'rb'); os.fsync(f.fileno()); f.close(); "
        "os.replace(tmp,dst); "
        "fd=os.open(parent,os.O_RDONLY); os.fsync(fd); os.close(fd)"
    )
    _run(client, f"python3 -c {shlex.quote(script)}")


def _verify_service(client, duration=24):
    """An instant is-active check also passes a rapidly crashing service."""
    deadline = time.monotonic() + duration
    initial_pid = None
    while True:
        output, _ = _run(client, "systemctl show mbt03-client "
                         "-p ActiveState -p MainPID -p NRestarts")
        state = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
        pid = state.get('MainPID', '0')
        if state.get('ActiveState') != 'active' or pid == '0':
            raise RuntimeError(f"Client did not remain active: {state}")
        identity = (pid, state.get('NRestarts'))
        if initial_pid is None:
            initial_pid = identity
        elif identity != initial_pid:
            raise RuntimeError(f"Client restarted during verification: {state}")
        if time.monotonic() >= deadline:
            return
        time.sleep(2)


def _connect(args):
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    known_hosts = os.path.expanduser("~/.ssh/known_hosts")
    if os.path.exists(known_hosts):
        client.load_host_keys(known_hosts)
    if args.trust_new_host:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    password = args.password
    if password is None and sys.stdin.isatty():
        password = getpass.getpass(
            "SSH password (để trống nếu dùng SSH key): "
        ) or None
    client.connect(
        args.host,
        username=args.user,
        password=password,
        timeout=15,
        banner_timeout=15,
        look_for_keys=True,
        allow_agent=True,
    )
    if args.trust_new_host:
        try:
            os.makedirs(os.path.dirname(known_hosts), exist_ok=True)
            client.save_host_keys(known_hosts)
        except OSError:
            pass
    return client


def _rollback_targets(live_dir):
    targets = [
        (posixpath.join(live_dir, relative), f"live/{relative}")
        for relative in DEPLOY_FILES.values()
    ]
    targets.extend([
        (posixpath.join(live_dir, "security_config.json"),
         "live/security_config.json"),
        (posixpath.join(live_dir, "server_client/security.py"),
         "live/server_client/security.py"),
        ("/etc/systemd/system/mbt03-client.service.d/runtime.conf",
         "service/runtime.conf"),
        ("/etc/systemd/system/wifi-watchdog.service.d/mbt03-transaction.conf",
         "service/wifi-watchdog-mbt03-transaction.conf"),
    ])
    return targets


def _snapshot_remote_files(client, stage_dir, targets):
    """Save every file that may be replaced, including missing-file markers."""
    for source, key in targets:
        backup = posixpath.join(stage_dir, "rollback/files", key)
        missing = posixpath.join(stage_dir, "rollback/missing", key)
        command = (
            f"install -d -m 700 {shlex.quote(posixpath.dirname(backup))} "
            f"{shlex.quote(posixpath.dirname(missing))} && "
            f"if [ -e {shlex.quote(source)} ]; then "
            f"cp -p -- {shlex.quote(source)} {shlex.quote(backup)}; "
            f"else : > {shlex.quote(missing)}; fi"
        )
        _run(client, command)


def _restore_remote_files(client, stage_dir, targets):
    """Restore the exact pre-deploy file set after a failed installation."""
    for destination, key in targets:
        backup = posixpath.join(stage_dir, "rollback/files", key)
        missing = posixpath.join(stage_dir, "rollback/missing", key)
        command = (
            f"if [ -e {shlex.quote(backup)} ]; then "
            f"install -d {shlex.quote(posixpath.dirname(destination))} && "
            f"cp -p -- {shlex.quote(backup)} {shlex.quote(destination)}; "
            f"elif [ -e {shlex.quote(missing)} ]; then "
            f"rm -f -- {shlex.quote(destination)}; fi"
        )
        _run(client, command)


def deploy(args):
    # Required, private local configuration; never silently deploy an image
    # that lacks the requested startup fallback credentials.
    from OrangePiZero2W.wifi_sync import _load_startup_defaults
    _load_startup_defaults()
    stage_name = f"mbt03-deploy-{uuid.uuid4().hex[:10]}"
    stage_dir = f"/root/{stage_name}"
    live_dir = "/root/mbt03"
    service_was_stopped = False
    backup_ready = False
    install_started = False
    client = None
    rollback_targets = _rollback_targets(live_dir)

    try:
        print(f"Deploying to Orange Pi Zero 2W ({args.host})...")
        client = _connect(args)

        _run(client, f"install -d -m 700 {shlex.quote(stage_dir)}/server_client")
        sftp = client.open_sftp()
        try:
            for local_path, relative_remote in DEPLOY_FILES.items():
                if not os.path.isfile(local_path):
                    raise FileNotFoundError(local_path)
                if os.path.getsize(local_path) == 0 and relative_remote != 'server_client/__init__.py':
                    raise ValueError(f"Refusing empty runtime file: {relative_remote}")
                remote_path = posixpath.join(stage_dir, relative_remote)
                sftp.put(local_path, remote_path)

        finally:
            sftp.close()

        expected = {
            relative: _sha256(local)
            for local, relative in DEPLOY_FILES.items()
        }
        for relative, local_digest in expected.items():
            remote_path = posixpath.join(stage_dir, relative)
            output, _status = _run(
                client, f"sha256sum {shlex.quote(remote_path)}"
            )
            if output.split()[0].lower() != local_digest.lower():
                raise RuntimeError(f"Hash mismatch after upload: {relative}")

        # Abort before stopping the live service when the board image is not
        # ready for the transactional Wi-Fi and shared ZMQ runtime.
        dependency_check = "import yaml, zmq, zeroconf, cv2, numpy, serial; from PyQt5.QtCore import QObject"
        _run(client, f"python3 -c {shlex.quote(dependency_check)}")

        _run(
            client,
            "python3 -m py_compile "
            + " ".join(
                shlex.quote(posixpath.join(stage_dir, relative))
                for relative in DEPLOY_FILES.values()
                if relative.endswith(".py")
            ),
        )

        # Keep a file-for-file rollback copy before touching the live service.
        # New files receive a missing marker so rollback removes them again.
        _snapshot_remote_files(client, stage_dir, rollback_targets)
        backup_ready = True
        backup_path, _status = _run(
            client,
            "install -d -m 700 /root/mbt03-backups && "
            "backup=/root/mbt03-backups/mbt03-before-plaintext-$(date +%Y%m%d-%H%M%S).tar.gz && "
            f"tar -czf \"$backup\" -C /root mbt03 {shlex.quote(stage_name)}/rollback && printf '%s' \"$backup\"",
        )
        print(f"Persistent board backup: {backup_path}")
        _run(client, "systemctl stop mbt03-client")
        service_was_stopped = True
        install_started = True
        _run(client, f"install -d -m 700 {live_dir}/server_client")
        for relative in DEPLOY_FILES.values():
            source = posixpath.join(stage_dir, relative)
            destination = posixpath.join(live_dir, relative)
            _atomic_install(client, source, destination)
            output, _ = _run(client, f"sha256sum {shlex.quote(destination)}")
            if output.split()[0].lower() != expected[relative].lower():
                raise RuntimeError(f"Live hash mismatch: {relative}")
        _run(
            client,
            f"rm -f -- {live_dir}/security_config.json "
            f"{live_dir}/server_client/security.py",
        )
        _run(
            client,
            "install -d -m 755 /etc/systemd/system/mbt03-client.service.d && "
            "printf '[Service]\\nUser=root\\nExecStartPre=\\nTimeoutStopSec=20\\n"
            "Environment=PYTHONDONTWRITEBYTECODE=1\\n"
            "Environment=MBT03_UART_WIFI_SYNC=1\\n' "
            "> /etc/systemd/system/mbt03-client.service.d/runtime.conf && "
            "systemctl daemon-reload",
        )
        _run(
            client,
            "if systemctl cat wifi-watchdog.service >/dev/null 2>&1; then "
            "install -d -m 755 /etc/systemd/system/wifi-watchdog.service.d && "
            "printf '[Unit]\\nConditionPathExists=!/run/mbt03-wifi-change\\n' "
            "> /etc/systemd/system/wifi-watchdog.service.d/mbt03-transaction.conf; "
            "fi && systemctl daemon-reload",
        )
        _run(client, "systemctl start mbt03-client")
        print("Checking stable client process for 24 seconds...")
        _verify_service(client)
        service_was_stopped = False
        print("Done. Live hashes verified; client process remained stable. Server pairing must be checked separately.")
    finally:
        if client is not None:
            if service_was_stopped:
                if backup_ready and install_started:
                    try:
                        _run(
                            client,
                            "systemctl stop mbt03-client",
                            check=False,
                        )
                        _restore_remote_files(
                            client, stage_dir, rollback_targets
                        )
                        _run(client, "systemctl daemon-reload", check=False)
                        print(
                            "Deploy failed after service stop; restored the "
                            "pre-deploy files.",
                            file=sys.stderr,
                        )
                    except Exception as rollback_exc:
                        print(
                            f"WARNING: deploy rollback failed: {rollback_exc}",
                            file=sys.stderr,
                        )
                try:
                    _run(client, "systemctl start mbt03-client", check=False)
                except Exception:
                    pass
            try:
                # Exact generated staging path; never target /root or live_dir.
                _run(client, f"rm -r -- {shlex.quote(stage_dir)}", check=False)
            except Exception:
                pass
            client.close()


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", nargs="?", default=os.environ.get("OPI_IP"))
    parser.add_argument("--user", default=os.environ.get("OPI_USER", "root"))
    parser.add_argument(
        "--password",
        default=os.environ.get("OPI_PASSWORD"),
        help="SSH password; prefer OPI_PASSWORD or the interactive prompt",
    )
    parser.add_argument(
        "--trust-new-host",
        action="store_true",
        help="Trust and save a board host key that is not in known_hosts",
    )
    args = parser.parse_args(argv)
    if not args.host:
        parser.error("host is required (or set OPI_IP)")
    return args


def main(argv=None):
    try:
        deploy(_parse_args(argv))
        return 0
    except Exception as exc:
        print(f"Deploy failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
