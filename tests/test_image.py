"""Tests for the container image. They build and run the real image, so they
skip when docker is unavailable (CI's `test` job and off-host runs)."""

import shutil
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TAG = "palsave-api:test"


def _docker_usable() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


@unittest.skipUnless(_docker_usable(), "docker is not available")
class ImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build = subprocess.run(
            ["docker", "build", "-t", TAG, str(REPO)], capture_output=True, text=True
        )
        if build.returncode != 0:
            raise RuntimeError(f"docker build failed:\n{build.stdout}\n{build.stderr}")

    def run_in_image(self, *args):
        # --entrypoint "" so the commands under test run directly rather than
        # as arguments to the service entrypoint.
        return subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "", TAG, *args],
            capture_output=True,
            text=True,
        )

    def test_image_runs_as_nonroot_matching_the_host_identity(self):
        uid = self.run_in_image("id", "-u")
        gid = self.run_in_image("id", "-g")
        self.assertEqual(uid.stdout.strip(), "992", uid.stderr)
        self.assertEqual(gid.stdout.strip(), "979", gid.stderr)

    def test_image_can_load_the_ooz_library(self):
        # decompress loads libooz lazily, so a bare `import decompress` passes
        # on a broken image; _get_ooz_lib() forces the dlopen. No
        # PALSAVE_API_OOZ_LIB_PATH is passed: the image's own default is under test.
        result = self.run_in_image(
            "python", "-c", "import decompress; decompress._get_ooz_lib()"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_image_carries_no_build_toolchain(self):
        for tool in ("gcc", "g++", "cc", "cmake", "make", "git"):
            result = self.run_in_image("sh", "-c", f"command -v {tool} || true")
            self.assertEqual(result.stdout.strip(), "", f"{tool} present in image")

    def test_entrypoint_runs_main_py(self):
        inspect = subprocess.run(
            ["docker", "inspect", "--format", "{{json .Config.Entrypoint}}{{json .Config.Cmd}}", TAG],
            capture_output=True,
            text=True,
        )
        self.assertIn("main.py", inspect.stdout)


if __name__ == "__main__":
    unittest.main()
