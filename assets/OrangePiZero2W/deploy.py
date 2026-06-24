import paramiko
import time
import os
import sys

# CONFIG
host = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("OPI_IP")
if not host:
    raise SystemExit("Usage: python OrangePiZero2W/deploy.py <ORANGE_PI_IP>  (or set OPI_IP)")
user = "root"
password = "1"
local_dir = os.path.dirname(__file__)
common_dir = os.path.join(local_dir, "..", "server_client")

def deploy():
    try:
        print(f"Deploying to Orange Pi Zero 2W ({host})...")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(host, username=user, password=password, timeout=10)

        client.exec_command("systemctl stop mbt03-client")
        
        sftp = client.open_sftp()
        client.exec_command("mkdir -p /root/mbt03/server_client")
        
        # Upload Board-specific files
        sftp.put(os.path.join(local_dir, "r_client.py"), "/root/mbt03/r_client.py")
        
        # Upload Common Core files
        for f in ["client_core.py", "protocol.py", "discovery.py"]:
            sftp.put(os.path.join(common_dir, f), f"/root/mbt03/server_client/{f}")
        
        sftp.close()

        print("Optimizing Orange Pi performance...")
        client.exec_command("echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor")
        client.exec_command(
            "mkdir -p /etc/systemd/system/mbt03-client.service.d && "
            "printf '[Service]\\nEnvironment=PYTHONDONTWRITEBYTECODE=1\\n' "
            "> /etc/systemd/system/mbt03-client.service.d/runtime.conf && "
            "systemctl daemon-reload"
        )
        client.exec_command(
            "mkdir -p /etc/systemd/journald.conf.d && "
            "printf '[Journal]\\nStorage=volatile\\nRuntimeMaxUse=8M\\n"
            "RuntimeMaxFileSize=2M\\nForwardToSyslog=yes\\n' "
            "> /etc/systemd/journald.conf.d/99-mbt03-volatile.conf && "
            "systemctl disable --now apt-daily.timer apt-daily-upgrade.timer "
            "dpkg-db-backup.timer man-db.timer e2scrub_all.timer "
            "fake-hwclock-save.timer fake-hwclock-save.service logrotate.timer "
            "2>/dev/null || true"
        )

        client.exec_command("systemctl start mbt03-client")
        print("Done! Orange Pi Client is running (using Hardware UART5).")
        client.close()

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    deploy()
