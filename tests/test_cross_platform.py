"""Cross-platform, PyInstaller bundle-safety, WSL mocking, and Simulated Shell tests."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from rich.console import Console

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app as cli_app  # noqa: E402
from engine import ProgressTracker, load_all_questions  # noqa: E402
from labs import get_all_labs, get_lab_by_id  # noqa: E402
import paths  # noqa: E402
from sandbox import (  # noqa: E402
    BACKEND_NATIVE,
    BACKEND_SIMULATED,
    BACKEND_WSL,
    SandboxSession,
    get_sandbox_capabilities,
    is_wsl_available,
    verify_lab,
)
from web_app import create_app  # noqa: E402


class PathsResolutionTests(unittest.TestCase):
    """Verify paths.py resolves source and frozen PyInstaller paths across OSes."""

    def test_source_mode_paths_and_explicit_override(self) -> None:
        self.assertFalse(paths.is_frozen())
        self.assertEqual(paths.get_resource_path(), PROJECT_ROOT)
        self.assertEqual(paths.get_questions_dir(), PROJECT_ROOT / "data" / "questions")
        self.assertEqual(paths.get_templates_dir(), PROJECT_ROOT / "templates")
        self.assertEqual(paths.get_static_dir(), PROJECT_ROOT / "static")
        self.assertEqual(paths.get_user_data_dir(create=False), PROJECT_ROOT / "data")
        self.assertEqual(
            paths.get_progress_file(create_dir=False),
            PROJECT_ROOT / "data" / "progress.json",
        )
        custom = Path("/tmp/custom_progress.json")
        self.assertEqual(paths.get_progress_file(custom), custom)

    def test_frozen_meipass_resource_and_os_user_data_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            meipass_dir = tmp / "meipass_bundle"
            meipass_dir.mkdir()

            # Linux frozen
            linux_home = tmp / "linux_home"
            with patch.object(sys, "_MEIPASS", str(meipass_dir), create=True), patch.object(
                sys, "frozen", True, create=True
            ), patch.object(sys, "platform", "linux"), patch.dict(
                os.environ, {}, clear=True
            ), patch.object(Path, "home", return_value=linux_home):
                self.assertTrue(paths.is_frozen())
                self.assertEqual(paths.get_resource_path("templates"), meipass_dir / "templates")
                self.assertEqual(
                    paths.get_questions_dir(), meipass_dir / "data" / "questions"
                )
                data_dir = paths.get_user_data_dir()
                self.assertEqual(data_dir, linux_home / ".local" / "share" / "linux-plus-trainer")
                self.assertTrue(data_dir.is_dir())

            # macOS frozen
            mac_home = tmp / "mac_home"
            with patch.object(sys, "_MEIPASS", str(meipass_dir), create=True), patch.object(
                sys, "frozen", True, create=True
            ), patch.object(sys, "platform", "darwin"), patch.object(
                Path, "home", return_value=mac_home
            ):
                data_dir = paths.get_user_data_dir()
                self.assertEqual(
                    data_dir,
                    mac_home / "Library" / "Application Support" / "LinuxPlusTrainer",
                )
                self.assertTrue(data_dir.is_dir())

            # Windows frozen
            win_appdata = tmp / "WinAppData"
            with patch.object(sys, "_MEIPASS", str(meipass_dir), create=True), patch.object(
                sys, "frozen", True, create=True
            ), patch.object(sys, "platform", "win32"), patch.dict(
                os.environ, {"APPDATA": str(win_appdata)}, clear=False
            ):
                data_dir = paths.get_user_data_dir()
                self.assertEqual(data_dir, win_appdata / "LinuxPlusTrainer")
                self.assertTrue(data_dir.is_dir())
                self.assertEqual(paths.get_progress_file(), data_dir / "progress.json")

    def test_web_app_uses_frozen_meipass_assets_and_user_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            bundle = tmp / "bundle"
            shutil.copytree(PROJECT_ROOT / "data" / "questions", bundle / "data" / "questions")
            shutil.copytree(PROJECT_ROOT / "templates", bundle / "templates")
            shutil.copytree(PROJECT_ROOT / "static", bundle / "static")
            user_home = tmp / "frozen_home"

            with patch.object(sys, "_MEIPASS", str(bundle), create=True), patch.object(
                sys, "frozen", True, create=True
            ), patch.object(sys, "platform", "linux"), patch.dict(
                os.environ, {}, clear=True
            ), patch.object(Path, "home", return_value=user_home):
                flask_app = create_app()
                self.assertEqual(Path(flask_app.template_folder), bundle / "templates")
                self.assertEqual(Path(flask_app.static_folder), bundle / "static")
                expected_progress = (
                    user_home / ".local" / "share" / "linux-plus-trainer" / "progress.json"
                )
                self.assertTrue(expected_progress.is_file())
                client = flask_app.test_client()
                resp = client.get("/")
                self.assertEqual(resp.status_code, 200)


class MockedWindowsWSLTests(unittest.TestCase):
    """Verify zero-config Windows WSL detection, temp dir lifecycle, and checks."""

    def test_capabilities_detect_wsl_and_fallback_on_windows(self) -> None:
        with patch.object(sys, "platform", "win32"), patch(
            "sandbox.shutil.which", side_effect=lambda cmd: "C:\\Windows\\System32\\wsl.exe" if "wsl" in cmd else None
        ), patch(
            "sandbox.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["wsl.exe", "-e", "bash", "-c", "echo ok"],
                returncode=0,
                stdout="ok\n",
                stderr="",
            ),
        ):
            self.assertTrue(is_wsl_available())
            caps = get_sandbox_capabilities()
            self.assertEqual(caps["os"], "windows")
            self.assertEqual(caps["available_backends"], [BACKEND_WSL, BACKEND_SIMULATED])
            self.assertEqual(caps["default_backend"], BACKEND_WSL)

        # Probe timeout / failure falls back to simulated
        with patch.object(sys, "platform", "win32"), patch(
            "sandbox.shutil.which", return_value="C:\\Windows\\System32\\wsl.exe"
        ), patch(
            "sandbox.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="wsl.exe", timeout=3),
        ):
            self.assertFalse(is_wsl_available())
            caps = get_sandbox_capabilities()
            self.assertEqual(caps["available_backends"], [BACKEND_SIMULATED])
            self.assertEqual(caps["default_backend"], BACKEND_SIMULATED)

    def test_wsl_session_lifecycle_uses_linux_tmp_and_verifies(self) -> None:
        invoked_scripts: list[str] = []

        def fake_run(cmd, **kwargs):
            script = cmd[-1]
            invoked_scripts.append(script)
            if script == "echo ok":
                return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")
            if script.startswith("mktemp -d /tmp/linux_plus_lab_"):
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="/tmp/linux_plus_lab_abc123\n", stderr=""
                )
            if "CHECK:0:1" in script or "project/src" in script:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    stdout="CHECK:0:1\nCHECK:1:1\nCHECK:2:1\nCHECK:3:1\n",
                    stderr="",
                )
            if "__LINUX_PLUS_SANDBOX_CWD__" in script:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    stdout="app.py\nconfig.ini\n__LINUX_PLUS_SANDBOX_CWD__:/tmp/linux_plus_lab_abc123/inbox\n",
                    stderr="",
                )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch.object(sys, "platform", "win32"), patch(
            "sandbox.shutil.which",
            side_effect=lambda name: "C:\\Windows\\System32\\wsl.exe" if "wsl" in name else None,
        ), patch("sandbox.subprocess.run", side_effect=fake_run):
            with SandboxSession("lab_01", backend=BACKEND_WSL) as session:
                self.assertEqual(session.backend, BACKEND_WSL)
                self.assertEqual(session.backend_label, "WSL Linux")
                self.assertEqual(session.root, PurePosixPath("/tmp/linux_plus_lab_abc123"))
                self.assertNotIn("/mnt/c", str(session.root))

                # Blocked command never calls WSL subprocess
                count_before = len(invoked_scripts)
                blocked = session.execute("cat /etc/passwd")
                self.assertTrue(blocked.blocked)
                self.assertEqual(blocked.returncode, 126)
                self.assertEqual(len(invoked_scripts), count_before)

                # Command execution updates cwd from marker
                res = session.execute("cd inbox && ls")
                self.assertEqual(res.returncode, 0)
                self.assertEqual(res.cwd, "~/inbox")
                self.assertIn("app.py", res.stdout)

                # Verification evaluates through WSL
                vr = session.verify()
                self.assertTrue(vr.passed)
                self.assertEqual(len(vr.checks), 4)
                vr_direct = verify_lab("lab_01", session.root)
                self.assertTrue(vr_direct.passed)

            # Cleanup issued rm -rf against WSL /tmp path
            self.assertTrue(
                any("rm -rf -- /tmp/linux_plus_lab_abc123" in s for s in invoked_scripts)
            )


class SimulatedShellEndToEndTests(unittest.TestCase):
    """Verify pure-Python Simulated Shell guardrails, commands, and all 10 labs."""

    def test_simulated_guardrails_timeout_and_core_commands(self) -> None:
        with SandboxSession("lab_03", timeout=0.6, backend=BACKEND_SIMULATED) as session:
            self.assertEqual(session.backend, BACKEND_SIMULATED)
            self.assertEqual(session.backend_label, "Simulated Shell")

            for bad in ("cd ..", "cat /etc/passwd", "sudo ls", "echo a | xargs kill", "cat C:\\Windows\\win.ini"):
                res = session.execute(bad)
                self.assertTrue(res.blocked, f"Expected blocked in simulated shell: {bad!r}")
                self.assertEqual(res.returncode, 126)

            t_res = session.execute("sleep 2")
            self.assertTrue(t_res.timed_out)
            self.assertEqual(t_res.returncode, 124)

            ls_res = session.execute("ls -la logs")
            self.assertEqual(ls_res.returncode, 0)
            self.assertIn("app.log", ls_res.stdout)

            grep_res = session.execute("grep -i -n error logs/app.log | head -n 2")
            self.assertEqual(grep_res.returncode, 0)
            self.assertEqual(len(grep_res.stdout.strip().splitlines()), 2)

            append_res = session.execute("echo line1 > note.txt && echo line2 >> note.txt && wc -l note.txt")
            self.assertEqual(append_res.returncode, 0)
            self.assertEqual(append_res.stdout.strip(), "2")

    def test_all_10_labs_fail_initially_and_pass_in_simulated_shell(self) -> None:
        for lab in get_all_labs():
            with self.subTest(lab_id=lab.id):
                with SandboxSession(lab, backend=BACKEND_SIMULATED) as session:
                    initial = session.verify()
                    self.assertFalse(
                        initial.passed,
                        f"{lab.id} should fail initially in simulated shell",
                    )

                    exec_res = session.execute(lab.solution_example)
                    self.assertFalse(
                        exec_res.blocked,
                        f"{lab.id} solution_example blocked in simulated shell: {exec_res.stderr}",
                    )
                    self.assertEqual(
                        exec_res.returncode,
                        0,
                        f"{lab.id} failed in simulated shell: {exec_res.stderr}",
                    )

                    after = session.verify()
                    self.assertTrue(
                        after.passed,
                        f"{lab.id} failed verification in simulated shell: {after.checks}",
                    )
                    after_direct = verify_lab(lab.id, session.root)
                    self.assertTrue(after_direct.passed)

    def test_alternative_solutions_and_virtual_symlink_fallback_in_simulated_shell(self) -> None:
        # Lab 2 symbolic chmod
        with SandboxSession("lab_02", backend=BACKEND_SIMULATED) as s2:
            res = s2.execute(
                "chmod u=rw,go= secrets/api.key && "
                "chmod u=rwx,g=rx,o= scripts/backup.sh && "
                "chmod u=rw,go=r public/readme.txt"
            )
            self.assertEqual(res.returncode, 0)
            self.assertTrue(s2.verify().passed)

        # Lab 6 find -exec rm
        with SandboxSession("lab_06", backend=BACKEND_SIMULATED) as s6:
            res = s6.execute("find configs -type f -name '*.bak' -exec rm {} +")
            self.assertEqual(res.returncode, 0)
            self.assertTrue(s6.verify().passed)

        # Lab 7 cut | sort | uniq
        with SandboxSession("lab_07", backend=BACKEND_SIMULATED) as s7:
            res = s7.execute("cut -d' ' -f1 logs/access.log | sort | uniq > unique_ips.txt")
            self.assertEqual(res.returncode, 0)
            self.assertTrue(s7.verify().passed)

        # Lab 4 and Lab 10 with OS symlinks raising PermissionError (unprivileged Windows)
        with patch.object(Path, "symlink_to", side_effect=PermissionError("WinError 1314")):
            with SandboxSession("lab_04", backend=BACKEND_SIMULATED) as s4:
                self.assertFalse(s4.verify().passed)
                res4 = s4.execute(get_lab_by_id("lab_04").solution_example)
                self.assertEqual(res4.returncode, 0)
                self.assertTrue(s4.verify().passed)

            with SandboxSession("lab_10", backend=BACKEND_SIMULATED) as s10:
                self.assertFalse(s10.verify().passed)
                res10 = s10.execute(get_lab_by_id("lab_10").solution_example)
                self.assertEqual(res10.returncode, 0)
                self.assertTrue(s10.verify().passed)


class CrossPlatformUIBackendTests(unittest.TestCase):
    """Verify Terminal Mode and Web Mode expose backend indicators and switching."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.progress_path = Path(self.tmpdir.name) / "progress.json"
        self.flask_app = create_app(
            questions_dir=PROJECT_ROOT / "data" / "questions",
            progress_path=self.progress_path,
        )
        self.flask_app.testing = True
        self.client = self.flask_app.test_client()

    def tearDown(self) -> None:
        for sb in list(self.flask_app.extensions.get("lab_sessions", {}).values()):
            sb.cleanup()
        self.tmpdir.cleanup()

    def test_web_api_and_ui_backend_toggle_across_all_themes(self) -> None:
        cap_resp = self.client.get("/api/sandbox/capabilities")
        self.assertEqual(cap_resp.status_code, 200)
        cap_data = cap_resp.get_json()
        self.assertIn(BACKEND_SIMULATED, cap_data["available_backends"])
        self.assertEqual(cap_data["default_backend"], BACKEND_NATIVE)

        labs_resp = self.client.get("/api/labs")
        self.assertEqual(labs_resp.status_code, 200)
        self.assertIn("sandbox", labs_resp.get_json())

        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("dashboard-backend-badge", html)
        self.assertIn("dashboard-backend-toggle", html)
        self.assertIn("lab-backend-badge", html)
        self.assertIn("lab-backend-toggle", html)

        with self.client.get("/static/styles.css") as css_resp:
            css = css_resp.get_data(as_text=True)
        self.assertIn(".badge-backend", css)
        self.assertIn('[data-theme="osrs"] .backend-btn.active', css)
        self.assertIn('[data-theme="cyberpunk"] .backend-btn.active', css)
        self.assertIn('[data-theme="oot"] .backend-btn.active', css)

        # Start lab specifically on Simulated Shell backend
        start_resp = self.client.post(
            "/api/labs/start",
            json={"lab_id": "lab_02", "backend": BACKEND_SIMULATED},
        )
        self.assertEqual(start_resp.status_code, 200)
        start_data = start_resp.get_json()
        self.assertEqual(start_data["backend"], BACKEND_SIMULATED)
        self.assertEqual(start_data["backend_label"], "Simulated Shell")
        sid = start_data["session_id"]

        exec_resp = self.client.post(
            "/api/labs/exec",
            json={"session_id": sid, "command": get_lab_by_id("lab_02").solution_example},
        )
        self.assertEqual(exec_resp.status_code, 200)
        self.assertEqual(exec_resp.get_json()["returncode"], 0)

        check_resp = self.client.post("/api/labs/check", json={"session_id": sid})
        self.assertEqual(check_resp.status_code, 200)
        self.assertTrue(check_resp.get_json()["passed"])

        bad_resp = self.client.post(
            "/api/labs/start",
            json={"lab_id": "lab_01", "backend": "unknown_backend"},
        )
        self.assertEqual(bad_resp.status_code, 400)

    def test_terminal_mode_displays_backend_and_allows_switching(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ProgressTracker(Path(tmpdir) / "progress.json", categories=["Cat"])
            out = io.StringIO()
            console = Console(file=out, force_terminal=False, width=100)
            lab = get_lab_by_id("lab_01")

            inputs = iter(
                [
                    "backend",  # switch from simulated -> native (or vice versa)
                    "backend simulated",
                    lab.solution_example,
                    "check",
                    "quit",
                ]
            )
            passed = cli_app.run_sandbox_lab_session(
                console,
                lab,
                tracker,
                input_fn=lambda _: next(inputs),
                backend=BACKEND_SIMULATED,
            )
            self.assertTrue(passed)
            rendered = out.getvalue()
            self.assertIn("Simulated Shell", rendered)
            self.assertIn("Switched sandbox backend", rendered)

            # Lab menu toggle with 's'
            switched: list[str] = []
            menu_out = io.StringIO()
            menu_console = Console(file=menu_out, force_terminal=False, width=100)
            with patch("rich.console.Console.input", side_effect=["s", "b"]):
                picked = cli_app.select_sandbox_lab(
                    menu_console,
                    tracker,
                    backend=BACKEND_NATIVE,
                    on_backend_change=switched.append,
                )
            self.assertIsNone(picked)
            self.assertEqual(switched, [BACKEND_SIMULATED])
            self.assertIn("Simulated Shell", menu_out.getvalue())


if __name__ == "__main__":
    unittest.main()
