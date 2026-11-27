"""Unit tests for the CompTIA Linux+ (XK0-006) study trainer engine and question bank."""

from __future__ import annotations

import io
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest

from rich.console import Console

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import (  # noqa: E402
    MODE_EXACT_COMMAND,
    MODE_MULTIPLE_CHOICE,
    QUESTIONS_DIR,
    ProgressTracker,
    Question,
    evaluate_multiple_choice,
    filter_questions_by_difficulty,
    get_categories,
    is_exact_command_match,
    load_all_questions,
    load_questions_from_file,
    normalize_command,
    parse_meta_command,
    prepare_shuffled_choices,
    run_quiz_session,
    validate_question_dict,
)


class QuestionBankLoaderTests(unittest.TestCase):
    """Verify starter JSON banks exist, meet counts, and validate cleanly."""

    EXPECTED_FILES = (
        "01_navigation_and_files.json",
        "02_permissions_and_users.json",
        "03_processes_services_logs.json",
        "04_storage_and_networking.json",
        "05_security_and_hardening.json",
        "06_automation_git_and_scripting.json",
        "07_packages_containers_and_troubleshooting.json",
    )

    def test_expected_files_exist_with_minimum_counts(self) -> None:
        total = 0
        for filename in self.EXPECTED_FILES:
            path = QUESTIONS_DIR / filename
            self.assertTrue(path.is_file(), f"Missing question file: {path}")
            loaded = load_questions_from_file(path)
            self.assertGreaterEqual(
                len(loaded), 10, f"{filename} must contain at least 10 questions"
            )
            beginner_count = sum(1 for q in loaded if q.difficulty == "beginner")
            self.assertGreaterEqual(
                beginner_count,
                10,
                f"{filename} must contain at least 10 beginner questions",
            )
            intermediate_count = sum(1 for q in loaded if q.difficulty == "intermediate")
            self.assertGreaterEqual(
                intermediate_count,
                10,
                f"{filename} must contain at least 10 intermediate questions",
            )
            hard_count = sum(1 for q in loaded if q.difficulty == "hard")
            self.assertGreaterEqual(
                hard_count,
                10,
                f"{filename} must contain at least 10 hard questions",
            )
            total += len(loaded)
        self.assertGreaterEqual(total, 40, "Starter bank must have at least 40 questions total")

    def test_all_loaded_questions_satisfy_invariants(self) -> None:
        questions = load_all_questions(QUESTIONS_DIR)
        self.assertGreaterEqual(len(questions), 40)

        ids = [q.id for q in questions]
        self.assertEqual(len(ids), len(set(ids)), "Question IDs must be globally unique")

        categories = get_categories(questions)
        self.assertEqual(len(categories), 7)

        for question in questions:
            self.assertIn(question.difficulty, {"beginner", "intermediate", "hard"})
            self.assertEqual(len(question.choices), 4)
            self.assertEqual(len(set(question.choices)), 4)
            self.assertIn(question.correct_choice, question.choices)
            self.assertTrue(
                is_exact_command_match(question.correct_choice, question.accepted_commands),
                f"{question.id}: correct_choice must match accepted_commands",
            )
            for cmd in question.accepted_commands:
                self.assertIsNone(
                    parse_meta_command(cmd),
                    f"{question.id}: accepted command {cmd!r} collides with meta-command",
                )

    def test_validate_question_dict_rejects_invalid_payloads(self) -> None:
        valid = {
            "id": "test_01",
            "domain": "1.0 System Management",
            "category": "Test",
            "difficulty": "beginner",
            "prompt": "Show current working directory.",
            "choices": ["pwd", "ls", "cd", "whoami"],
            "correct_choice": "pwd",
            "accepted_commands": ["pwd"],
            "hint": "Print working directory.",
            "explanation": "pwd outputs the full path of the current directory.",
        }
        self.assertIsInstance(validate_question_dict(valid), Question)

        # Hard difficulty is accepted
        hard_valid = dict(valid, difficulty="hard")
        self.assertEqual(validate_question_dict(hard_valid).difficulty, "hard")

        # Missing required field
        missing_hint = dict(valid)
        del missing_hint["hint"]
        with self.assertRaises(ValueError):
            validate_question_dict(missing_hint)

        # Invalid difficulty
        bad_diff = dict(valid, difficulty="expert")
        with self.assertRaises(ValueError):
            validate_question_dict(bad_diff)

        # Wrong number of choices
        bad_choices = dict(valid, choices=["pwd", "ls", "cd"])
        with self.assertRaises(ValueError):
            validate_question_dict(bad_choices)

        # Duplicate choices
        dup_choices = dict(valid, choices=["pwd", "pwd", "ls", "cd"])
        with self.assertRaises(ValueError):
            validate_question_dict(dup_choices)

        # correct_choice missing from choices
        bad_correct = dict(valid, correct_choice="id")
        with self.assertRaises(ValueError):
            validate_question_dict(bad_correct)

        # Empty accepted_commands
        empty_accepted = dict(valid, accepted_commands=[])
        with self.assertRaises(ValueError):
            validate_question_dict(empty_accepted)

    def test_load_all_questions_rejects_duplicate_ids(self) -> None:
        sample = [
            {
                "id": "dup_01",
                "domain": "1.0 System Management",
                "category": "Cat",
                "difficulty": "beginner",
                "prompt": "Prompt",
                "choices": ["a", "b", "c", "d"],
                "correct_choice": "a",
                "accepted_commands": ["a"],
                "hint": "Hint",
                "explanation": "Explanation",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "01.json").write_text(json.dumps(sample), encoding="utf-8")
            (tmp_path / "02.json").write_text(json.dumps(sample), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_all_questions(tmp_path)


class CommandMatchingTests(unittest.TestCase):
    """Verify whitespace normalization, exact-command variants, and meta-command parsing."""

    def test_normalize_command_whitespace(self) -> None:
        self.assertEqual(normalize_command("  ls   -la\t /etc   "), "ls -la /etc")
        self.assertEqual(normalize_command("\n\t  "), "")
        self.assertEqual(normalize_command("cat /etc/passwd | wc -l"), "cat /etc/passwd | wc -l")

    def test_exact_command_matching_variants_and_whitespace(self) -> None:
        accepted = ["ls -la", "ls -al", "ls -a -l"]
        self.assertTrue(is_exact_command_match("ls -la", accepted))
        self.assertTrue(is_exact_command_match("   ls    -al  ", accepted))
        self.assertTrue(is_exact_command_match("\tls\t-a   -l\n", accepted))

    def test_exact_command_matching_rejects_invalid_and_wrong_case(self) -> None:
        accepted = ["ls -la", "ls -al", "ls -a -l"]
        self.assertFalse(is_exact_command_match("", accepted))
        self.assertFalse(is_exact_command_match("   ", accepted))
        self.assertFalse(is_exact_command_match("ls", accepted))
        self.assertFalse(is_exact_command_match("ls -l", accepted))
        self.assertFalse(is_exact_command_match("ls -LA", accepted))
        self.assertFalse(is_exact_command_match("ls -la /tmp", accepted))

    def test_parse_meta_command(self) -> None:
        self.assertEqual(parse_meta_command("hint"), "hint")
        self.assertEqual(parse_meta_command("  HINT  "), "hint")
        self.assertEqual(parse_meta_command("skip"), "skip")
        self.assertEqual(parse_meta_command("\tSKIP\n"), "skip")
        self.assertEqual(parse_meta_command("quit"), "quit")
        self.assertEqual(parse_meta_command("exit"), "quit")
        self.assertEqual(parse_meta_command(":q"), "quit")
        self.assertEqual(parse_meta_command("ls -la"), None)


class MultipleChoiceAndProgressTests(unittest.TestCase):
    """Verify choice shuffling, progress persistence, and quiz session execution."""

    def _sample_questions(self) -> list[Question]:
        return [
            Question(
                id="q1",
                domain="1.0 System Management",
                category="Navigation & File Management",
                difficulty="beginner",
                prompt="List hidden files in long format.",
                choices=["ls -la", "ls -lh", "ls -i", "ls -d"],
                correct_choice="ls -la",
                accepted_commands=["ls -la", "ls -al", "ls -a -l"],
                hint="Use -l and -a.",
                explanation="ls -la lists all files including dotfiles in long format.",
            ),
            Question(
                id="q2",
                domain="5.0 Troubleshooting",
                category="Storage & Networking",
                difficulty="intermediate",
                prompt="Check inode usage across mounted filesystems.",
                choices=["df -i", "df -h", "du -sh", "lsblk -f"],
                correct_choice="df -i",
                accepted_commands=["df -i", "df --inodes"],
                hint="Use inode flag.",
                explanation="df -i shows inode utilization.",
            ),
        ]

    def test_multiple_choice_shuffle_and_evaluation(self) -> None:
        question = self._sample_questions()[0]
        choice_map = prepare_shuffled_choices(question, rng=random.Random(42))
        self.assertEqual(list(choice_map.keys()), ["A", "B", "C", "D"])
        self.assertEqual(set(choice_map.values()), set(question.choices))

        correct_letter = next(k for k, v in choice_map.items() if v == question.correct_choice)
        wrong_letter = next(k for k, v in choice_map.items() if v != question.correct_choice)

        is_ok, selected = evaluate_multiple_choice(correct_letter.lower(), choice_map, question)
        self.assertTrue(is_ok)
        self.assertEqual(selected, "ls -la")

        is_bad, _ = evaluate_multiple_choice(wrong_letter, choice_map, question)
        self.assertFalse(is_bad)

    def test_progress_tracker_auto_creates_persists_and_clears_missed(self) -> None:
        questions = self._sample_questions()
        cats = get_categories(questions)

        with tempfile.TemporaryDirectory() as tmpdir:
            progress_path = Path(tmpdir) / "nested" / "progress.json"
            self.assertFalse(progress_path.exists())

            tracker = ProgressTracker(progress_path, categories=cats)
            self.assertTrue(progress_path.exists(), "progress.json must be auto-created")

            tracker.record_attempt(questions[0], is_correct=False)
            tracker.record_attempt(questions[0], is_correct=False)  # duplicate miss ID check
            tracker.record_attempt(questions[1], is_correct=True)

            # Reload from disk to verify persistence
            reloaded = ProgressTracker(progress_path, categories=cats)
            self.assertEqual(reloaded.missed_question_ids, ["q1"])
            stats = reloaded.get_summary_stats(cats)
            self.assertEqual(stats["total_answered"], 3)
            self.assertEqual(stats["total_correct"], 1)
            self.assertEqual(stats["missed_count"], 1)
            self.assertEqual(stats["categories"]["Navigation & File Management"]["answered"], 2)
            self.assertEqual(stats["categories"]["Navigation & File Management"]["correct"], 0)
            self.assertEqual(stats["categories"]["Storage & Networking"]["accuracy"], 100.0)

            # Answering missed question correctly removes it from missed queue
            reloaded.record_attempt(questions[0], is_correct=True)
            self.assertEqual(reloaded.missed_question_ids, [])
            self.assertEqual(reloaded.get_missed_questions(questions), [])

    def test_progress_tracker_recovers_from_corrupted_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            progress_path = Path(tmpdir) / "progress.json"
            progress_path.write_text("{corrupt json", encoding="utf-8")
            tracker = ProgressTracker(progress_path, categories=["Cat A"])
            stats = tracker.get_summary_stats(["Cat A"])
            self.assertEqual(stats["total_answered"], 0)
            self.assertEqual(stats["missed_count"], 0)

    def test_run_quiz_session_exact_mode_hint_skip_and_match(self) -> None:
        questions = self._sample_questions()
        cats = get_categories(questions)
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ProgressTracker(Path(tmpdir) / "progress.json", categories=cats)
            console = Console(file=io.StringIO(), force_terminal=False, width=100)

            # Q1: ask for hint -> whitespace-padded variant -> press Enter
            # Q2: skip
            inputs = iter(["hint", "  ls   -a   -l  ", "", "skip"])
            summary = run_quiz_session(
                questions=questions,
                mode=MODE_EXACT_COMMAND,
                tracker=tracker,
                console=console,
                shuffle_questions=False,
                input_fn=lambda _: next(inputs),
            )

            self.assertEqual(summary.total_questions, 2)
            self.assertEqual(summary.answered, 1)
            self.assertEqual(summary.correct, 1)
            self.assertEqual(summary.skipped, 1)
            self.assertEqual(summary.hints_used, 1)
            self.assertFalse(summary.quit_early)
            self.assertEqual(tracker.missed_question_ids, ["q2"])

    def test_run_quiz_session_multiple_choice_mode(self) -> None:
        questions = [self._sample_questions()[0]]
        cats = get_categories(questions)
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ProgressTracker(Path(tmpdir) / "progress.json", categories=cats)
            console = Console(file=io.StringIO(), force_terminal=False, width=100)

            rng_seed = 7
            expected_map = prepare_shuffled_choices(questions[0], rng=random.Random(rng_seed))
            correct_letter = next(
                k for k, v in expected_map.items() if v == questions[0].correct_choice
            )

            inputs = iter([correct_letter.lower()])
            summary = run_quiz_session(
                questions=questions,
                mode=MODE_MULTIPLE_CHOICE,
                tracker=tracker,
                console=console,
                shuffle_questions=False,
                input_fn=lambda _: next(inputs),
                rng=random.Random(rng_seed),
            )
            self.assertEqual(summary.answered, 1)
            self.assertEqual(summary.correct, 1)
            self.assertEqual(tracker.missed_question_ids, [])

    def test_filter_questions_by_difficulty(self) -> None:
        questions = self._sample_questions() + [
            Question(
                id="q3",
                domain="3.0 Security",
                category="Permissions & User Management",
                difficulty="hard",
                prompt="Lock user account tempadmin.",
                choices=["passwd -l tempadmin", "passwd -u tempadmin", "id tempadmin", "sudo -l"],
                correct_choice="passwd -l tempadmin",
                accepted_commands=["passwd -l tempadmin"],
                hint="Use -l.",
                explanation="passwd -l locks the password.",
            )
        ]

        self.assertEqual(len(filter_questions_by_difficulty(questions, "all")), 3)
        self.assertEqual([q.id for q in filter_questions_by_difficulty(questions, "beginner")], ["q1"])
        self.assertEqual(
            [q.id for q in filter_questions_by_difficulty(questions, "intermediate")], ["q2"]
        )
        self.assertEqual([q.id for q in filter_questions_by_difficulty(questions, "hard")], ["q3"])
        self.assertEqual(filter_questions_by_difficulty(questions[:2], "hard"), [])

        with self.assertRaises(ValueError):
            filter_questions_by_difficulty(questions, "impossible")

    def test_progress_tracker_reset_single_category(self) -> None:
        questions = self._sample_questions()
        cats = get_categories(questions)
        with tempfile.TemporaryDirectory() as tmpdir:
            progress_path = Path(tmpdir) / "progress.json"
            tracker = ProgressTracker(progress_path, categories=cats)
            tracker.record_attempt(questions[0], is_correct=False)
            tracker.record_attempt(questions[1], is_correct=False)

            tracker.reset_category("Navigation & File Management", questions)
            stats = tracker.get_summary_stats(cats)
            self.assertEqual(stats["categories"]["Navigation & File Management"]["answered"], 0)
            self.assertEqual(stats["categories"]["Navigation & File Management"]["correct"], 0)
            self.assertEqual(stats["categories"]["Storage & Networking"]["answered"], 1)
            self.assertEqual(tracker.missed_question_ids, ["q2"])

            with self.assertRaises(ValueError):
                tracker.reset_category("Nonexistent Category", questions)


if __name__ == "__main__":
    unittest.main()
