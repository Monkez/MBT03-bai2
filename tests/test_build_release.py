import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_release as build


class BuildReleaseTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="MBT Bai2 ")))
        for name, value in (
            ("PROJECT_DIR", self.root), ("DIST_DIR", self.root / "dist"),
            ("BUILD_DIR", self.root / "build"), ("STATE_FILE", self.root / "build_state.json"),
        ):
            self.stack.enter_context(patch.object(build, name, value))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(patch.object(build.importlib.util, "find_spec", return_value=object()))
        for resource, _ in build.DATA_FILES:
            path = self.root / resource
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"test resource")

    def test_dry_run_does_not_write_state_or_output(self):
        with patch.object(build.subprocess, "run") as run:
            self.assertEqual(build.build_release(dry_run=True), 0)
        run.assert_not_called()
        self.assertFalse(build.STATE_FILE.exists())
        self.assertFalse(build.DIST_DIR.exists())
        self.assertFalse(build.BUILD_DIR.exists())

    def test_next_version_preserves_existing_releases_even_with_stale_state(self):
        build.STATE_FILE.write_text('{"version": 3}', encoding="utf-8")
        old_release = build.DIST_DIR / "MBT03-Bai2-V9-101026"
        old_release.mkdir(parents=True)
        self.assertEqual(build.next_build_name()[0], 10)
        self.assertTrue(old_release.is_dir())

    def test_command_preserves_paths_with_spaces_and_excludes_device_data(self):
        command = build.pyinstaller_command("MBT03-Bai2-V1-101026")
        self.assertIn(str(self.root / "main.py"), command)
        data = [command[index + 1] for index, arg in enumerate(command) if arg == "--add-data"]
        self.assertIn(f"{self.root / 'assets/configurations/config.json'};assets/configurations", data)
        self.assertFalse(any("server_client" in arg or "OrangePi" in arg for arg in data))
        self.assertNotIn(f"{self.root / 'assets'};assets", data)
        self.assertIn("qfluentwidgets", command)
        self.assertIn("monkez_image", command)

    def test_missing_resource_fails_before_building(self):
        (self.root / "assets/models").unlink()
        with patch.object(build.subprocess, "run") as run:
            with self.assertRaises(FileNotFoundError):
                build.build_release()
        run.assert_not_called()
        self.assertFalse(build.STATE_FILE.exists())

    def test_failed_packager_does_not_advance_version(self):
        with patch.object(build.subprocess, "run") as run:
            run.return_value.returncode = 7
            self.assertEqual(build.build_release(), 7)
        self.assertFalse(build.STATE_FILE.exists())

    def test_missing_build_tool_reports_failure_without_starting_packager(self):
        with (patch.object(build.importlib.util, "find_spec", return_value=None),
              patch.object(build.subprocess, "run") as run):
            self.assertEqual(build.build_release(), 1)
        run.assert_not_called()
        self.assertFalse(build.STATE_FILE.exists())

    def test_incomplete_output_does_not_advance_version(self):
        with patch.object(build.subprocess, "run") as run:
            run.return_value.returncode = 0
            with self.assertRaises(FileNotFoundError):
                build.build_release()
        self.assertFalse(build.STATE_FILE.exists())

    def test_success_records_version_only_after_output_is_verified(self):
        def package(command, **kwargs):
            build_name = command[command.index("--name") + 1]
            for filename in (
                f"{build_name}.exe", "_internal/assets/models/weights.onnx",
                "_internal/assets/qt/main.ui", "_internal/assets/sounds/TN.mp3",
            ):
                path = build.DIST_DIR / build_name / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"test")
            return build.subprocess.CompletedProcess(command, 0)

        with patch.object(build.subprocess, "run", side_effect=package):
            self.assertEqual(build.build_release(), 0)
        state = json.loads(build.STATE_FILE.read_text(encoding="utf-8"))
        self.assertEqual(state["version"], 1)
        self.assertEqual(build.next_build_name()[0], 2)
        self.assertFalse(build.STATE_FILE.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
