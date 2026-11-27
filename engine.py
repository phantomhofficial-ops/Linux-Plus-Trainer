"""Core quiz engine, question schema validation, command matching, and progress tracking."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import random
from typing import Callable

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from paths import get_progress_file, get_questions_dir, get_resource_path

BASE_DIR = get_resource_path()
QUESTIONS_DIR = get_questions_dir()
PROGRESS_FILE = get_progress_file(create_dir=False)

MODE_MULTIPLE_CHOICE = "multiple_choice"
MODE_EXACT_COMMAND = "exact_command"

VALID_DIFFICULTIES = {"beginner", "intermediate", "hard"}
DIFFICULTY_FILTERS = ("all", "beginner", "intermediate", "hard")
QUIZ_LENGTH_PRESETS: dict[str, int | None] = {
    "short": 10,
    "medium": 20,
    "long": 40,
    "all": None,
}
CANONICAL_DOMAINS: tuple[str, ...] = (
    "1.0 System Management",
    "2.0 Services and User Management",
    "3.0 Security",
    "4.0 Automation, Orchestration, and Scripting",
    "5.0 Troubleshooting",
)
REQUIRED_FIELDS = (
    "id",
    "domain",
    "category",
    "difficulty",
    "prompt",
    "choices",
    "correct_choice",
    "accepted_commands",
    "hint",
    "explanation",
)
CHOICE_LETTERS = ("A", "B", "C", "D")


@dataclass(frozen=True)
class Question:
    """Represents a single CompTIA Linux+ (XK0-006) study question."""

    id: str
    domain: str
    category: str
    difficulty: str
    prompt: str
    choices: list[str]
    correct_choice: str
    accepted_commands: list[str]
    hint: str
    explanation: str


@dataclass
class SessionSummary:
    """Tracks metrics for a single study quiz session."""

    total_questions: int
    answered: int = 0
    correct: int = 0
    skipped: int = 0
    hints_used: int = 0
    quit_early: bool = False

    @property
    def accuracy(self) -> float:
        """Return session accuracy percentage across answered and skipped questions."""
        attempted = self.answered + self.skipped
        if attempted == 0:
            return 0.0
        return (self.correct / attempted) * 100.0


def _require_non_empty_str(value: object, field_name: str, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}: '{field_name}' must be a non-empty string")
    return value.strip()


def validate_question_dict(raw: object, source: str = "") -> Question:
    """Validate a raw dictionary against the question JSON schema and return a Question."""
    context = f"Invalid question in {source}" if source else "Invalid question"
    if not isinstance(raw, dict):
        raise ValueError(f"{context}: entry must be a JSON object")

    missing = [field for field in REQUIRED_FIELDS if field not in raw]
    if missing:
        raise ValueError(f"{context}: missing required field(s): {', '.join(missing)}")

    q_id = _require_non_empty_str(raw["id"], "id", context)
    context = f"{context} ({q_id})"

    domain = _require_non_empty_str(raw["domain"], "domain", context)
    category = _require_non_empty_str(raw["category"], "category", context)
    difficulty = _require_non_empty_str(raw["difficulty"], "difficulty", context).lower()
    if difficulty not in VALID_DIFFICULTIES:
        raise ValueError(
            f"{context}: 'difficulty' must be one of {sorted(VALID_DIFFICULTIES)}, got {difficulty!r}"
        )

    prompt = _require_non_empty_str(raw["prompt"], "prompt", context)
    correct_choice = _require_non_empty_str(raw["correct_choice"], "correct_choice", context)
    hint = _require_non_empty_str(raw["hint"], "hint", context)
    explanation = _require_non_empty_str(raw["explanation"], "explanation", context)

    raw_choices = raw["choices"]
    if not isinstance(raw_choices, list) or len(raw_choices) != 4:
        raise ValueError(f"{context}: 'choices' must be a list of exactly 4 items")
    choices: list[str] = []
    for idx, item in enumerate(raw_choices):
        choices.append(_require_non_empty_str(item, f"choices[{idx}]", context))
    if len(set(choices)) != 4:
        raise ValueError(f"{context}: 'choices' must contain 4 distinct options")

    if correct_choice not in choices:
        raise ValueError(f"{context}: 'correct_choice' must match one of the items in 'choices'")

    raw_accepted = raw["accepted_commands"]
    if not isinstance(raw_accepted, list) or not raw_accepted:
        raise ValueError(f"{context}: 'accepted_commands' must be a non-empty list of strings")
    accepted_commands: list[str] = []
    for idx, item in enumerate(raw_accepted):
        accepted_commands.append(_require_non_empty_str(item, f"accepted_commands[{idx}]", context))

    return Question(
        id=q_id,
        domain=domain,
        category=category,
        difficulty=difficulty,
        prompt=prompt,
        choices=choices,
        correct_choice=correct_choice,
        accepted_commands=accepted_commands,
        hint=hint,
        explanation=explanation,
    )


def load_questions_from_file(path: Path) -> list[Question]:
    """Load and validate all questions from a single JSON file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in {path.name}: {exc}") from exc

    if not isinstance(data, list) or not data:
        raise ValueError(f"{path.name}: top-level JSON value must be a non-empty list")

    return [validate_question_dict(item, source=f"{path.name}[{idx}]") for idx, item in enumerate(data)]


def load_all_questions(questions_dir: Path | None = None) -> list[Question]:
    """Load and validate all question banks from sorted *.json files in questions_dir."""
    resolved_dir = Path(questions_dir) if questions_dir is not None else get_questions_dir()
    if not resolved_dir.is_dir():
        raise ValueError(f"Questions directory does not exist: {resolved_dir}")

    json_files = sorted(resolved_dir.glob("*.json"))
    if not json_files:
        raise ValueError(f"No question JSON files found in: {resolved_dir}")

    questions: list[Question] = []
    seen_ids: set[str] = set()
    for path in json_files:
        file_questions = load_questions_from_file(path)
        for question in file_questions:
            if question.id in seen_ids:
                raise ValueError(f"Duplicate question ID '{question.id}' found in {path.name}")
            seen_ids.add(question.id)
            questions.append(question)

    return questions


def get_categories(questions: list[Question]) -> list[str]:
    """Return ordered unique category names from loaded questions."""
    categories: list[str] = []
    seen: set[str] = set()
    for question in questions:
        if question.category not in seen:
            seen.add(question.category)
            categories.append(question.category)
    return categories


def filter_questions_by_difficulty(
    questions: list[Question], difficulty: str = "all"
) -> list[Question]:
    """Filter questions by difficulty ('all', 'beginner', 'intermediate', 'hard')."""
    normalized = normalize_command(difficulty).lower() or "all"
    if normalized not in DIFFICULTY_FILTERS:
        raise ValueError(
            f"Unsupported difficulty filter {difficulty!r}; expected one of {DIFFICULTY_FILTERS}"
        )
    if normalized == "all":
        return list(questions)
    return [q for q in questions if q.difficulty == normalized]


def _normalize_primary_domain(domain: str) -> str:
    raw = (domain or "").strip()
    for canonical in CANONICAL_DOMAINS:
        prefix = canonical.split(" ", 1)[0]
        if raw == canonical or raw.startswith(prefix):
            return canonical
    return raw


def select_practice_questions(
    all_questions: list[Question],
    categories: list[str] | None = None,
    domains: list[str] | None = None,
    difficulty: str = "all",
    length: str | int | None = "all",
    missed_ids: set[str] | list[str] | None = None,
    answered_ids: set[str] | list[str] | None = None,
    rng: random.Random | None = None,
) -> list[Question]:
    """Filter questions by categories, domains, difficulty, and optional length cap.

    When a finite length (e.g. 10, 20, 40 or 'short'/'medium'/'long') is requested,
    prioritizes unseen and missed questions before already-answered ones while
    shuffling within each priority tier.
    """
    filtered = list(all_questions)

    if categories:
        allowed_cats = {c for c in categories if isinstance(c, str) and c.strip()}
        if allowed_cats:
            filtered = [q for q in filtered if q.category in allowed_cats]

    if domains:
        allowed_domains = {_normalize_primary_domain(d) for d in domains if isinstance(d, str) and d.strip()}
        if allowed_domains:
            filtered = [q for q in filtered if _normalize_primary_domain(q.domain) in allowed_domains]

    filtered = filter_questions_by_difficulty(filtered, difficulty)

    limit: int | None
    if isinstance(length, int) and not isinstance(length, bool):
        limit = length if length > 0 else None
    elif length is None:
        limit = None
    else:
        norm_len = normalize_command(str(length)).lower() or "all"
        if norm_len not in QUIZ_LENGTH_PRESETS:
            raise ValueError(
                f"Unsupported quiz length {length!r}; expected one of {tuple(QUIZ_LENGTH_PRESETS)}"
            )
        limit = QUIZ_LENGTH_PRESETS[norm_len]

    if limit is None:
        return filtered

    if limit >= len(filtered):
        result = list(filtered)
        (rng or random.Random()).shuffle(result)
        return result

    missed_set = set(missed_ids or ())
    answered_set = set(answered_ids or ())
    shuffler = rng or random.Random()

    unseen_or_missed: list[Question] = []
    seen_mastered: list[Question] = []
    for q in filtered:
        if q.id in missed_set or q.id not in answered_set:
            unseen_or_missed.append(q)
        else:
            seen_mastered.append(q)

    shuffler.shuffle(unseen_or_missed)
    shuffler.shuffle(seen_mastered)
    combined = unseen_or_missed + seen_mastered
    selected = combined[:limit]
    shuffler.shuffle(selected)
    return selected


def normalize_command(command: str) -> str:
    """Trim leading/trailing whitespace and collapse repeated whitespace runs to single spaces."""
    if not isinstance(command, str):
        return ""
    return " ".join(command.strip().split())


def is_exact_command_match(user_input: str, accepted_commands: list[str]) -> bool:
    """Return True if normalized user_input matches any normalized accepted command (case-sensitive)."""
    normalized_input = normalize_command(user_input)
    if not normalized_input:
        return False
    normalized_accepted = {
        norm for cmd in accepted_commands if (norm := normalize_command(cmd))
    }
    return normalized_input in normalized_accepted


def parse_meta_command(user_input: str) -> str | None:
    """Detect interactive meta-commands ('hint', 'skip', 'quit') from user input."""
    normalized = normalize_command(user_input).lower()
    if normalized == "hint":
        return "hint"
    if normalized == "skip":
        return "skip"
    if normalized in {"quit", "exit", ":q", "q"}:
        return "quit"
    return None


def prepare_shuffled_choices(
    question: Question, rng: random.Random | None = None
) -> dict[str, str]:
    """Return a dict mapping 'A'..'D' to a freshly shuffled copy of question.choices."""
    options = list(question.choices)
    shuffler = rng if rng is not None else random
    shuffler.shuffle(options)
    return dict(zip(CHOICE_LETTERS, options))


def evaluate_multiple_choice(
    selection: str, choice_map: dict[str, str], question: Question
) -> tuple[bool, str]:
    """Evaluate a multiple-choice letter ('A'..'D') and return (is_correct, selected_text)."""
    letter = normalize_command(selection).upper()
    if letter not in choice_map:
        raise ValueError(f"Invalid choice letter: {selection!r}")
    selected_text = choice_map[letter]
    return selected_text == question.correct_choice, selected_text


class ProgressTracker:
    """Persists per-category accuracy statistics and missed question IDs in JSON."""

    def __init__(
        self,
        progress_path: Path | None = None,
        categories: list[str] | None = None,
    ) -> None:
        self.progress_path = get_progress_file(progress_path)
        self.categories: dict[str, dict[str, int]] = {}
        self.missed_question_ids: list[str] = []
        self.completed_labs: list[str] = []
        self.difficulty_stats: dict[str, dict[str, dict[str, object]]] = {}
        self.mock_exam_history: list[dict[str, object]] = []
        self._known_categories = list(categories or [])
        self._load_or_initialize()

    def _ensure_category_entries(self, categories: list[str]) -> bool:
        changed = False
        for category in categories:
            if category not in self.categories:
                self.categories[category] = {"answered": 0, "correct": 0}
                changed = True
        return changed

    def _load_or_initialize(self) -> None:
        needs_save = False
        if self.progress_path.exists():
            try:
                raw = json.loads(self.progress_path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raise ValueError("Top-level progress JSON must be an object")

                raw_categories = raw.get("categories", {})
                if isinstance(raw_categories, dict):
                    for cat, stats in raw_categories.items():
                        if isinstance(cat, str) and isinstance(stats, dict):
                            answered = max(0, int(stats.get("answered", 0)))
                            correct = max(0, min(answered, int(stats.get("correct", 0))))
                            self.categories[cat] = {"answered": answered, "correct": correct}

                raw_missed = raw.get("missed_question_ids", [])
                if isinstance(raw_missed, list):
                    seen: set[str] = set()
                    for qid in raw_missed:
                        if isinstance(qid, str) and qid.strip() and qid not in seen:
                            seen.add(qid)
                            self.missed_question_ids.append(qid)

                raw_labs = raw.get("completed_labs", [])
                if isinstance(raw_labs, list):
                    seen_labs: set[str] = set()
                    for lid in raw_labs:
                        if isinstance(lid, str) and lid.strip() and lid not in seen_labs:
                            seen_labs.add(lid)
                            self.completed_labs.append(lid)

                raw_diff = raw.get("difficulty_stats", {})
                if isinstance(raw_diff, dict):
                    for cat, tiers in raw_diff.items():
                        if not isinstance(cat, str) or not isinstance(tiers, dict):
                            continue
                        cat_entry: dict[str, dict[str, object]] = {}
                        for diff_name, stats in tiers.items():
                            if diff_name not in VALID_DIFFICULTIES or not isinstance(stats, dict):
                                continue
                            answered = max(0, int(stats.get("answered", 0)))
                            correct = max(0, min(answered, int(stats.get("correct", 0))))
                            raw_uids = stats.get("unique_ids", [])
                            unique_ids: list[str] = []
                            if isinstance(raw_uids, list):
                                seen_uids: set[str] = set()
                                for uid in raw_uids:
                                    if isinstance(uid, str) and uid.strip() and uid not in seen_uids:
                                        seen_uids.add(uid)
                                        unique_ids.append(uid)
                            cat_entry[diff_name] = {
                                "answered": answered,
                                "correct": correct,
                                "unique_ids": unique_ids,
                            }
                        if cat_entry:
                            self.difficulty_stats[cat] = cat_entry

                raw_history = raw.get("mock_exam_history", [])
                if isinstance(raw_history, list):
                    for item in raw_history[-50:]:
                        if isinstance(item, dict):
                            self.mock_exam_history.append(dict(item))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                self.categories = {}
                self.missed_question_ids = []
                self.completed_labs = []
                self.difficulty_stats = {}
                self.mock_exam_history = []
                needs_save = True
        else:
            needs_save = True

        if self._ensure_category_entries(self._known_categories):
            needs_save = True

        if needs_save:
            self.save()

    def save(self) -> None:
        """Write current progress state atomically to progress_path."""
        self.progress_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, object] = {
            "categories": self.categories,
            "missed_question_ids": self.missed_question_ids,
        }
        if self.completed_labs:
            payload["completed_labs"] = self.completed_labs
        if self.difficulty_stats:
            payload["difficulty_stats"] = self.difficulty_stats
        if self.mock_exam_history:
            payload["mock_exam_history"] = self.mock_exam_history
        tmp_path = self.progress_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp_path.replace(self.progress_path)

    def record_lab_completion(self, lab_id: str) -> bool:
        """Record a completed sandbox lab ID and persist progress.

        Returns True if newly completed, False if it was already recorded.
        """
        cleaned = _require_non_empty_str(lab_id, "lab_id", "ProgressTracker")
        if cleaned in self.completed_labs:
            return False
        self.completed_labs.append(cleaned)
        self.save()
        return True

    def is_lab_completed(self, lab_id: str) -> bool:
        """Return True if the given lab ID is marked completed."""
        return lab_id in self.completed_labs

    def record_attempt(
        self,
        question: Question,
        is_correct: bool,
        difficulty: str | None = None,
    ) -> None:
        """Record an answered or skipped question and persist progress."""
        entry = self.categories.setdefault(question.category, {"answered": 0, "correct": 0})
        entry["answered"] += 1
        if is_correct:
            entry["correct"] += 1
            if question.id in self.missed_question_ids:
                self.missed_question_ids.remove(question.id)
        else:
            if question.id not in self.missed_question_ids:
                self.missed_question_ids.append(question.id)

        diff = (difficulty or question.difficulty or "").strip().lower()
        if diff in VALID_DIFFICULTIES:
            cat_diffs = self.difficulty_stats.setdefault(question.category, {})
            diff_entry = cat_diffs.setdefault(
                diff, {"answered": 0, "correct": 0, "unique_ids": []}
            )
            diff_entry["answered"] = int(diff_entry["answered"]) + 1
            if is_correct:
                diff_entry["correct"] = int(diff_entry["correct"]) + 1
            unique_ids = diff_entry["unique_ids"]
            if isinstance(unique_ids, list) and question.id not in unique_ids:
                unique_ids.append(question.id)

        self.save()

    def record_answer(
        self,
        question: Question,
        is_correct: bool,
        difficulty: str | None = None,
    ) -> None:
        """Alias for record_attempt() supporting explicit difficulty tracking."""
        self.record_attempt(question, is_correct=is_correct, difficulty=difficulty)

    def get_category_difficulty_stats(
        self, category: str, difficulty: str
    ) -> dict[str, object]:
        """Return answered, correct, unique_answered, unique_ids, and accuracy for a tier."""
        cat_diffs = self.difficulty_stats.get(category, {})
        raw = cat_diffs.get(difficulty, {})
        answered = int(raw.get("answered", 0)) if isinstance(raw, dict) else 0
        correct = int(raw.get("correct", 0)) if isinstance(raw, dict) else 0
        unique_ids = list(raw.get("unique_ids", [])) if isinstance(raw, dict) else []
        accuracy = (correct / answered * 100.0) if answered > 0 else 0.0
        return {
            "answered": answered,
            "correct": correct,
            "unique_answered": len(unique_ids),
            "unique_ids": unique_ids,
            "accuracy": accuracy,
        }

    def get_missed_questions(self, all_questions: list[Question]) -> list[Question]:
        """Return Question objects matching missed_question_ids in preserved order."""
        by_id = {q.id: q for q in all_questions}
        return [by_id[qid] for qid in self.missed_question_ids if qid in by_id]

    def get_summary_stats(self, categories: list[str] | None = None) -> dict[str, object]:
        """Compute per-category and overall accuracy metrics."""
        ordered_cats = list(categories or self._known_categories)
        for cat in self.categories:
            if cat not in ordered_cats:
                ordered_cats.append(cat)

        per_category: dict[str, dict[str, float | int]] = {}
        total_answered = 0
        total_correct = 0

        for cat in ordered_cats:
            stats = self.categories.get(cat, {"answered": 0, "correct": 0})
            answered = int(stats["answered"])
            correct = int(stats["correct"])
            accuracy = (correct / answered * 100.0) if answered > 0 else 0.0
            per_category[cat] = {
                "answered": answered,
                "correct": correct,
                "accuracy": accuracy,
            }
            total_answered += answered
            total_correct += correct

        overall_accuracy = (total_correct / total_answered * 100.0) if total_answered > 0 else 0.0
        return {
            "categories": per_category,
            "total_answered": total_answered,
            "total_correct": total_correct,
            "overall_accuracy": overall_accuracy,
            "missed_count": len(self.missed_question_ids),
            "completed_labs": list(self.completed_labs),
            "completed_labs_count": len(self.completed_labs),
        }

    def get_all_answered_ids(self) -> set[str]:
        """Return all unique question IDs recorded across per-difficulty stats."""
        answered: set[str] = set()
        for tiers in self.difficulty_stats.values():
            for stats in tiers.values():
                raw_uids = stats.get("unique_ids", [])
                if isinstance(raw_uids, list):
                    for uid in raw_uids:
                        if isinstance(uid, str):
                            answered.add(uid)
        return answered

    def record_mock_exam(self, entry: dict[str, object]) -> None:
        """Append a completed mock exam summary entry and persist."""
        self.mock_exam_history.append(dict(entry))
        if len(self.mock_exam_history) > 50:
            self.mock_exam_history = self.mock_exam_history[-50:]
        self.save()

    def reset(self, categories: list[str] | None = None) -> None:
        """Clear all recorded statistics, missed questions, and completed labs, preserving category keys."""
        cats = list(categories or self._known_categories or self.categories.keys())
        self.categories = {cat: {"answered": 0, "correct": 0} for cat in cats}
        self.missed_question_ids = []
        self.completed_labs = []
        self.difficulty_stats = {}
        self.mock_exam_history = []
        self.save()

    def reset_category(self, category: str, all_questions: list[Question]) -> None:
        """Reset recorded stats and missed question IDs for a single category."""
        known = set(self.categories.keys()) | {q.category for q in all_questions}
        if category not in known:
            raise ValueError(f"Unknown category: {category!r}")
        self.categories[category] = {"answered": 0, "correct": 0}
        cat_qids = {q.id for q in all_questions if q.category == category}
        self.missed_question_ids = [
            qid for qid in self.missed_question_ids if qid not in cat_qids
        ]
        self.difficulty_stats.pop(category, None)
        self.save()


def _render_question_panel(
    console: Console, question: Question, index: int, total: int, mode: str
) -> None:
    mode_label = (
        "Multiple Choice" if mode == MODE_MULTIPLE_CHOICE else "Exact Command Entry"
    )
    diff_style = {
        "beginner": "green",
        "intermediate": "yellow",
        "hard": "red",
    }.get(question.difficulty, "yellow")

    header = Text()
    header.append(f"Question {index}/{total}", style="bold cyan")
    header.append("  •  ", style="dim")
    header.append(question.category, style="bold white")
    header.append("  •  ", style="dim")
    header.append(question.difficulty.title(), style=f"bold {diff_style}")
    header.append("  •  ", style="dim")
    header.append(mode_label, style="magenta")

    body = Text()
    body.append(f"XK0-006 Domain: {question.domain}\n\n", style="dim cyan")
    body.append(question.prompt, style="bold white")

    console.print()
    console.print(
        Panel(
            body,
            title=header,
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


def _render_feedback_panel(
    console: Console,
    question: Question,
    status: str,
    user_answer: str | None = None,
) -> None:
    """Display right/wrong/skipped feedback with command breakdown and XK0-006 domain."""
    if status == "correct":
        title = "[bold green]✓ CORRECT[/bold green]"
        border_style = "green"
    elif status == "skipped":
        title = "[bold yellow]» SKIPPED[/bold yellow]"
        border_style = "yellow"
    else:
        title = "[bold red]✗ INCORRECT[/bold red]"
        border_style = "red"

    lines = Text()
    if user_answer is not None and status == "incorrect":
        lines.append("Your answer: ", style="bold red")
        lines.append(f"{user_answer}\n", style="white")

    lines.append("Expected command: ", style="bold green")
    lines.append(f"{question.correct_choice}\n", style="bold white")

    extra_variants = [
        cmd
        for cmd in question.accepted_commands
        if normalize_command(cmd) != normalize_command(question.correct_choice)
    ]
    if extra_variants:
        preview = ", ".join(extra_variants[:4])
        if len(extra_variants) > 4:
            preview += f" (+{len(extra_variants) - 4} more)"
        lines.append("Also accepted: ", style="dim")
        lines.append(f"{preview}\n", style="dim white")

    lines.append("XK0-006 Domain: ", style="bold cyan")
    lines.append(f"{question.domain}\n\n", style="cyan")
    lines.append("Explanation:\n", style="bold white")
    lines.append(question.explanation, style="white")

    console.print(
        Panel(
            lines,
            title=title,
            border_style=border_style,
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


def _render_session_summary(console: Console, summary: SessionSummary) -> None:
    table = Table(
        title="Session Summary",
        box=box.ROUNDED,
        border_style="cyan",
        show_header=False,
        padding=(0, 2),
    )
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value", style="bold white", justify="right")

    attempted = summary.answered + summary.skipped
    table.add_row("Questions Attempted", f"{attempted} / {summary.total_questions}")
    table.add_row("Correct", f"[green]{summary.correct}[/green]")
    table.add_row("Incorrect", f"[red]{summary.answered - summary.correct}[/red]")
    table.add_row("Skipped", f"[yellow]{summary.skipped}[/yellow]")
    table.add_row("Hints Used", str(summary.hints_used))
    table.add_row("Session Accuracy", f"{summary.accuracy:.1f}%")

    console.print()
    console.print(table)


def run_quiz_session(
    questions: list[Question],
    mode: str,
    tracker: ProgressTracker,
    console: Console,
    shuffle_questions: bool = True,
    input_fn: Callable[[str], str] | None = None,
    rng: random.Random | None = None,
) -> SessionSummary:
    """Run an interactive quiz loop in Multiple Choice or Exact Command Entry mode."""
    if mode not in {MODE_MULTIPLE_CHOICE, MODE_EXACT_COMMAND}:
        raise ValueError(f"Unsupported quiz mode: {mode!r}")

    if not questions:
        return SessionSummary(total_questions=0)

    shuffler = rng if rng is not None else random
    session_questions = list(questions)
    if shuffle_questions:
        shuffler.shuffle(session_questions)

    reader: Callable[[str], str] = (
        input_fn if input_fn is not None else lambda prompt: console.input(prompt)
    )
    summary = SessionSummary(total_questions=len(session_questions))

    for idx, question in enumerate(session_questions, start=1):
        _render_question_panel(console, question, idx, len(session_questions), mode)

        choice_map: dict[str, str] = {}
        if mode == MODE_MULTIPLE_CHOICE:
            choice_map = prepare_shuffled_choices(question, rng=shuffler)
            options_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
            options_table.add_column("Key", style="bold yellow", width=4)
            options_table.add_column("Command", style="white")
            for letter in CHOICE_LETTERS:
                options_table.add_row(f"[{letter}]", escape(choice_map[letter]))
            console.print(options_table)
            console.print(
                "[dim]Select A-D  |  'hint' for clue  |  'skip' to reveal  |  'quit' for menu[/dim]"
            )
        else:
            console.print(
                "[dim]Type the exact Bash/POSIX command  |  'hint' for clue  |  'skip' to reveal  |  'quit' for menu[/dim]"
            )

        hint_counted = False
        quit_requested = False

        while True:
            prompt_str = (
                "[bold cyan]Choice (A-D):[/bold cyan] "
                if mode == MODE_MULTIPLE_CHOICE
                else "[bold green]linux+:~$[/bold green] "
            )
            try:
                raw_input = reader(prompt_str)
            except (EOFError, KeyboardInterrupt):
                quit_requested = True
                break

            normalized = normalize_command(raw_input)
            if not normalized:
                console.print("[dim]Please enter an answer, 'hint', 'skip', or 'quit'.[/dim]")
                continue

            meta = parse_meta_command(normalized)
            if meta == "quit":
                quit_requested = True
                break

            if meta == "hint":
                if not hint_counted:
                    summary.hints_used += 1
                    hint_counted = True
                console.print(
                    Panel(
                        Text(question.hint, style="yellow"),
                        title="[bold yellow]Hint[/bold yellow]",
                        border_style="yellow",
                        box=box.ROUNDED,
                    )
                )
                continue

            if meta == "skip":
                summary.skipped += 1
                tracker.record_answer(question, is_correct=False, difficulty=question.difficulty)
                _render_feedback_panel(console, question, status="skipped")
                break

            if mode == MODE_MULTIPLE_CHOICE:
                letter = normalized.upper()
                if letter not in choice_map:
                    console.print(
                        "[red]Invalid choice. Enter A, B, C, D, 'hint', 'skip', or 'quit'.[/red]"
                    )
                    continue
                is_correct, selected_cmd = evaluate_multiple_choice(
                    letter, choice_map, question
                )
                summary.answered += 1
                if is_correct:
                    summary.correct += 1
                tracker.record_answer(question, is_correct=is_correct, difficulty=question.difficulty)
                _render_feedback_panel(
                    console,
                    question,
                    status="correct" if is_correct else "incorrect",
                    user_answer=f"{letter}) {selected_cmd}",
                )
                break

            # Exact Command Entry evaluation
            is_correct = is_exact_command_match(raw_input, question.accepted_commands)
            summary.answered += 1
            if is_correct:
                summary.correct += 1
            tracker.record_answer(question, is_correct=is_correct, difficulty=question.difficulty)
            _render_feedback_panel(
                console,
                question,
                status="correct" if is_correct else "incorrect",
                user_answer=normalized,
            )
            break

        if quit_requested:
            summary.quit_early = True
            console.print("\n[yellow]Ending session early and returning to menu...[/yellow]")
            break

        if idx < len(session_questions):
            try:
                next_action = reader(
                    "\n[dim]Press Enter for next question (or 'q' to finish session):[/dim] "
                )
            except (EOFError, KeyboardInterrupt):
                summary.quit_early = True
                break
            if parse_meta_command(next_action) == "quit":
                summary.quit_early = True
                break

    _render_session_summary(console, summary)
    return summary
