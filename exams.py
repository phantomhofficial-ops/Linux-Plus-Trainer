"""Weighted CompTIA Linux+ (XK0-006) mock exam builder and scorer."""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Iterable

from engine import Question

XK0_006_DOMAINS: tuple[str, ...] = (
    "1.0 System Management",
    "2.0 Services and User Management",
    "3.0 Security",
    "4.0 Automation, Orchestration, and Scripting",
    "5.0 Troubleshooting",
)

DOMAIN_WEIGHTS: dict[str, int] = {
    "1.0 System Management": 23,
    "2.0 Services and User Management": 20,
    "3.0 Security": 18,
    "4.0 Automation, Orchestration, and Scripting": 17,
    "5.0 Troubleshooting": 22,
}

# 90-question official exam distribution matching XK0-006 weights (sum = 90)
QUOTAS_90: dict[str, int] = {
    "1.0 System Management": 21,
    "2.0 Services and User Management": 18,
    "3.0 Security": 16,
    "4.0 Automation, Orchestration, and Scripting": 15,
    "5.0 Troubleshooting": 20,
}

# 45-question half-length exam distribution (sum = 45)
QUOTAS_45: dict[str, int] = {
    "1.0 System Management": 10,
    "2.0 Services and User Management": 9,
    "3.0 Security": 8,
    "4.0 Automation, Orchestration, and Scripting": 8,
    "5.0 Troubleshooting": 10,
}

PASSING_SCALED_SCORE = 720
MIN_SCALED_SCORE = 100
MAX_SCALED_SCORE = 900

EXAM_PRESETS: dict[str, dict[str, object]] = {
    "exam_a": {
        "id": "exam_a",
        "title": "Mock Exam A",
        "subtitle": "Full-Length XK0-006 Blueprint (Set 1 of 3)",
        "question_count": 90,
        "duration_minutes": 90,
        "quotas": QUOTAS_90,
        "partition_index": 0,
        "randomize": False,
    },
    "exam_b": {
        "id": "exam_b",
        "title": "Mock Exam B",
        "subtitle": "Full-Length XK0-006 Blueprint (Set 2 of 3)",
        "question_count": 90,
        "duration_minutes": 90,
        "quotas": QUOTAS_90,
        "partition_index": 1,
        "randomize": False,
    },
    "exam_c": {
        "id": "exam_c",
        "title": "Mock Exam C",
        "subtitle": "Full-Length XK0-006 Blueprint (Set 3 of 3)",
        "question_count": 90,
        "duration_minutes": 90,
        "quotas": QUOTAS_90,
        "partition_index": 2,
        "randomize": False,
    },
    "half": {
        "id": "half",
        "title": "Half-Length Timed Exam",
        "subtitle": "45 Weighted Questions in 45 Minutes",
        "question_count": 45,
        "duration_minutes": 45,
        "quotas": QUOTAS_45,
        "partition_index": None,
        "randomize": True,
    },
    "random": {
        "id": "random",
        "title": "Random Weighted Mock Exam",
        "subtitle": "Fresh 90-Question Weighted Draw",
        "question_count": 90,
        "duration_minutes": 90,
        "quotas": QUOTAS_90,
        "partition_index": None,
        "randomize": True,
    },
}


@dataclass(frozen=True)
class MockExamBuild:
    """Built mock exam payload with metadata and ordered questions."""

    preset_id: str
    title: str
    subtitle: str
    duration_minutes: int
    questions: list[Question]
    domain_counts: dict[str, int]


def get_primary_domain(domain: str) -> str:
    """Normalize a question's domain string to one of the 5 canonical XK0-006 domains."""
    raw = (domain or "").strip()
    for canonical in XK0_006_DOMAINS:
        prefix = canonical.split(" ", 1)[0]
        if raw == canonical or raw.startswith(prefix):
            return canonical
    return raw


def _interleave_by_difficulty(questions: list[Question]) -> list[Question]:
    """Interleave beginner, intermediate, and hard questions evenly within a domain."""
    buckets: dict[str, list[Question]] = {
        "beginner": [],
        "intermediate": [],
        "hard": [],
    }
    other: list[Question] = []
    for q in questions:
        diff = (q.difficulty or "").strip().lower()
        if diff in buckets:
            buckets[diff].append(q)
        else:
            other.append(q)

    ordered: list[Question] = []
    idx = 0
    while True:
        added = False
        for key in ("beginner", "intermediate", "hard"):
            if idx < len(buckets[key]):
                ordered.append(buckets[key][idx])
                added = True
        if not added:
            break
        idx += 1
    ordered.extend(other)
    return ordered


def build_mock_exam(
    all_questions: Iterable[Question],
    preset_id: str,
    rng: random.Random | None = None,
) -> MockExamBuild:
    """Build a weighted XK0-006 mock exam for the requested preset."""
    if preset_id not in EXAM_PRESETS:
        raise ValueError(f"Unknown mock exam preset: {preset_id!r}")

    preset = EXAM_PRESETS[preset_id]
    quotas: dict[str, int] = dict(preset["quotas"])  # type: ignore[arg-type]
    partition_index: int | None = preset["partition_index"]  # type: ignore[assignment]
    randomize: bool = bool(preset["randomize"])
    rng = rng or random.Random()

    by_domain: dict[str, list[Question]] = {d: [] for d in XK0_006_DOMAINS}
    for q in all_questions:
        primary = get_primary_domain(q.domain)
        if primary in by_domain:
            by_domain[primary].append(q)

    selected: list[Question] = []
    domain_counts: dict[str, int] = {d: 0 for d in XK0_006_DOMAINS}

    for domain in XK0_006_DOMAINS:
        quota = quotas.get(domain, 0)
        pool = sorted(by_domain[domain], key=lambda item: item.id)
        interleaved = _interleave_by_difficulty(pool)

        if partition_index is not None:
            # Stride-3 partitioning *within each difficulty tier* guarantees zero overlap
            # across Exam A, B, and C while giving every exam a balanced Beg/Int/Hard mix.
            buckets: dict[str, list[Question]] = {
                "beginner": [],
                "intermediate": [],
                "hard": [],
            }
            other: list[Question] = []
            for q in pool:
                diff = (q.difficulty or "").strip().lower()
                if diff in buckets:
                    buckets[diff].append(q)
                else:
                    other.append(q)

            part_beg = buckets["beginner"][partition_index::3]
            part_int = buckets["intermediate"][partition_index::3]
            part_hard = buckets["hard"][partition_index::3]
            part_other = other[partition_index::3]

            sliced: list[Question] = []
            idx = 0
            while len(sliced) < quota:
                added = False
                for group in (part_beg, part_int, part_hard, part_other):
                    if len(sliced) >= quota:
                        break
                    if idx < len(group):
                        sliced.append(group[idx])
                        added = True
                if not added:
                    break
                idx += 1

            if len(sliced) < quota:
                used_ids = {q.id for q in sliced}
                remainder = [q for q in interleaved if q.id not in used_ids]
                chosen = sliced + remainder[: quota - len(sliced)]
            else:
                chosen = sliced[:quota]
        elif randomize:
            if len(interleaved) <= quota:
                chosen = list(interleaved)
            else:
                # Sample proportionally across difficulty tiers when possible
                chosen = _sample_balanced(interleaved, quota, rng)
        else:
            chosen = interleaved[:quota]

        selected.extend(chosen)
        domain_counts[domain] = len(chosen)

    if randomize:
        rng.shuffle(selected)

    return MockExamBuild(
        preset_id=preset_id,
        title=str(preset["title"]),
        subtitle=str(preset["subtitle"]),
        duration_minutes=int(preset["duration_minutes"]),  # type: ignore[arg-type]
        questions=selected,
        domain_counts=domain_counts,
    )


def _sample_balanced(
    pool: list[Question],
    quota: int,
    rng: random.Random,
) -> list[Question]:
    """Randomly sample `quota` questions while preserving difficulty balance."""
    tiers: dict[str, list[Question]] = {"beginner": [], "intermediate": [], "hard": []}
    other: list[Question] = []
    for q in pool:
        diff = (q.difficulty or "").strip().lower()
        if diff in tiers:
            tiers[diff].append(q)
        else:
            other.append(q)

    for key in tiers:
        rng.shuffle(tiers[key])
    rng.shuffle(other)

    chosen: list[Question] = []
    used_ids: set[str] = set()
    tier_order = ["beginner", "intermediate", "hard"]
    idx = 0
    while len(chosen) < quota:
        progressed = False
        for key in tier_order:
            if len(chosen) >= quota:
                break
            if idx < len(tiers[key]):
                q = tiers[key][idx]
                chosen.append(q)
                used_ids.add(q.id)
                progressed = True
        if not progressed:
            break
        idx += 1

    if len(chosen) < quota and other:
        for q in other:
            if len(chosen) >= quota:
                break
            if q.id not in used_ids:
                chosen.append(q)
                used_ids.add(q.id)

    return chosen


def compute_scaled_score(correct: int, total: int) -> int:
    """Scale raw accuracy to CompTIA's 100–900 scale (720 = 77.5% passing)."""
    if total <= 0:
        return MIN_SCALED_SCORE
    ratio = max(0.0, min(1.0, correct / total))
    return round(MIN_SCALED_SCORE + ratio * (MAX_SCALED_SCORE - MIN_SCALED_SCORE))


def score_mock_exam(
    questions: list[Question],
    answers: dict[str, int | None],
    flagged_ids: Iterable[str] | None = None,
) -> dict[str, object]:
    """Score a completed mock exam and produce scaled score, domain breakdown, and item review."""
    flagged_set = set(flagged_ids or ())
    total = len(questions)
    correct_count = 0
    answered_count = 0

    domain_stats: dict[str, dict[str, object]] = {
        d: {
            "domain": d,
            "weight": DOMAIN_WEIGHTS[d],
            "total": 0,
            "answered": 0,
            "correct": 0,
            "accuracy": 0.0,
        }
        for d in XK0_006_DOMAINS
    }

    review_items: list[dict[str, object]] = []
    for index, q in enumerate(questions):
        primary = get_primary_domain(q.domain)
        if primary not in domain_stats:
            domain_stats[primary] = {
                "domain": primary,
                "weight": 0,
                "total": 0,
                "answered": 0,
                "correct": 0,
                "accuracy": 0.0,
            }

        selected_idx = answers.get(q.id)
        try:
            correct_idx = q.choices.index(q.correct_choice)
        except ValueError:
            correct_idx = 0
        correct_text = q.correct_choice
        selected_text = (
            q.choices[selected_idx]
            if isinstance(selected_idx, int) and 0 <= selected_idx < len(q.choices)
            else None
        )
        is_answered = selected_idx is not None
        is_correct = is_answered and selected_text == correct_text
        is_flagged = q.id in flagged_set

        domain_stats[primary]["total"] = int(domain_stats[primary]["total"]) + 1
        if is_answered:
            answered_count += 1
            domain_stats[primary]["answered"] = int(domain_stats[primary]["answered"]) + 1
        if is_correct:
            correct_count += 1
            domain_stats[primary]["correct"] = int(domain_stats[primary]["correct"]) + 1

        review_items.append(
            {
                "number": index + 1,
                "id": q.id,
                "domain": primary,
                "category": q.category,
                "difficulty": q.difficulty,
                "prompt": q.prompt,
                "choices": list(q.choices),
                "selected_index": selected_idx,
                "selected_text": selected_text,
                "correct_index": correct_idx,
                "correct_text": correct_text,
                "is_answered": is_answered,
                "is_correct": is_correct,
                "is_flagged": is_flagged,
                "explanation": q.explanation,
            }
        )

    domain_breakdown: list[dict[str, object]] = []
    for domain in XK0_006_DOMAINS:
        entry = domain_stats[domain]
        dom_total = int(entry["total"])
        dom_correct = int(entry["correct"])
        entry["accuracy"] = round((dom_correct / dom_total) * 100, 1) if dom_total else 0.0
        domain_breakdown.append(entry)

    scaled_score = compute_scaled_score(correct_count, total)
    accuracy = round((correct_count / total) * 100, 1) if total else 0.0
    passed = scaled_score >= PASSING_SCALED_SCORE

    return {
        "total": total,
        "answered": answered_count,
        "unanswered": total - answered_count,
        "correct": correct_count,
        "incorrect": total - correct_count,
        "accuracy": accuracy,
        "scaled_score": scaled_score,
        "passing_score": PASSING_SCALED_SCORE,
        "passed": passed,
        "domain_breakdown": domain_breakdown,
        "review_items": review_items,
    }
