"""Tests for the container image. They build the real image (a git clone and a
cmake build of libooz) and run it, so they skip when docker is unavailable and
when PALSAVE_API_SKIP_IMAGE_TESTS is set. CI's `test` job sets it on purpose:
the deploy reconciler gates on every job named `test`, and a slow,
network-dependent image build must not sit in front of a deploy. CI runs these
in the separate `image` job instead."""

import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TAG = "palsave-api:test"


def _docker_usable() -> bool:
    if os.environ.get("PALSAVE_API_SKIP_IMAGE_TESTS"):
        return False
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
        # as arguments to the service entrypoint; -w /app because the image's
        # own cwd is /state and the modules under test live in /app.
        return subprocess.run(
            ["docker", "run", "--rm", "-w", "/app", "--entrypoint", "", TAG, *args],
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

    def test_image_serves_over_a_published_port(self):
        # Proves the container binds beyond its own loopback: a published port
        # forwards to the bridge side, so a 127.0.0.1 bind would never answer.
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        with tempfile.TemporaryDirectory() as backup:
            os.chmod(backup, 0o755)  # mkdtemp is 0700; uid 992 must read the :ro mount
            run = subprocess.run(
                ["docker", "run", "-d", "-p", f"127.0.0.1:{port}:8788",
                 "-v", f"{backup}:/backups:ro",
                 "-e", "PALSAVE_API_BACKUP_DIR=/backups", TAG],
                capture_output=True, text=True,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            cid = run.stdout.strip()
            try:
                status = None
                for _ in range(30):
                    try:
                        with urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/events/new-pals", timeout=2
                        ) as r:
                            status = r.status
                            break
                    except urllib.error.HTTPError as e:
                        status = e.code
                        break
                    except OSError:
                        time.sleep(0.5)
                logs = subprocess.run(["docker", "logs", cid], capture_output=True, text=True)
                self.assertEqual(status, 200, logs.stdout + logs.stderr)
            finally:
                subprocess.run(["docker", "rm", "-f", cid], capture_output=True)

    def test_image_reports_a_health_verdict_and_reaches_healthy(self):
        # lyly-admin's services board reads Docker's health verdict out of
        # `docker compose ps`; with no HEALTHCHECK, Health is empty and every
        # row is green regardless. This asserts the verdict exists AND that the
        # probe actually works inside the image -- a HEALTHCHECK whose command
        # is broken fails exactly as loudly as a dead service, which is why
        # inspecting .Config.Healthcheck alone would not be enough.
        with tempfile.TemporaryDirectory() as backup:
            os.chmod(backup, 0o755)  # mkdtemp is 0700; uid 992 must read the :ro mount
            run = subprocess.run(
                ["docker", "run", "-d", "-v", f"{backup}:/backups:ro",
                 "-e", "PALSAVE_API_BACKUP_DIR=/backups", TAG],
                capture_output=True, text=True,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            cid = run.stdout.strip()
            try:
                health = None
                # --start-interval=3s in the Dockerfile is what makes this
                # bounded: on the 30s interval alone the first verdict would
                # not land until well past any patience a test should have.
                for _ in range(40):
                    probe = subprocess.run(
                        ["docker", "inspect", "--format", "{{.State.Health.Status}}", cid],
                        capture_output=True, text=True,
                    )
                    health = probe.stdout.strip()
                    if health == "healthy":
                        break
                    time.sleep(1)
                logs = subprocess.run(["docker", "logs", cid], capture_output=True, text=True)
                self.assertEqual(health, "healthy", logs.stdout + logs.stderr)
            finally:
                subprocess.run(["docker", "rm", "-f", cid], capture_output=True)

    def test_image_writes_state_into_a_mounted_volume(self):
        # A *fresh* named volume: ownership is initialized from the image's
        # /state on first mount, and that is the step that breaks if the
        # directory is missing from the image. A GET cannot see it.
        volume = f"palsave-api-test-{time.time_ns()}"
        cid = None
        try:
            subprocess.run(["docker", "volume", "create", volume], check=True, capture_output=True)
            with tempfile.TemporaryDirectory() as backup:
                os.chmod(backup, 0o755)  # mkdtemp is 0700; uid 992 must read the :ro mount
                run = subprocess.run(
                    ["docker", "run", "-d", "-v", f"{volume}:/state",
                     "-v", f"{backup}:/backups:ro",
                     "-e", "PALSAVE_API_BACKUP_DIR=/backups", TAG],
                    capture_output=True, text=True,
                )
                self.assertEqual(run.returncode, 0, run.stderr)
                cid = run.stdout.strip()
                owner = None
                for _ in range(30):
                    ls = subprocess.run(
                        ["docker", "run", "--rm", "-v", f"{volume}:/state", "--entrypoint", "",
                         TAG, "stat", "-c", "%u:%g", "/state"],
                        capture_output=True, text=True,
                    )
                    owner = ls.stdout.strip()
                    if owner:
                        break
                    time.sleep(0.5)
                self.assertEqual(owner, "992:979", ls.stderr)
                # The running service's own uid can create a file in its cwd.
                write = subprocess.run(
                    ["docker", "exec", cid, "sh", "-c", "touch probe && pwd && id -u"],
                    capture_output=True, text=True,
                )
                self.assertEqual(write.returncode, 0, write.stderr)
                self.assertEqual(write.stdout.split(), ["/state", "992"])
        finally:
            if cid:
                subprocess.run(["docker", "rm", "-f", cid], capture_output=True)
            subprocess.run(["docker", "volume", "rm", "-f", volume], capture_output=True)


if __name__ == "__main__":
    unittest.main()
