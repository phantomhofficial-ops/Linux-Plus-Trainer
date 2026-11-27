"""Unit tests for Practice Session Builder and Weighted XK0-006 Mock Exam Hub."""

from __future__ import annotations

import json
from pathlib import Path
import random
import tempfile
import unittest

from engine import (
    ProgressTracker,
    load_all_questions,
    select_practice_questions,
)
from exams import (
    PASSING_SCALED_SCORE,
    QUOTAS_45,
    QUOTAS_90,
    XK0_006_DOMAINS,
    build_mock_exam,
    compute_scaled_score,
    score_mock_exam,
)
from web_app import create_app


class MockExamAndPracticeBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.questions = load_all_questions()

    def test_quotas_sum_to_90_and_45(self) -> None:
        self.assertEqual(sum(QUOTAS_90.values()), 90)
        self.assertEqual(sum(QUOTAS_45.values()), 45)

    def test_static_exams_abc_have_exact_quotas_and_zero_overlap(self) -> None:
        exam_a = build_mock_exam(self.questions, "exam_a")
        exam_b = build_mock_exam(self.questions, "exam_b")
        exam_c = build_mock_exam(self.questions, "exam_c")

        for build in (exam_a, exam_b, exam_c):
            self.assertEqual(len(build.questions), 90)
            self.assertEqual(build.duration_minutes, 90)
            self.assertEqual(build.domain_counts, QUOTAS_90)
            diffs = {q.difficulty for q in build.questions}
            self.assertEqual(diffs, {"beginner", "intermediate", "hard"})

        ids_a = {q.id for q in exam_a.questions}
        ids_b = {q.id for q in exam_b.questions}
        ids_c = {q.id for q in exam_c.questions}
        self.assertEqual(len(ids_a & ids_b), 0)
        self.assertEqual(len(ids_a & ids_c), 0)
        self.assertEqual(len(ids_b & ids_c), 0)
        self.assertEqual(len(ids_a | ids_b | ids_c), 270)

    def test_half_and_random_exam_presets(self) -> None:
        half = build_mock_exam(self.questions, "half", rng=random.Random(42))
        self.assertEqual(len(half.questions), 45)
        self.assertEqual(half.duration_minutes, 45)
        self.assertEqual(half.domain_counts, QUOTAS_45)

        rand_exam = build_mock_exam(self.questions, "random", rng=random.Random(42))
        self.assertEqual(len(rand_exam.questions), 90)
        self.assertEqual(rand_exam.duration_minutes, 90)
        self.assertEqual(rand_exam.domain_counts, QUOTAS_90)

    def test_scaled_score_and_pass_threshold(self) -> None:
        self.assertEqual(compute_scaled_score(0, 90), 100)
        self.assertEqual(compute_scaled_score(90, 90), 900)
        # 70 / 90 = 77.78% -> 100 + 0.7778 * 800 = 722 >= 720 (PASS)
        self.assertGreaterEqual(compute_scaled_score(70, 90), PASSING_SCALED_SCORE)
        # 69 / 90 = 76.67% -> 100 + 0.7667 * 800 = 713 < 720 (FAIL)
        self.assertLess(compute_scaled_score(69, 90), PASSING_SCALED_SCORE)

    def test_score_mock_exam_breakdown_and_flagged_items(self) -> None:
        build = build_mock_exam(self.questions, "half", rng=random.Random(7))
        answers = {q.id: q.choices.index(q.correct_choice) for q in build.questions[:35]}
        flagged = {build.questions[0].id, build.questions[40].id}
        result = score_mock_exam(build.questions, answers, flagged_ids=flagged)

        self.assertEqual(result["total"], 45)
        self.assertEqual(result["answered"], 35)
        self.assertEqual(result["unanswered"], 10)
        self.assertEqual(result["correct"], 35)
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["domain_breakdown"]), len(XK0_006_DOMAINS))
        flagged_reviews = [item for item in result["review_items"] if item["is_flagged"]]
        self.assertEqual(len(flagged_reviews), 2)

    def test_select_practice_questions_multi_filter_and_priority(self) -> None:
        selected = select_practice_questions(
            self.questions,
            domains=["3.0 Security", "5.0 Troubleshooting"],
            difficulty="intermediate",
            length="short",
            missed_ids=[q.id for q in self.questions[:2]],
            rng=random.Random(1),
        )
        self.assertEqual(len(selected), 10)
        for q in selected:
            self.assertEqual(q.difficulty, "intermediate")
            self.assertTrue(q.domain.startswith("3.0") or q.domain.startswith("5.0"))

    def test_progress_tracker_mock_exam_history_backward_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prog_path = Path(tmp) / "progress.json"
            tracker = ProgressTracker(prog_path, categories=["Files, Storage & Text"])
            raw = json.loads(prog_path.read_text(encoding="utf-8"))
            self.assertEqual(set(raw.keys()), {"categories", "missed_question_ids"})

            tracker.record_mock_exam(
                {
                    "preset_id": "exam_a",
                    "title": "Mock Exam A",
                    "scaled_score": 760,
                    "passed": True,
                    "correct": 74,
                    "total": 90,
                    "accuracy": 82.2,
                }
            )
            reloaded = ProgressTracker(prog_path, categories=["Files, Storage & Text"])
            self.assertEqual(len(reloaded.mock_exam_history), 1)
            self.assertEqual(reloaded.mock_exam_history[0]["scaled_score"], 760)

            reloaded.reset()
            self.assertEqual(reloaded.mock_exam_history, [])

    def test_web_api_exams_custom_quiz_and_3tab_ui(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prog_path = Path(tmp) / "progress.json"
            app = create_app(progress_path=prog_path)
            client = app.test_client()

            home = client.get("/")
            self.assertEqual(home.status_code, 200)
            html = home.get_data(as_text=True)
            self.assertIn('id="tab-practice"', html)
            self.assertIn('id="tab-exams"', html)
            self.assertIn('id="tab-labs"', html)
            self.assertIn('id="exam-view"', html)
            self.assertIn('id="exam-scorecard-view"', html)

            state_resp = client.get("/api/state")
            self.assertEqual(state_resp.status_code, 200)
            state_data = state_resp.get_json()
            self.assertEqual(len(state_data["domains"]), 5)
            self.assertEqual(len(state_data["quiz_lengths"]), 4)

            custom_resp = client.post(
                "/api/quiz/start",
                json={
                    "scope": "custom",
                    "domains": ["1.0 System Management", "3.0 Security"],
                    "difficulty": "beginner",
                    "length": "short",
                },
            )
            self.assertEqual(custom_resp.status_code, 200)
            self.assertEqual(custom_resp.get_json()["total_questions"], 10)

            exams_resp = client.get("/api/exams")
            self.assertEqual(exams_resp.status_code, 200)
            self.assertEqual(len(exams_resp.get_json()["presets"]), 5)

            start_resp = client.post("/api/exams/start", json={"preset": "half"})
            self.assertEqual(start_resp.status_code, 200)
            start_data = start_resp.get_json()
            self.assertEqual(start_data["total_questions"], 45)
            exam_sid = start_data["exam_session_id"]
            first_q = start_data["questions"][0]

            ans_resp = client.post(
                "/api/exams/answer",
                json={
                    "exam_session_id": exam_sid,
                    "question_id": first_q["id"],
                    "selected_index": 0,
                    "flagged": True,
                },
            )
            self.assertEqual(ans_resp.status_code, 200)
            self.assertEqual(ans_resp.get_json()["answered_count"], 1)
            self.assertEqual(ans_resp.get_json()["flagged_count"], 1)

            sub_resp = client.post(
                "/api/exams/submit",
                json={"exam_session_id": exam_sid, "elapsed_seconds": 120},
            )
            self.assertEqual(sub_resp.status_code, 200)
            sub_data = sub_resp.get_json()
            self.assertIn("scaled_score", sub_data)
            self.assertEqual(len(sub_data["domain_breakdown"]), 5)
            self.assertEqual(len(sub_data["dashboard"]["mock_exam_history"]), 1)


if __name__ == "__main__":
    unittest.main()
