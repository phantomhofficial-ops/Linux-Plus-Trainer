# CompTIA Linux+ (XK0-006 / V8) CLI & Web Study Trainer

An interactive study trainer for **CompTIA Linux+ (XK0-006 / V8)** built with Python 3, [`rich`](https://github.com/Textualize/rich) (Terminal Mode), and [`Flask`](https://flask.palletsprojects.com/) (Local Web App Mode).

## Features

- **Startup Mode Selector & CLI Flags**:
  - Run `python app.py` with no flags for an interactive prompt to pick **Terminal Mode**, **Web App Mode**, or **Quit**.
  - Jump straight into a mode with `--terminal` or `--web [--port 5000]`.
- **Shared Question Bank & Progress**: Both Terminal Mode and Web App Mode share `data/questions/` (45 scenario questions) and `data/progress.json`.
- **Difficulty Filtering**: Filter any category, All Categories, or Missed Questions by **All**, **Beginner**, **Intermediate**, or **Hard** in both Terminal Mode and Web App Mode (cleanly returning a friendly notice if a selection has 0 matching questions).
- **Flexible Score Resetting**: Reset all progress across every category or reset a **single category's score & missed questions** in both Terminal Mode (`c` in Summary Stats) and Web App Mode (per-category **Reset** button).
- **Two Quiz Modes**:
  - **Multiple Choice (`A`–`D`)**: Shuffled 4-option questions with keyboard selection (`1–4` or `A–D` in the Web UI).
  - **Exact Command Entry**: Realistic Bash/POSIX terminal scenarios where you type the exact command. Supports whitespace normalization, multiple valid flag/syntax permutations (`accepted_commands`), `hint` (without failing the question), and `skip` (to reveal the answer and explanation).
- **Web Dashboard & Tri-Theme Switcher (`localStorage`)**:
  - Category cards with accuracy, answered count, and gamified **Skill Level & XP bars** (derived from correct answers).
  - Instant top-bar switcher between **RuneScape (OSRS)** (classic beveled panels, gold headings, hit-splat badges), **Cyberpunk** (deep obsidian, neon cyan/magenta borders, CRT scanline overlay, glowing terminal prompt), and **Ocarina of Time** (Hyrule midnight-blue translucent panels, gold bevel borders, A/B/C button palette, Rupee-inspired XP/accuracy bars) persisted without losing active quiz state.
- **XK0-006 Exam Explanations**: Every answered or skipped question displays the command breakdown, accepted variations, flag details, and mapped XK0-006 exam domain.

## Setup & Run (`.venv`)

```bash
cd /home/phantom/linux-plus-trainer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

### Direct Launch Examples

```bash
python app.py              # Interactive mode selector (Terminal / Web App / Quit)
python app.py --terminal   # Launch straight into Rich Terminal CLI
python app.py --web        # Launch local Web GUI on http://127.0.0.1:5000
python app.py --web --port 8080
```

## Running Unit Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Project Structure

```text
linux-plus-trainer/
├── app.py                              # Entry point, startup selector, CLI flags & Rich menus
├── web_app.py                          # Local Flask web server & REST API
├── engine.py                           # Schema loader, validator, quiz loop, progress tracker
├── requirements.txt                    # Python dependencies (rich, flask)
├── README.md
├── templates/
│   └── index.html                      # Web UI SPA template
├── static/
│   ├── styles.css                      # Dual OSRS & Cyberpunk themes
│   └── app.js                          # Web quiz state, keyboard shortcuts & theme persistence
├── data/
│   ├── progress.json                   # Auto-created progress & missed-question storage
│   └── questions/
│       ├── 01_navigation_and_files.json
│       ├── 02_permissions_and_users.json
│       ├── 03_processes_services_logs.json
│       └── 04_storage_and_networking.json
└── tests/
    ├── test_trainer.py                 # Core engine & question bank tests
    └── test_web_app.py                 # Flask test client & startup selector tests
```

## Question JSON Schema & XK0-006 Domain Mapping

Each file in `data/questions/` contains a JSON array of question objects with the following schema:

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `string` | Unique identifier across all files (e.g., `nav_01`) |
| `domain` | `string` | CompTIA Linux+ XK0-006 domain (e.g., `1.0 System Management`) |
| `category` | `string` | Study category name |
| `difficulty` | `string` | `"beginner"` or `"intermediate"` |
| `prompt` | `string` | Realistic terminal scenario description |
| `choices` | `list[str]` | Exactly 4 distinct command options |
| `correct_choice` | `string` | Canonical answer (must match one entry in `choices`) |
| `accepted_commands` | `list[str]` | Valid Bash/POSIX command variants for Exact Command mode |
| `hint` | `string` | Clue shown on `hint` without penalizing the question |
| `explanation` | `string` | Detailed explanation of command, flags, and XK0-006 domain context |

### Starter Question Bank Domains

- **Domain 1.0 — System Management**: Navigation, file operations, archiving (`tar`), mounting, block devices, and host networking (`ip`).
- **Domain 2.0 — Services and User Management**: Links (`ln`), permissions (`chmod`, `chown`), user/group administration (`useradd`, `usermod`), `ps`, `systemctl`, and `crontab`.
- **Domain 3.0 — Security**: Special permissions (SGID), `umask`, account locking/status (`passwd`), and privilege escalation (`sudo`).
- **Domain 5.0 — Troubleshooting**: Signal handling (`kill`), service diagnostics (`systemctl status`, `--failed`), `journalctl`, storage/inode diagnostics (`df`, `du`, `mount -a`), and network/DNS checks (`ip route`, `ss`, `dig`).
