"""Local Flask web GUI and REST API for the CompTIA Linux+ (XK0-006 / V8) trainer."""

from __future__ import annotations

import atexit
from dataclasses import dataclass, field
from pathlib import Path
import random
import threading
import uuid
import webbrowser

from flask import Flask, jsonify, render_template, request

from engine import (
    CHOICE_LETTERS,
    DIFFICULTY_FILTERS,
    MODE_EXACT_COMMAND,
    MODE_MULTIPLE_CHOICE,
    ProgressTracker,
    Question,
    evaluate_multiple_choice,
    filter_questions_by_difficulty,
    get_categories,
    is_exact_command_match,
    load_all_questions,
    normalize_command,
    parse_meta_command,
    prepare_shuffled_choices,
)
from labs import get_all_labs, get_lab_by_id
from paths import (
    get_progress_file,
    get_questions_dir,
    get_resource_path,
    get_static_dir,
    get_templates_dir,
)
from sandbox import BACKEND_AUTO, SandboxSession, get_sandbox_capabilities, verify_lab

BASE_DIR = get_resource_path()
XP_PER_CORRECT = 100
MAX_SKILL_LEVEL = 99
NUMBER_TO_LETTER = {"1": "A", "2": "B", "3": "C", "4": "D"}


def compute_skill_xp(correct: int) -> dict[str, int | float]:
    """Derive a purely visual RPG skill level and XP progress from correct answers."""
    xp = max(0, int(correct)) * XP_PER_CORRECT
    level = 1
    remaining = xp

    while level < MAX_SKILL_LEVEL:
        xp_needed = 200 + (level * 100)
        if remaining >= xp_needed:
            remaining -= xp_needed
            level += 1
        else:
            break

    if level >= MAX_SKILL_LEVEL:
        xp_needed = 200 + (MAX_SKILL_LEVEL * 100)
        return {
            "level": MAX_SKILL_LEVEL,
            "xp": xp,
            "xp_in_level": xp_needed,
            "xp_for_next_level": xp_needed,
            "xp_percent": 100.0,
        }

    xp_needed = 200 + (level * 100)
    return {
        "level": level,
        "xp": xp,
        "xp_in_level": remaining,
        "xp_for_next_level": xp_needed,
        "xp_percent": round((remaining / xp_needed) * 100.0, 1),
    }


@dataclass
class WebQuizSession:
    """In-memory state for an active web browser quiz session."""

    session_id: str
    mode: str
    scope_label: str
    questions: list[Question]
    choice_maps: dict[str, dict[str, str]] = field(default_factory=dict)
    current_idx: int = 0
    answered_count: int = 0
    correct_count: int = 0
    skipped_count: int = 0
    hints_used: int = 0
    current_hint_used: bool = False
    current_result: dict[str, object] | None = None

    def current_question(self) -> Question:
        return self.questions[self.current_idx]

    def session_stats(self) -> dict[str, int | float]:
        attempted = self.answered_count + self.skipped_count
        accuracy = (self.correct_count / attempted * 100.0) if attempted > 0 else 0.0
        return {
            "total_questions": len(self.questions),
            "answered": self.answered_count,
            "correct": self.correct_count,
            "skipped": self.skipped_count,
            "hints_used": self.hints_used,
            "xp_earned": self.correct_count * XP_PER_CORRECT,
            "accuracy": round(accuracy, 1),
        }


def _count_difficulties(questions: list[Question]) -> dict[str, int]:
    return {
        "beginner": sum(1 for q in questions if q.difficulty == "beginner"),
        "intermediate": sum(1 for q in questions if q.difficulty == "intermediate"),
        "hard": sum(1 for q in questions if q.difficulty == "hard"),
    }


def _build_dashboard_payload(
    questions: list[Question],
    categories: list[str],
    tracker: ProgressTracker,
) -> dict[str, object]:
    stats = tracker.get_summary_stats(categories)
    per_cat = stats["categories"]
    category_cards: list[dict[str, object]] = []
    total_level = 0

    for category in categories:
        cat_stats = per_cat[category]
        answered = int(cat_stats["answered"])
        correct = int(cat_stats["correct"])
        accuracy = round(float(cat_stats["accuracy"]), 1)
        skill = compute_skill_xp(correct)
        total_level += int(skill["level"])
        cat_questions = [q for q in questions if q.category == category]
        category_cards.append(
            {
                "name": category,
                "question_count": len(cat_questions),
                "difficulty_counts": _count_difficulties(cat_questions),
                "answered": answered,
                "correct": correct,
                "accuracy": accuracy,
                "skill": skill,
            }
        )

    all_labs = get_all_labs()
    total_correct = int(stats["total_correct"])
    return {
        "total_questions": len(questions),
        "difficulty_counts": _count_difficulties(questions),
        "overall": {
            "answered": int(stats["total_answered"]),
            "correct": total_correct,
            "accuracy": round(float(stats["overall_accuracy"]), 1),
            "missed_count": int(stats["missed_count"]),
            "total_level": total_level,
            "total_xp": total_correct * XP_PER_CORRECT,
        },
        "categories": category_cards,
        "completed_labs": list(tracker.completed_labs),
        "total_labs": len(all_labs),
    }


def _serialize_question(session: WebQuizSession, question: Question) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": question.id,
        "domain": question.domain,
        "category": question.category,
        "difficulty": question.difficulty,
        "prompt": question.prompt,
    }
    if session.mode == MODE_MULTIPLE_CHOICE:
        payload["choices"] = session.choice_maps[question.id]
    return payload


def create_app(
    questions_dir: Path | None = None,
    progress_path: Path | None = None,
) -> Flask:
    """Create and configure the Flask web application."""
    resolved_questions_dir = (
        Path(questions_dir) if questions_dir is not None else get_questions_dir()
    )
    resolved_progress_path = get_progress_file(progress_path)

    questions = load_all_questions(resolved_questions_dir)
    categories = get_categories(questions)
    # Ensure progress.json exists immediately on app initialization
    ProgressTracker(resolved_progress_path, categories=categories)

    app = Flask(
        __name__,
        template_folder=str(get_templates_dir()),
        static_folder=str(get_static_dir()),
    )
    sessions: dict[str, WebQuizSession] = {}
    app.extensions["quiz_sessions"] = sessions
    lab_sessions: dict[str, SandboxSession] = {}
    app.extensions["lab_sessions"] = lab_sessions

    def _cleanup_all_lab_sessions() -> None:
        for sb in list(lab_sessions.values()):
            sb.cleanup()
        lab_sessions.clear()

    atexit.register(_cleanup_all_lab_sessions)

    def _get_tracker() -> ProgressTracker:
        return ProgressTracker(resolved_progress_path, categories=categories)

    def _get_session(session_id: object) -> WebQuizSession | None:
        if not isinstance(session_id, str) or not session_id:
            return None
        return sessions.get(session_id)

    def _get_lab_session(session_id: object) -> SandboxSession | None:
        if not isinstance(session_id, str) or not session_id:
            return None
        return lab_sessions.get(session_id)

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/api/state")
    def api_state():
        tracker = _get_tracker()
        return jsonify(_build_dashboard_payload(questions, categories, tracker))

    @app.post("/api/quiz/start")
    def api_quiz_start():
        data = request.get_json(silent=True) or {}
        mode = data.get("mode", MODE_MULTIPLE_CHOICE)
        scope = data.get("scope", "all")
        category = data.get("category")
        difficulty = str(data.get("difficulty") or "all").strip().lower()
        shuffle = bool(data.get("shuffle", True))

        if mode not in {MODE_MULTIPLE_CHOICE, MODE_EXACT_COMMAND}:
            return jsonify({"error": f"Unsupported quiz mode: {mode!r}"}), 400
        if difficulty not in DIFFICULTY_FILTERS:
            return jsonify({"error": f"Unsupported difficulty: {difficulty!r}"}), 400

        tracker = _get_tracker()
        if scope == "all":
            selected_questions = list(questions)
            scope_label = "All Categories"
        elif scope == "category":
            if not isinstance(category, str) or category not in categories:
                return jsonify({"error": "Unknown or missing category."}), 400
            selected_questions = [q for q in questions if q.category == category]
            scope_label = category
        elif scope == "missed":
            selected_questions = tracker.get_missed_questions(questions)
            if not selected_questions:
                return jsonify({"error": "No missed questions in your review queue."}), 400
            scope_label = "Review Missed Questions"
        else:
            return jsonify({"error": f"Unsupported scope: {scope!r}"}), 400

        selected_questions = filter_questions_by_difficulty(selected_questions, difficulty)
        if not selected_questions:
            return (
                jsonify(
                    {
                        "error": f"No {difficulty} questions available in '{scope_label}' yet. Try selecting another difficulty.",
                        "empty": True,
                    }
                ),
                400,
            )

        display_scope = (
            scope_label
            if difficulty == "all"
            else f"{scope_label} • {difficulty.title()}"
        )

        if shuffle:
            random.shuffle(selected_questions)

        choice_maps: dict[str, dict[str, str]] = {}
        if mode == MODE_MULTIPLE_CHOICE:
            for q in selected_questions:
                choice_maps[q.id] = prepare_shuffled_choices(q)

        session_id = uuid.uuid4().hex
        session = WebQuizSession(
            session_id=session_id,
            mode=mode,
            scope_label=display_scope,
            questions=selected_questions,
            choice_maps=choice_maps,
        )
        sessions[session_id] = session
        first_q = session.current_question()

        return jsonify(
            {
                "session_id": session_id,
                "mode": mode,
                "difficulty": difficulty,
                "scope_label": display_scope,
                "total_questions": len(selected_questions),
                "current_index": 1,
                "session_stats": session.session_stats(),
                "question": _serialize_question(session, first_q),
            }
        )

    @app.post("/api/quiz/hint")
    def api_quiz_hint():
        data = request.get_json(silent=True) or {}
        session = _get_session(data.get("session_id"))
        if session is None:
            return jsonify({"error": "Quiz session not found or expired."}), 404

        question = session.current_question()
        if not session.current_hint_used:
            session.current_hint_used = True
            session.hints_used += 1

        return jsonify(
            {
                "question_id": question.id,
                "hint": question.hint,
                "hints_used": session.hints_used,
            }
        )

    @app.post("/api/quiz/answer")
    def api_quiz_answer():
        data = request.get_json(silent=True) or {}
        session = _get_session(data.get("session_id"))
        if session is None:
            return jsonify({"error": "Quiz session not found or expired."}), 404

        if session.current_result is not None:
            return jsonify(session.current_result)

        question = session.current_question()
        tracker = _get_tracker()
        action = str(data.get("action") or "").strip().lower()

        raw_command = str(data.get("command") or "")
        if session.mode == MODE_EXACT_COMMAND and action != "skip":
            meta = parse_meta_command(raw_command)
            if meta == "hint":
                if not session.current_hint_used:
                    session.current_hint_used = True
                    session.hints_used += 1
                return jsonify(
                    {
                        "status": "hint",
                        "question_id": question.id,
                        "hint": question.hint,
                        "hints_used": session.hints_used,
                    }
                )
            if meta == "skip":
                action = "skip"

        selected_letter: str | None = None
        user_answer: str | None = None

        if action == "skip":
            session.skipped_count += 1
            tracker.record_attempt(question, is_correct=False)
            is_correct = False
            status = "skipped"
        elif session.mode == MODE_MULTIPLE_CHOICE:
            raw_choice = normalize_command(str(data.get("choice") or "")).upper()
            letter = NUMBER_TO_LETTER.get(raw_choice, raw_choice)
            choice_map = session.choice_maps[question.id]
            if letter not in choice_map:
                return jsonify({"error": "Invalid multiple-choice selection (use A–D or 1–4)."}), 400
            is_correct, selected_text = evaluate_multiple_choice(letter, choice_map, question)
            selected_letter = letter
            user_answer = f"{letter}) {selected_text}"
            session.answered_count += 1
            if is_correct:
                session.correct_count += 1
            tracker.record_attempt(question, is_correct=is_correct)
            status = "correct" if is_correct else "incorrect"
        else:
            normalized = normalize_command(raw_command)
            if not normalized:
                return jsonify({"error": "Please enter a Bash/POSIX command."}), 400
            is_correct = is_exact_command_match(raw_command, question.accepted_commands)
            user_answer = normalized
            session.answered_count += 1
            if is_correct:
                session.correct_count += 1
            tracker.record_attempt(question, is_correct=is_correct)
            status = "correct" if is_correct else "incorrect"

        correct_letter: str | None = None
        if session.mode == MODE_MULTIPLE_CHOICE:
            choice_map = session.choice_maps[question.id]
            correct_letter = next(
                (ltr for ltr in CHOICE_LETTERS if choice_map[ltr] == question.correct_choice),
                None,
            )

        result: dict[str, object] = {
            "status": status,
            "correct": is_correct,
            "skipped": status == "skipped",
            "xp_gained": XP_PER_CORRECT if is_correct else 0,
            "user_answer": user_answer,
            "selected_letter": selected_letter,
            "correct_letter": correct_letter,
            "correct_choice": question.correct_choice,
            "accepted_commands": question.accepted_commands,
            "domain": question.domain,
            "explanation": question.explanation,
            "is_last_question": session.current_idx + 1 >= len(session.questions),
            "session_stats": session.session_stats(),
            "dashboard": _build_dashboard_payload(questions, categories, tracker),
        }
        session.current_result = result
        return jsonify(result)

    @app.post("/api/quiz/next")
    def api_quiz_next():
        data = request.get_json(silent=True) or {}
        session = _get_session(data.get("session_id"))
        if session is None:
            return jsonify({"error": "Quiz session not found or expired."}), 404

        if session.current_result is None:
            return jsonify({"error": "Answer or skip the current question first."}), 400

        if session.current_idx + 1 < len(session.questions):
            session.current_idx += 1
            session.current_hint_used = False
            session.current_result = None
            next_q = session.current_question()
            return jsonify(
                {
                    "completed": False,
                    "current_index": session.current_idx + 1,
                    "total_questions": len(session.questions),
                    "session_stats": session.session_stats(),
                    "question": _serialize_question(session, next_q),
                }
            )

        summary = session.session_stats()
        sessions.pop(session.session_id, None)
        tracker = _get_tracker()
        return jsonify(
            {
                "completed": True,
                "scope_label": session.scope_label,
                "mode": session.mode,
                "summary": summary,
                "dashboard": _build_dashboard_payload(questions, categories, tracker),
            }
        )

    @app.post("/api/progress/reset")
    def api_progress_reset():
        data = request.get_json(silent=True) or {}
        if data.get("confirm") is not True:
            return jsonify({"error": "Reset requires explicit confirmation."}), 400

        category = data.get("category")
        tracker = _get_tracker()

        if category is None or category == "":
            tracker.reset(categories)
            sessions.clear()
            reset_cat = None
        else:
            if not isinstance(category, str) or category not in categories:
                return jsonify({"error": f"Unknown category: {category!r}"}), 400
            tracker.reset_category(category, questions)
            reset_cat = category

        return jsonify(
            {
                "reset": True,
                "category": reset_cat,
                "dashboard": _build_dashboard_payload(questions, categories, tracker),
            }
        )

    # -----------------------------------------------------------------------
    # Sandbox Lab API Routes
    # -----------------------------------------------------------------------

    @app.get("/api/sandbox/capabilities")
    def api_sandbox_capabilities():
        return jsonify(get_sandbox_capabilities())

    @app.get("/api/labs")
    def api_labs_list():
        tracker = _get_tracker()
        completed_set = set(tracker.completed_labs)
        labs_payload = [
            lab.to_metadata_dict(completed=(lab.id in completed_set))
            for lab in get_all_labs()
        ]
        return jsonify(
            {
                "labs": labs_payload,
                "completed_count": len(completed_set),
                "total_labs": len(labs_payload),
                "sandbox": get_sandbox_capabilities(),
            }
        )

    @app.post("/api/labs/start")
    def api_labs_start():
        data = request.get_json(silent=True) or {}
        lab_id = str(data.get("lab_id") or "").strip()
        backend = str(data.get("backend") or BACKEND_AUTO).strip().lower()
        try:
            lab = get_lab_by_id(lab_id)
        except KeyError:
            return jsonify({"error": f"Unknown lab ID: {lab_id!r}"}), 404

        if len(lab_sessions) >= 20:
            oldest_id = next(iter(lab_sessions))
            oldest = lab_sessions.pop(oldest_id)
            oldest.cleanup()

        try:
            sb_session = SandboxSession(lab, backend=backend)
        except (ValueError, RuntimeError) as exc:
            return jsonify({"error": str(exc)}), 400

        session_id = uuid.uuid4().hex
        lab_sessions[session_id] = sb_session
        tracker = _get_tracker()

        return jsonify(
            {
                "session_id": session_id,
                "lab": lab.to_metadata_dict(completed=tracker.is_lab_completed(lab.id)),
                "backend": sb_session.backend,
                "backend_label": sb_session.backend_label,
                "cwd": sb_session.relative_cwd(),
                "prompt": sb_session.prompt(),
                "verification": sb_session.verify().to_dict(),
            }
        )

    @app.post("/api/labs/exec")
    def api_labs_exec():
        data = request.get_json(silent=True) or {}
        sb_session = _get_lab_session(data.get("session_id"))
        if sb_session is None:
            return jsonify({"error": "Lab session not found or expired."}), 404

        command = str(data.get("command") or "")
        result = sb_session.execute(command)
        return jsonify(result.to_dict())

    @app.post("/api/labs/check")
    def api_labs_check():
        data = request.get_json(silent=True) or {}
        sb_session = _get_lab_session(data.get("session_id"))
        if sb_session is None:
            return jsonify({"error": "Lab session not found or expired."}), 404

        verification = sb_session.verify()
        tracker = _get_tracker()
        newly_completed = False
        if verification.passed:
            newly_completed = tracker.record_lab_completion(sb_session.lab.id)

        payload = verification.to_dict()
        payload["newly_completed"] = newly_completed
        payload["completed_labs"] = list(tracker.completed_labs)
        payload["dashboard"] = _build_dashboard_payload(questions, categories, tracker)
        return jsonify(payload)

    @app.post("/api/labs/reset")
    def api_labs_reset():
        data = request.get_json(silent=True) or {}
        sb_session = _get_lab_session(data.get("session_id"))
        if sb_session is None:
            return jsonify({"error": "Lab session not found or expired."}), 404

        sb_session.reset_lab()
        return jsonify(
            {
                "reset": True,
                "backend": sb_session.backend,
                "backend_label": sb_session.backend_label,
                "cwd": sb_session.relative_cwd(),
                "prompt": sb_session.prompt(),
                "verification": sb_session.verify().to_dict(),
            }
        )

    @app.post("/api/labs/hint")
    def api_labs_hint():
        data = request.get_json(silent=True) or {}
        sb_session = _get_lab_session(data.get("session_id"))
        if sb_session is not None:
            lab = sb_session.lab
        else:
            lab_id = str(data.get("lab_id") or "").strip()
            try:
                lab = get_lab_by_id(lab_id)
            except KeyError:
                return jsonify({"error": "Lab session or lab_id not found."}), 404

        return jsonify({"lab_id": lab.id, "hint": lab.hint})

    @app.post("/api/labs/solution")
    def api_labs_solution():
        data = request.get_json(silent=True) or {}
        sb_session = _get_lab_session(data.get("session_id"))
        if sb_session is not None:
            lab = sb_session.lab
        else:
            lab_id = str(data.get("lab_id") or "").strip()
            try:
                lab = get_lab_by_id(lab_id)
            except KeyError:
                return jsonify({"error": "Lab session or lab_id not found."}), 404

        return jsonify({"lab_id": lab.id, "solution_example": lab.solution_example})

    @app.post("/api/labs/close")
    def api_labs_close():
        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id")
        if isinstance(session_id, str) and session_id in lab_sessions:
            sb = lab_sessions.pop(session_id)
            sb.cleanup()
        return jsonify({"closed": True})

    return app


def _safe_open_browser(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception:
        pass


def run_web_server(
    host: str = "127.0.0.1",
    port: int = 5000,
    open_browser: bool = True,
    questions_dir: Path | None = None,
    progress_path: Path | None = None,
) -> None:
    """Start the local Flask development server and optionally open the browser."""
    app = create_app(questions_dir=questions_dir, progress_path=progress_path)
    url = f"http://{host}:{port}"
    if open_browser:
        timer = threading.Timer(0.6, _safe_open_browser, args=[url])
        timer.daemon = True
        timer.start()
    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    run_web_server()
