"""Entry point, startup mode selector, and interactive Rich CLI menus for the CompTIA Linux+ (XK0-006) trainer."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Callable

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from engine import (
    MODE_EXACT_COMMAND,
    MODE_MULTIPLE_CHOICE,
    ProgressTracker,
    Question,
    filter_questions_by_difficulty,
    get_categories,
    load_all_questions,
    run_quiz_session,
)
from labs import LabDefinition, get_all_labs
from paths import get_progress_file, get_questions_dir
from sandbox import (
    BACKEND_AUTO,
    BACKEND_LABELS,
    SandboxSession,
    get_sandbox_capabilities,
    resolve_backend,
    verify_lab,
)
from web_app import run_web_server
from desktop_app import run_desktop_app


def _safe_input(console: Console, prompt: str) -> str:
    try:
        return console.input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return "q"


def _accuracy_bar(accuracy: float, answered: int, width: int = 12) -> str:
    if answered == 0:
        return "[dim]" + ("░" * width) + "[/dim]"
    filled = round((accuracy / 100.0) * width)
    empty = width - filled
    color = "green" if accuracy >= 80 else "yellow" if accuracy >= 50 else "red"
    return f"[{color}]" + ("█" * filled) + "[/]" + "[dim]" + ("░" * empty) + "[/]"


def render_banner(
    console: Console, total_questions: int, tracker: ProgressTracker, categories: list[str]
) -> None:
    """Display the trainer title banner with live progress metrics."""
    stats = tracker.get_summary_stats(categories)
    subtitle = (
        f"[bold white]Bank:[/bold white] [cyan]{total_questions} questions[/cyan]   "
        f"[bold white]Answered:[/bold white] [cyan]{stats['total_answered']}[/cyan]   "
        f"[bold white]Accuracy:[/bold white] [green]{stats['overall_accuracy']:.1f}%[/green]   "
        f"[bold white]Missed Queue:[/bold white] [yellow]{stats['missed_count']}[/yellow]"
    )
    title_text = Text("CompTIA Linux+ (XK0-006 / V8) Study Trainer", style="bold cyan")
    console.print()
    console.print(
        Panel(
            subtitle,
            title=title_text,
            subtitle="[dim]Standard Bash / POSIX CLI Practice[/dim]",
            border_style="cyan",
            box=box.DOUBLE_EDGE,
            padding=(1, 2),
        )
    )


def select_quiz_mode(console: Console, scope_label: str, question_count: int) -> str | None:
    """Prompt the user to pick Multiple Choice or Exact Command Entry mode."""
    table = Table(
        title=f"Select Quiz Mode — {escape(scope_label)} ({question_count} questions)",
        box=box.ROUNDED,
        border_style="magenta",
        show_header=False,
        padding=(0, 2),
    )
    table.add_column("Option", style="bold yellow", width=5)
    table.add_column("Mode", style="bold white")
    table.add_column("Description", style="dim")

    table.add_row("[1]", "Multiple Choice", "4 shuffled options (A–D) with keyboard selection")
    table.add_row(
        "[2]",
        "Exact Command Entry",
        "Type the exact Bash/POSIX command (supports 'hint' and 'skip')",
    )
    table.add_row("[B]", "Back", "Return to Main Menu")

    while True:
        console.print()
        console.print(table)
        choice = _safe_input(console, "[bold magenta]Mode (1/2/B):[/bold magenta] ").lower()
        if choice == "1":
            return MODE_MULTIPLE_CHOICE
        if choice == "2":
            return MODE_EXACT_COMMAND
        if choice in {"b", "back", "q", "quit"}:
            return None
        console.print("[red]Invalid selection. Choose 1, 2, or B.[/red]")


def select_category(
    console: Console,
    questions: list[Question],
    categories: list[str],
    tracker: ProgressTracker,
) -> tuple[str, list[Question]] | None:
    """Display the category submenu and return (category_name, filtered_questions)."""
    stats = tracker.get_summary_stats(categories)["categories"]

    table = Table(
        title="Choose a Study Category",
        box=box.ROUNDED,
        border_style="cyan",
        padding=(0, 2),
    )
    table.add_column("#", style="bold yellow", width=4)
    table.add_column("Category", style="bold white")
    table.add_column("Questions", justify="right", style="cyan")
    table.add_column("Accuracy", justify="right")

    for idx, cat in enumerate(categories, start=1):
        count = sum(1 for q in questions if q.category == cat)
        cat_stats = stats[cat]
        acc_str = (
            f"{cat_stats['accuracy']:.1f}% ({cat_stats['correct']}/{cat_stats['answered']})"
            if cat_stats["answered"] > 0
            else "[dim]Not attempted[/dim]"
        )
        table.add_row(f"[{idx}]", escape(cat), str(count), acc_str)

    table.add_row("[B]", "Back to Main Menu", "", "")

    while True:
        console.print()
        console.print(table)
        choice = _safe_input(
            console, f"[bold cyan]Category (1-{len(categories)} or B):[/bold cyan] "
        ).lower()
        if choice in {"b", "back", "q", "quit"}:
            return None
        if choice.isdigit():
            num = int(choice)
            if 1 <= num <= len(categories):
                selected_cat = categories[num - 1]
                filtered = [q for q in questions if q.category == selected_cat]
                return selected_cat, filtered
        console.print(
            f"[red]Invalid choice. Enter 1–{len(categories)} or B to go back.[/red]"
        )


def select_difficulty(
    console: Console, scope_label: str, questions: list[Question]
) -> tuple[str, list[Question]] | None:
    """Prompt the user to filter questions by difficulty and return (difficulty, filtered_questions)."""
    counts = {
        "all": len(questions),
        "beginner": sum(1 for q in questions if q.difficulty == "beginner"),
        "intermediate": sum(1 for q in questions if q.difficulty == "intermediate"),
        "hard": sum(1 for q in questions if q.difficulty == "hard"),
    }

    table = Table(
        title=f"Filter by Difficulty — {escape(scope_label)}",
        box=box.ROUNDED,
        border_style="cyan",
        padding=(0, 2),
    )
    table.add_column("Key", style="bold yellow", width=5)
    table.add_column("Difficulty", style="bold white")
    table.add_column("Questions", justify="right", style="cyan")

    table.add_row("[1]", "All", str(counts["all"]))
    table.add_row("[2]", "[green]Beginner[/green]", str(counts["beginner"]))
    table.add_row("[3]", "[yellow]Intermediate[/yellow]", str(counts["intermediate"]))
    table.add_row("[4]", "[red]Hard[/red]", str(counts["hard"]))
    table.add_row("[B]", "Back to Main Menu", "")

    key_map = {
        "1": "all",
        "all": "all",
        "2": "beginner",
        "beginner": "beginner",
        "3": "intermediate",
        "intermediate": "intermediate",
        "4": "hard",
        "hard": "hard",
    }

    while True:
        console.print()
        console.print(table)
        choice = _safe_input(
            console, "[bold cyan]Difficulty (1-4 or B):[/bold cyan] "
        ).lower()
        if choice in {"b", "back", "q", "quit"}:
            return None
        if choice in key_map:
            chosen_diff = key_map[choice]
            filtered = filter_questions_by_difficulty(questions, chosen_diff)
            if not filtered:
                console.print(
                    Panel(
                        f"[yellow]No {chosen_diff.title()} questions are currently available in '{escape(scope_label)}'.[/yellow]",
                        title="[bold yellow]No Matching Questions[/bold yellow]",
                        border_style="yellow",
                        box=box.ROUNDED,
                    )
                )
                return None
            return chosen_diff, filtered
        console.print("[red]Invalid selection. Enter 1–4 or B to go back.[/red]")


def show_summary_stats(
    console: Console,
    tracker: ProgressTracker,
    categories: list[str],
    questions: list[Question] | None = None,
    progress_path: Path | None = None,
) -> None:
    """Display per-category accuracy and overall study stats, with full or per-category reset."""
    display_progress_path = (
        Path(progress_path) if progress_path is not None else tracker.progress_path
    )
    while True:
        stats = tracker.get_summary_stats(categories)
        per_category = stats["categories"]

        table = Table(
            title="Study Progress & Accuracy Summary",
            box=box.ROUNDED,
            border_style="cyan",
            padding=(0, 2),
        )
        table.add_column("Category", style="bold white")
        table.add_column("Answered", justify="right", style="cyan")
        table.add_column("Correct", justify="right", style="green")
        table.add_column("Accuracy", justify="right", style="bold white")
        table.add_column("Progress", justify="left", no_wrap=True)

        for cat, cat_stats in per_category.items():
            answered = int(cat_stats["answered"])
            correct = int(cat_stats["correct"])
            accuracy = float(cat_stats["accuracy"])
            acc_label = f"{accuracy:.1f}%" if answered > 0 else "—"
            table.add_row(
                escape(cat),
                str(answered),
                str(correct),
                acc_label,
                _accuracy_bar(accuracy, answered),
            )

        table.add_section()
        total_answered = int(stats["total_answered"])
        total_correct = int(stats["total_correct"])
        overall_acc = float(stats["overall_accuracy"])
        table.add_row(
            "[bold cyan]TOTAL[/bold cyan]",
            f"[bold cyan]{total_answered}[/bold cyan]",
            f"[bold green]{total_correct}[/bold green]",
            f"[bold white]{overall_acc:.1f}%[/bold white]" if total_answered > 0 else "—",
            _accuracy_bar(overall_acc, total_answered),
        )

        console.print()
        console.print(table)
        console.print(
            f"[bold yellow]Missed Questions Queue:[/bold yellow] {stats['missed_count']} question(s)   "
            f"[bold green]Sandbox Labs Completed:[/bold green] {stats['completed_labs_count']}/{len(get_all_labs())}   "
            f"[dim](Saved in {display_progress_path})[/dim]"
        )

        action = _safe_input(
            console,
            "\n[dim]Press Enter to return, 'reset' to clear ALL progress, or 'c' to reset one category:[/dim] ",
        ).lower()
        if action in {"reset", "r"}:
            confirm = _safe_input(
                console,
                "[bold red]Reset all stats and missed questions? Type 'yes' to confirm:[/bold red] ",
            ).lower()
            if confirm == "yes":
                tracker.reset(categories)
                console.print("[green]All progress reset.[/green]")
            else:
                console.print("[yellow]Reset canceled.[/yellow]")
            continue
        if action in {"c", "cat", "reset-cat"}:
            cat_table = Table(
                title="Reset Single Category Score",
                box=box.ROUNDED,
                border_style="yellow",
                show_header=False,
                padding=(0, 2),
            )
            cat_table.add_column("Key", style="bold yellow", width=4)
            cat_table.add_column("Category", style="bold white")
            for idx, cat in enumerate(categories, start=1):
                cat_table.add_row(f"[{idx}]", escape(cat))
            cat_table.add_row("[B]", "Cancel")
            console.print()
            console.print(cat_table)

            pick = _safe_input(
                console, f"[bold yellow]Select category (1-{len(categories)} or B):[/bold yellow] "
            ).lower()
            if pick.isdigit() and 1 <= int(pick) <= len(categories):
                selected_cat = categories[int(pick) - 1]
                confirm = _safe_input(
                    console,
                    f"[bold red]Reset stats and missed questions for '{escape(selected_cat)}'? Type 'yes' to confirm:[/bold red] ",
                ).lower()
                if confirm == "yes":
                    tracker.reset_category(selected_cat, questions or [])
                    console.print(f"[green]Progress reset for {escape(selected_cat)}.[/green]")
                else:
                    console.print("[yellow]Category reset canceled.[/yellow]")
            else:
                console.print("[yellow]Category reset canceled.[/yellow]")
            continue
        break


def select_sandbox_lab(
    console: Console,
    tracker: ProgressTracker,
    backend: str = BACKEND_AUTO,
    on_backend_change: Callable[[str], None] | None = None,
) -> LabDefinition | None:
    """Display the Sandbox Labs menu and return the chosen LabDefinition or None."""
    labs = get_all_labs()
    diff_styles = {
        "beginner": "green",
        "intermediate": "yellow",
        "hard": "red",
    }
    current_backend = backend

    while True:
        caps = get_sandbox_capabilities()
        available = list(caps["available_backends"])  # type: ignore[arg-type]
        try:
            active_backend = resolve_backend(current_backend)
        except (ValueError, RuntimeError):
            active_backend = str(caps["default_backend"])
        backend_label = BACKEND_LABELS.get(active_backend, active_backend)

        table = Table(
            title="Sandbox Labs (Hands-On Terminal)",
            caption=f"[dim]Backend:[/dim] [bold cyan]{escape(backend_label)}[/bold cyan]  [dim](OS: {escape(str(caps['os']))})[/dim]",
            box=box.ROUNDED,
            border_style="green",
            padding=(0, 2),
        )
        table.add_column("#", style="bold yellow", width=4)
        table.add_column("Status", width=9)
        table.add_column("Lab Title", style="bold white")
        table.add_column("Difficulty", width=13)
        table.add_column("XK0-006 Domain", style="cyan")

        for idx, lab in enumerate(labs, start=1):
            done = tracker.is_lab_completed(lab.id)
            status_str = "[bold green]✓ Done[/bold green]" if done else "[dim]○ Todo[/dim]"
            d_style = diff_styles.get(lab.difficulty, "white")
            table.add_row(
                f"[{idx}]",
                status_str,
                escape(lab.title),
                f"[{d_style}]{lab.difficulty.title()}[/{d_style}]",
                escape(lab.domain),
            )
        if len(available) > 1:
            table.add_row(
                "[S]",
                "",
                f"Switch Sandbox Backend (active: {escape(backend_label)})",
                "",
                "",
            )
        table.add_row("[B]", "", "Back to Main Menu", "", "")

        console.print()
        console.print(table)
        prompt_hint = f"1-{len(labs)}, S, or B" if len(available) > 1 else f"1-{len(labs)} or B"
        choice = _safe_input(
            console, f"[bold green]Select lab ({prompt_hint}):[/bold green] "
        ).lower()
        if choice in {"b", "back", "q", "quit"}:
            return None
        if choice == "s" and len(available) > 1:
            next_idx = (available.index(active_backend) + 1) % len(available)
            current_backend = available[next_idx]
            if on_backend_change is not None:
                on_backend_change(current_backend)
            next_label = BACKEND_LABELS.get(current_backend, current_backend)
            console.print(f"[cyan]Sandbox backend switched to {escape(next_label)}.[/cyan]")
            continue
        if choice.isdigit():
            num = int(choice)
            if 1 <= num <= len(labs):
                return labs[num - 1]
        console.print(f"[red]Invalid choice. Enter 1–{len(labs)} or B to go back.[/red]")


def _render_lab_intro(
    console: Console, lab: LabDefinition, backend_label: str = "Native Bash"
) -> None:
    diff_style = {"beginner": "green", "intermediate": "yellow", "hard": "red"}.get(
        lab.difficulty, "white"
    )
    body = Text()
    body.append("Domain: ", style="bold cyan")
    body.append(f"{lab.domain}   ", style="cyan")
    body.append("Difficulty: ", style="bold cyan")
    body.append(f"{lab.difficulty.title()}   ", style=f"bold {diff_style}")
    body.append("Backend: ", style="bold cyan")
    body.append(f"{backend_label}\n\n", style="bold white")
    body.append("Objective:\n", style="bold white")
    body.append(f"{lab.objective}\n\n", style="white")
    body.append("Verification Checklist:\n", style="bold white")
    for item in lab.checklist:
        body.append(f"  ○ {item}\n", style="dim white")
    body.append(
        "\nMeta-commands: check | hint | reset | solution | backend | quit",
        style="dim cyan",
    )
    console.print()
    console.print(
        Panel(
            body,
            title=f"[bold green]Sandbox Lab: {escape(lab.title)}[/bold green]",
            border_style="green",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


def run_sandbox_lab_session(
    console: Console,
    lab: LabDefinition,
    tracker: ProgressTracker,
    input_fn: Callable[[str], str] | None = None,
    backend: str = BACKEND_AUTO,
) -> bool:
    """Run an interactive sandbox session for a single lab.

    Returns True if the lab passed verification during the session.
    """
    reader: Callable[[str], str] = (
        input_fn if input_fn is not None else lambda prompt: console.input(prompt)
    )
    passed_in_session = False

    session = SandboxSession(lab, backend=backend)
    try:
        _render_lab_intro(console, lab, backend_label=session.backend_label)

        while True:
            prompt_markup = f"[bold green]{escape(session.prompt())}[/bold green] "
            try:
                raw_input = reader(prompt_markup)
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Exiting sandbox lab...[/yellow]")
                break

            cmd = raw_input.strip()
            if not cmd:
                continue

            lowered = cmd.lower()
            if lowered in {"quit", "exit", ":q"}:
                console.print("[yellow]Leaving sandbox lab and cleaning up workspace...[/yellow]")
                break

            if lowered == "hint":
                console.print(
                    Panel(
                        Text(lab.hint, style="yellow"),
                        title="[bold yellow]Lab Hint[/bold yellow]",
                        border_style="yellow",
                        box=box.ROUNDED,
                    )
                )
                continue

            if lowered == "solution":
                console.print(
                    Panel(
                        Text(lab.solution_example, style="magenta"),
                        title="[bold magenta]Example Solution[/bold magenta]",
                        border_style="magenta",
                        box=box.ROUNDED,
                    )
                )
                continue

            if lowered == "reset":
                session.reset_lab()
                console.print(
                    "[green]Sandbox workspace reset to initial clean state.[/green]"
                )
                continue

            if lowered == "backend" or lowered.startswith("backend "):
                caps = get_sandbox_capabilities()
                available = list(caps["available_backends"])  # type: ignore[arg-type]
                if len(available) <= 1:
                    console.print(
                        f"[yellow]Only {escape(session.backend_label)} is available on this system.[/yellow]"
                    )
                    continue
                requested = lowered.split(None, 1)[1].strip() if " " in lowered else ""
                if requested:
                    if requested not in available:
                        console.print(
                            f"[red]Backend '{escape(requested)}' unavailable. Available: {', '.join(available)}[/red]"
                        )
                        continue
                    next_backend = requested
                else:
                    next_backend = available[(available.index(session.backend) + 1) % len(available)]
                if next_backend == session.backend:
                    console.print(f"[cyan]Already using {escape(session.backend_label)}.[/cyan]")
                    continue
                session.cleanup()
                session = SandboxSession(lab, backend=next_backend)
                console.print(
                    f"[cyan]Switched sandbox backend to {escape(session.backend_label)} (workspace reset).[/cyan]"
                )
                continue

            if lowered == "check":
                result = session.verify()
                lines = Text()
                for item in result.checks:
                    if item.passed:
                        lines.append("  ✓ ", style="bold green")
                        lines.append(f"{item.description}\n", style="green")
                    else:
                        lines.append("  ✗ ", style="bold red")
                        lines.append(f"{item.description}\n", style="red")

                border = "green" if result.passed else "yellow"
                title = (
                    "[bold green]✓ LAB PASSED[/bold green]"
                    if result.passed
                    else "[bold yellow]Verification Checklist[/bold yellow]"
                )
                console.print(Panel(lines, title=title, border_style=border, box=box.ROUNDED))

                if result.passed:
                    passed_in_session = True
                    newly_completed = tracker.record_lab_completion(lab.id)
                    if newly_completed:
                        console.print(
                            "[bold green]Progress saved! Lab marked as completed.[/bold green]"
                        )
                continue

            res = session.execute(raw_input)
            if res.blocked:
                console.print(
                    Panel(
                        Text(res.stderr, style="yellow"),
                        title="[bold red]Sandbox Guardrail[/bold red]",
                        border_style="red",
                        box=box.ROUNDED,
                    )
                )
                continue

            if res.stdout:
                out_text = res.stdout if res.stdout.endswith("\n") else res.stdout + "\n"
                console.print(out_text, end="", markup=False)
            if res.stderr:
                err_text = res.stderr if res.stderr.endswith("\n") else res.stderr + "\n"
                console.print(Text(err_text, style="red"), end="")
    finally:
        session.cleanup()

    return passed_in_session


def run_terminal_app(
    console: Console | None = None,
    questions_dir: Path | None = None,
    progress_path: Path | None = None,
) -> int:
    """Run the interactive Rich terminal CLI trainer loop."""
    active_console = console or Console()
    resolved_questions_dir = (
        Path(questions_dir) if questions_dir is not None else get_questions_dir()
    )
    resolved_progress_path = get_progress_file(progress_path)
    try:
        questions = load_all_questions(resolved_questions_dir)
    except ValueError as exc:
        active_console.print(f"[bold red]Failed to load question bank:[/bold red] {exc}")
        return 1

    categories = get_categories(questions)
    tracker = ProgressTracker(resolved_progress_path, categories=categories)
    sandbox_backend = str(get_sandbox_capabilities()["default_backend"])

    def _set_sandbox_backend(new_backend: str) -> None:
        nonlocal sandbox_backend
        sandbox_backend = new_backend

    while True:
        render_banner(active_console, len(questions), tracker, categories)

        menu = Table(
            title="Main Menu",
            box=box.ROUNDED,
            border_style="cyan",
            show_header=False,
            padding=(0, 2),
        )
        menu.add_column("Key", style="bold yellow", width=5)
        menu.add_column("Action", style="bold white")
        menu.add_column("Details", style="dim")

        missed_count = len(tracker.get_missed_questions(questions))
        total_labs = len(get_all_labs())
        completed_labs = len(tracker.completed_labs)
        menu.add_row("[1]", "Choose a Category", f"Study one of {len(categories)} Linux+ topics")
        menu.add_row("[2]", "All Categories", f"Practice across all {len(questions)} questions")
        menu.add_row(
            "[3]",
            "Review Missed Questions",
            f"{missed_count} question(s) queued" if missed_count else "Queue currently empty",
        )
        menu.add_row("[4]", "View Summary Stats", "Per-category accuracy and total answered")
        menu.add_row(
            "[5]",
            "Sandbox Labs (Hands-On)",
            f"Interactive Bash labs ({completed_labs}/{total_labs} completed)",
        )
        menu.add_row("[Q]", "Quit", "Exit trainer")

        active_console.print(menu)
        choice = _safe_input(
            active_console, "[bold cyan]Select an option (1-5 or Q):[/bold cyan] "
        ).lower()

        if choice == "1":
            picked = select_category(active_console, questions, categories, tracker)
            if picked is None:
                continue
            cat_name, cat_questions = picked
            diff_pick = select_difficulty(active_console, cat_name, cat_questions)
            if diff_pick is None:
                continue
            chosen_diff, filtered_questions = diff_pick
            effective_label = (
                cat_name if chosen_diff == "all" else f"{cat_name} ({chosen_diff.title()})"
            )
            mode = select_quiz_mode(active_console, effective_label, len(filtered_questions))
            if mode is not None:
                run_quiz_session(filtered_questions, mode, tracker, active_console)
        elif choice == "2":
            diff_pick = select_difficulty(active_console, "All Categories", questions)
            if diff_pick is None:
                continue
            chosen_diff, filtered_questions = diff_pick
            effective_label = (
                "All Categories"
                if chosen_diff == "all"
                else f"All Categories ({chosen_diff.title()})"
            )
            mode = select_quiz_mode(active_console, effective_label, len(filtered_questions))
            if mode is not None:
                run_quiz_session(filtered_questions, mode, tracker, active_console)
        elif choice == "3":
            missed_questions = tracker.get_missed_questions(questions)
            if not missed_questions:
                active_console.print(
                    Panel(
                        "[green]You have no missed questions in your review queue right now![/green]",
                        title="[bold green]All Caught Up[/bold green]",
                        border_style="green",
                        box=box.ROUNDED,
                    )
                )
                continue
            diff_pick = select_difficulty(
                active_console, "Review Missed Questions", missed_questions
            )
            if diff_pick is None:
                continue
            chosen_diff, filtered_questions = diff_pick
            effective_label = (
                "Review Missed Questions"
                if chosen_diff == "all"
                else f"Review Missed Questions ({chosen_diff.title()})"
            )
            mode = select_quiz_mode(active_console, effective_label, len(filtered_questions))
            if mode is not None:
                run_quiz_session(filtered_questions, mode, tracker, active_console)
        elif choice == "4":
            show_summary_stats(
                active_console,
                tracker,
                categories,
                questions=questions,
                progress_path=resolved_progress_path,
            )
        elif choice == "5":
            while True:
                picked_lab = select_sandbox_lab(
                    active_console,
                    tracker,
                    backend=sandbox_backend,
                    on_backend_change=_set_sandbox_backend,
                )
                if picked_lab is None:
                    break
                run_sandbox_lab_session(
                    active_console,
                    picked_lab,
                    tracker,
                    backend=sandbox_backend,
                )
        elif choice in {"q", "quit", "exit"}:
            active_console.print("\n[cyan]Good luck on your CompTIA Linux+ (XK0-006) exam![/cyan]\n")
            return 0
        else:
            active_console.print("[red]Invalid option. Please choose 1, 2, 3, 4, 5, or Q.[/red]")


def launch_web_mode(
    console: Console,
    port: int = 5000,
    open_browser: bool = True,
    questions_dir: Path | None = None,
    progress_path: Path | None = None,
) -> int:
    """Start the local Flask web server and print connection instructions."""
    url = f"http://127.0.0.1:{port}"
    body = (
        f"[bold white]Local Web GUI URL:[/bold white] [bold cyan]{url}[/bold cyan]\n"
        "[dim]Opening in your default browser (if available)...[/dim]\n\n"
        "[bold yellow]Press Ctrl+C to stop the web server.[/bold yellow]"
    )
    console.print()
    console.print(
        Panel(
            body,
            title="[bold magenta]CompTIA Linux+ Web App Mode[/bold magenta]",
            border_style="magenta",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    try:
        run_web_server(
            host="127.0.0.1",
            port=port,
            open_browser=open_browser,
            questions_dir=questions_dir,
            progress_path=progress_path,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Web server stopped.[/yellow]")
    return 0


def launch_desktop_mode(
    console: Console,
    port: int = 0,
    questions_dir: Path | None = None,
    progress_path: Path | None = None,
) -> int:
    """Start the local Flask server and open the trainer in a native desktop window."""
    return run_desktop_app(
        questions_dir=questions_dir,
        progress_path=progress_path,
        port=port,
        console=console,
    )


def select_startup_mode(console: Console, port: int = 5000) -> str:
    """Display the interactive startup mode selector and return 'terminal', 'web', 'desktop', or 'quit'."""
    console.print()
    console.print(
        Panel(
            "[bold white]Choose how you want to run the Linux+ (XK0-006 / V8) study trainer.[/bold white]",
            title="[bold cyan]CompTIA Linux+ (XK0-006 / V8) Study Trainer[/bold cyan]",
            subtitle="[dim]Shared Question Bank & Progress[/dim]",
            border_style="cyan",
            box=box.DOUBLE_EDGE,
            padding=(1, 2),
        )
    )

    table = Table(
        title="Startup Mode Selector",
        box=box.ROUNDED,
        border_style="cyan",
        show_header=False,
        padding=(0, 2),
    )
    table.add_column("Option", style="bold yellow", width=5)
    table.add_column("Mode", style="bold white")
    table.add_column("Description", style="dim")

    table.add_row("[1]", "Terminal Mode", "Classic Rich interactive command-line trainer")
    table.add_row(
        "[2]",
        "Web App Mode",
        f"Local browser GUI (http://127.0.0.1:{port}) with OSRS & Cyberpunk themes",
    )
    table.add_row(
        "[3]",
        "Desktop Window Mode",
        "Native desktop window (with automatic browser fallback)",
    )
    table.add_row("[4]", "Quit", "Exit trainer")

    while True:
        console.print(table)
        choice = _safe_input(console, "[bold cyan]Choose mode (1/2/3/4):[/bold cyan] ").lower()
        if choice == "1":
            return "terminal"
        if choice == "2":
            return "web"
        if choice == "3":
            return "desktop"
        if choice in {"4", "q", "quit", "exit"}:
            return "quit"
        console.print(
            "[red]Invalid selection. Enter 1 (Terminal), 2 (Web App), 3 (Desktop), or 4 (Quit).[/red]"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse optional CLI launch flags."""
    parser = argparse.ArgumentParser(
        description="CompTIA Linux+ (XK0-006 / V8) Study Trainer"
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--terminal",
        action="store_true",
        help="Launch directly into Rich Terminal CLI mode",
    )
    mode_group.add_argument(
        "--web",
        action="store_true",
        help="Launch directly into local Flask Web App mode",
    )
    mode_group.add_argument(
        "--desktop",
        action="store_true",
        help="Launch directly into Native Desktop Window mode",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port for Web App mode (default: 5000)",
    )
    args = parser.parse_args(argv)
    if not (1 <= args.port <= 65535):
        parser.error("--port must be between 1 and 65535")
    return args


def main(argv: list[str] | None = None) -> int:
    """Application entry point with startup mode selector and CLI flags."""
    args = parse_args(argv)
    console = Console()

    if args.terminal:
        return run_terminal_app(console=console)
    if args.web:
        return launch_web_mode(console=console, port=args.port)
    if args.desktop:
        return launch_desktop_mode(console=console)

    if getattr(sys, "frozen", False):
        return launch_desktop_mode(console=console)

    selected = select_startup_mode(console, port=args.port)
    if selected == "terminal":
        return run_terminal_app(console=console)
    if selected == "web":
        return launch_web_mode(console=console, port=args.port)
    if selected == "desktop":
        return launch_desktop_mode(console=console)

    console.print("\n[cyan]Goodbye! Keep practicing for XK0-006.[/cyan]\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
