"""Comprehensive unit tests for Sandbox Lab Mode, isolation guardrails, 10 labs, persistence, and web API."""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

from rich.console import Console

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app as cli_app  # noqa: E402
from engine import QUESTIONS_DIR, ProgressTracker, get_categories, load_all_questions  # noqa: E402
from labs import get_all_labs, get_lab_by_id  # noqa: E402
from sandbox import SandboxSession, verify_lab  # noqa: E402
from web_app import create_app  # noqa: E402


class SandboxIsolationTests(unittest.TestCase):
    """Verify sandbox path isolation, dangerous command blocking, cwd persistence, timeout, and reset."""

    def test_blocks_path_escapes_and_sensitive_host_paths(self) -> None:
        with SandboxSession("lab_01") as session:
            blocked_inputs = [
                "cd ..",
                "cd inbox && cd ../..",
                "cat /etc/passwd",
                "ls /home",
                "ls /var",
                "ls /usr",
                "ls /root",
                "ls /",
                "chmod 777 /tmp/x",
                "ln -s /etc/passwd leak",
                "cat ../outside.txt",
                "ls ~root",
            ]
            for cmd in blocked_inputs:
                res = session.execute(cmd)
                self.assertTrue(res.blocked, f"Expected command to be blocked: {cmd!r}")
                self.assertEqual(res.returncode, 126, f"Expected returncode 126 for {cmd!r}")
                self.assertIn("Sandbox warning", res.stderr)

    def test_blocks_dangerous_system_commands(self) -> None:
        with SandboxSession("lab_01") as session:
            dangerous = [
                "sudo ls",
                "su root",
                "rm -rf /",
                "mkfs.ext4 /dev/sda1",
                "dd if=/dev/zero of=test.img",
                "shutdown -h now",
                "reboot",
                "systemctl status sshd",
                "pacman -Syu",
                "kill -9 1",
                "pkill python",
                "find . -exec sudo ls {} +",
                "echo a | xargs kill",
            ]
            for cmd in dangerous:
                res = session.execute(cmd)
                self.assertTrue(res.blocked, f"Expected dangerous command to be blocked: {cmd!r}")
                self.assertEqual(res.returncode, 126)

    def test_cd_state_persists_and_in_sandbox_parent_traversal_works(self) -> None:
        with SandboxSession("lab_01") as session:
            self.assertEqual(session.relative_cwd(), "~")
            self.assertEqual(session.prompt(), "lab@sandbox:~$")

            res1 = session.execute("cd inbox")
            self.assertFalse(res1.blocked)
            self.assertEqual(res1.returncode, 0)
            self.assertEqual(res1.cwd, "~/inbox")
            self.assertEqual(res1.prompt, "lab@sandbox:~/inbox$")

            res2 = session.execute("ls")
            self.assertEqual(res2.returncode, 0)
            self.assertIn("app.py", res2.stdout)

            res3 = session.execute("cd ..")
            self.assertFalse(res3.blocked)
            self.assertEqual(res3.cwd, "~")

    def test_timeout_enforced_and_reset_cleans_workspace(self) -> None:
        with SandboxSession("lab_01", timeout=1.0) as session:
            t_res = session.execute("sleep 5")
            self.assertTrue(t_res.timed_out)
            self.assertEqual(t_res.returncode, 124)
            self.assertIn("timed out", t_res.stderr.lower())

            session.execute("touch extra_file.txt && cd inbox")
            self.assertTrue((session.root / "extra_file.txt").exists())
            old_root = session.root

            session.reset_lab()
            self.assertFalse(old_root.exists())
            self.assertTrue(session.root.exists())
            self.assertEqual(session.relative_cwd(), "~")
            self.assertFalse((session.root / "extra_file.txt").exists())
            self.assertTrue((session.root / "inbox/app.py").is_file())

        # Context manager exit cleans up temp dir
        self.assertFalse(session.root.exists())


class StarterLabsVerificationTests(unittest.TestCase):
    """Verify all 10 labs fail initially, pass with their solution, and accept alternative valid approaches."""

    def test_ten_unique_labs_across_all_difficulties(self) -> None:
        labs = get_all_labs()
        self.assertEqual(len(labs), 10)
        ids = [lab.id for lab in labs]
        self.assertEqual(len(ids), len(set(ids)))

        difficulties = {lab.difficulty for lab in labs}
        self.assertEqual(difficulties, {"beginner", "intermediate", "hard"})

        with self.assertRaises(KeyError):
            get_lab_by_id("nonexistent_lab")

    def test_all_10_labs_fail_initially_and_pass_after_solution(self) -> None:
        for lab in get_all_labs():
            with self.subTest(lab_id=lab.id):
                with SandboxSession(lab) as session:
                    initial = session.verify()
                    self.assertFalse(
                        initial.passed,
                        f"{lab.id} should not pass in its initial setup state",
                    )

                    exec_res = session.execute(lab.solution_example)
                    self.assertFalse(
                        exec_res.blocked,
                        f"{lab.id} solution_example was blocked: {exec_res.stderr}",
                    )
                    self.assertEqual(
                        exec_res.returncode,
                        0,
                        f"{lab.id} solution_example failed: {exec_res.stderr}",
                    )

                    after = verify_lab(lab.id, session.root)
                    self.assertTrue(
                        after.passed,
                        f"{lab.id} failed verification after solution_example: {after.checks}",
                    )

    def test_alternative_valid_linux_approaches_pass(self) -> None:
        # Lab 2: symbolic chmod instead of octal
        with SandboxSession("lab_02") as s2:
            res = s2.execute(
                "chmod u=rw,go= secrets/api.key && "
                "chmod u=rwx,g=rx,o= scripts/backup.sh && "
                "chmod u=rw,go=r public/readme.txt"
            )
            self.assertEqual(res.returncode, 0)
            self.assertTrue(s2.verify().passed)

        # Lab 6: find -exec rm instead of -delete
        with SandboxSession("lab_06") as s6:
            res = s6.execute("find configs -type f -name '*.bak' -exec rm {} +")
            self.assertEqual(res.returncode, 0)
            self.assertTrue(s6.verify().passed)

        # Lab 7: cut | sort | uniq instead of awk | sort -u
        with SandboxSession("lab_07") as s7:
            res = s7.execute("cut -d' ' -f1 logs/access.log | sort | uniq > unique_ips.txt")
            self.assertEqual(res.returncode, 0)
            self.assertTrue(s7.verify().passed)


class CompletedLabsPersistenceTests(unittest.TestCase):
    """Verify backward-compatible completed_labs persistence in ProgressTracker."""

    def test_legacy_progress_loads_and_completed_labs_persist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            progress_path = Path(tmpdir) / "progress.json"
            legacy_payload = {
                "categories": {"Navigation & File Management": {"answered": 2, "correct": 1}},
                "missed_question_ids": ["nav_01"],
            }
            progress_path.write_text(json.dumps(legacy_payload), encoding="utf-8")

            tracker = ProgressTracker(progress_path, categories=["Navigation & File Management"])
            self.assertEqual(tracker.completed_labs, [])
            self.assertFalse(tracker.is_lab_completed("lab_01"))

            self.assertTrue(tracker.record_lab_completion("lab_01"))
            self.assertFalse(tracker.record_lab_completion("lab_01"))  # deduplicated
            self.assertTrue(tracker.record_lab_completion("lab_02"))

            reloaded = ProgressTracker(progress_path, categories=["Navigation & File Management"])
            self.assertEqual(reloaded.completed_labs, ["lab_01", "lab_02"])
            self.assertTrue(reloaded.is_lab_completed("lab_01"))
            stats = reloaded.get_summary_stats(["Navigation & File Management"])
            self.assertEqual(stats["completed_labs_count"], 2)

            # reset_category preserves completed_labs
            all_questions = load_all_questions(QUESTIONS_DIR)
            reloaded.reset_category("Navigation & File Management", all_questions)
            self.assertEqual(reloaded.completed_labs, ["lab_01", "lab_02"])

            # full reset clears completed_labs
            reloaded.reset(get_categories(all_questions))
            self.assertEqual(reloaded.completed_labs, [])


class TerminalAndWebSandboxTests(unittest.TestCase):
    """Verify Terminal Mode sandbox session and Flask Sandbox API routes."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.progress_path = Path(self.tmpdir.name) / "progress.json"
        self.flask_app = create_app(
            questions_dir=QUESTIONS_DIR,
            progress_path=self.progress_path,
        )
        self.flask_app.testing = True
        self.client = self.flask_app.test_client()

    def tearDown(self) -> None:
        for sb in list(self.flask_app.extensions.get("lab_sessions", {}).values()):
            sb.cleanup()
        self.tmpdir.cleanup()

    def test_terminal_sandbox_session_interactive_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ProgressTracker(Path(tmpdir) / "progress.json", categories=["Cat"])
            console = Console(file=io.StringIO(), force_terminal=False, width=100)
            lab = get_lab_by_id("lab_04")

            inputs = iter(
                [
                    "hint",
                    "check",
                    "ln -s releases/v2 current",
                    "check",
                    "solution",
                    "reset",
                    "quit",
                ]
            )
            passed = cli_app.run_sandbox_lab_session(
                console, lab, tracker, input_fn=lambda _: next(inputs)
            )
            self.assertTrue(passed)
            self.assertTrue(tracker.is_lab_completed("lab_04"))

    def test_web_sandbox_api_lifecycle_and_themes(self) -> None:
        # Dashboard & theme assets include sandbox lab UI
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("sandbox-labs-panel", html)
        self.assertIn("lab-view", html)
        self.assertIn("lab@sandbox:~$", html)

        with self.client.get("/static/styles.css") as css_resp:
            css = css_resp.get_data(as_text=True)
            self.assertIn(".lab-terminal-output", css)
            self.assertIn('[data-theme="osrs"] .lab-card', css)
            self.assertIn('[data-theme="cyberpunk"] .lab-card', css)
            self.assertIn('[data-theme="oot"] .lab-card', css)

        # List labs
        list_resp = self.client.get("/api/labs")
        self.assertEqual(list_resp.status_code, 200)
        list_data = list_resp.get_json()
        self.assertEqual(list_data["total_labs"], 10)
        self.assertEqual(list_data["completed_count"], 0)

        # Start lab_03
        start_resp = self.client.post("/api/labs/start", json={"lab_id": "lab_03"})
        self.assertEqual(start_resp.status_code, 200)
        start_data = start_resp.get_json()
        session_id = start_data["session_id"]
        self.assertEqual(start_data["cwd"], "~")
        self.assertFalse(start_data["verification"]["passed"])

        # Blocked command
        blocked_resp = self.client.post(
            "/api/labs/exec",
            json={"session_id": session_id, "command": "cat /etc/passwd"},
        )
        self.assertEqual(blocked_resp.status_code, 200)
        self.assertTrue(blocked_resp.get_json()["blocked"])

        # Hint & Solution
        hint_resp = self.client.post("/api/labs/hint", json={"session_id": session_id})
        self.assertEqual(hint_resp.status_code, 200)
        self.assertIn("grep", hint_resp.get_json()["hint"])

        sol_resp = self.client.post("/api/labs/solution", json={"session_id": session_id})
        self.assertEqual(sol_resp.status_code, 200)
        solution_cmd = sol_resp.get_json()["solution_example"]

        # Execute solution and check
        exec_resp = self.client.post(
            "/api/labs/exec",
            json={"session_id": session_id, "command": solution_cmd},
        )
        self.assertEqual(exec_resp.status_code, 200)
        self.assertEqual(exec_resp.get_json()["returncode"], 0)

        check_resp = self.client.post("/api/labs/check", json={"session_id": session_id})
        self.assertEqual(check_resp.status_code, 200)
        check_data = check_resp.get_json()
        self.assertTrue(check_data["passed"])
        self.assertTrue(check_data["newly_completed"])
        self.assertIn("lab_03", check_data["completed_labs"])

        # Reset workspace and verify checks fail again
        reset_resp = self.client.post("/api/labs/reset", json={"session_id": session_id})
        self.assertEqual(reset_resp.status_code, 200)
        self.assertFalse(reset_resp.get_json()["verification"]["passed"])

        # Close session
        close_resp = self.client.post("/api/labs/close", json={"session_id": session_id})
        self.assertEqual(close_resp.status_code, 200)
        self.assertTrue(close_resp.get_json()["closed"])


if __name__ == "__main__":
    unittest.main()
