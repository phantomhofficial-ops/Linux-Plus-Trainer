"""Unit tests for the Flask web app, API endpoints, and app.py startup selector."""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from rich.console import Console

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app as cli_app  # noqa: E402
from engine import QUESTIONS_DIR, load_all_questions  # noqa: E402
from web_app import compute_skill_xp, create_app  # noqa: E402


class WebAppTests(unittest.TestCase):
    """Test Flask web GUI rendering, quiz APIs, XP calculation, and persistence."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.progress_path = Path(self.tmpdir.name) / "progress.json"
        self.flask_app = create_app(
            questions_dir=QUESTIONS_DIR,
            progress_path=self.progress_path,
        )
        self.flask_app.testing = True
        self.client = self.flask_app.test_client()
        self.all_questions = load_all_questions(QUESTIONS_DIR)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_dashboard_page_and_static_assets_render(self) -> None:
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("CompTIA Linux+ (XK0-006 / V8)", html)
        self.assertIn("phantom@linux-plus:~$", html)
        self.assertIn('data-theme-target="osrs"', html)
        self.assertIn('data-theme-target="cyberpunk"', html)

        with self.client.get("/static/styles.css") as css_resp:
            self.assertEqual(css_resp.status_code, 200)
            css = css_resp.get_data(as_text=True)
            self.assertIn('[data-theme="osrs"]', css)
            self.assertIn('[data-theme="cyberpunk"]', css)

        with self.client.get("/static/app.js") as js_resp:
            self.assertEqual(js_resp.status_code, 200)
            self.assertIn("linux_plus_theme", js_resp.get_data(as_text=True))

    def test_api_state_computes_xp_without_changing_progress_schema(self) -> None:
        resp = self.client.get("/api/state")
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()

        self.assertEqual(payload["total_questions"], len(self.all_questions))
        self.assertEqual(len(payload["categories"]), 7)
        self.assertEqual(payload["overall"]["total_level"], 7)
        self.assertEqual(payload["overall"]["total_xp"], 0)
        for card in payload["categories"]:
            self.assertEqual(card["skill"]["level"], 1)
            self.assertEqual(card["skill"]["xp"], 0)

        # Verify on-disk progress.json preserves the exact original schema
        raw_disk = json.loads(self.progress_path.read_text(encoding="utf-8"))
        self.assertEqual(set(raw_disk.keys()), {"categories", "missed_question_ids"})

        # Check XP progression helper curve
        lv2 = compute_skill_xp(3)
        self.assertEqual(lv2["level"], 2)
        self.assertEqual(lv2["xp"], 300)

    def test_multiple_choice_session_answers_and_stats(self) -> None:
        category = "Navigation & File Management"
        cat_questions = [q for q in self.all_questions if q.category == category]

        start_resp = self.client.post(
            "/api/quiz/start",
            json={"scope": "category", "category": category, "mode": "multiple_choice", "shuffle": False},
        )
        self.assertEqual(start_resp.status_code, 200)
        start_data = start_resp.get_json()
        session_id = start_data["session_id"]
        self.assertEqual(start_data["total_questions"], len(cat_questions))

        # Q1: pick correct option using letter
        q1 = cat_questions[0]
        choices1 = start_data["question"]["choices"]
        correct_letter = next(k for k, v in choices1.items() if v == q1.correct_choice)
        ans1 = self.client.post(
            "/api/quiz/answer",
            json={"session_id": session_id, "choice": correct_letter},
        )
        self.assertEqual(ans1.status_code, 200)
        ans1_data = ans1.get_json()
        self.assertTrue(ans1_data["correct"])
        self.assertEqual(ans1_data["xp_gained"], 100)
        self.assertEqual(ans1_data["domain"], q1.domain)
        self.assertIn(q1.correct_choice, ans1_data["correct_choice"])

        # Advance to Q2 and pick wrong option using numeric shortcut '1'..'4'
        next_resp = self.client.post("/api/quiz/next", json={"session_id": session_id})
        self.assertEqual(next_resp.status_code, 200)
        next_data = next_resp.get_json()
        self.assertFalse(next_data["completed"])
        self.assertEqual(next_data["current_index"], 2)

        q2 = cat_questions[1]
        choices2 = next_data["question"]["choices"]
        wrong_num = next(
            str(idx)
            for idx, letter in enumerate(["A", "B", "C", "D"], start=1)
            if choices2[letter] != q2.correct_choice
        )
        ans2 = self.client.post(
            "/api/quiz/answer",
            json={"session_id": session_id, "choice": wrong_num},
        )
        self.assertEqual(ans2.status_code, 200)
        ans2_data = ans2.get_json()
        self.assertFalse(ans2_data["correct"])
        self.assertEqual(ans2_data["xp_gained"], 0)

        # Verify persisted progress stats
        state = self.client.get("/api/state").get_json()
        self.assertEqual(state["overall"]["answered"], 2)
        self.assertEqual(state["overall"]["correct"], 1)
        self.assertEqual(state["overall"]["accuracy"], 50.0)
        self.assertEqual(state["overall"]["missed_count"], 1)

    def test_exact_command_session_hint_whitespace_match_and_skip(self) -> None:
        category = "Navigation & File Management"
        cat_questions = [q for q in self.all_questions if q.category == category]

        start_resp = self.client.post(
            "/api/quiz/start",
            json={"scope": "category", "category": category, "mode": "exact_command", "shuffle": False},
        )
        self.assertEqual(start_resp.status_code, 200)
        session_id = start_resp.get_json()["session_id"]
        self.assertNotIn("choices", start_resp.get_json()["question"])

        # Request hint via /api/quiz/hint
        hint_resp = self.client.post("/api/quiz/hint", json={"session_id": session_id})
        self.assertEqual(hint_resp.status_code, 200)
        self.assertEqual(hint_resp.get_json()["hint"], cat_questions[0].hint)
        self.assertEqual(hint_resp.get_json()["hints_used"], 1)

        # Typing 'hint' inside command bar also returns hint without failing
        inline_hint = self.client.post(
            "/api/quiz/answer",
            json={"session_id": session_id, "command": "  hint  "},
        )
        self.assertEqual(inline_hint.status_code, 200)
        self.assertEqual(inline_hint.get_json()["status"], "hint")
        self.assertEqual(inline_hint.get_json()["hints_used"], 1)

        # Empty command returns 400
        empty_resp = self.client.post(
            "/api/quiz/answer",
            json={"session_id": session_id, "command": "   "},
        )
        self.assertEqual(empty_resp.status_code, 400)

        # Submit valid command with extra whitespace
        padded_cmd = f"   {cat_questions[0].accepted_commands[-1].replace(' ', '   ')}   "
        ans1 = self.client.post(
            "/api/quiz/answer",
            json={"session_id": session_id, "command": padded_cmd},
        )
        self.assertEqual(ans1.status_code, 200)
        self.assertTrue(ans1.get_json()["correct"])

        # Advance to Q2 and skip it
        self.client.post("/api/quiz/next", json={"session_id": session_id})
        skip_resp = self.client.post(
            "/api/quiz/answer",
            json={"session_id": session_id, "action": "skip"},
        )
        self.assertEqual(skip_resp.status_code, 200)
        skip_data = skip_resp.get_json()
        self.assertTrue(skip_data["skipped"])
        self.assertFalse(skip_data["correct"])
        self.assertEqual(skip_data["correct_choice"], cat_questions[1].correct_choice)

        # Start missed-questions quiz and verify it starts with Q2
        missed_start = self.client.post(
            "/api/quiz/start",
            json={"scope": "missed", "mode": "exact_command", "shuffle": False},
        )
        self.assertEqual(missed_start.status_code, 200)
        self.assertEqual(missed_start.get_json()["total_questions"], 1)
        self.assertEqual(missed_start.get_json()["question"]["id"], cat_questions[1].id)

    def test_reset_progress_requires_confirmation_and_clears_stats(self) -> None:
        start_resp = self.client.post(
            "/api/quiz/start",
            json={"scope": "all", "mode": "exact_command", "shuffle": False},
        )
        session_id = start_resp.get_json()["session_id"]
        self.client.post("/api/quiz/answer", json={"session_id": session_id, "action": "skip"})

        bad_reset = self.client.post("/api/progress/reset", json={})
        self.assertEqual(bad_reset.status_code, 400)

        ok_reset = self.client.post("/api/progress/reset", json={"confirm": True})
        self.assertEqual(ok_reset.status_code, 200)
        reset_data = ok_reset.get_json()
        self.assertTrue(reset_data["reset"])
        self.assertEqual(reset_data["dashboard"]["overall"]["answered"], 0)
        self.assertEqual(reset_data["dashboard"]["overall"]["missed_count"], 0)

    def test_ocarina_of_time_theme_present(self) -> None:
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('data-theme-target="oot"', html)
        self.assertIn("Ocarina of Time", html)

        with self.client.get("/static/styles.css") as css_resp:
            self.assertIn('[data-theme="oot"]', css_resp.get_data(as_text=True))

        with self.client.get("/static/app.js") as js_resp:
            js_text = js_resp.get_data(as_text=True)
            self.assertIn("btnThemeOot", js_text)
            self.assertIn('"oot"', js_text)

    def test_appearance_customizer_assets_and_hooks(self) -> None:
        html = self.client.get("/").get_data(as_text=True)
        self.assertNotIn('type="color"', html)
        for token in (
            "btn-open-customizer",
            "customizer-drawer",
            'data-theme-preset="halo"',
            'data-theme-preset="custom1"',
            'data-theme-preset="custom2"',
            'data-theme-target="halo"',
            'data-theme-target="custom1"',
            'data-theme-target="custom2"',
            "btn-save-custom1",
            "btn-save-custom2",
            "color-target-grid",
            "inline-color-editor",
            "editor-hex-input",
            "slider-h",
            "slider-s",
            "slider-b",
            "slider-r",
            "slider-g",
            "slider-b-rgb",
            "custom-ui-font",
            "custom-mono-font",
            "custom-font-scale",
            "custom-radius",
            "custom-effects-toggle",
            "data-density-target",
            "btn-randomize-customizer",
            "btn-reset-customizer",
            "linux_plus_custom_ui",
            'value="modern-sans"',
            'value="scifi"',
            'value="rpg-serif"',
            'value="arcade"',
            'value="legible"',
            'value="jetbrains"',
            'value="fira"',
            'value="source-code"',
            'value="ibm-plex"',
            'value="retro-crt"',
        ):
            self.assertIn(token, html)

        with self.client.get("/static/styles.css") as css_resp:
            css = css_resp.get_data(as_text=True)
            self.assertNotIn('[data-theme="light"]', css)
            for token in (
                '[data-theme="halo"]',
                '[data-theme="nordic"]',
                '[data-theme="matrix"]',
                '[data-theme="custom1"]',
                '[data-theme="custom2"]',
                '[data-effects="off"]',
                '[data-density="compact"]',
                "max-width: min(380px, 100vw)",
                "overflow-x: hidden",
                "--font-scale",
                ".customizer-drawer",
                ".hue-slider",
            ):
                self.assertIn(token, css)

        with self.client.get("/static/app.js") as js_resp:
            js_text = js_resp.get_data(as_text=True)
            for token in (
                "linux_plus_custom_ui",
                "linux_plus_custom_slots",
                "applyCustomUi",
                "saveCurrentLookToSlot",
                "rgbToHsb",
                "hsbToRgb",
                "randomizeAppearance",
                "resetCustomizerToThemeDefaults",
            ):
                self.assertIn(token, js_text)

    def test_web_difficulty_filtering_and_empty_combo(self) -> None:
        category = "Navigation & File Management"
        beginner_expected = [
            q for q in self.all_questions if q.category == category and q.difficulty == "beginner"
        ]

        start_resp = self.client.post(
            "/api/quiz/start",
            json={
                "scope": "category",
                "category": category,
                "mode": "multiple_choice",
                "difficulty": "beginner",
                "shuffle": False,
            },
        )
        self.assertEqual(start_resp.status_code, 200)
        start_data = start_resp.get_json()
        self.assertEqual(start_data["difficulty"], "beginner")
        self.assertEqual(start_data["total_questions"], len(beginner_expected))
        self.assertEqual(start_data["question"]["difficulty"], "beginner")

        # Hard difficulty in category returns all hard questions in that category (>= 18)
        hard_expected = [
            q for q in self.all_questions if q.category == category and q.difficulty == "hard"
        ]
        hard_resp = self.client.post(
            "/api/quiz/start",
            json={
                "scope": "category",
                "category": category,
                "mode": "exact_command",
                "difficulty": "hard",
                "shuffle": False,
            },
        )
        self.assertEqual(hard_resp.status_code, 200)
        hard_data = hard_resp.get_json()
        self.assertEqual(hard_data["difficulty"], "hard")
        self.assertEqual(hard_data["total_questions"], len(hard_expected))
        self.assertGreaterEqual(hard_data["total_questions"], 18)
        self.assertEqual(hard_data["question"]["difficulty"], "hard")

        # Skip a beginner question so missed queue has 1 beginner and 0 hard -> empty 400
        beg_sid = start_data["session_id"]
        self.client.post("/api/quiz/answer", json={"session_id": beg_sid, "action": "skip"})
        empty_resp = self.client.post(
            "/api/quiz/start",
            json={
                "scope": "missed",
                "mode": "exact_command",
                "difficulty": "hard",
            },
        )
        self.assertEqual(empty_resp.status_code, 400)
        empty_data = empty_resp.get_json()
        self.assertTrue(empty_data["empty"])
        self.assertIn("No hard questions", empty_data["error"])

        # Invalid difficulty rejected
        bad_diff = self.client.post(
            "/api/quiz/start",
            json={"scope": "all", "mode": "multiple_choice", "difficulty": "nightmare"},
        )
        self.assertEqual(bad_diff.status_code, 400)

    def test_web_per_category_progress_reset(self) -> None:
        cat_a = "Navigation & File Management"
        cat_b = "Storage & Networking"

        s1 = self.client.post(
            "/api/quiz/start",
            json={"scope": "category", "category": cat_a, "mode": "exact_command", "shuffle": False},
        ).get_json()["session_id"]
        self.client.post("/api/quiz/answer", json={"session_id": s1, "action": "skip"})

        s2 = self.client.post(
            "/api/quiz/start",
            json={"scope": "category", "category": cat_b, "mode": "exact_command", "shuffle": False},
        ).get_json()["session_id"]
        self.client.post("/api/quiz/answer", json={"session_id": s2, "action": "skip"})

        # Reset only cat_a
        reset_resp = self.client.post(
            "/api/progress/reset",
            json={"confirm": True, "category": cat_a},
        )
        self.assertEqual(reset_resp.status_code, 200)
        reset_data = reset_resp.get_json()
        self.assertEqual(reset_data["category"], cat_a)
        by_name = {c["name"]: c for c in reset_data["dashboard"]["categories"]}
        self.assertEqual(by_name[cat_a]["answered"], 0)
        self.assertEqual(by_name[cat_b]["answered"], 1)
        self.assertEqual(reset_data["dashboard"]["overall"]["missed_count"], 1)

        # Unknown category rejected
        bad_cat = self.client.post(
            "/api/progress/reset",
            json={"confirm": True, "category": "Unknown"},
        )
        self.assertEqual(bad_cat.status_code, 400)

    def test_api_state_difficulty_breakdowns_and_segmented_bar_hooks(self) -> None:
        state_before = self.client.get("/api/state").get_json()
        self.assertIn("all", state_before["difficulty_counts"])
        self.assertEqual(state_before["difficulty_counts"]["all"], len(self.all_questions))
        self.assertIn("answered_by_difficulty", state_before)
        self.assertIn("missed_by_difficulty", state_before)
        for card in state_before["categories"]:
            self.assertIn("difficulties", card)
            self.assertEqual(set(card["difficulties"].keys()), {"beginner", "intermediate", "hard"})

        # Answer 1 beginner question correctly and skip 1 hard question
        cat = "Navigation & File Management"
        s_beg = self.client.post(
            "/api/quiz/start",
            json={"scope": "category", "category": cat, "mode": "exact_command", "difficulty": "beginner", "shuffle": False},
        ).get_json()["session_id"]
        beg_q = [q for q in self.all_questions if q.category == cat and q.difficulty == "beginner"][0]
        self.client.post("/api/quiz/answer", json={"session_id": s_beg, "command": beg_q.correct_choice})

        s_hrd = self.client.post(
            "/api/quiz/start",
            json={"scope": "category", "category": cat, "mode": "exact_command", "difficulty": "hard", "shuffle": False},
        ).get_json()["session_id"]
        self.client.post("/api/quiz/answer", json={"session_id": s_hrd, "action": "skip"})

        state_after = self.client.get("/api/state").get_json()
        self.assertEqual(state_after["answered_by_difficulty"]["beginner"], 1)
        self.assertEqual(state_after["answered_by_difficulty"]["hard"], 1)
        self.assertEqual(state_after["missed_by_difficulty"]["hard"], 1)
        self.assertEqual(state_after["missed_by_difficulty"]["all"], 1)

        cat_card = next(c for c in state_after["categories"] if c["name"] == cat)
        self.assertEqual(cat_card["difficulties"]["beginner"]["unique_answered"], 1)
        self.assertEqual(cat_card["difficulties"]["beginner"]["correct"], 1)
        self.assertEqual(cat_card["difficulties"]["hard"]["unique_answered"], 1)
        self.assertEqual(cat_card["difficulties"]["hard"]["correct"], 0)

        html = self.client.get("/").get_data(as_text=True)
        for token in ("diff-count-all", "diff-count-beginner", "diff-count-intermediate", "diff-count-hard"):
            self.assertIn(token, html)

        with self.client.get("/static/styles.css") as css_resp:
            css = css_resp.get_data(as_text=True)
            for token in (".segmented-progress-track", ".seg-beginner", ".seg-intermediate", ".seg-hard"):
                self.assertIn(token, css)

        with self.client.get("/static/app.js") as js_resp:
            js_text = js_resp.get_data(as_text=True)
            for token in ("segmented-progress-track", "diff-mini-breakdown", "missed_by_difficulty"):
                self.assertIn(token, js_text)


class AppStartupSelectorTests(unittest.TestCase):
    """Verify app.py CLI flags and interactive startup mode selector."""

    def test_parse_args_modes_and_port(self) -> None:
        default_args = cli_app.parse_args([])
        self.assertFalse(default_args.terminal)
        self.assertFalse(default_args.web)
        self.assertEqual(default_args.port, 5000)

        term_args = cli_app.parse_args(["--terminal"])
        self.assertTrue(term_args.terminal)
        self.assertFalse(term_args.web)

        web_args = cli_app.parse_args(["--web", "--port", "8080"])
        self.assertTrue(web_args.web)
        self.assertEqual(web_args.port, 8080)

    def test_main_direct_flags_dispatch_without_prompt(self) -> None:
        with patch.object(cli_app, "run_terminal_app", return_value=0) as mock_term:
            rc = cli_app.main(["--terminal"])
            self.assertEqual(rc, 0)
            mock_term.assert_called_once()

        with patch.object(cli_app, "launch_web_mode", return_value=0) as mock_web:
            rc = cli_app.main(["--web", "--port", "5055"])
            self.assertEqual(rc, 0)
            mock_web.assert_called_once()
            self.assertEqual(mock_web.call_args.kwargs["port"], 5055)

    def test_interactive_startup_selector_choices(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            with patch("rich.console.Console.input", side_effect=["bad", "1"]), patch.object(
                cli_app, "run_terminal_app", return_value=0
            ) as mock_term:
                rc = cli_app.main([])
                self.assertEqual(rc, 0)
                mock_term.assert_called_once()

            with patch("rich.console.Console.input", return_value="2"), patch.object(
                cli_app, "launch_web_mode", return_value=0
            ) as mock_web:
                rc = cli_app.main([])
                self.assertEqual(rc, 0)
                mock_web.assert_called_once()
                self.assertEqual(mock_web.call_args.kwargs["port"], 5000)

            with patch("rich.console.Console.input", return_value="3"), patch.object(
                cli_app, "launch_desktop_mode", return_value=0
            ) as mock_desktop:
                rc = cli_app.main([])
                self.assertEqual(rc, 0)
                mock_desktop.assert_called_once()

            with patch("rich.console.Console.input", return_value="4"):
                rc = cli_app.main([])
                self.assertEqual(rc, 0)

    def test_terminal_difficulty_filter_empty_returns_none(self) -> None:
        questions = load_all_questions(QUESTIONS_DIR)
        console = Console(file=io.StringIO(), force_terminal=False, width=100)

        no_hard_questions = [q for q in questions if q.difficulty != "hard"]
        with patch("rich.console.Console.input", return_value="4"):
            picked = cli_app.select_difficulty(console, "All Categories", no_hard_questions)
            self.assertIsNone(picked)

        with patch("rich.console.Console.input", return_value="4"):
            picked_hard = cli_app.select_difficulty(console, "All Categories", questions)
            self.assertIsNotNone(picked_hard)
            diff_name, filtered_hard = picked_hard
            self.assertEqual(diff_name, "hard")
            expected_hard_total = sum(1 for q in questions if q.difficulty == "hard")
            self.assertEqual(len(filtered_hard), expected_hard_total)
            self.assertGreaterEqual(len(filtered_hard), 70)
            self.assertTrue(all(q.difficulty == "hard" for q in filtered_hard))

        with patch("rich.console.Console.input", return_value="2"):
            picked_beginner = cli_app.select_difficulty(console, "All Categories", questions)
            self.assertIsNotNone(picked_beginner)
            diff_name, filtered = picked_beginner
            self.assertEqual(diff_name, "beginner")
            self.assertTrue(all(q.difficulty == "beginner" for q in filtered))


if __name__ == "__main__":
    unittest.main()
