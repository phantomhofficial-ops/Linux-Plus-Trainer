"""Safe, isolated cross-platform sandbox engine (Native Bash, WSL, and Simulated Shell)."""

from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import glob as pyglob
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

from labs import (
    LabDefinition,
    VirtualFSState,
    build_wsl_setup_script,
    build_wsl_verify_script,
    get_lab_by_id,
    get_virtual_fs,
    get_wsl_verifier,
    register_simulated_script_runner,
    register_virtual_fs,
    register_wsl_verifier,
    unregister_virtual_fs,
    unregister_wsl_verifier,
)

DEFAULT_TIMEOUT_SECONDS = 5.0
MAX_OUTPUT_CHARS = 65536
_CWD_MARKER = "__LINUX_PLUS_SANDBOX_CWD__:"
VIRTUAL_HOME = "/home/lab"
_VIRTUAL_HOME_RE = re.compile(
    r"(?<![A-Za-z0-9_./-])" + re.escape(VIRTUAL_HOME) + r"(?=/|$|[\s'\"`;|&<>)\]}])"
)

BACKEND_AUTO = "auto"
BACKEND_NATIVE = "native"
BACKEND_WSL = "wsl"
BACKEND_SIMULATED = "simulated"
VALID_BACKENDS = (BACKEND_AUTO, BACKEND_NATIVE, BACKEND_WSL, BACKEND_SIMULATED)
BACKEND_LABELS: dict[str, str] = {
    BACKEND_NATIVE: "Native Bash",
    BACKEND_WSL: "WSL Linux",
    BACKEND_SIMULATED: "Simulated Shell",
}

BLOCKED_COMMANDS = frozenset(
    {
        "sudo",
        "su",
        "doas",
        "pkexec",
        "mkfs",
        "fdisk",
        "parted",
        "gdisk",
        "wipefs",
        "mount",
        "umount",
        "dd",
        "shutdown",
        "reboot",
        "poweroff",
        "halt",
        "init",
        "telinit",
        "systemctl",
        "service",
        "journalctl",
        "pacman",
        "apt",
        "apt-get",
        "dnf",
        "yum",
        "zypper",
        "apk",
        "kill",
        "pkill",
        "killall",
        "useradd",
        "userdel",
        "usermod",
        "groupadd",
        "groupdel",
        "passwd",
        "chpasswd",
        "visudo",
        "chown",
        "chgrp",
        "chroot",
        "nsenter",
        "unshare",
        "iptables",
        "nft",
        "ufw",
        "crontab",
        "curl",
        "wget",
        "nc",
        "ncat",
        "ssh",
        "scp",
        "rsync",
        "python",
        "python3",
        "perl",
        "ruby",
        "node",
        "eval",
        "exec",
        "nohup",
    }
)

SENSITIVE_ROOT_PREFIXES = (
    "/etc",
    "/home",
    "/var",
    "/usr",
    "/root",
    "/proc",
    "/sys",
    "/dev",
    "/boot",
    "/opt",
    "/srv",
    "/tmp",
    "/run",
    "/mnt",
    "/media",
    "/sbin",
    "/lib",
    "/lib64",
    "/bin",
)

_WRAPPER_COMMANDS = frozenset({"env", "command", "builtin", "time", "xargs"})
_SUBSHELL_RE = re.compile(r"\$\(([^)]*)\)|`([^`]*)`")
_SEGMENT_SPLIT_RE = re.compile(r"\s*(?:&&|\|\||[;\n|&])\s*")
_SHEBANG_RE = re.compile(r"#!\s*/bin/(?:ba)?sh\b")
_WINDOWS_DRIVE_RE = re.compile(r"^[a-zA-Z]:")


@dataclass(frozen=True)
class CommandResult:
    """Result of executing a single command inside a SandboxSession."""

    command: str
    stdout: str
    stderr: str
    returncode: int
    cwd: str
    prompt: str
    blocked: bool = False
    timed_out: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
            "cwd": self.cwd,
            "prompt": self.prompt,
            "blocked": self.blocked,
            "timed_out": self.timed_out,
        }


@dataclass(frozen=True)
class CheckResult:
    """Result of evaluating a single lab verification criterion."""

    description: str
    passed: bool

    def to_dict(self) -> dict[str, object]:
        return {"description": self.description, "passed": self.passed}


@dataclass(frozen=True)
class VerificationResult:
    """Aggregate state-based verification result for a lab workspace."""

    lab_id: str
    passed: bool
    checks: list[CheckResult]

    def to_dict(self) -> dict[str, object]:
        return {
            "lab_id": self.lab_id,
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
        }


def _detect_os() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform


def _is_native_bash_available() -> bool:
    if _detect_os() == "windows":
        return False
    return shutil.which("bash") is not None


def _find_wsl_executable() -> str | None:
    return shutil.which("wsl") or shutil.which("wsl.exe")


def is_wsl_available(timeout: float = 3.0) -> bool:
    """Return True on Windows when wsl.exe exists and responds cleanly to bash."""
    if _detect_os() != "windows":
        return False
    wsl_exe = _find_wsl_executable()
    if not wsl_exe:
        return False
    try:
        proc = subprocess.run(
            [wsl_exe, "-e", "bash", "-c", "echo ok"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return proc.returncode == 0 and "ok" in (proc.stdout or "")
    except (OSError, subprocess.SubprocessError):
        return False


def get_sandbox_capabilities() -> dict[str, object]:
    """Return active OS, available sandbox backends, and auto-selected default."""
    current_os = _detect_os()
    available: list[str] = []
    if current_os == "windows":
        if is_wsl_available():
            available.append(BACKEND_WSL)
        available.append(BACKEND_SIMULATED)
    else:
        if _is_native_bash_available():
            available.append(BACKEND_NATIVE)
        available.append(BACKEND_SIMULATED)

    default_backend = available[0]
    return {
        "os": current_os,
        "available_backends": available,
        "default_backend": default_backend,
        "backend_labels": dict(BACKEND_LABELS),
    }


def resolve_backend(backend: str = BACKEND_AUTO) -> str:
    """Resolve 'auto' or validate an explicit sandbox backend selection."""
    normalized = (backend or BACKEND_AUTO).strip().lower()
    if normalized not in VALID_BACKENDS:
        raise ValueError(
            f"Unsupported sandbox backend {backend!r}; expected one of {VALID_BACKENDS}"
        )
    caps = get_sandbox_capabilities()
    available = list(caps["available_backends"])  # type: ignore[arg-type]
    if normalized == BACKEND_AUTO:
        return str(caps["default_backend"])
    if normalized not in available:
        raise RuntimeError(
            f"Sandbox backend '{normalized}' is not available on {caps['os']}. "
            f"Available backends: {', '.join(available)}"
        )
    return normalized


def verify_lab(lab_id: str, sandbox_root: Path | PurePosixPath | str) -> VerificationResult:
    """Evaluate actual filesystem state for lab_id inside sandbox_root."""
    lab = get_lab_by_id(lab_id)
    wsl_verifier = get_wsl_verifier(str(sandbox_root))
    if wsl_verifier is not None:
        outcomes = wsl_verifier(lab.id)
        results = [
            CheckResult(
                description=check.description,
                passed=bool(outcomes[idx]) if idx < len(outcomes) else False,
            )
            for idx, check in enumerate(lab.checks)
        ]
        return VerificationResult(
            lab_id=lab.id,
            passed=all(r.passed for r in results) and len(results) > 0,
            checks=results,
        )

    root = Path(sandbox_root)
    results = []
    for check in lab.checks:
        try:
            ok = bool(check.predicate(root))
        except OSError:
            ok = False
        results.append(CheckResult(description=check.description, passed=ok))
    return VerificationResult(
        lab_id=lab.id,
        passed=all(r.passed for r in results) and len(results) > 0,
        checks=results,
    )


def _use_posix_paths(sandbox_root: Path | PurePosixPath) -> bool:
    return isinstance(sandbox_root, PurePosixPath) or os.sep == "/"


def _norm_sandbox_path(path: Path | PurePosixPath | str, use_posix: bool) -> str:
    raw = str(path)
    if use_posix:
        return posixpath.normpath(raw.replace("\\", "/"))
    return os.path.normcase(os.path.normpath(raw))


def _join_sandbox_path(base: Path | PurePosixPath | str, rel: str, use_posix: bool) -> str:
    if use_posix:
        return posixpath.normpath(posixpath.join(str(base), rel.replace("\\", "/")))
    return os.path.normpath(os.path.join(str(base), rel))


def _is_within_sandbox(
    candidate: Path | PurePosixPath | str,
    sandbox_root: Path | PurePosixPath,
) -> bool:
    use_posix = _use_posix_paths(sandbox_root)
    sep = "/" if use_posix else os.sep
    root_norm = _norm_sandbox_path(sandbox_root, use_posix)
    cand_norm = _norm_sandbox_path(candidate, use_posix)
    if root_norm == sep:
        return cand_norm.startswith(sep)
    return cand_norm == root_norm or cand_norm.startswith(root_norm + sep)


def _map_virtual_home_to_sandbox(
    candidate: str,
    sandbox_root: Path | PurePosixPath,
    use_posix: bool,
) -> str | None:
    """Map /home/lab(/...) to sandbox_root, returning None if '..' escapes /home/lab."""
    normed = posixpath.normpath(candidate.replace("\\", "/"))
    if normed == VIRTUAL_HOME:
        return str(sandbox_root)
    if normed.startswith(VIRTUAL_HOME + "/"):
        rel = normed[len(VIRTUAL_HOME) + 1 :]
        return _join_sandbox_path(sandbox_root, rel, use_posix)
    return None


def _rewrite_virtual_home(command: str, sandbox_root: Path | PurePosixPath) -> str:
    """Rewrite /home/lab references in a validated command to the real sandbox root."""
    root_str = str(sandbox_root)
    return _VIRTUAL_HOME_RE.sub(lambda _m: root_str, command)


def _mask_sandbox_paths(text: str, sandbox_root: Path | PurePosixPath) -> str:
    """Mask raw temporary sandbox root paths in output with /home/lab."""
    if not text:
        return text
    variants: list[str] = [str(sandbox_root)]
    if isinstance(sandbox_root, Path):
        variants.append(sandbox_root.as_posix())
        try:
            resolved = sandbox_root.resolve()
            variants.append(str(resolved))
            variants.append(resolved.as_posix())
        except OSError:
            pass
    seen: set[str] = set()
    ordered: list[str] = []
    for v in sorted(variants, key=len, reverse=True):
        if v and v not in seen:
            seen.add(v)
            ordered.append(v)
    masked = text
    for raw_root in ordered:
        masked = masked.replace(raw_root, VIRTUAL_HOME)
    if os.sep != "/":
        masked = masked.replace(VIRTUAL_HOME + "\\", VIRTUAL_HOME + "/")
    return masked


def _is_blocked_command_name(token: str) -> str | None:
    base = token.rsplit("/", 1)[-1]
    if base in BLOCKED_COMMANDS or base.startswith("mkfs."):
        return base
    return None


def _tokenize_segment(segment: str) -> list[str]:
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def _looks_like_sed_or_awk_expr(token: str) -> bool:
    # sed substitution e.g. s/old/new/ or awk regex /ERROR/ (not starting with a system dir)
    if re.match(r"^[sy][^a-zA-Z0-9\s]", token):
        return True
    if token.startswith("/") and token.endswith("/") and len(token) >= 2:
        inner = token[1:-1]
        if "/" not in inner and not any(
            token == prefix or token.startswith(prefix + "/")
            for prefix in SENSITIVE_ROOT_PREFIXES
        ):
            return True
    return False


def _extract_path_candidates(token: str) -> list[str]:
    candidates: list[str] = []
    stripped = token.lstrip("<>")
    if stripped:
        candidates.append(stripped)
    if "=" in stripped:
        _, rhs = stripped.split("=", 1)
        if rhs:
            candidates.append(rhs)
    return candidates


def _check_path_token(
    token: str,
    sandbox_root: Path | PurePosixPath,
    sim_cwd: Path | PurePosixPath,
) -> str | None:
    if _looks_like_sed_or_awk_expr(token):
        return None

    use_posix = _use_posix_paths(sandbox_root)
    for candidate in _extract_path_candidates(token):
        if candidate.startswith("~") and len(candidate) > 1 and candidate[1] != "/":
            return (
                "Sandbox warning: home directory shortcuts for other users "
                f"({candidate!r}) are blocked in the lab sandbox."
            )

        if "$OLDPWD" in candidate or "${OLDPWD}" in candidate:
            return "Sandbox warning: $OLDPWD navigation is disabled in the lab sandbox."

        if _WINDOWS_DRIVE_RE.match(candidate) or candidate.startswith("\\\\"):
            if not _is_within_sandbox(candidate, sandbox_root):
                return (
                    f"Sandbox warning: host path '{candidate}' is outside the sandbox root."
                )

        if candidate.startswith("/"):
            if candidate == VIRTUAL_HOME or candidate.startswith(VIRTUAL_HOME + "/"):
                mapped = _map_virtual_home_to_sandbox(candidate, sandbox_root, use_posix)
                if mapped is None or not _is_within_sandbox(mapped, sandbox_root):
                    return (
                        f"Sandbox warning: path '{candidate}' escapes the lab workspace ({VIRTUAL_HOME}). "
                        "Use relative paths (e.g., '../src') or '~/...'."
                    )
                continue
            for prefix in SENSITIVE_ROOT_PREFIXES:
                if candidate == prefix or candidate.startswith(prefix + "/"):
                    return (
                        f"Sandbox warning: access to host path '{candidate}' is blocked. "
                        f"Work inside {VIRTUAL_HOME} using relative paths (e.g., '../src') or '~/...' instead of a leading '/'."
                    )
            if candidate in {"/", "/*"}:
                return (
                    "Sandbox warning: referencing the host root '/' is blocked. "
                    f"Work inside {VIRTUAL_HOME} using relative paths (e.g., '../src') or '~/...' instead of a leading '/'."
                )
            if not _is_within_sandbox(candidate, sandbox_root):
                return (
                    f"Sandbox warning: absolute path '{candidate}' is outside the lab workspace. "
                    "Use relative paths (e.g., '../src') or '~/...' instead of a leading '/'."
                )

        if ".." in candidate.replace("\\", "/").split("/"):
            resolved = _join_sandbox_path(sim_cwd, candidate, use_posix)
            if not _is_within_sandbox(resolved, sandbox_root):
                return (
                    f"Sandbox warning: path '{candidate}' escapes the sandbox root directory."
                )

    return None


def validate_command(
    command: str,
    sandbox_root: Path | PurePosixPath,
    current_cwd: Path | PurePosixPath,
) -> str | None:
    """Validate a Bash command against sandbox isolation and safety guardrails.

    Returns None if the command is safe to execute, or a friendly warning string if blocked.
    """
    if not isinstance(command, str) or not command.strip():
        return None

    if ":(){" in command.replace(" ", "") or "(){:" in command.replace(" ", ""):
        return "Sandbox warning: fork-bomb patterns are blocked."

    # Allow literal #!/bin/bash and #!/bin/sh shebangs when creating scripts (e.g. Lab 8)
    sanitized = _SHEBANG_RE.sub("#!SHEBANG", command)

    # Also inspect any subshell expressions inside $(...) or backticks
    segments_to_check = _SEGMENT_SPLIT_RE.split(sanitized)
    for match in _SUBSHELL_RE.finditer(sanitized):
        inner = match.group(1) or match.group(2) or ""
        if inner.strip():
            segments_to_check.extend(_SEGMENT_SPLIT_RE.split(inner))

    use_posix = _use_posix_paths(sandbox_root)
    sim_cwd: Path | PurePosixPath | str = current_cwd

    for raw_segment in segments_to_check:
        segment = raw_segment.strip()
        if not segment:
            continue

        tokens = _tokenize_segment(segment)
        if not tokens:
            continue

        # Identify command token(s), skipping leading ENV=val assignments
        idx = 0
        while idx < len(tokens) and "=" in tokens[idx] and not tokens[idx].startswith(("=", "/")):
            idx += 1

        if idx < len(tokens):
            cmd_token = tokens[idx]
            blocked_name = _is_blocked_command_name(cmd_token)
            if blocked_name:
                return (
                    f"Sandbox warning: '{blocked_name}' is disabled in the lab sandbox "
                    "to protect the host system."
                )

            # Check wrapped commands (env, xargs, find -exec, etc.)
            if cmd_token.rsplit("/", 1)[-1] in _WRAPPER_COMMANDS:
                for arg in tokens[idx + 1 :]:
                    if not arg.startswith("-"):
                        wrapped_blocked = _is_blocked_command_name(arg)
                        if wrapped_blocked:
                            return (
                                f"Sandbox warning: '{wrapped_blocked}' is disabled in the lab sandbox."
                            )

        for tok_idx, tok in enumerate(tokens):
            if tok in {"-exec", "-execdir"} and tok_idx + 1 < len(tokens):
                exec_blocked = _is_blocked_command_name(tokens[tok_idx + 1])
                if exec_blocked:
                    return (
                        f"Sandbox warning: '{exec_blocked}' is disabled in the lab sandbox."
                    )

            path_err = _check_path_token(tok, sandbox_root, Path(str(sim_cwd)) if not use_posix else PurePosixPath(str(sim_cwd)))
            if path_err:
                return path_err

        # Simulate cd to track cwd across chained commands (e.g. `cd sub && cd ..`)
        if idx < len(tokens) and tokens[idx] == "cd":
            target = tokens[idx + 1] if idx + 1 < len(tokens) else "~"
            if target == "-":
                return "Sandbox warning: 'cd -' is disabled in the lab sandbox."
            if target == "~" or target == "":
                sim_cwd = sandbox_root
            elif target.startswith("~/"):
                candidate = _join_sandbox_path(sandbox_root, target[2:], use_posix)
                if not _is_within_sandbox(candidate, sandbox_root):
                    return "Sandbox warning: cannot 'cd' above the sandbox root directory."
                sim_cwd = candidate
            elif target.startswith("/"):
                if target == VIRTUAL_HOME or target.startswith(VIRTUAL_HOME + "/"):
                    mapped = _map_virtual_home_to_sandbox(target, sandbox_root, use_posix)
                    if mapped is None or not _is_within_sandbox(mapped, sandbox_root):
                        return "Sandbox warning: cannot 'cd' outside the sandbox root directory."
                    sim_cwd = mapped
                else:
                    candidate = _norm_sandbox_path(target, use_posix) if use_posix else target
                    if not _is_within_sandbox(candidate, sandbox_root):
                        return "Sandbox warning: cannot 'cd' outside the sandbox root directory."
                    sim_cwd = candidate
            else:
                candidate = _join_sandbox_path(sim_cwd, target, use_posix)
                if not _is_within_sandbox(candidate, sandbox_root):
                    return "Sandbox warning: cannot 'cd' above the sandbox root directory."
                sim_cwd = candidate

    return None


# ---------------------------------------------------------------------------
# Built-in Pure-Python Simulated Shell Backend
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _LexToken:
    kind: str  # "word", "op", "redir"
    value: str
    quoted: bool = False


@dataclass
class _Redirect:
    kind: str  # ">", ">>", "2>", "2>>", "<"
    target: str


@dataclass
class _SimpleCommand:
    args: list[str]
    quoted_flags: list[bool]
    redirects: list[_Redirect]


@dataclass
class _Pipeline:
    commands: list[_SimpleCommand]


@dataclass
class _CommandStep:
    connector: str | None  # None, "&&", "||", ";"
    pipeline: _Pipeline


def _lex_shell(command: str) -> list[_LexToken]:
    """Quote-aware POSIX shell tokenizer preserving operator boundaries."""
    tokens: list[_LexToken] = []
    buf: list[str] = []
    has_word = False
    word_quoted = False
    i = 0
    n = len(command)

    def flush_word() -> None:
        nonlocal buf, has_word, word_quoted
        if has_word:
            word = "".join(buf)
            if not word_quoted:
                if word == "~":
                    word = VIRTUAL_HOME
                elif word.startswith("~/"):
                    word = VIRTUAL_HOME + word[1:]
            tokens.append(_LexToken("word", word, quoted=word_quoted))
            buf = []
            has_word = False
            word_quoted = False

    while i < n:
        ch = command[i]

        if ch in {" ", "\t", "\r"}:
            flush_word()
            i += 1
            continue

        if ch == "\n":
            flush_word()
            tokens.append(_LexToken("op", ";"))
            i += 1
            continue

        if ch == "#" and not has_word:
            while i < n and command[i] != "\n":
                i += 1
            continue

        # Operators and redirections
        two = command[i : i + 2]
        three = command[i : i + 3]
        if three == "2>>":
            flush_word()
            tokens.append(_LexToken("redir", "2>>"))
            i += 3
            continue
        if two in {"&&", "||"}:
            flush_word()
            tokens.append(_LexToken("op", two))
            i += 2
            continue
        if two in {">>", "2>", "1>"}:
            flush_word()
            tokens.append(_LexToken("redir", ">" if two == "1>" else two))
            i += 2
            continue
        if ch in {";", "|"}:
            flush_word()
            tokens.append(_LexToken("op", ch))
            i += 1
            continue
        if ch in {">", "<"}:
            flush_word()
            tokens.append(_LexToken("redir", ch))
            i += 1
            continue

        # Word segment (unquoted / single-quoted / double-quoted)
        if ch == "'":
            has_word = True
            word_quoted = True
            i += 1
            while i < n and command[i] != "'":
                buf.append(command[i])
                i += 1
            if i >= n:
                raise ValueError("Unterminated single quote")
            i += 1
            continue

        if ch == '"':
            has_word = True
            word_quoted = True
            i += 1
            while i < n and command[i] != '"':
                if command[i] == "\\" and i + 1 < n and command[i + 1] in {'"', "\\", "$", "`"}:
                    buf.append(command[i + 1])
                    i += 2
                elif command[i : i + 7] == "${HOME}":
                    buf.append(VIRTUAL_HOME)
                    i += 7
                elif command[i : i + 5] == "$HOME" and (
                    i + 5 >= n or not (command[i + 5].isalnum() or command[i + 5] == "_")
                ):
                    buf.append(VIRTUAL_HOME)
                    i += 5
                else:
                    buf.append(command[i])
                    i += 1
            if i >= n:
                raise ValueError("Unterminated double quote")
            i += 1
            continue

        if ch == "\\" and i + 1 < n:
            has_word = True
            word_quoted = True
            buf.append(command[i + 1])
            i += 2
            continue

        if command[i : i + 7] == "${HOME}":
            has_word = True
            buf.append(VIRTUAL_HOME)
            i += 7
            continue

        if command[i : i + 5] == "$HOME" and (
            i + 5 >= n or not (command[i + 5].isalnum() or command[i + 5] == "_")
        ):
            has_word = True
            buf.append(VIRTUAL_HOME)
            i += 5
            continue

        has_word = True
        buf.append(ch)
        i += 1

    flush_word()
    return tokens


def _parse_shell_steps(tokens: list[_LexToken]) -> list[_CommandStep]:
    """Parse tokenized commands into connector-chained pipelines."""
    steps: list[_CommandStep] = []
    connector: str | None = None
    pipeline_cmds: list[_SimpleCommand] = []
    args: list[str] = []
    quoted_flags: list[bool] = []
    redirects: list[_Redirect] = []

    def finish_simple() -> None:
        nonlocal args, quoted_flags, redirects
        if args or redirects:
            pipeline_cmds.append(_SimpleCommand(args=args, quoted_flags=quoted_flags, redirects=redirects))
            args = []
            quoted_flags = []
            redirects = []

    def finish_pipeline() -> None:
        nonlocal pipeline_cmds
        finish_simple()
        if pipeline_cmds:
            steps.append(_CommandStep(connector=connector, pipeline=_Pipeline(pipeline_cmds)))
            pipeline_cmds = []

    idx = 0
    while idx < len(tokens):
        tok = tokens[idx]
        if tok.kind == "op":
            if tok.value == "|":
                finish_simple()
            elif tok.value in {"&&", "||", ";"}:
                finish_pipeline()
                connector = tok.value
        elif tok.kind == "redir":
            if idx + 1 >= len(tokens) or tokens[idx + 1].kind != "word":
                raise ValueError(f"Syntax error near unexpected redirection '{tok.value}'")
            redirects.append(_Redirect(kind=tok.value, target=tokens[idx + 1].value))
            idx += 1
        else:
            args.append(tok.value)
            quoted_flags.append(tok.quoted)
        idx += 1

    finish_pipeline()
    return steps


def _unescape_c_escapes(text: str) -> str:
    out: list[str] = []
    i = 0
    n = len(text)
    escapes = {
        "n": "\n",
        "t": "\t",
        "r": "\r",
        "\\": "\\",
        '"': '"',
        "'": "'",
        "a": "\a",
        "b": "\b",
        "f": "\f",
        "v": "\v",
        "0": "\0",
    }
    while i < n:
        if text[i] == "\\" and i + 1 < n:
            nxt = text[i + 1]
            if nxt in escapes:
                out.append(escapes[nxt])
                i += 2
                continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _format_mode_string(mode: int, is_dir: bool, is_link: bool) -> str:
    kind = "l" if is_link else ("d" if is_dir else "-")
    bits = [
        stat.S_IRUSR,
        stat.S_IWUSR,
        stat.S_IXUSR,
        stat.S_IRGRP,
        stat.S_IWGRP,
        stat.S_IXGRP,
        stat.S_IROTH,
        stat.S_IWOTH,
        stat.S_IXOTH,
    ]
    chars = ["r", "w", "x"] * 3
    perms = "".join(c if (mode & b) else "-" for b, c in zip(bits, chars))
    return kind + perms


def _apply_chmod_spec(current_mode: int, spec: str) -> int:
    """Apply an octal (e.g. 600, 0750) or symbolic (e.g. u+x, o-w, u=rw,go=) mode."""
    stripped = spec.strip()
    if re.fullmatch(r"[0-7]{3,4}", stripped):
        return int(stripped, 8) & 0o7777

    mode = current_mode & 0o7777
    who_shifts = {"u": 6, "g": 3, "o": 0}
    perm_bits = {"r": 4, "w": 2, "x": 1}

    for clause in stripped.split(","):
        m = re.fullmatch(r"([ugoa]*)([+\-=][rwx]*)+", clause)
        if not m:
            raise ValueError(f"chmod: invalid mode: '{spec}'")
        who_part = m.group(1) or "a"
        targets = ("u", "g", "o") if "a" in who_part else tuple(dict.fromkeys(who_part))

        ops_part = clause[len(m.group(1)) :]
        for op_match in re.finditer(r"([+\-=])([rwx]*)", ops_part):
            op = op_match.group(1)
            perms = op_match.group(2)
            val = 0
            for p in perms:
                val |= perm_bits[p]
            for who in targets:
                shift = who_shifts[who]
                if op == "+":
                    mode |= val << shift
                elif op == "-":
                    mode &= ~(val << shift)
                elif op == "=":
                    mode = (mode & ~(0o7 << shift)) | (val << shift)
    return mode & 0o7777


def _split_sed_script(script: str) -> list[str]:
    """Split a sed script on unquoted/unescaped ';' outside s<delim>...<delim>...<delim>."""
    commands: list[str] = []
    i = 0
    n = len(script)
    while i < n:
        while i < n and script[i] in {" ", "\t", ";", "\n"}:
            i += 1
        if i >= n:
            break
        if script[i] == "s" and i + 1 < n and not script[i + 1].isalnum():
            delim = script[i + 1]
            start = i
            i += 2
            delim_count = 0
            while i < n and delim_count < 2:
                if script[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if script[i] == delim:
                    delim_count += 1
                i += 1
            while i < n and script[i].isalpha():
                i += 1
            commands.append(script[start:i])
        else:
            start = i
            while i < n and script[i] != ";":
                i += 1
            commands.append(script[start:i].strip())
    return [c for c in commands if c]


def _parse_sed_subst(expr: str) -> tuple[str, str, str]:
    if not expr.startswith("s") or len(expr) < 4:
        raise ValueError(f"sed: unsupported command {expr!r}")
    delim = expr[1]
    parts: list[str] = []
    buf: list[str] = []
    i = 2
    n = len(expr)
    while i < n and len(parts) < 2:
        ch = expr[i]
        if ch == "\\" and i + 1 < n:
            nxt = expr[i + 1]
            if nxt == delim:
                buf.append(delim)
            else:
                buf.append("\\" + nxt)
            i += 2
            continue
        if ch == delim:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    if len(parts) != 2:
        raise ValueError(f"sed: unterminated `s' command: {expr!r}")
    flags = expr[i:]
    return parts[0], parts[1], flags


def _parse_cut_fields(spec: str) -> list[tuple[int, int | None]]:
    ranges: list[tuple[int, int | None]] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo_s, hi_s = part.split("-", 1)
            lo = int(lo_s) if lo_s else 1
            hi = int(hi_s) if hi_s else None
            ranges.append((max(1, lo), hi))
        else:
            idx = int(part)
            ranges.append((idx, idx))
    return ranges


class SimulatedShell:
    """Pure-Python POSIX-like shell engine for cross-platform sandbox lab execution."""

    def __init__(self, root: Path, vfs: VirtualFSState, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.root = Path(root).resolve()
        self.vfs = vfs
        self.timeout = float(timeout)

    def _resolve_user_path(
        self,
        raw: str,
        cwd: Path,
        *,
        follow_final: bool = True,
    ) -> Path:
        cleaned = raw.strip()
        if cleaned in {"~", VIRTUAL_HOME}:
            return self.root
        if cleaned.startswith("~/"):
            candidate = Path(os.path.normpath(str(self.root / cleaned[2:])))
        elif cleaned.startswith(VIRTUAL_HOME + "/"):
            rel = cleaned[len(VIRTUAL_HOME) + 1 :]
            candidate = Path(os.path.normpath(str(self.root / rel)))
        elif cleaned.startswith("/"):
            candidate = Path(posixpath.normpath(cleaned))
        else:
            candidate = Path(os.path.normpath(str(cwd / cleaned)))

        if not _is_within_sandbox(candidate, self.root):
            raise PermissionError(f"Path '{raw}' escapes sandbox root")
        resolved = self.vfs.resolve_path(candidate, follow_final=follow_final)
        if not _is_within_sandbox(resolved, self.root):
            raise PermissionError(f"Path '{raw}' escapes sandbox root")
        return resolved

    def _expand_glob(self, word: str, cwd: Path) -> list[str]:
        if not any(ch in word for ch in "*?["):
            return [word]
        if word.startswith("~/") or word.startswith(VIRTUAL_HOME + "/"):
            prefix = "~/" if word.startswith("~/") else VIRTUAL_HOME + "/"
            sub = word[len(prefix) :]
            pattern = str(self.root / sub)
            matches = sorted(pyglob.glob(pattern))
            rel_matches = []
            for m in matches:
                mp = Path(m)
                if _is_within_sandbox(mp, self.root):
                    rel_matches.append(prefix + mp.relative_to(self.root).as_posix())
            return rel_matches or [word]
        if word.startswith("/"):
            return [word]
        base_cwd = cwd
        matches = sorted(pyglob.glob(str(base_cwd / word)))
        rels: list[str] = []
        for m in matches:
            mp = Path(m)
            if _is_within_sandbox(mp, self.root):
                rels.append(mp.relative_to(base_cwd).as_posix())
        return rels or [word]

    def _effective_mode(self, path: Path) -> int:
        mode = self.vfs.get_mode(path)
        if mode is not None:
            return mode
        return 0o755 if path.is_dir() else 0o644

    def _set_effective_mode(self, path: Path, mode: int) -> None:
        self.vfs.set_mode(path, mode)
        try:
            os.chmod(path, mode)
        except OSError:
            pass

    def _read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="replace")

    def _write_text(self, path: Path, content: str, *, append: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        existed = path.exists()
        if append:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(content)
        else:
            path.write_text(content, encoding="utf-8")
        if not existed:
            self._set_effective_mode(path, 0o644)

    def run_script_file(self, script_path: Path) -> tuple[int, str, str]:
        """Execute a simple #!/bin/bash script file inside the simulated workspace."""
        try:
            target = self.vfs.resolve_path(script_path, follow_final=True)
        except OSError as exc:
            return 126, "", str(exc) + "\n"
        if not target.is_file():
            return 127, "", f"{script_path.name}: No such file or directory\n"
        mode = self._effective_mode(target)
        if not (mode & stat.S_IXUSR):
            return 126, "", f"bash: {script_path}: Permission denied\n"

        lines = self._read_text(target).splitlines()
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        last_rc = 0
        cur_cwd = self.root
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            out, err, rc, cur_cwd, timed_out = self.run(stripped, cur_cwd)
            if out:
                stdout_parts.append(out)
            if err:
                stderr_parts.append(err)
            last_rc = rc
            if timed_out:
                return 124, "".join(stdout_parts), "".join(stderr_parts)
        return last_rc, "".join(stdout_parts), "".join(stderr_parts)

    def run(self, command: str, cwd: Path) -> tuple[str, str, int, Path, bool]:
        """Run a full command string and return (stdout, stderr, returncode, new_cwd, timed_out)."""
        try:
            tokens = _lex_shell(command)
            steps = _parse_shell_steps(tokens)
        except ValueError as exc:
            return "", f"bash: syntax error: {exc}\n", 2, cwd, False

        if not steps:
            return "", "", 0, cwd, False

        deadline = time.monotonic() + self.timeout
        cur_cwd = cwd
        stdout_acc: list[str] = []
        stderr_acc: list[str] = []
        last_rc = 0

        for step in steps:
            if step.connector == "&&" and last_rc != 0:
                continue
            if step.connector == "||" and last_rc == 0:
                continue

            out, err, rc, cur_cwd, timed_out = self._run_pipeline(
                step.pipeline, cur_cwd, deadline
            )
            if out:
                stdout_acc.append(out)
            if err:
                stderr_acc.append(err)
            last_rc = rc
            if timed_out:
                return (
                    "",
                    f"Sandbox warning: command timed out after {int(self.timeout)} seconds.",
                    124,
                    cur_cwd,
                    True,
                )

        return "".join(stdout_acc), "".join(stderr_acc), last_rc, cur_cwd, False

    def _run_pipeline(
        self, pipeline: _Pipeline, cwd: Path, deadline: float
    ) -> tuple[str, str, int, Path, bool]:
        stdin_data = ""
        err_acc: list[str] = []
        cur_cwd = cwd
        last_rc = 0
        is_pipe = len(pipeline.commands) > 1

        for idx, cmd in enumerate(pipeline.commands):
            expanded_args: list[str] = []
            for arg, was_quoted in zip(cmd.args, cmd.quoted_flags):
                if was_quoted:
                    expanded_args.append(arg)
                else:
                    expanded_args.extend(self._expand_glob(arg, cur_cwd))

            cmd_stdin = stdin_data
            for redir in cmd.redirects:
                if redir.kind == "<":
                    try:
                        in_path = self._resolve_user_path(redir.target, cur_cwd)
                        cmd_stdin = self._read_text(in_path)
                    except OSError as exc:
                        return "", f"bash: {redir.target}: {exc}\n", 1, cur_cwd, False

            out, err, rc, next_cwd, timed_out = self._exec_simple(
                expanded_args, cmd_stdin, cur_cwd, deadline
            )
            if not is_pipe:
                cur_cwd = next_cwd
            if timed_out:
                return "", err, 124, cur_cwd, True

            stderr_written = False
            stdout_written = False
            for redir in cmd.redirects:
                if redir.kind in {">", ">>"}:
                    try:
                        out_path = self._resolve_user_path(
                            redir.target, cur_cwd, follow_final=False
                        )
                        if out_path.is_dir():
                            return "", f"bash: {redir.target}: Is a directory\n", 1, cur_cwd, False
                        self._write_text(out_path, out, append=(redir.kind == ">>"))
                        stdout_written = True
                    except OSError as exc:
                        return "", f"bash: {redir.target}: {exc}\n", 1, cur_cwd, False
                elif redir.kind in {"2>", "2>>"}:
                    try:
                        err_path = self._resolve_user_path(
                            redir.target, cur_cwd, follow_final=False
                        )
                        self._write_text(err_path, err, append=(redir.kind == "2>>"))
                        stderr_written = True
                    except OSError as exc:
                        return "", f"bash: {redir.target}: {exc}\n", 1, cur_cwd, False

            if err and not stderr_written:
                err_acc.append(err)

            stdin_data = "" if stdout_written else out
            last_rc = rc
            if idx == len(pipeline.commands) - 1:
                return stdin_data, "".join(err_acc), last_rc, cur_cwd, False

        return "", "".join(err_acc), last_rc, cur_cwd, False

    def _exec_simple(
        self,
        args: list[str],
        stdin_data: str,
        cwd: Path,
        deadline: float,
    ) -> tuple[str, str, int, Path, bool]:
        if not args:
            return "", "", 0, cwd, False

        cmd_name = args[0]
        rest = args[1:]

        if cmd_name in {"true", ":"}:
            return "", "", 0, cwd, False
        if cmd_name == "false":
            return "", "", 1, cwd, False

        if cmd_name == "pwd":
            rel = "" if cwd == self.root else "/" + cwd.relative_to(self.root).as_posix()
            return f"{VIRTUAL_HOME}{rel}\n", "", 0, cwd, False

        if cmd_name == "whoami":
            return "lab\n", "", 0, cwd, False

        if cmd_name == "hostname":
            return "sandbox\n", "", 0, cwd, False

        if cmd_name == "sleep":
            return self._cmd_sleep(rest, cwd, deadline)

        if cmd_name == "cd":
            return self._cmd_cd(rest, cwd)

        if cmd_name == "ls":
            return self._cmd_ls(rest, cwd)

        if cmd_name == "mkdir":
            return self._cmd_mkdir(rest, cwd)

        if cmd_name == "touch":
            return self._cmd_touch(rest, cwd)

        if cmd_name == "cp":
            return self._cmd_cp(rest, cwd)

        if cmd_name == "mv":
            return self._cmd_mv(rest, cwd)

        if cmd_name == "rm":
            return self._cmd_rm(rest, cwd)

        if cmd_name == "cat":
            return self._cmd_cat(rest, stdin_data, cwd)

        if cmd_name == "echo":
            return self._cmd_echo(rest, cwd)

        if cmd_name == "printf":
            return self._cmd_printf(rest, cwd)

        if cmd_name == "grep":
            return self._cmd_grep(rest, stdin_data, cwd)

        if cmd_name == "sort":
            return self._cmd_sort(rest, stdin_data, cwd)

        if cmd_name == "uniq":
            return self._cmd_uniq(rest, stdin_data, cwd)

        if cmd_name == "cut":
            return self._cmd_cut(rest, stdin_data, cwd)

        if cmd_name == "awk":
            return self._cmd_awk(rest, stdin_data, cwd)

        if cmd_name == "sed":
            return self._cmd_sed(rest, stdin_data, cwd)

        if cmd_name == "find":
            return self._cmd_find(rest, cwd)

        if cmd_name == "chmod":
            return self._cmd_chmod(rest, cwd)

        if cmd_name == "ln":
            return self._cmd_ln(rest, cwd)

        if cmd_name == "tar":
            return self._cmd_tar(rest, cwd)

        if cmd_name == "head":
            return self._cmd_head_tail(rest, stdin_data, cwd, is_head=True)

        if cmd_name == "tail":
            return self._cmd_head_tail(rest, stdin_data, cwd, is_head=False)

        if cmd_name == "wc":
            return self._cmd_wc(rest, stdin_data, cwd)

        if cmd_name == "readlink":
            return self._cmd_readlink(rest, cwd)

        if cmd_name in {"bash", "sh"}:
            if not rest:
                return "", "bash: interactive nested shell is not supported\n", 1, cwd, False
            try:
                script_p = self._resolve_user_path(rest[0], cwd)
            except (OSError, PermissionError) as exc:
                return "", f"{cmd_name}: {rest[0]}: {exc}\n", 127, cwd, False
            if not script_p.is_file():
                return "", f"{cmd_name}: {rest[0]}: No such file or directory\n", 127, cwd, False
            # bash <script> does not require execute bit
            lines = self._read_text(script_p).splitlines()
            out_all: list[str] = []
            err_all: list[str] = []
            last_rc = 0
            sub_cwd = cwd
            for line in lines:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                o, e, last_rc, sub_cwd, timed_out = self.run(s, sub_cwd)
                if o:
                    out_all.append(o)
                if e:
                    err_all.append(e)
                if timed_out:
                    return "", "", 124, cwd, True
            return "".join(out_all), "".join(err_all), last_rc, cwd, False

        # Direct script execution: ./scripts/healthcheck.sh or path/to/script.sh
        if "/" in cmd_name or cmd_name.startswith("."):
            try:
                script_p = self._resolve_user_path(cmd_name, cwd)
            except (OSError, PermissionError) as exc:
                return "", f"bash: {cmd_name}: {exc}\n", 126, cwd, False
            rc, out, err = self.run_script_file(script_p)
            return out, err, rc, cwd, False

        return "", f"bash: {cmd_name}: command not found\n", 127, cwd, False

    def _cmd_sleep(
        self, args: list[str], cwd: Path, deadline: float
    ) -> tuple[str, str, int, Path, bool]:
        if not args:
            return "", "sleep: missing operand\n", 1, cwd, False
        try:
            duration = float(args[0].rstrip("s"))
        except ValueError:
            return "", f"sleep: invalid time interval '{args[0]}'\n", 1, cwd, False
        remaining = deadline - time.monotonic()
        if duration > remaining:
            if remaining > 0:
                time.sleep(min(remaining, 0.2))
            return "", "timed out", 124, cwd, True
        time.sleep(max(0.0, duration))
        return "", "", 0, cwd, False

    def _cmd_cd(self, args: list[str], cwd: Path) -> tuple[str, str, int, Path, bool]:
        target = args[0] if args else "~"
        try:
            resolved = self._resolve_user_path(target, cwd)
        except PermissionError as exc:
            return "", f"bash: cd: {exc}\n", 1, cwd, False
        if not resolved.exists():
            return "", f"bash: cd: {target}: No such file or directory\n", 1, cwd, False
        if not resolved.is_dir():
            return "", f"bash: cd: {target}: Not a directory\n", 1, cwd, False
        return "", "", 0, resolved, False

    def _cmd_ls(self, args: list[str], cwd: Path) -> tuple[str, str, int, Path, bool]:
        show_all = False
        long_fmt = False
        targets: list[str] = []
        for arg in args:
            if arg.startswith("-") and len(arg) > 1:
                for ch in arg[1:]:
                    if ch in {"a", "A"}:
                        show_all = True
                    elif ch == "l":
                        long_fmt = True
                    elif ch in {"1", "h", "F"}:
                        pass
            else:
                targets.append(arg)
        if not targets:
            targets = ["."]

        out_lines: list[str] = []
        err_lines: list[str] = []
        rc = 0
        multi = len(targets) > 1
        for raw_t in targets:
            try:
                p = self._resolve_user_path(raw_t, cwd, follow_final=False)
                is_link = self.vfs.is_symlink(p)
                resolved = self.vfs.resolve_path(p, follow_final=True) if not is_link else p
            except (OSError, PermissionError) as exc:
                err_lines.append(f"ls: cannot access '{raw_t}': {exc}\n")
                rc = 2
                continue

            if not p.exists() and not is_link:
                err_lines.append(f"ls: cannot access '{raw_t}': No such file or directory\n")
                rc = 2
                continue

            if p.is_dir() and not is_link:
                if multi:
                    out_lines.append(f"{raw_t}:")
                entries = sorted(p.iterdir(), key=lambda x: x.name)
                if not show_all:
                    entries = [e for e in entries if not e.name.startswith(".")]
                for entry in entries:
                    out_lines.append(self._format_ls_entry(entry, long_fmt))
            else:
                out_lines.append(self._format_ls_entry(resolved if not is_link else p, long_fmt, display_name=raw_t))

        out = ("\n".join(out_lines) + "\n") if out_lines else ""
        return out, "".join(err_lines), rc, cwd, False

    def _format_ls_entry(
        self, entry: Path, long_fmt: bool, display_name: str | None = None
    ) -> str:
        name = display_name or entry.name
        is_link = self.vfs.is_symlink(entry)
        if not long_fmt:
            return name
        if is_link:
            target = self.vfs.readlink(entry) or "?"
            return f"lrwxrwxrwx 1 lab lab 0 {name} -> {target}"
        mode = self._effective_mode(entry)
        is_dir = entry.is_dir()
        size = 4096 if is_dir else entry.stat().st_size
        perm_str = _format_mode_string(mode, is_dir=is_dir, is_link=False)
        return f"{perm_str} 1 lab lab {size:6d} {name}"

    def _cmd_mkdir(self, args: list[str], cwd: Path) -> tuple[str, str, int, Path, bool]:
        parents = False
        targets: list[str] = []
        for arg in args:
            if arg.startswith("-") and len(arg) > 1:
                if "p" in arg[1:]:
                    parents = True
            else:
                targets.append(arg)
        if not targets:
            return "", "mkdir: missing operand\n", 1, cwd, False

        err_lines: list[str] = []
        rc = 0
        for raw in targets:
            try:
                target = self._resolve_user_path(raw, cwd, follow_final=False)
                if target.exists():
                    if not parents:
                        err_lines.append(f"mkdir: cannot create directory '{raw}': File exists\n")
                        rc = 1
                    continue
                if not parents and not target.parent.exists():
                    err_lines.append(
                        f"mkdir: cannot create directory '{raw}': No such file or directory\n"
                    )
                    rc = 1
                    continue
                target.mkdir(parents=parents, exist_ok=True)
                self._set_effective_mode(target, 0o755)
            except (OSError, PermissionError) as exc:
                err_lines.append(f"mkdir: cannot create directory '{raw}': {exc}\n")
                rc = 1
        return "", "".join(err_lines), rc, cwd, False

    def _cmd_touch(self, args: list[str], cwd: Path) -> tuple[str, str, int, Path, bool]:
        targets = [a for a in args if not a.startswith("-")]
        if not targets:
            return "", "touch: missing file operand\n", 1, cwd, False
        err_lines: list[str] = []
        rc = 0
        for raw in targets:
            try:
                target = self._resolve_user_path(raw, cwd, follow_final=True)
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.touch()
                    self._set_effective_mode(target, 0o644)
                else:
                    os.utime(target, None)
            except (OSError, PermissionError) as exc:
                err_lines.append(f"touch: cannot touch '{raw}': {exc}\n")
                rc = 1
        return "", "".join(err_lines), rc, cwd, False

    def _copy_recursive(self, src: Path, dst: Path) -> None:
        if self.vfs.is_symlink(src):
            link_target = self.vfs.readlink(src) or ""
            try:
                dst.symlink_to(link_target)
            except OSError:
                pass
            self.vfs.set_symlink(dst, link_target)
            return
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
            self._set_effective_mode(dst, self._effective_mode(src))
            for child in src.iterdir():
                self._copy_recursive(child, dst / child.name)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            self._set_effective_mode(dst, self._effective_mode(src))

    def _cmd_cp(self, args: list[str], cwd: Path) -> tuple[str, str, int, Path, bool]:
        recursive = False
        operands: list[str] = []
        for arg in args:
            if arg.startswith("-") and len(arg) > 1:
                if any(ch in arg[1:] for ch in {"r", "R", "a"}):
                    recursive = True
            else:
                operands.append(arg)
        if len(operands) < 2:
            return "", "cp: missing file operand\n", 1, cwd, False

        dst_raw = operands[-1]
        srcs_raw = operands[:-1]
        try:
            dst = self._resolve_user_path(dst_raw, cwd, follow_final=True)
        except (OSError, PermissionError) as exc:
            return "", f"cp: {exc}\n", 1, cwd, False

        dst_is_dir = dst.is_dir() or dst_raw.endswith("/")
        if len(srcs_raw) > 1 and not dst.is_dir():
            return "", f"cp: target '{dst_raw}' is not a directory\n", 1, cwd, False

        err_lines: list[str] = []
        rc = 0
        for src_raw in srcs_raw:
            try:
                src = self._resolve_user_path(src_raw, cwd, follow_final=True)
                if not src.exists():
                    err_lines.append(f"cp: cannot stat '{src_raw}': No such file or directory\n")
                    rc = 1
                    continue
                if src.is_dir() and not recursive:
                    err_lines.append(f"cp: -r not specified; omitting directory '{src_raw}'\n")
                    rc = 1
                    continue
                target_dst = (dst / src.name) if dst_is_dir else dst
                self._copy_recursive(src, target_dst)
            except (OSError, PermissionError) as exc:
                err_lines.append(f"cp: '{src_raw}': {exc}\n")
                rc = 1
        return "", "".join(err_lines), rc, cwd, False

    def _cmd_mv(self, args: list[str], cwd: Path) -> tuple[str, str, int, Path, bool]:
        operands = [a for a in args if not a.startswith("-")]
        if len(operands) < 2:
            return "", "mv: missing file operand\n", 1, cwd, False

        dst_raw = operands[-1]
        srcs_raw = operands[:-1]
        try:
            dst = self._resolve_user_path(dst_raw, cwd, follow_final=True)
        except (OSError, PermissionError) as exc:
            return "", f"mv: {exc}\n", 1, cwd, False

        dst_is_dir = dst.is_dir() or dst_raw.endswith("/")
        if len(srcs_raw) > 1 and not dst.is_dir():
            return "", f"mv: target '{dst_raw}' is not a directory\n", 1, cwd, False

        err_lines: list[str] = []
        rc = 0
        for src_raw in srcs_raw:
            try:
                src = self._resolve_user_path(src_raw, cwd, follow_final=False)
                if not src.exists() and not self.vfs.is_symlink(src):
                    err_lines.append(f"mv: cannot stat '{src_raw}': No such file or directory\n")
                    rc = 1
                    continue
                target_dst = (dst / src.name) if dst_is_dir else dst
                target_dst.parent.mkdir(parents=True, exist_ok=True)
                if self.vfs.is_symlink(src) and not src.is_symlink():
                    link_target = self.vfs.readlink(src) or ""
                    self.vfs.remove_entry(src)
                    self.vfs.set_symlink(target_dst, link_target)
                else:
                    shutil.move(str(src), str(target_dst))
                    self.vfs.move_entry(src, target_dst)
            except (OSError, PermissionError) as exc:
                err_lines.append(f"mv: '{src_raw}': {exc}\n")
                rc = 1
        return "", "".join(err_lines), rc, cwd, False

    def _cmd_rm(self, args: list[str], cwd: Path) -> tuple[str, str, int, Path, bool]:
        recursive = False
        force = False
        targets: list[str] = []
        for arg in args:
            if arg.startswith("-") and len(arg) > 1:
                for ch in arg[1:]:
                    if ch in {"r", "R"}:
                        recursive = True
                    elif ch == "f":
                        force = True
            else:
                targets.append(arg)
        if not targets:
            return ("", "", 0, cwd, False) if force else ("", "rm: missing operand\n", 1, cwd, False)

        err_lines: list[str] = []
        rc = 0
        for raw in targets:
            try:
                target = self._resolve_user_path(raw, cwd, follow_final=False)
            except (OSError, PermissionError) as exc:
                if not force:
                    err_lines.append(f"rm: cannot remove '{raw}': {exc}\n")
                    rc = 1
                continue

            if target == self.root:
                err_lines.append("rm: refusing to remove sandbox root\n")
                rc = 1
                continue

            is_vlink = self.vfs.is_symlink(target)
            if not target.exists() and not target.is_symlink() and not is_vlink:
                if not force:
                    err_lines.append(f"rm: cannot remove '{raw}': No such file or directory\n")
                    rc = 1
                continue

            try:
                if target.is_dir() and not target.is_symlink() and not is_vlink:
                    if not recursive:
                        err_lines.append(f"rm: cannot remove '{raw}': Is a directory\n")
                        rc = 1
                        continue
                    shutil.rmtree(target)
                elif target.exists() or target.is_symlink():
                    target.unlink()
                self.vfs.remove_entry(target)
            except OSError as exc:
                if not force:
                    err_lines.append(f"rm: cannot remove '{raw}': {exc}\n")
                    rc = 1
        return "", "".join(err_lines), rc, cwd, False

    def _cmd_cat(
        self, args: list[str], stdin_data: str, cwd: Path
    ) -> tuple[str, str, int, Path, bool]:
        files = [a for a in args if a != "-" and not a.startswith("-")]
        if not files:
            return stdin_data, "", 0, cwd, False
        out_parts: list[str] = []
        err_parts: list[str] = []
        rc = 0
        for raw in files:
            try:
                p = self._resolve_user_path(raw, cwd)
                if not p.exists():
                    err_parts.append(f"cat: {raw}: No such file or directory\n")
                    rc = 1
                elif p.is_dir():
                    err_parts.append(f"cat: {raw}: Is a directory\n")
                    rc = 1
                else:
                    out_parts.append(self._read_text(p))
            except (OSError, PermissionError) as exc:
                err_parts.append(f"cat: {raw}: {exc}\n")
                rc = 1
        return "".join(out_parts), "".join(err_parts), rc, cwd, False

    def _cmd_echo(self, args: list[str], cwd: Path) -> tuple[str, str, int, Path, bool]:
        newline = True
        interpret = False
        idx = 0
        while idx < len(args) and args[idx].startswith("-") and len(args[idx]) > 1:
            flags = args[idx][1:]
            if all(c in {"n", "e", "E"} for c in flags):
                if "n" in flags:
                    newline = False
                if "e" in flags:
                    interpret = True
                if "E" in flags:
                    interpret = False
                idx += 1
            else:
                break
        text = " ".join(args[idx:])
        if interpret:
            text = _unescape_c_escapes(text)
        if newline:
            text += "\n"
        return text, "", 0, cwd, False

    def _cmd_printf(self, args: list[str], cwd: Path) -> tuple[str, str, int, Path, bool]:
        if not args:
            return "", "printf: usage: printf format [arguments]\n", 1, cwd, False
        fmt = _unescape_c_escapes(args[0])
        values = list(args[1:])
        if not values:
            return fmt, "", 0, cwd, False

        out_parts: list[str] = []
        pos = 0
        # Consume values repeatedly if format specifiers exist
        has_spec = bool(re.search(r"%[sd%]", fmt))
        if not has_spec:
            return fmt, "", 0, cwd, False

        while True:
            rendered = []
            i = 0
            consumed = False
            while i < len(fmt):
                if fmt[i] == "%" and i + 1 < len(fmt):
                    spec = fmt[i + 1]
                    if spec == "%":
                        rendered.append("%")
                        i += 2
                        continue
                    if spec == "s":
                        val = values[pos] if pos < len(values) else ""
                        if pos < len(values):
                            pos += 1
                            consumed = True
                        rendered.append(val)
                        i += 2
                        continue
                    if spec == "d":
                        val_s = values[pos] if pos < len(values) else "0"
                        if pos < len(values):
                            pos += 1
                            consumed = True
                        try:
                            rendered.append(str(int(val_s)))
                        except ValueError:
                            rendered.append("0")
                        i += 2
                        continue
                rendered.append(fmt[i])
                i += 1
            out_parts.append("".join(rendered))
            if not consumed or pos >= len(values):
                break
        return "".join(out_parts), "", 0, cwd, False

    def _cmd_grep(
        self, args: list[str], stdin_data: str, cwd: Path
    ) -> tuple[str, str, int, Path, bool]:
        ignore_case = False
        invert = False
        line_numbers = False
        count_only = False
        files_with_matches = False
        recursive = False
        pattern: str | None = None
        targets: list[str] = []

        i = 0
        while i < len(args):
            arg = args[i]
            if arg in {"-e", "--regexp"} and i + 1 < len(args):
                pattern = args[i + 1]
                i += 2
                continue
            if arg.startswith("-") and len(arg) > 1:
                for ch in arg[1:]:
                    if ch == "i":
                        ignore_case = True
                    elif ch == "v":
                        invert = True
                    elif ch == "n":
                        line_numbers = True
                    elif ch == "c":
                        count_only = True
                    elif ch == "l":
                        files_with_matches = True
                    elif ch in {"r", "R"}:
                        recursive = True
                    elif ch in {"E", "F", "q"}:
                        pass
                i += 1
                continue
            if pattern is None:
                pattern = arg
            else:
                targets.append(arg)
            i += 1

        if pattern is None:
            return "", "grep: missing pattern\n", 2, cwd, False

        flags = re.IGNORECASE if ignore_case else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error:
            regex = re.compile(re.escape(pattern), flags)

        inputs: list[tuple[str | None, str]] = []
        err_lines: list[str] = []
        if not targets:
            inputs.append((None, stdin_data))
        else:
            file_paths: list[tuple[str, Path]] = []
            for raw in targets:
                try:
                    p = self._resolve_user_path(raw, cwd)
                except (OSError, PermissionError) as exc:
                    err_lines.append(f"grep: {raw}: {exc}\n")
                    continue
                if not p.exists():
                    err_lines.append(f"grep: {raw}: No such file or directory\n")
                    continue
                if p.is_dir():
                    if recursive:
                        for sub in sorted(p.rglob("*")):
                            if sub.is_file():
                                file_paths.append((sub.relative_to(cwd).as_posix(), sub))
                    else:
                        err_lines.append(f"grep: {raw}: Is a directory\n")
                else:
                    file_paths.append((raw, p))
            show_prefix = len(file_paths) > 1 or recursive
            for label, fp in file_paths:
                inputs.append((label if show_prefix else None, self._read_text(fp)))

        out_lines: list[str] = []
        any_match = False
        for label, content in inputs:
            matched_count = 0
            for lineno, line in enumerate(content.splitlines(), start=1):
                hit = bool(regex.search(line))
                if invert:
                    hit = not hit
                if hit:
                    any_match = True
                    matched_count += 1
                    if not count_only and not files_with_matches:
                        prefix = ""
                        if label is not None:
                            prefix += f"{label}:"
                        if line_numbers:
                            prefix += f"{lineno}:"
                        out_lines.append(f"{prefix}{line}")
            if files_with_matches and matched_count > 0 and label is not None:
                out_lines.append(label)
            elif count_only:
                out_lines.append(f"{label}:{matched_count}" if label else str(matched_count))

        out = ("\n".join(out_lines) + "\n") if out_lines else ""
        rc = 2 if err_lines and not any_match else (0 if any_match else 1)
        return out, "".join(err_lines), rc, cwd, False

    def _read_lines_or_stdin(
        self, files: list[str], stdin_data: str, cwd: Path, cmd_name: str
    ) -> tuple[list[str] | None, str]:
        if not files:
            return stdin_data.splitlines(), ""
        all_lines: list[str] = []
        for raw in files:
            try:
                p = self._resolve_user_path(raw, cwd)
                if not p.is_file():
                    return None, f"{cmd_name}: {raw}: No such file or directory\n"
                all_lines.extend(self._read_text(p).splitlines())
            except (OSError, PermissionError) as exc:
                return None, f"{cmd_name}: {raw}: {exc}\n"
        return all_lines, ""

    def _cmd_sort(
        self, args: list[str], stdin_data: str, cwd: Path
    ) -> tuple[str, str, int, Path, bool]:
        unique = False
        reverse = False
        numeric = False
        ignore_case = False
        files: list[str] = []
        for arg in args:
            if arg.startswith("-") and len(arg) > 1:
                for ch in arg[1:]:
                    if ch == "u":
                        unique = True
                    elif ch == "r":
                        reverse = True
                    elif ch == "n":
                        numeric = True
                    elif ch == "f":
                        ignore_case = True
            else:
                files.append(arg)

        lines, err = self._read_lines_or_stdin(files, stdin_data, cwd, "sort")
        if lines is None:
            return "", err, 2, cwd, False

        def key_fn(line: str) -> tuple[object, str]:
            if numeric:
                m = re.match(r"\s*([+-]?\d+(?:\.\d+)?)", line)
                num = float(m.group(1)) if m else 0.0
                return (num, line)
            return (line.lower() if ignore_case else line, line)

        sorted_lines = sorted(lines, key=key_fn, reverse=reverse)
        if unique:
            deduped: list[str] = []
            seen: set[object] = set()
            for ln in sorted_lines:
                k = ln.lower() if ignore_case else ln
                if k not in seen:
                    seen.add(k)
                    deduped.append(ln)
            sorted_lines = deduped
        out = ("\n".join(sorted_lines) + "\n") if sorted_lines else ""
        return out, "", 0, cwd, False

    def _cmd_uniq(
        self, args: list[str], stdin_data: str, cwd: Path
    ) -> tuple[str, str, int, Path, bool]:
        count = False
        dup_only = False
        uniq_only = False
        ignore_case = False
        files: list[str] = []
        for arg in args:
            if arg.startswith("-") and len(arg) > 1:
                for ch in arg[1:]:
                    if ch == "c":
                        count = True
                    elif ch == "d":
                        dup_only = True
                    elif ch == "u":
                        uniq_only = True
                    elif ch == "i":
                        ignore_case = True
            else:
                files.append(arg)

        lines, err = self._read_lines_or_stdin(files, stdin_data, cwd, "uniq")
        if lines is None:
            return "", err, 1, cwd, False
        if not lines:
            return "", "", 0, cwd, False

        groups: list[tuple[str, int]] = []
        for ln in lines:
            k = ln.lower() if ignore_case else ln
            if groups and (groups[-1][0].lower() if ignore_case else groups[-1][0]) == k:
                groups[-1] = (groups[-1][0], groups[-1][1] + 1)
            else:
                groups.append((ln, 1))

        out_lines: list[str] = []
        for ln, cnt in groups:
            if dup_only and cnt < 2:
                continue
            if uniq_only and cnt > 1:
                continue
            out_lines.append(f"{cnt:7d} {ln}" if count else ln)
        out = ("\n".join(out_lines) + "\n") if out_lines else ""
        return out, "", 0, cwd, False

    def _cmd_cut(
        self, args: list[str], stdin_data: str, cwd: Path
    ) -> tuple[str, str, int, Path, bool]:
        delim = "\t"
        fields_spec: str | None = None
        chars_spec: str | None = None
        files: list[str] = []

        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "-d" and i + 1 < len(args):
                delim = args[i + 1]
                i += 2
            elif arg.startswith("-d") and len(arg) > 2:
                delim = arg[2:]
                i += 1
            elif arg == "-f" and i + 1 < len(args):
                fields_spec = args[i + 1]
                i += 2
            elif arg.startswith("-f") and len(arg) > 2:
                fields_spec = arg[2:]
                i += 1
            elif arg == "-c" and i + 1 < len(args):
                chars_spec = args[i + 1]
                i += 2
            elif arg.startswith("-c") and len(arg) > 2:
                chars_spec = arg[2:]
                i += 1
            elif arg.startswith("-") and len(arg) > 1:
                i += 1
            else:
                files.append(arg)
                i += 1

        lines, err = self._read_lines_or_stdin(files, stdin_data, cwd, "cut")
        if lines is None:
            return "", err, 1, cwd, False

        out_lines: list[str] = []
        if fields_spec is not None:
            ranges = _parse_cut_fields(fields_spec)
            for ln in lines:
                if delim not in ln:
                    out_lines.append(ln)
                    continue
                parts = ln.split(delim)
                picked: list[str] = []
                for lo, hi in ranges:
                    end = len(parts) if hi is None else min(len(parts), hi)
                    for idx in range(lo, end + 1):
                        if 1 <= idx <= len(parts):
                            picked.append(parts[idx - 1])
                out_lines.append(delim.join(picked))
        elif chars_spec is not None:
            ranges = _parse_cut_fields(chars_spec)
            for ln in lines:
                chars: list[str] = []
                for lo, hi in ranges:
                    end = len(ln) if hi is None else min(len(ln), hi)
                    for idx in range(lo, end + 1):
                        if 1 <= idx <= len(ln):
                            chars.append(ln[idx - 1])
                out_lines.append("".join(chars))
        else:
            return "", "cut: you must specify a list of bytes, characters, or fields\n", 1, cwd, False

        out = ("\n".join(out_lines) + "\n") if out_lines else ""
        return out, "", 0, cwd, False

    def _cmd_awk(
        self, args: list[str], stdin_data: str, cwd: Path
    ) -> tuple[str, str, int, Path, bool]:
        field_sep: str | None = None
        prog: str | None = None
        files: list[str] = []

        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "-F" and i + 1 < len(args):
                field_sep = args[i + 1]
                i += 2
            elif arg.startswith("-F") and len(arg) > 2:
                field_sep = arg[2:]
                i += 1
            elif arg.startswith("-") and len(arg) > 1:
                i += 1
            elif prog is None:
                prog = arg
                i += 1
            else:
                files.append(arg)
                i += 1

        if prog is None:
            return "", "awk: missing program\n", 1, cwd, False

        m = re.fullmatch(r"\s*(?:/([^/]*)/)?\s*\{\s*print\s*(.*?)\s*;?\s*\}\s*", prog)
        if not m:
            return "", f"awk: unsupported program: {prog}\n", 2, cwd, False
        pattern_filter = m.group(1)
        print_expr = m.group(2)

        lines, err = self._read_lines_or_stdin(files, stdin_data, cwd, "awk")
        if lines is None:
            return "", err, 2, cwd, False

        filter_re = re.compile(pattern_filter) if pattern_filter is not None else None
        out_lines: list[str] = []
        for ln in lines:
            if filter_re is not None and not filter_re.search(ln):
                continue
            fields = ln.split(field_sep) if field_sep is not None else ln.split()
            if not print_expr or print_expr == "$0":
                out_lines.append(ln)
                continue
            rendered: list[str] = []
            for item in [p.strip() for p in print_expr.split(",")]:
                if item == "$0":
                    rendered.append(ln)
                elif item == "$NF":
                    rendered.append(fields[-1] if fields else "")
                elif re.fullmatch(r"\$\d+", item):
                    f_idx = int(item[1:])
                    if f_idx == 0:
                        rendered.append(ln)
                    elif 1 <= f_idx <= len(fields):
                        rendered.append(fields[f_idx - 1])
                    else:
                        rendered.append("")
                elif (item.startswith('"') and item.endswith('"')) or (
                    item.startswith("'") and item.endswith("'")
                ):
                    rendered.append(item[1:-1])
                else:
                    rendered.append(item)
            out_lines.append(" ".join(rendered))

        out = ("\n".join(out_lines) + "\n") if out_lines else ""
        return out, "", 0, cwd, False

    def _cmd_sed(
        self, args: list[str], stdin_data: str, cwd: Path
    ) -> tuple[str, str, int, Path, bool]:
        in_place = False
        expressions: list[str] = []
        operands: list[str] = []

        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "-e" and i + 1 < len(args):
                expressions.append(args[i + 1])
                i += 2
            elif arg == "-i" or (arg.startswith("-i") and len(arg) > 2):
                in_place = True
                i += 1
            elif arg in {"-E", "-r", "-n"}:
                i += 1
            elif arg.startswith("-") and len(arg) > 1:
                if "i" in arg[1:]:
                    in_place = True
                i += 1
            else:
                operands.append(arg)
                i += 1

        if not expressions:
            if not operands:
                return "", "sed: missing script\n", 1, cwd, False
            expressions.append(operands.pop(0))

        substitutions: list[tuple[re.Pattern[str], str, int]] = []
        try:
            for expr in expressions:
                for sub_cmd in _split_sed_script(expr):
                    pat_str, repl_str, flags_str = _parse_sed_subst(sub_cmd)
                    re_flags = re.IGNORECASE if "i" in flags_str else 0
                    count = 0 if "g" in flags_str else 1
                    substitutions.append((re.compile(pat_str, re_flags), repl_str, count))
        except (ValueError, re.error) as exc:
            return "", f"sed: {exc}\n", 1, cwd, False

        def transform(text: str) -> str:
            ends_nl = text.endswith("\n")
            lines = text.splitlines()
            new_lines: list[str] = []
            for ln in lines:
                cur = ln
                for pat, repl, cnt in substitutions:
                    cur = pat.sub(repl, cur, count=cnt)
                new_lines.append(cur)
            res = "\n".join(new_lines)
            if ends_nl and (new_lines or text):
                res += "\n"
            return res

        if not operands:
            return transform(stdin_data), "", 0, cwd, False

        out_parts: list[str] = []
        err_parts: list[str] = []
        rc = 0
        for raw in operands:
            try:
                p = self._resolve_user_path(raw, cwd)
                if not p.is_file():
                    err_parts.append(f"sed: can't read {raw}: No such file or directory\n")
                    rc = 2
                    continue
                updated = transform(self._read_text(p))
                if in_place:
                    mode = self._effective_mode(p)
                    p.write_text(updated, encoding="utf-8")
                    self._set_effective_mode(p, mode)
                else:
                    out_parts.append(updated)
            except (OSError, PermissionError) as exc:
                err_parts.append(f"sed: {raw}: {exc}\n")
                rc = 2
        return "".join(out_parts), "".join(err_parts), rc, cwd, False

    def _cmd_find(self, args: list[str], cwd: Path) -> tuple[str, str, int, Path, bool]:
        start_paths: list[str] = []
        idx = 0
        while idx < len(args) and not args[idx].startswith("-") and args[idx] not in {"!", "("}:
            start_paths.append(args[idx])
            idx += 1
        if not start_paths:
            start_paths = ["."]

        name_pat: str | None = None
        iname_pat: str | None = None
        type_filter: str | None = None
        maxdepth: int | None = None
        mindepth: int = 0
        delete_action = False
        exec_cmd: list[str] | None = None
        exec_batch = False

        while idx < len(args):
            tok = args[idx]
            if tok == "-name" and idx + 1 < len(args):
                name_pat = args[idx + 1]
                idx += 2
            elif tok == "-iname" and idx + 1 < len(args):
                iname_pat = args[idx + 1].lower()
                idx += 2
            elif tok == "-type" and idx + 1 < len(args):
                type_filter = args[idx + 1]
                idx += 2
            elif tok == "-maxdepth" and idx + 1 < len(args):
                maxdepth = int(args[idx + 1])
                idx += 2
            elif tok == "-mindepth" and idx + 1 < len(args):
                mindepth = int(args[idx + 1])
                idx += 2
            elif tok == "-delete":
                delete_action = True
                idx += 1
            elif tok in {"-exec", "-execdir"}:
                idx += 1
                cmd_parts: list[str] = []
                while idx < len(args) and args[idx] not in {";", "+"}:
                    cmd_parts.append(args[idx])
                    idx += 1
                if idx < len(args) and args[idx] == "+":
                    exec_batch = True
                exec_cmd = cmd_parts
                idx += 1
            else:
                idx += 1

        matches: list[tuple[str, Path]] = []
        err_lines: list[str] = []
        for raw_start in start_paths:
            try:
                start_p = self._resolve_user_path(raw_start, cwd, follow_final=False)
            except (OSError, PermissionError) as exc:
                err_lines.append(f"find: '{raw_start}': {exc}\n")
                continue
            if not start_p.exists() and not self.vfs.is_symlink(start_p):
                err_lines.append(f"find: '{raw_start}': No such file or directory\n")
                continue

            prefix = raw_start.rstrip("/") or "."

            def walk(cur: Path, disp: str, depth: int) -> None:
                if maxdepth is not None and depth > maxdepth:
                    return
                is_link = self.vfs.is_symlink(cur)
                is_dir = cur.is_dir() and not is_link
                is_file = cur.is_file() and not is_link

                if depth >= mindepth:
                    ok = True
                    if type_filter == "f" and not is_file:
                        ok = False
                    elif type_filter == "d" and not is_dir:
                        ok = False
                    elif type_filter == "l" and not is_link:
                        ok = False
                    if ok and name_pat is not None and not fnmatch.fnmatch(cur.name, name_pat):
                        ok = False
                    if ok and iname_pat is not None and not fnmatch.fnmatch(cur.name.lower(), iname_pat):
                        ok = False
                    if ok:
                        matches.append((disp, cur))

                if is_dir and (maxdepth is None or depth < maxdepth):
                    for child in sorted(cur.iterdir(), key=lambda c: c.name):
                        child_disp = f"{disp}/{child.name}" if disp != "." else f"./{child.name}"
                        walk(child, child_disp, depth + 1)

            walk(start_p, prefix, 0)

        if delete_action:
            # Depth-first removal so directories remove after children
            for _, p in sorted(matches, key=lambda item: len(item[1].parts), reverse=True):
                if p == self.root:
                    continue
                if p.is_dir() and not self.vfs.is_symlink(p):
                    try:
                        p.rmdir()
                        self.vfs.remove_entry(p)
                    except OSError:
                        pass
                else:
                    if p.exists() or p.is_symlink():
                        p.unlink()
                    self.vfs.remove_entry(p)
            return "", "".join(err_lines), 1 if err_lines else 0, cwd, False

        if exec_cmd is not None:
            out_acc: list[str] = []
            deadline = time.monotonic() + self.timeout
            if exec_batch:
                batch_args: list[str] = []
                for part in exec_cmd:
                    if part == "{}":
                        batch_args.extend(disp for disp, _ in matches)
                    else:
                        batch_args.append(part)
                if matches:
                    o, e, _, _, _ = self._exec_simple(batch_args, "", cwd, deadline)
                    if o:
                        out_acc.append(o)
                    if e:
                        err_lines.append(e)
            else:
                for disp, _ in matches:
                    one_args = [disp if part == "{}" else part for part in exec_cmd]
                    o, e, _, _, _ = self._exec_simple(one_args, "", cwd, deadline)
                    if o:
                        out_acc.append(o)
                    if e:
                        err_lines.append(e)
            return "".join(out_acc), "".join(err_lines), 1 if err_lines else 0, cwd, False

        out = ("\n".join(disp for disp, _ in matches) + "\n") if matches else ""
        return out, "".join(err_lines), 1 if err_lines else 0, cwd, False

    def _cmd_chmod(self, args: list[str], cwd: Path) -> tuple[str, str, int, Path, bool]:
        recursive = False
        positional: list[str] = []
        for arg in args:
            if arg in {"-R", "--recursive"}:
                recursive = True
            elif arg.startswith("-") and len(arg) > 1 and not re.fullmatch(r"-[rwx]+", arg):
                continue
            else:
                positional.append(arg)

        if len(positional) < 2:
            return "", "chmod: missing operand\n", 1, cwd, False

        mode_spec = positional[0]
        targets = positional[1:]
        err_lines: list[str] = []
        rc = 0

        for raw in targets:
            try:
                p = self._resolve_user_path(raw, cwd, follow_final=True)
            except (OSError, PermissionError) as exc:
                err_lines.append(f"chmod: cannot access '{raw}': {exc}\n")
                rc = 1
                continue
            if not p.exists():
                err_lines.append(f"chmod: cannot access '{raw}': No such file or directory\n")
                rc = 1
                continue

            to_update = [p]
            if recursive and p.is_dir():
                to_update.extend(sorted(p.rglob("*")))

            for item in to_update:
                try:
                    new_mode = _apply_chmod_spec(self._effective_mode(item), mode_spec)
                except ValueError as exc:
                    return "", f"{exc}\n", 1, cwd, False
                self._set_effective_mode(item, new_mode)

        return "", "".join(err_lines), rc, cwd, False

    def _cmd_ln(self, args: list[str], cwd: Path) -> tuple[str, str, int, Path, bool]:
        symbolic = False
        force = False
        operands: list[str] = []
        for arg in args:
            if arg.startswith("-") and len(arg) > 1:
                for ch in arg[1:]:
                    if ch == "s":
                        symbolic = True
                    elif ch == "f":
                        force = True
                    elif ch in {"n", "v"}:
                        pass
            else:
                operands.append(arg)

        if not symbolic:
            return "", "ln: hard links are not supported; use 'ln -s'\n", 1, cwd, False
        if len(operands) < 2:
            return "", "ln: missing file operand\n", 1, cwd, False

        target_str = operands[0]
        link_raw = operands[1]
        try:
            link_path = self._resolve_user_path(link_raw, cwd, follow_final=False)
        except (OSError, PermissionError) as exc:
            return "", f"ln: {exc}\n", 1, cwd, False

        if link_path.is_dir() and not self.vfs.is_symlink(link_path):
            link_path = link_path / Path(target_str).name

        exists = link_path.exists() or link_path.is_symlink() or self.vfs.is_symlink(link_path)
        if exists:
            if not force:
                return "", f"ln: failed to create symbolic link '{link_raw}': File exists\n", 1, cwd, False
            if link_path.is_symlink() or link_path.is_file():
                link_path.unlink()
            self.vfs.remove_entry(link_path)

        link_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            link_path.symlink_to(target_str)
        except OSError:
            pass
        self.vfs.set_symlink(link_path, target_str)
        return "", "", 0, cwd, False

    def _cmd_tar(self, args: list[str], cwd: Path) -> tuple[str, str, int, Path, bool]:
        create = False
        extract = False
        list_mode = False
        gzip_mode = False
        verbose = False
        archive_raw: str | None = None
        excludes: list[str] = []
        sources: list[str] = []
        target_dir: Path = cwd

        i = 0
        while i < len(args):
            arg = args[i]
            if arg.startswith("--exclude="):
                excludes.append(arg.split("=", 1)[1])
                i += 1
                continue
            if arg == "--exclude" and i + 1 < len(args):
                excludes.append(args[i + 1])
                i += 2
                continue
            if arg == "-C" and i + 1 < len(args):
                try:
                    target_dir = self._resolve_user_path(args[i + 1], cwd)
                except (OSError, PermissionError) as exc:
                    return "", f"tar: {exc}\n", 2, cwd, False
                i += 2
                continue
            if arg.startswith("-") or (i == 0 and any(c in arg for c in "ctxzvf")):
                flags = arg.lstrip("-")
                idx_f = 0
                while idx_f < len(flags):
                    ch = flags[idx_f]
                    if ch == "c":
                        create = True
                    elif ch == "x":
                        extract = True
                    elif ch == "t":
                        list_mode = True
                    elif ch == "z":
                        gzip_mode = True
                    elif ch == "v":
                        verbose = True
                    elif ch == "f":
                        rest_inline = flags[idx_f + 1 :]
                        if rest_inline:
                            archive_raw = rest_inline
                        elif i + 1 < len(args):
                            archive_raw = args[i + 1]
                            i += 1
                        break
                    idx_f += 1
                i += 1
                continue
            sources.append(arg)
            i += 1

        if archive_raw is None:
            return "", "tar: archive filename (-f) is required\n", 2, cwd, False

        try:
            archive_path = self._resolve_user_path(archive_raw, cwd, follow_final=False)
        except (OSError, PermissionError) as exc:
            return "", f"tar: {exc}\n", 2, cwd, False

        def is_excluded(rel_posix: str, name: str) -> bool:
            for pat in excludes:
                if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel_posix, pat):
                    return True
            return False

        if create:
            if not sources:
                return "", "tar: Cowardly refusing to create an empty archive\n", 2, cwd, False
            mode = "w:gz" if gzip_mode else "w"
            out_lines: list[str] = []
            try:
                archive_path.parent.mkdir(parents=True, exist_ok=True)
                with tarfile.open(archive_path, mode) as tf:
                    for raw_src in sources:
                        src_p = self._resolve_user_path(raw_src, cwd)
                        if not src_p.exists():
                            return "", f"tar: {raw_src}: Cannot stat: No such file or directory\n", 2, cwd, False
                        base_arc = raw_src.rstrip("/").lstrip("./") or src_p.name

                        def add_entry(path: Path, arcname: str) -> None:
                            if is_excluded(arcname, path.name):
                                return
                            info = tf.gettarinfo(str(path), arcname=arcname)
                            info.mode = self._effective_mode(path)
                            if path.is_file():
                                with path.open("rb") as fh:
                                    tf.addfile(info, fh)
                                if verbose:
                                    out_lines.append(arcname)
                            elif path.is_dir():
                                tf.addfile(info)
                                if verbose:
                                    out_lines.append(arcname + "/")
                                for child in sorted(path.iterdir(), key=lambda c: c.name):
                                    add_entry(child, f"{arcname}/{child.name}")

                        add_entry(src_p, base_arc)
                self._set_effective_mode(archive_path, 0o644)
            except (tarfile.TarError, OSError, PermissionError) as exc:
                return "", f"tar: {exc}\n", 2, cwd, False
            return ("\n".join(out_lines) + "\n") if out_lines else "", "", 0, cwd, False

        if list_mode:
            if not archive_path.is_file():
                return "", f"tar: {archive_raw}: Cannot open: No such file or directory\n", 2, cwd, False
            mode = "r:gz" if gzip_mode else "r:*"
            try:
                with tarfile.open(archive_path, mode) as tf:
                    names = [m.name for m in tf.getmembers()]
                return ("\n".join(names) + "\n") if names else "", "", 0, cwd, False
            except (tarfile.TarError, OSError) as exc:
                return "", f"tar: {exc}\n", 2, cwd, False

        if extract:
            if not archive_path.is_file():
                return "", f"tar: {archive_raw}: Cannot open: No such file or directory\n", 2, cwd, False
            mode = "r:gz" if gzip_mode else "r:*"
            try:
                with tarfile.open(archive_path, mode) as tf:
                    for member in tf.getmembers():
                        dest = Path(os.path.normpath(str(target_dir / member.name)))
                        if not _is_within_sandbox(dest, self.root):
                            return "", f"tar: refusing unsafe archive path '{member.name}'\n", 2, cwd, False
                        tf.extract(member, path=target_dir)
                        if member.isfile():
                            self._set_effective_mode(dest, member.mode or 0o644)
                return "", "", 0, cwd, False
            except (tarfile.TarError, OSError) as exc:
                return "", f"tar: {exc}\n", 2, cwd, False

        return "", "tar: must specify -c, -t, or -x\n", 2, cwd, False

    def _cmd_head_tail(
        self, args: list[str], stdin_data: str, cwd: Path, *, is_head: bool
    ) -> tuple[str, str, int, Path, bool]:
        count = 10
        files: list[str] = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "-n" and i + 1 < len(args):
                count = max(0, int(args[i + 1]))
                i += 2
            elif arg.startswith("-n") and arg[2:].isdigit():
                count = int(arg[2:])
                i += 1
            elif arg.startswith("-") and arg[1:].isdigit():
                count = int(arg[1:])
                i += 1
            else:
                files.append(arg)
                i += 1
        lines, err = self._read_lines_or_stdin(files, stdin_data, cwd, "head" if is_head else "tail")
        if lines is None:
            return "", err, 1, cwd, False
        sliced = lines[:count] if is_head else (lines[-count:] if count > 0 else [])
        out = ("\n".join(sliced) + "\n") if sliced else ""
        return out, "", 0, cwd, False

    def _cmd_wc(
        self, args: list[str], stdin_data: str, cwd: Path
    ) -> tuple[str, str, int, Path, bool]:
        count_l = count_w = count_c = False
        files: list[str] = []
        for arg in args:
            if arg.startswith("-") and len(arg) > 1:
                for ch in arg[1:]:
                    if ch == "l":
                        count_l = True
                    elif ch == "w":
                        count_w = True
                    elif ch == "c":
                        count_c = True
            else:
                files.append(arg)
        if not (count_l or count_w or count_c):
            count_l = count_w = count_c = True

        lines, err = self._read_lines_or_stdin(files, stdin_data, cwd, "wc")
        if lines is None:
            return "", err, 1, cwd, False
        text = ("\n".join(lines) + "\n") if lines else ""
        parts: list[str] = []
        if count_l:
            parts.append(str(len(lines)))
        if count_w:
            parts.append(str(len(text.split())))
        if count_c:
            parts.append(str(len(text.encode("utf-8"))))
        return " ".join(parts) + "\n", "", 0, cwd, False

    def _cmd_readlink(self, args: list[str], cwd: Path) -> tuple[str, str, int, Path, bool]:
        follow = False
        targets: list[str] = []
        for arg in args:
            if arg in {"-f", "-e", "-m"}:
                follow = True
            elif not arg.startswith("-"):
                targets.append(arg)
        if not targets:
            return "", "readlink: missing operand\n", 1, cwd, False
        out_lines: list[str] = []
        for raw in targets:
            try:
                p = self._resolve_user_path(raw, cwd, follow_final=False)
                if follow:
                    resolved = self.vfs.resolve_path(p, follow_final=True)
                    rel = resolved.relative_to(self.root).as_posix()
                    out_lines.append(f"{VIRTUAL_HOME}/{rel}" if rel != "." else VIRTUAL_HOME)
                else:
                    target = self.vfs.readlink(p)
                    if target is None:
                        return "", "", 1, cwd, False
                    out_lines.append(target)
            except (OSError, PermissionError):
                return "", "", 1, cwd, False
        return "\n".join(out_lines) + "\n", "", 0, cwd, False


def _simulated_script_runner(root: Path, script_path: Path) -> tuple[int, str, str]:
    vfs = get_virtual_fs(root)
    if vfs is None:
        vfs = VirtualFSState(root)
    shell = SimulatedShell(root, vfs)
    return shell.run_script_file(script_path)


register_simulated_script_runner(_simulated_script_runner)


# ---------------------------------------------------------------------------
# Unified SandboxSession
# ---------------------------------------------------------------------------


class SandboxSession:
    """Manages an isolated temporary workspace and persistent cwd for a single lab."""

    def __init__(
        self,
        lab_or_id: LabDefinition | str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        backend: str = BACKEND_AUTO,
    ) -> None:
        self.lab: LabDefinition = (
            lab_or_id
            if isinstance(lab_or_id, LabDefinition)
            else get_lab_by_id(lab_or_id)
        )
        self.timeout = float(timeout)
        self.backend: str = resolve_backend(backend)
        self.backend_label: str = BACKEND_LABELS[self.backend]
        self._tmpdir: tempfile.TemporaryDirectory[str] | None = None
        self._vfs: VirtualFSState | None = None
        self._sim_shell: SimulatedShell | None = None
        self._wsl_exe: str | None = None
        self.root: Path | PurePosixPath = Path(".")
        self.cwd: Path | PurePosixPath = Path(".")
        self._init_workspace()

    def _init_workspace(self) -> None:
        if self.backend == BACKEND_WSL:
            self._init_wsl_workspace()
            return

        self._tmpdir = tempfile.TemporaryDirectory(prefix="linux_plus_lab_")
        self.root = Path(self._tmpdir.name).resolve()
        self.cwd = self.root
        if self.backend == BACKEND_SIMULATED:
            self._vfs = VirtualFSState(self.root)
            register_virtual_fs(self.root, self._vfs)
            self.lab.setup(self.root)
            self._sim_shell = SimulatedShell(self.root, self._vfs, timeout=self.timeout)
        else:
            self.lab.setup(self.root)

    def _init_wsl_workspace(self) -> None:
        wsl_exe = _find_wsl_executable()
        if not wsl_exe:
            raise RuntimeError("WSL executable is not available.")
        self._wsl_exe = wsl_exe

        mk = subprocess.run(
            [wsl_exe, "-e", "bash", "-c", "mktemp -d /tmp/linux_plus_lab_XXXXXX"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(self.timeout, 5.0),
            check=False,
        )
        wsl_dir = (mk.stdout or "").strip().splitlines()[0].strip() if mk.stdout else ""
        if mk.returncode != 0 or not wsl_dir.startswith("/tmp/linux_plus_lab_"):
            raise RuntimeError(
                f"Failed to initialize WSL sandbox workspace: {(mk.stderr or '').strip() or 'unknown error'}"
            )

        self.root = PurePosixPath(wsl_dir)
        self.cwd = self.root

        setup_script = build_wsl_setup_script(self.lab.id)
        wrapped_setup = f"cd {shlex.quote(wsl_dir)} && (\n{setup_script}\n)"
        setup_proc = subprocess.run(
            [wsl_exe, "-e", "bash", "-c", wrapped_setup],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(self.timeout, 10.0),
            check=False,
        )
        if setup_proc.returncode != 0:
            self.cleanup()
            raise RuntimeError(
                f"Failed to populate WSL lab '{self.lab.id}': {(setup_proc.stderr or '').strip()}"
            )

        register_wsl_verifier(str(self.root), self._run_wsl_checks)

    def _run_wsl_checks(self, lab_id: str) -> list[bool]:
        if not self._wsl_exe:
            return []
        verify_script = build_wsl_verify_script(lab_id)
        wrapped = f"cd {shlex.quote(str(self.root))} && {{\n{verify_script}\n}}"
        try:
            proc = subprocess.run(
                [self._wsl_exe, "-e", "bash", "-c", wrapped],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(self.timeout, 5.0),
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return []

        outcomes: dict[int, bool] = {}
        for line in (proc.stdout or "").splitlines():
            m = re.match(r"^CHECK:(\d+):([01])$", line.strip())
            if m:
                outcomes[int(m.group(1))] = m.group(2) == "1"
        lab = get_lab_by_id(lab_id)
        return [outcomes.get(idx, False) for idx in range(len(lab.checks))]

    def __enter__(self) -> SandboxSession:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        """Delete the temporary sandbox workspace."""
        if self.backend == BACKEND_WSL:
            root_str = str(self.root)
            unregister_wsl_verifier(root_str)
            if self._wsl_exe and root_str.startswith("/tmp/linux_plus_lab_"):
                try:
                    subprocess.run(
                        [self._wsl_exe, "-e", "bash", "-c", f"rm -rf -- {shlex.quote(root_str)}"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=3.0,
                        check=False,
                    )
                except (OSError, subprocess.SubprocessError):
                    pass
            return

        if isinstance(self.root, Path):
            unregister_virtual_fs(self.root)
        self._vfs = None
        self._sim_shell = None
        if self._tmpdir is not None:
            self._tmpdir.cleanup()
            self._tmpdir = None

    def reset_lab(self) -> None:
        """Destroy the current workspace and rebuild a fresh clean lab environment."""
        self.cleanup()
        self._init_workspace()

    def relative_cwd(self) -> str:
        """Return the current working directory formatted relative to sandbox root."""
        if self.cwd == self.root:
            return "~"
        try:
            rel = self.cwd.relative_to(self.root).as_posix()
            return f"~/{rel}"
        except ValueError:
            return "~"

    def prompt(self) -> str:
        """Return the interactive sandbox shell prompt string."""
        return f"lab@sandbox:{self.relative_cwd()}$"

    def _sandbox_env(self) -> dict[str, str]:
        return {
            "HOME": str(self.root),
            "PWD": str(self.cwd),
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LC_ALL": "C",
            "LANG": "C",
            "TERM": "xterm-256color",
        }

    def execute(self, command: str) -> CommandResult:
        """Execute a command safely inside the sandbox with persistent cwd."""
        trimmed = command.strip() if isinstance(command, str) else ""
        if not trimmed:
            return CommandResult(
                command="",
                stdout="",
                stderr="",
                returncode=0,
                cwd=self.relative_cwd(),
                prompt=self.prompt(),
            )

        warning = validate_command(command, self.root, self.cwd)
        if warning is not None:
            return CommandResult(
                command=command,
                stdout="",
                stderr=warning,
                returncode=126,
                cwd=self.relative_cwd(),
                prompt=self.prompt(),
                blocked=True,
            )

        if self.backend == BACKEND_SIMULATED:
            return self._execute_simulated(command)
        if self.backend == BACKEND_WSL:
            return self._execute_wsl(command)
        return self._execute_native(command)

    def _execute_simulated(self, command: str) -> CommandResult:
        assert self._sim_shell is not None
        assert isinstance(self.cwd, Path)
        assert isinstance(self.root, Path)
        raw_stdout, raw_stderr, rc, new_cwd, timed_out = self._sim_shell.run(command, self.cwd)
        if timed_out:
            return CommandResult(
                command=command,
                stdout="",
                stderr=raw_stderr
                or f"Sandbox warning: command timed out after {int(self.timeout)} seconds.",
                returncode=124,
                cwd=self.relative_cwd(),
                prompt=self.prompt(),
                timed_out=True,
            )
        if _is_within_sandbox(new_cwd, self.root) and new_cwd.is_dir():
            self.cwd = new_cwd
        return self._format_result(command, raw_stdout, raw_stderr, rc)

    def _execute_wsl(self, command: str) -> CommandResult:
        assert self._wsl_exe is not None
        exec_command = _rewrite_virtual_home(command, self.root)
        wrapped = (
            f"export HOME={shlex.quote(str(self.root))} "
            "PATH=/usr/local/bin:/usr/bin:/bin LC_ALL=C LANG=C TERM=xterm-256color\n"
            f"cd {shlex.quote(str(self.cwd))} || exit 1\n"
            "{\n"
            f"{exec_command}\n"
            "}\n"
            "__sb_rc=$?\n"
            f"printf '\\n%s%s\\n' '{_CWD_MARKER}' \"$(pwd -P)\"\n"
            "exit $__sb_rc\n"
        )
        try:
            proc = subprocess.run(
                [self._wsl_exe, "-e", "bash", "-c", wrapped],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                command=command,
                stdout="",
                stderr=f"Sandbox warning: command timed out after {int(self.timeout)} seconds.",
                returncode=124,
                cwd=self.relative_cwd(),
                prompt=self.prompt(),
                timed_out=True,
            )

        raw_stdout = proc.stdout or ""
        raw_stderr = proc.stderr or ""
        if _CWD_MARKER in raw_stdout:
            before, marker_tail = raw_stdout.rsplit(_CWD_MARKER, 1)
            new_cwd_str = marker_tail.strip().splitlines()[0] if marker_tail.strip() else ""
            if new_cwd_str:
                candidate = PurePosixPath(posixpath.normpath(new_cwd_str))
                if _is_within_sandbox(candidate, self.root):
                    self.cwd = candidate
            raw_stdout = before[:-1] if before.endswith("\n") else before

        return self._format_result(command, raw_stdout, raw_stderr, proc.returncode)

    def _execute_native(self, command: str) -> CommandResult:
        exec_command = _rewrite_virtual_home(command, self.root)
        wrapped = (
            "{\n"
            f"{exec_command}\n"
            "}\n"
            "__sb_rc=$?\n"
            f"printf '\\n%s%s\\n' '{_CWD_MARKER}' \"$(pwd -P)\"\n"
            "exit $__sb_rc\n"
        )

        try:
            proc = subprocess.run(
                ["bash", "-c", wrapped],
                cwd=str(self.cwd),
                env=self._sandbox_env(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                command=command,
                stdout="",
                stderr=f"Sandbox warning: command timed out after {int(self.timeout)} seconds.",
                returncode=124,
                cwd=self.relative_cwd(),
                prompt=self.prompt(),
                timed_out=True,
            )

        raw_stdout = proc.stdout or ""
        raw_stderr = proc.stderr or ""

        # Extract updated cwd marker from stdout
        if _CWD_MARKER in raw_stdout:
            before, marker_tail = raw_stdout.rsplit(_CWD_MARKER, 1)
            new_cwd_str = marker_tail.strip().splitlines()[0] if marker_tail.strip() else ""
            if new_cwd_str and isinstance(self.root, Path):
                candidate = Path(new_cwd_str).resolve()
                if _is_within_sandbox(candidate, self.root) and candidate.is_dir():
                    self.cwd = candidate
            raw_stdout = before[:-1] if before.endswith("\n") else before

        return self._format_result(command, raw_stdout, raw_stderr, proc.returncode)

    def _format_result(
        self, command: str, raw_stdout: str, raw_stderr: str, returncode: int
    ) -> CommandResult:
        raw_stdout = _mask_sandbox_paths(raw_stdout, self.root)
        raw_stderr = _mask_sandbox_paths(raw_stderr, self.root)
        if len(raw_stdout) > MAX_OUTPUT_CHARS:
            raw_stdout = raw_stdout[:MAX_OUTPUT_CHARS] + "\n...[output truncated]"
        if len(raw_stderr) > MAX_OUTPUT_CHARS:
            raw_stderr = raw_stderr[:MAX_OUTPUT_CHARS] + "\n...[stderr truncated]"

        return CommandResult(
            command=command,
            stdout=raw_stdout,
            stderr=raw_stderr,
            returncode=returncode,
            cwd=self.relative_cwd(),
            prompt=self.prompt(),
        )

    def verify(self) -> VerificationResult:
        """Run state-based verification for the active lab workspace."""
        return verify_lab(self.lab.id, self.root)
