import subprocess
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


class MacOSAppLauncherTests(unittest.TestCase):
    def test_build_creates_native_arm64_launcher(self):
        subprocess.run(
            ["bash", str(ROOT_DIR / "scripts" / "build_macos_app.sh")],
            cwd=ROOT_DIR,
            check=True,
            capture_output=True,
            text=True,
        )

        launcher = (
            ROOT_DIR
            / "dist"
            / "VideoCaptioner.app"
            / "Contents"
            / "MacOS"
            / "VideoCaptioner"
        )
        result = subprocess.run(
            ["file", str(launcher)],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("Mach-O 64-bit executable arm64", result.stdout)
        self.assertNotIn("shell script", result.stdout)


if __name__ == "__main__":
    unittest.main()
