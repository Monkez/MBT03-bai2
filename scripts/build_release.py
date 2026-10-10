"""Build a versioned, portable Windows folder without copying local device data."""

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
DIST_DIR = PROJECT_DIR / "dist"
BUILD_DIR = PROJECT_DIR / "build"
STATE_FILE = PROJECT_DIR / "build_state.json"
BUILD_PREFIX = "MBT03-Bai2"

# Whitelist resources; never copy all of assets (device credentials, captures).
DATA_FILES = (
    ("assets/app.ico", "assets"),
    ("assets/configurations/config.json", "assets/configurations"),
    ("assets/fonts", "assets/fonts"),
    ("assets/images", "assets/images"),
    ("assets/models", "assets/models"),
    ("assets/qt", "assets/qt"),
    ("assets/signs", "assets/signs"),
    ("assets/sounds", "assets/sounds"),
    # Hidden-imported promoted widgets live at the bundle root when frozen.
    ("MonkezCustomWidgets/monkez_assets", "monkez_assets"),
)
HIDDEN_IMPORTS = (
    "qfluentwidgets", "monkez_button", "monkez_combobox",
    "monkez_image", "monkez_usb_camera",
)


def next_build_name():
    version = 0
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        version = int(state["version"])
        if version < 0:
            raise ValueError("build_state.json: version must be nonnegative")
    pattern = re.compile(rf"^{re.escape(BUILD_PREFIX)}-V(\d+)-\d{{6}}$")
    if DIST_DIR.exists():
        for path in DIST_DIR.iterdir():
            match = pattern.fullmatch(path.name)
            if match:
                version = max(version, int(match[1]))
    version += 1
    build_date = datetime.now().strftime("%d%m%y")
    return version, build_date, f"{BUILD_PREFIX}-V{version}-{build_date}"


def pyinstaller_command(build_name):
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onedir", "--windowed", "--contents-directory", "_internal",
        "--name", build_name, "--icon", str(PROJECT_DIR / "assets/app.ico"),
        "--paths", str(PROJECT_DIR),
        "--paths", str(PROJECT_DIR / "MonkezCustomWidgets"),
        "--specpath", str(BUILD_DIR / build_name),
        "--workpath", str(BUILD_DIR / build_name / "work"),
        "--distpath", str(DIST_DIR),
    ]
    for source, destination in DATA_FILES:
        path = PROJECT_DIR / source
        if not path.exists():
            raise FileNotFoundError(f"Missing build resource: {path}")
        command.extend(("--add-data", f"{path};{destination}"))
    for module in HIDDEN_IMPORTS:
        command.extend(("--hidden-import", module))
    # This application uses CPU ONNX, not the training frameworks.
    for module in ("torch", "torchvision", "tensorflow", "keras", "PySide6", "PyQt6"):
        command.extend(("--exclude-module", module))
    command.append(str(PROJECT_DIR / "main.py"))
    return command


def build_release(dry_run=False):
    version, build_date, build_name = next_build_name()
    output = DIST_DIR / build_name
    command = pyinstaller_command(build_name)
    print(f"Build name: {build_name}", flush=True)
    print(f"Output: {output}", flush=True)
    print(f"Command: {subprocess.list2cmdline(command)}", flush=True)
    if dry_run:
        return 0
    if importlib.util.find_spec("PyInstaller") is None:
        print("Missing PyInstaller. Install build dependencies, then run build.bat again:")
        print(r"  uv pip install --python .venv\Scripts\python.exe -r requirements-build.txt")
        print(r"  or: .venv\Scripts\python.exe -m pip install -r requirements-build.txt")
        return 1
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing release: {output}")
    (BUILD_DIR / build_name).mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, cwd=PROJECT_DIR, check=False)
    if result.returncode:
        return result.returncode
    for resource in (
        f"{build_name}.exe", "_internal/assets/models/weights.onnx",
        "_internal/assets/qt/main.ui", "_internal/assets/sounds/TN.mp3",
    ):
        if not (output / resource).is_file():
            raise FileNotFoundError(f"Incomplete release: {output / resource}")
    state = {
        "version": version, "build_date": build_date,
        "build_name": build_name, "date_format": "ddmmyy",
    }
    temporary_state = STATE_FILE.with_suffix(".json.tmp")
    temporary_state.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary_state.replace(STATE_FILE)
    print(f"Done: {output / (build_name + '.exe')}", flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview without building or incrementing version")
    args = parser.parse_args()
    try:
        return build_release(args.dry_run)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
