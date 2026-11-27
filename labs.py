"""Starter pack of 10 hands-on CompTIA Linux+ (XK0-006) sandbox labs."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import os
from pathlib import Path, PurePosixPath
import shlex
import stat
import subprocess
import tarfile
from typing import Callable


class VirtualFSState:
    """In-memory POSIX permission and symlink metadata for a simulated sandbox root."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.modes: dict[str, int] = {}
        self.symlinks: dict[str, str] = {}

    def rel_key(self, path: Path) -> str:
        """Return a normalized POSIX key relative to sandbox root without resolving final symlink."""
        abs_root = os.path.normpath(os.path.abspath(str(self.root)))
        raw_path = os.path.normpath(os.path.abspath(str(path)))
        rel = os.path.relpath(raw_path, abs_root)
        if rel == "..":
            raise ValueError(f"Path outside virtual root: {path}")
        if rel.startswith(".." + os.sep):
            # Retry with resolved parent in case root was accessed via OS symlink (e.g. /var -> /private/var)
            parent_resolved = os.path.realpath(os.path.dirname(raw_path))
            candidate = os.path.join(parent_resolved, os.path.basename(raw_path))
            rel = os.path.relpath(candidate, abs_root)
        if rel == ".." or rel.startswith(".." + os.sep):
            raise ValueError(f"Path outside virtual root: {path}")
        posix_rel = Path(rel).as_posix()
        return "." if posix_rel in {"", "."} else posix_rel.lstrip("./")

    def set_mode(self, path: Path, mode: int) -> None:
        key = self.rel_key(path)
        self.modes[key] = int(mode) & 0o7777

    def get_mode(self, path: Path) -> int | None:
        key = self.rel_key(path)
        return self.modes.get(key)

    def set_symlink(self, link_path: Path, target: str) -> None:
        key = self.rel_key(link_path)
        self.symlinks[key] = target

    def is_symlink(self, path: Path) -> bool:
        try:
            key = self.rel_key(path)
        except ValueError:
            return False
        if key in self.symlinks:
            return True
        return path.is_symlink()

    def readlink(self, path: Path) -> str | None:
        try:
            key = self.rel_key(path)
        except ValueError:
            return None
        if key in self.symlinks:
            return self.symlinks[key]
        if path.is_symlink():
            return os.readlink(path)
        return None

    def remove_entry(self, path: Path) -> None:
        try:
            key = self.rel_key(path)
        except ValueError:
            return
        if key == ".":
            return
        prefix = key + "/"
        for store in (self.modes, self.symlinks):
            for k in [existing for existing in store if existing == key or existing.startswith(prefix)]:
                del store[k]

    def move_entry(self, src: Path, dst: Path) -> None:
        try:
            src_key = self.rel_key(src)
            dst_key = self.rel_key(dst)
        except ValueError:
            return
        if src_key == "." or dst_key == ".":
            return
        src_prefix = src_key + "/"
        for store in (self.modes, self.symlinks):
            updates: dict[str, object] = {}
            removals: list[str] = []
            for k, val in store.items():
                if k == src_key:
                    updates[dst_key] = val
                    removals.append(k)
                elif k.startswith(src_prefix):
                    updates[dst_key + "/" + k[len(src_prefix) :]] = val
                    removals.append(k)
            for k in removals:
                del store[k]
            for k, val in updates.items():
                store[k] = val  # type: ignore[assignment]

    def resolve_path(self, path: Path, *, follow_final: bool = True, max_depth: int = 20) -> Path:
        """Resolve virtual and native symlinks inside the sandbox root."""
        key = self.rel_key(path)
        if key == ".":
            return self.root
        queue: list[str] = [p for p in PurePosixPath(key).parts if p not in {"", "."}]
        cur_parts: list[str] = []
        depth = 0

        while queue:
            part = queue.pop(0)
            if part in {"", "."}:
                continue
            if part == "..":
                if cur_parts:
                    cur_parts.pop()
                continue

            cur_parts.append(part)
            cur_key = "/".join(cur_parts)
            is_final = len(queue) == 0

            target: str | None = None
            if cur_key in self.symlinks:
                target = self.symlinks[cur_key]
            else:
                real_candidate = self.root.joinpath(*cur_parts)
                if real_candidate.is_symlink():
                    target = os.readlink(real_candidate)

            if target is not None and (not is_final or follow_final):
                depth += 1
                if depth > max_depth:
                    raise OSError("Too many levels of symbolic links")
                cur_parts.pop()
                posix_target = target.replace("\\", "/")
                if posix_target.startswith("/"):
                    root_posix = self.root.as_posix().rstrip("/")
                    if posix_target == root_posix or posix_target.startswith(root_posix + "/"):
                        rel_target = posix_target[len(root_posix) :].lstrip("/")
                        cur_parts = []
                        target_parts = [p for p in PurePosixPath(rel_target).parts if p not in {"", "."}]
                    else:
                        raise OSError(f"Symlink target outside sandbox: {target}")
                else:
                    target_parts = [p for p in PurePosixPath(posix_target).parts if p not in {"", "."}]
                queue = target_parts + queue

        return self.root.joinpath(*cur_parts) if cur_parts else self.root


_VIRTUAL_FS_REGISTRY: dict[Path, VirtualFSState] = {}
_SIMULATED_SCRIPT_RUNNER: Callable[[Path, Path], tuple[int, str, str]] | None = None
_WSL_VERIFIER_REGISTRY: dict[str, Callable[[str], list[bool]]] = {}


def register_virtual_fs(root: Path, state: VirtualFSState) -> None:
    _VIRTUAL_FS_REGISTRY[Path(root).resolve()] = state


def unregister_virtual_fs(root: Path) -> None:
    _VIRTUAL_FS_REGISTRY.pop(Path(root).resolve(), None)


def get_virtual_fs(root: Path) -> VirtualFSState | None:
    return _VIRTUAL_FS_REGISTRY.get(Path(root).resolve())


def register_simulated_script_runner(
    runner: Callable[[Path, Path], tuple[int, str, str]],
) -> None:
    global _SIMULATED_SCRIPT_RUNNER
    _SIMULATED_SCRIPT_RUNNER = runner


def register_wsl_verifier(root_key: str, verifier: Callable[[str], list[bool]]) -> None:
    _WSL_VERIFIER_REGISTRY[str(root_key)] = verifier


def unregister_wsl_verifier(root_key: str) -> None:
    _WSL_VERIFIER_REGISTRY.pop(str(root_key), None)


def get_wsl_verifier(root_key: str) -> Callable[[str], list[bool]] | None:
    return _WSL_VERIFIER_REGISTRY.get(str(root_key))


def _set_mode(root: Path, path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass
    vfs = get_virtual_fs(root)
    if vfs is not None:
        vfs.set_mode(path, mode)


def _make_symlink(root: Path, link_path: Path, target: str) -> None:
    if link_path.is_symlink() or link_path.exists():
        try:
            link_path.unlink()
        except OSError:
            pass
    try:
        link_path.symlink_to(target)
    except OSError:
        pass
    vfs = get_virtual_fs(root)
    if vfs is not None:
        vfs.set_symlink(link_path, target)


def _is_effective_symlink(root: Path, path: Path) -> bool:
    vfs = get_virtual_fs(root)
    if vfs is not None:
        return vfs.is_symlink(path)
    return path.is_symlink()


def _resolve_effective_path(root: Path, path: Path) -> Path:
    vfs = get_virtual_fs(root)
    if vfs is not None:
        return vfs.resolve_path(path, follow_final=True)
    return path.resolve()


def _get_effective_mode(root: Path, path: Path) -> int | None:
    vfs = get_virtual_fs(root)
    if vfs is not None:
        try:
            target = vfs.resolve_path(path, follow_final=True)
        except OSError:
            return None
        if not target.exists():
            return None
        mode = vfs.get_mode(target)
        if mode is not None:
            return mode
        return 0o755 if target.is_dir() else 0o644
    if not path.exists():
        return None
    return stat.S_IMODE(path.stat().st_mode)


@dataclass(frozen=True)
class LabCheck:
    """A single state-based verification check for a sandbox lab."""

    description: str
    predicate: Callable[[Path], bool]


@dataclass(frozen=True)
class LabDefinition:
    """Definition of a hands-on Linux+ sandbox lab with setup and state checks."""

    id: str
    title: str
    domain: str
    difficulty: str
    objective: str
    hint: str
    solution_example: str
    setup: Callable[[Path], None]
    checks: list[LabCheck]

    @property
    def checklist(self) -> list[str]:
        """Return human-readable verification criteria descriptions."""
        return [check.description for check in self.checks]

    def to_metadata_dict(self, completed: bool = False) -> dict[str, object]:
        """Serialize lab metadata for API responses."""
        return {
            "id": self.id,
            "title": self.title,
            "domain": self.domain,
            "difficulty": self.difficulty,
            "objective": self.objective,
            "checklist": self.checklist,
            "completed": completed,
        }


# ---------------------------------------------------------------------------
# Lab 01: Organize Project Directories & Files (Beginner)
# ---------------------------------------------------------------------------

_LAB01_APP_PY = "print('hello linux+')\n"
_LAB01_CONFIG_INI = "[server]\nport=8080\n"
_LAB01_README = "# Project Docs\n"


def _setup_lab_01(root: Path) -> None:
    inbox = root / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "app.py").write_text(_LAB01_APP_PY, encoding="utf-8")
    (inbox / "config.ini").write_text(_LAB01_CONFIG_INI, encoding="utf-8")
    (inbox / "README.md").write_text(_LAB01_README, encoding="utf-8")


def _lab01_dirs_exist(root: Path) -> bool:
    return all(
        (root / rel).is_dir()
        for rel in ("project/src", "project/config", "project/docs")
    )


def _lab01_app_moved(root: Path) -> bool:
    target = root / "project/src/app.py"
    source = root / "inbox/app.py"
    return (
        target.is_file()
        and not source.exists()
        and target.read_text(encoding="utf-8") == _LAB01_APP_PY
    )


def _lab01_config_moved(root: Path) -> bool:
    target = root / "project/config/config.ini"
    source = root / "inbox/config.ini"
    return (
        target.is_file()
        and not source.exists()
        and target.read_text(encoding="utf-8") == _LAB01_CONFIG_INI
    )


def _lab01_readme_copied(root: Path) -> bool:
    target = root / "project/docs/README.md"
    source = root / "inbox/README.md"
    return (
        target.is_file()
        and source.is_file()
        and target.read_text(encoding="utf-8") == _LAB01_README
        and source.read_text(encoding="utf-8") == _LAB01_README
    )


# ---------------------------------------------------------------------------
# Lab 02: Harden Key & Script Permissions (Beginner)
# ---------------------------------------------------------------------------


def _setup_lab_02(root: Path) -> None:
    (root / "secrets").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "public").mkdir(parents=True, exist_ok=True)

    api_key = root / "secrets/api.key"
    api_key.write_text("SECRET_TOKEN=xk0-006-demo\n", encoding="utf-8")
    _set_mode(root, api_key, 0o644)

    backup_sh = root / "scripts/backup.sh"
    backup_sh.write_text("#!/bin/bash\necho 'backup ok'\n", encoding="utf-8")
    _set_mode(root, backup_sh, 0o644)

    readme = root / "public/readme.txt"
    readme.write_text("Public documentation\n", encoding="utf-8")
    _set_mode(root, readme, 0o600)


def _has_mode(root: Path, path: Path, expected_mode: int) -> bool:
    target = _resolve_effective_path(root, path) if get_virtual_fs(root) is not None else path
    if not target.is_file():
        return False
    mode = _get_effective_mode(root, path)
    return mode == expected_mode


# ---------------------------------------------------------------------------
# Lab 03: Filter Application Error Logs (Beginner)
# ---------------------------------------------------------------------------

_LAB03_LOG_LINES = [
    "2026-11-25 10:00:01 INFO Service starting on port 8080",
    "2026-11-25 10:00:05 ERROR Failed to connect to database primary",
    "2026-11-25 10:01:12 WARN High memory usage detected (82%)",
    "2026-11-25 10:02:00 INFO Cache warmed successfully",
    "2026-11-25 10:03:44 ERROR Timeout waiting for auth upstream",
    "2026-11-25 10:04:10 INFO Healthcheck passed",
    "2026-11-25 10:05:19 ERROR Disk quota exceeded on /mnt/data",
]
_LAB03_EXPECTED_ERRORS = [line for line in _LAB03_LOG_LINES if "ERROR" in line]


def _setup_lab_03(root: Path) -> None:
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "app.log").write_text("\n".join(_LAB03_LOG_LINES) + "\n", encoding="utf-8")


def _lab03_errors_exist_and_exact(root: Path) -> bool:
    err_file = root / "logs/errors.log"
    if not err_file.is_file():
        return False
    lines = [ln for ln in err_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return lines == _LAB03_EXPECTED_ERRORS


def _lab03_source_intact(root: Path) -> bool:
    app_log = root / "logs/app.log"
    if not app_log.is_file():
        return False
    return app_log.read_text(encoding="utf-8").splitlines() == _LAB03_LOG_LINES


# ---------------------------------------------------------------------------
# Lab 04: Switch Release via Symbolic Link (Beginner)
# ---------------------------------------------------------------------------


def _setup_lab_04(root: Path) -> None:
    v1 = root / "releases/v1"
    v2 = root / "releases/v2"
    v1.mkdir(parents=True, exist_ok=True)
    v2.mkdir(parents=True, exist_ok=True)
    (v1 / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (v2 / "VERSION").write_text("2.0.0\n", encoding="utf-8")


def _lab04_is_symlink(root: Path) -> bool:
    return _is_effective_symlink(root, root / "current")


def _lab04_points_to_v2(root: Path) -> bool:
    link = root / "current"
    target = root / "releases/v2"
    if not _is_effective_symlink(root, link) or not target.is_dir():
        return False
    try:
        resolved = _resolve_effective_path(root, link)
    except OSError:
        return False
    return resolved.resolve() == target.resolve() and resolved.is_dir()


def _lab04_version_readable(root: Path) -> bool:
    try:
        version_file = _resolve_effective_path(root, root / "current/VERSION")
    except OSError:
        return False
    return version_file.is_file() and version_file.read_text(encoding="utf-8").strip() == "2.0.0"


# ---------------------------------------------------------------------------
# Lab 05: Create a Filtered .tar.gz Archive (Intermediate)
# ---------------------------------------------------------------------------


def _setup_lab_05(root: Path) -> None:
    webapp = root / "webapp"
    assets = webapp / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (webapp / "index.html").write_text("<h1>Linux+ Webapp</h1>\n", encoding="utf-8")
    (webapp / "app.js").write_text("console.log('ready');\n", encoding="utf-8")
    (webapp / "cache.tmp").write_text("temp cache\n", encoding="utf-8")
    (assets / "style.css").write_text("body { margin: 0; }\n", encoding="utf-8")
    (assets / "draft.tmp").write_text("draft temp\n", encoding="utf-8")


def _normalized_tar_files(archive_path: Path) -> list[str] | None:
    if not archive_path.is_file():
        return None
    try:
        with tarfile.open(archive_path, "r:gz") as tf:
            names: list[str] = []
            for member in tf.getmembers():
                if not member.isfile():
                    continue
                cleaned = member.name.lstrip("./")
                if cleaned.startswith("webapp/"):
                    cleaned = cleaned[len("webapp/") :]
                names.append(cleaned)
            return names
    except (tarfile.TarError, OSError):
        return None


def _lab05_archive_valid(root: Path) -> bool:
    return _normalized_tar_files(root / "webapp_backup.tar.gz") is not None


def _lab05_has_expected_files(root: Path) -> bool:
    files = _normalized_tar_files(root / "webapp_backup.tar.gz")
    if files is None:
        return False
    expected = {"index.html", "app.js", "assets/style.css"}
    return expected.issubset(set(files))


def _lab05_excludes_tmp(root: Path) -> bool:
    archive_path = root / "webapp_backup.tar.gz"
    if not archive_path.is_file():
        return False
    try:
        with tarfile.open(archive_path, "r:gz") as tf:
            members = [m.name for m in tf.getmembers()]
            return len(members) > 0 and not any(name.endswith(".tmp") for name in members)
    except (tarfile.TarError, OSError):
        return False


# ---------------------------------------------------------------------------
# Lab 06: Recursively Clean Up .bak Files (Intermediate)
# ---------------------------------------------------------------------------

_LAB06_ACTIVE_FILES = {
    "configs/nginx.conf": "worker_processes 2;\n",
    "configs/db/postgres.conf": "max_connections = 100\n",
    "configs/app/settings.yaml": "env: production\n",
}


def _setup_lab_06(root: Path) -> None:
    for rel, content in _LAB06_ACTIVE_FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    bak_files = [
        "configs/nginx.conf.bak",
        "configs/db/postgres.conf.bak",
        "configs/db/archive/legacy.bak",
        "configs/app/settings.yaml.bak",
    ]
    for rel in bak_files:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("backup\n", encoding="utf-8")


def _lab06_no_bak_remaining(root: Path) -> bool:
    configs = root / "configs"
    if not configs.is_dir():
        return False
    return not any(p.is_file() and p.name.endswith(".bak") for p in configs.rglob("*"))


def _lab06_active_intact(root: Path) -> bool:
    return all(
        (root / rel).is_file() and (root / rel).read_text(encoding="utf-8") == content
        for rel, content in _LAB06_ACTIVE_FILES.items()
    )


# ---------------------------------------------------------------------------
# Lab 07: Extract Sorted Unique IPs from Access Log (Intermediate)
# ---------------------------------------------------------------------------

_LAB07_ACCESS_LINES = [
    '192.168.10.25 - - [25/Nov/2026:10:00:01] "GET /index.html HTTP/1.1" 200',
    '10.0.0.12 - - [25/Nov/2026:10:00:02] "GET /api/status HTTP/1.1" 200',
    '192.168.10.15 - - [25/Nov/2026:10:00:05] "POST /login HTTP/1.1" 401',
    '192.168.10.25 - - [25/Nov/2026:10:01:10] "GET /assets/app.js HTTP/1.1" 200',
    '172.16.4.8 - - [25/Nov/2026:10:02:14] "GET /health HTTP/1.1" 200',
    '10.0.0.12 - - [25/Nov/2026:10:03:00] "GET /metrics HTTP/1.1" 200',
    '172.16.4.8 - - [25/Nov/2026:10:04:22] "GET /health HTTP/1.1" 200',
]
_LAB07_EXPECTED_IPS = ["10.0.0.12", "172.16.4.8", "192.168.10.15", "192.168.10.25"]


def _setup_lab_07(root: Path) -> None:
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "access.log").write_text("\n".join(_LAB07_ACCESS_LINES) + "\n", encoding="utf-8")


def _lab07_unique_ips_valid(root: Path) -> bool:
    out_file = root / "unique_ips.txt"
    if not out_file.is_file():
        return False
    lines = [ln.strip() for ln in out_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return lines == _LAB07_EXPECTED_IPS


# ---------------------------------------------------------------------------
# Lab 08: Write & Run an Executable Bash Script (Intermediate)
# ---------------------------------------------------------------------------


def _setup_lab_08(root: Path) -> None:
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "README.txt").write_text(
        "Create scripts/healthcheck.sh and write its output to status.out.\n",
        encoding="utf-8",
    )


def _lab08_script_has_shebang(root: Path) -> bool:
    script = root / "scripts/healthcheck.sh"
    if not script.is_file():
        return False
    lines = script.read_text(encoding="utf-8").splitlines()
    return bool(lines) and lines[0].strip() == "#!/bin/bash"


def _lab08_script_executable(root: Path) -> bool:
    script = root / "scripts/healthcheck.sh"
    if not script.is_file():
        return False
    mode = _get_effective_mode(root, script)
    return mode is not None and bool(mode & stat.S_IXUSR)


def _lab08_script_runs_cleanly(root: Path) -> bool:
    script = root / "scripts/healthcheck.sh"
    if not _lab08_script_has_shebang(root) or not _lab08_script_executable(root):
        return False
    if get_virtual_fs(root) is not None and _SIMULATED_SCRIPT_RUNNER is not None:
        rc, stdout, _ = _SIMULATED_SCRIPT_RUNNER(root, script)
        return rc == 0 and stdout.strip() == "SYSTEM_OK"
    try:
        proc = subprocess.run(
            [str(script)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        return proc.returncode == 0 and proc.stdout.strip() == "SYSTEM_OK"
    except (OSError, subprocess.SubprocessError):
        if _SIMULATED_SCRIPT_RUNNER is not None:
            rc, stdout, _ = _SIMULATED_SCRIPT_RUNNER(root, script)
            return rc == 0 and stdout.strip() == "SYSTEM_OK"
        return False


def _lab08_status_out_matches(root: Path) -> bool:
    status_file = root / "status.out"
    return status_file.is_file() and status_file.read_text(encoding="utf-8").strip() == "SYSTEM_OK"


# ---------------------------------------------------------------------------
# Lab 09: Safe In-Place Config Migration (Hard)
# ---------------------------------------------------------------------------

_LAB09_ORIGINAL_CONF = (
    "APP_NAME=linux-plus-api\n"
    "PORT=8080\n"
    "DEBUG=true\n"
    "LOG_LEVEL=debug\n"
)


def _setup_lab_09(root: Path) -> None:
    etc_app = root / "etc_app"
    etc_app.mkdir(parents=True, exist_ok=True)
    conf = etc_app / "service.conf"
    conf.write_text(_LAB09_ORIGINAL_CONF, encoding="utf-8")
    _set_mode(root, conf, 0o644)


def _lab09_backup_intact(root: Path) -> bool:
    bak = root / "etc_app/service.conf.bak"
    return bak.is_file() and bak.read_text(encoding="utf-8") == _LAB09_ORIGINAL_CONF


def _lab09_config_migrated(root: Path) -> bool:
    conf = root / "etc_app/service.conf"
    if not conf.is_file():
        return False
    lines = [ln.strip() for ln in conf.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return (
        "APP_NAME=linux-plus-api" in lines
        and "PORT=8443" in lines
        and "DEBUG=false" in lines
        and "LOG_LEVEL=debug" in lines
        and "PORT=8080" not in lines
        and "DEBUG=true" not in lines
    )


# ---------------------------------------------------------------------------
# Lab 10: Audit & Repair Broken Workspace (Hard)
# ---------------------------------------------------------------------------


def _setup_lab_10(root: Path) -> None:
    targets = root / "targets"
    targets.mkdir(parents=True, exist_ok=True)
    prod_conf = targets / "prod.conf"
    prod_conf.write_text("mode=production\n", encoding="utf-8")
    _set_mode(root, prod_conf, 0o644)

    # Dangling symlink pointing to a missing target
    _make_symlink(root, root / "active.conf", "targets/missing.conf")

    sensitive = root / "sensitive"
    sensitive.mkdir(parents=True, exist_ok=True)

    db_env = sensitive / "db.env"
    db_env.write_text("DB_PASS=changeme\n", encoding="utf-8")
    _set_mode(root, db_env, 0o666)

    token_key = sensitive / "token.key"
    token_key.write_text("TOKEN=abc123\n", encoding="utf-8")
    _set_mode(root, token_key, 0o777)

    notes = sensitive / "notes.txt"
    notes.write_text("Internal security notes\n", encoding="utf-8")
    _set_mode(root, notes, 0o644)


def _lab10_symlink_repaired(root: Path) -> bool:
    link = root / "active.conf"
    target = root / "targets/prod.conf"
    if not _is_effective_symlink(root, link) or not target.is_file():
        return False
    try:
        resolved = _resolve_effective_path(root, link)
    except OSError:
        return False
    return resolved.resolve() == target.resolve() and resolved.is_file()


def _lab10_no_world_writable(root: Path) -> bool:
    expected_files = ("db.env", "token.key", "notes.txt")
    for name in expected_files:
        path = root / "sensitive" / name
        if not path.is_file():
            return False
        mode = _get_effective_mode(root, path)
        if mode is None or (mode & stat.S_IWOTH):
            return False
    return True


def _lab10_audit_report_complete(root: Path) -> bool:
    report = root / "audit_report.txt"
    if not report.is_file():
        return False
    content = report.read_text(encoding="utf-8")
    return all(item in content for item in ("active.conf", "db.env", "token.key"))


# ---------------------------------------------------------------------------
# Lab Registry (10 Labs)
# ---------------------------------------------------------------------------

ALL_LABS: list[LabDefinition] = [
    LabDefinition(
        id="lab_01",
        title="Organize Project Directories & Files",
        domain="1.0 System Management",
        difficulty="beginner",
        objective=(
            "Create nested directories 'project/src', 'project/config', and 'project/docs'. "
            "Move 'inbox/app.py' into 'project/src/', move 'inbox/config.ini' into "
            "'project/config/', and copy 'inbox/README.md' into 'project/docs/' "
            "(keeping the original in 'inbox/')."
        ),
        hint="Use 'mkdir -p' to create nested directories, 'mv' to move files, and 'cp' to copy README.md.",
        solution_example=(
            "mkdir -p project/src project/config project/docs && "
            "mv inbox/app.py project/src/ && "
            "mv inbox/config.ini project/config/ && "
            "cp inbox/README.md project/docs/"
        ),
        setup=_setup_lab_01,
        checks=[
            LabCheck("Directories project/src, project/config, and project/docs exist", _lab01_dirs_exist),
            LabCheck("inbox/app.py moved to project/src/app.py", _lab01_app_moved),
            LabCheck("inbox/config.ini moved to project/config/config.ini", _lab01_config_moved),
            LabCheck("inbox/README.md copied to project/docs/README.md (original preserved)", _lab01_readme_copied),
        ],
    ),
    LabDefinition(
        id="lab_02",
        title="Harden Key & Script Permissions",
        domain="3.0 Security",
        difficulty="beginner",
        objective=(
            "Fix file permissions across the workspace: set 'secrets/api.key' to 0600, "
            "make 'scripts/backup.sh' executable with 0750, and set 'public/readme.txt' to 0644."
        ),
        hint="Use 'chmod' with octal modes (600, 750, 644) or symbolic modes like u=rw,go=.",
        solution_example="chmod 600 secrets/api.key && chmod 750 scripts/backup.sh && chmod 644 public/readme.txt",
        setup=_setup_lab_02,
        checks=[
            LabCheck("secrets/api.key has permissions 0600", lambda r: _has_mode(r, r / "secrets/api.key", 0o600)),
            LabCheck("scripts/backup.sh has permissions 0750", lambda r: _has_mode(r, r / "scripts/backup.sh", 0o750)),
            LabCheck("public/readme.txt has permissions 0644", lambda r: _has_mode(r, r / "public/readme.txt", 0o644)),
        ],
    ),
    LabDefinition(
        id="lab_03",
        title="Filter Application Error Logs",
        domain="1.0 System Management",
        difficulty="beginner",
        objective=(
            "Extract all lines containing 'ERROR' from 'logs/app.log' and write them into "
            "'logs/errors.log' without modifying 'logs/app.log'."
        ),
        hint="Use 'grep' with output redirection '>' into logs/errors.log.",
        solution_example='grep "ERROR" logs/app.log > logs/errors.log',
        setup=_setup_lab_03,
        checks=[
            LabCheck("logs/errors.log exists and contains only the 3 ERROR lines", _lab03_errors_exist_and_exact),
            LabCheck("Original logs/app.log remains unmodified", _lab03_source_intact),
        ],
    ),
    LabDefinition(
        id="lab_04",
        title="Switch Release via Symbolic Link",
        domain="1.0 System Management",
        difficulty="beginner",
        objective=(
            "Create a symbolic link named 'current' in the workspace root that points to "
            "'releases/v2' so 'current/VERSION' resolves to 2.0.0."
        ),
        hint="Use 'ln -s <target> <link_name>' from the workspace root.",
        solution_example="ln -s releases/v2 current",
        setup=_setup_lab_04,
        checks=[
            LabCheck("'current' exists as a symbolic link", _lab04_is_symlink),
            LabCheck("'current' resolves to releases/v2 directory", _lab04_points_to_v2),
            LabCheck("'current/VERSION' reads 2.0.0", _lab04_version_readable),
        ],
    ),
    LabDefinition(
        id="lab_05",
        title="Create a Filtered .tar.gz Archive",
        domain="1.0 System Management",
        difficulty="intermediate",
        objective=(
            "Create a gzip-compressed tar archive named 'webapp_backup.tar.gz' containing "
            "the 'webapp/' directory while excluding all '*.tmp' files."
        ),
        hint="Use 'tar -czf webapp_backup.tar.gz --exclude=\"*.tmp\" webapp'.",
        solution_example="tar -czf webapp_backup.tar.gz --exclude='*.tmp' webapp",
        setup=_setup_lab_05,
        checks=[
            LabCheck("webapp_backup.tar.gz is a valid gzip-compressed tar archive", _lab05_archive_valid),
            LabCheck("Archive includes index.html, app.js, and assets/style.css", _lab05_has_expected_files),
            LabCheck("Archive excludes all *.tmp files", _lab05_excludes_tmp),
        ],
    ),
    LabDefinition(
        id="lab_06",
        title="Recursively Clean Up .bak Files",
        domain="1.0 System Management",
        difficulty="intermediate",
        objective=(
            "Find and delete all '*.bak' backup files across all nested subdirectories under "
            "'configs/' without deleting any active configuration files."
        ),
        hint="Use 'find configs -type f -name \"*.bak\" -delete' (or '-exec rm {} +').",
        solution_example="find configs -type f -name '*.bak' -delete",
        setup=_setup_lab_06,
        checks=[
            LabCheck("All *.bak files under configs/ have been removed", _lab06_no_bak_remaining),
            LabCheck("Active config files (nginx.conf, postgres.conf, settings.yaml) remain intact", _lab06_active_intact),
        ],
    ),
    LabDefinition(
        id="lab_07",
        title="Extract Sorted Unique IPs from Access Log",
        domain="4.0 Scripting, Containers, and Automation",
        difficulty="intermediate",
        objective=(
            "Parse 'logs/access.log' to extract all unique client IP addresses (first field), "
            "sort them in ascending order, and save one IP per line to 'unique_ips.txt'."
        ),
        hint="Combine 'awk' or 'cut' with 'sort -u' (or 'sort | uniq') and redirect to unique_ips.txt.",
        solution_example="awk '{print $1}' logs/access.log | sort -u > unique_ips.txt",
        setup=_setup_lab_07,
        checks=[
            LabCheck("unique_ips.txt contains sorted, deduplicated IP addresses", _lab07_unique_ips_valid),
        ],
    ),
    LabDefinition(
        id="lab_08",
        title="Write & Run an Executable Bash Script",
        domain="4.0 Scripting, Containers, and Automation",
        difficulty="intermediate",
        objective=(
            "Create a Bash script at 'scripts/healthcheck.sh' starting with '#!/bin/bash' that "
            "outputs 'SYSTEM_OK', make it executable, and run it redirecting output to 'status.out'."
        ),
        hint="Write the script with printf/cat, run 'chmod +x scripts/healthcheck.sh', then './scripts/healthcheck.sh > status.out'.",
        solution_example="printf '#!/bin/bash\\necho \"SYSTEM_OK\"\\n' > scripts/healthcheck.sh && chmod +x scripts/healthcheck.sh && ./scripts/healthcheck.sh > status.out",
        setup=_setup_lab_08,
        checks=[
            LabCheck("scripts/healthcheck.sh exists and starts with #!/bin/bash", _lab08_script_has_shebang),
            LabCheck("scripts/healthcheck.sh has execute permission", _lab08_script_executable),
            LabCheck("Running scripts/healthcheck.sh exits 0 and prints SYSTEM_OK", _lab08_script_runs_cleanly),
            LabCheck("status.out exists and contains SYSTEM_OK", _lab08_status_out_matches),
        ],
    ),
    LabDefinition(
        id="lab_09",
        title="Safe In-Place Config Migration",
        domain="1.0 System Management",
        difficulty="hard",
        objective=(
            "Back up 'etc_app/service.conf' to 'etc_app/service.conf.bak', update 'etc_app/service.conf' "
            "in place to set 'PORT=8443' and 'DEBUG=false' while preserving other settings, and "
            "restrict permissions on 'etc_app/service.conf' to 0640."
        ),
        hint="Copy to .bak first, use 'sed -i' to update PORT and DEBUG, then run 'chmod 640 etc_app/service.conf'.",
        solution_example=(
            "cp etc_app/service.conf etc_app/service.conf.bak && "
            "sed -i 's/^PORT=8080$/PORT=8443/; s/^DEBUG=true$/DEBUG=false/' etc_app/service.conf && "
            "chmod 640 etc_app/service.conf"
        ),
        setup=_setup_lab_09,
        checks=[
            LabCheck("etc_app/service.conf.bak preserves original config untouched", _lab09_backup_intact),
            LabCheck("etc_app/service.conf updated to PORT=8443 and DEBUG=false", _lab09_config_migrated),
            LabCheck("etc_app/service.conf has strict 0640 permissions", lambda r: _has_mode(r, r / "etc_app/service.conf", 0o640)),
        ],
    ),
    LabDefinition(
        id="lab_10",
        title="Audit & Repair Broken Workspace",
        domain="5.0 Troubleshooting",
        difficulty="hard",
        objective=(
            "Repair the broken symlink 'active.conf' so it points to 'targets/prod.conf', "
            "remove world-writable permissions (o-w) from all files in 'sensitive/', and write "
            "'audit_report.txt' listing the repaired items ('active.conf', 'db.env', 'token.key')."
        ),
        hint="Use 'ln -sfn targets/prod.conf active.conf', 'chmod o-w sensitive/*', and write the filenames to audit_report.txt.",
        solution_example=(
            "ln -sfn targets/prod.conf active.conf && "
            "chmod o-w sensitive/db.env sensitive/token.key && "
            "printf 'active.conf\\ndb.env\\ntoken.key\\n' > audit_report.txt"
        ),
        setup=_setup_lab_10,
        checks=[
            LabCheck("active.conf symlink repaired to point to targets/prod.conf", _lab10_symlink_repaired),
            LabCheck("No files in sensitive/ have world-writable (o+w) permissions", _lab10_no_world_writable),
            LabCheck("audit_report.txt lists active.conf, db.env, and token.key", _lab10_audit_report_complete),
        ],
    ),
]

LABS_BY_ID: dict[str, LabDefinition] = {lab.id: lab for lab in ALL_LABS}


def get_all_labs() -> list[LabDefinition]:
    """Return all ordered starter sandbox labs."""
    return list(ALL_LABS)


def get_lab_by_id(lab_id: str) -> LabDefinition:
    """Return a LabDefinition by ID or raise KeyError if not found."""
    if lab_id not in LABS_BY_ID:
        raise KeyError(f"Unknown lab ID: {lab_id!r}")
    return LABS_BY_ID[lab_id]


def _b64_write_cmd(rel_path: str, content: str) -> str:
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    return f"printf '%s' {shlex.quote(encoded)} | base64 -d > {shlex.quote(rel_path)}"


def _b64_eq_expr(rel_path: str, expected_content: str) -> str:
    encoded = base64.b64encode(expected_content.encode("utf-8")).decode("ascii")
    quoted = shlex.quote(rel_path)
    return f"[ -f {quoted} ] && [ \"$(base64 -w0 {quoted} 2>/dev/null || base64 {quoted} | tr -d '\\n')\" = {shlex.quote(encoded)} ]"


def _wsl_check_line(idx: int, expr: str) -> str:
    return f"if {expr}; then echo 'CHECK:{idx}:1'; else echo 'CHECK:{idx}:0'; fi"


def build_wsl_setup_script(lab_id: str) -> str:
    """Generate a pure-POSIX Bash script to initialize lab_id inside a WSL workspace."""
    get_lab_by_id(lab_id)
    if lab_id == "lab_01":
        lines = [
            "mkdir -p inbox",
            _b64_write_cmd("inbox/app.py", _LAB01_APP_PY),
            _b64_write_cmd("inbox/config.ini", _LAB01_CONFIG_INI),
            _b64_write_cmd("inbox/README.md", _LAB01_README),
        ]
    elif lab_id == "lab_02":
        lines = [
            "mkdir -p secrets scripts public",
            _b64_write_cmd("secrets/api.key", "SECRET_TOKEN=xk0-006-demo\n"),
            "chmod 644 secrets/api.key",
            _b64_write_cmd("scripts/backup.sh", "#!/bin/bash\necho 'backup ok'\n"),
            "chmod 644 scripts/backup.sh",
            _b64_write_cmd("public/readme.txt", "Public documentation\n"),
            "chmod 600 public/readme.txt",
        ]
    elif lab_id == "lab_03":
        lines = [
            "mkdir -p logs",
            _b64_write_cmd("logs/app.log", "\n".join(_LAB03_LOG_LINES) + "\n"),
        ]
    elif lab_id == "lab_04":
        lines = [
            "mkdir -p releases/v1 releases/v2",
            _b64_write_cmd("releases/v1/VERSION", "1.0.0\n"),
            _b64_write_cmd("releases/v2/VERSION", "2.0.0\n"),
        ]
    elif lab_id == "lab_05":
        lines = [
            "mkdir -p webapp/assets",
            _b64_write_cmd("webapp/index.html", "<h1>Linux+ Webapp</h1>\n"),
            _b64_write_cmd("webapp/app.js", "console.log('ready');\n"),
            _b64_write_cmd("webapp/cache.tmp", "temp cache\n"),
            _b64_write_cmd("webapp/assets/style.css", "body { margin: 0; }\n"),
            _b64_write_cmd("webapp/assets/draft.tmp", "draft temp\n"),
        ]
    elif lab_id == "lab_06":
        lines = []
        for rel, content in _LAB06_ACTIVE_FILES.items():
            parent = rel.rsplit("/", 1)[0]
            lines.append(f"mkdir -p {shlex.quote(parent)}")
            lines.append(_b64_write_cmd(rel, content))
        for rel in (
            "configs/nginx.conf.bak",
            "configs/db/postgres.conf.bak",
            "configs/db/archive/legacy.bak",
            "configs/app/settings.yaml.bak",
        ):
            parent = rel.rsplit("/", 1)[0]
            lines.append(f"mkdir -p {shlex.quote(parent)}")
            lines.append(_b64_write_cmd(rel, "backup\n"))
    elif lab_id == "lab_07":
        lines = [
            "mkdir -p logs",
            _b64_write_cmd("logs/access.log", "\n".join(_LAB07_ACCESS_LINES) + "\n"),
        ]
    elif lab_id == "lab_08":
        lines = [
            "mkdir -p scripts",
            _b64_write_cmd(
                "README.txt",
                "Create scripts/healthcheck.sh and write its output to status.out.\n",
            ),
        ]
    elif lab_id == "lab_09":
        lines = [
            "mkdir -p etc_app",
            _b64_write_cmd("etc_app/service.conf", _LAB09_ORIGINAL_CONF),
            "chmod 644 etc_app/service.conf",
        ]
    elif lab_id == "lab_10":
        lines = [
            "mkdir -p targets sensitive",
            _b64_write_cmd("targets/prod.conf", "mode=production\n"),
            "chmod 644 targets/prod.conf",
            "ln -s targets/missing.conf active.conf",
            _b64_write_cmd("sensitive/db.env", "DB_PASS=changeme\n"),
            "chmod 666 sensitive/db.env",
            _b64_write_cmd("sensitive/token.key", "TOKEN=abc123\n"),
            "chmod 777 sensitive/token.key",
            _b64_write_cmd("sensitive/notes.txt", "Internal security notes\n"),
            "chmod 644 sensitive/notes.txt",
        ]
    else:
        raise KeyError(f"Unknown lab ID: {lab_id!r}")
    return "set -e\n" + "\n".join(lines) + "\n"


def build_wsl_verify_script(lab_id: str) -> str:
    """Generate a pure-POSIX Bash script emitting CHECK:<idx>:<0|1> for lab_id."""
    get_lab_by_id(lab_id)
    lines: list[str] = []
    if lab_id == "lab_01":
        lines.extend(
            [
                _wsl_check_line(0, "[ -d project/src ] && [ -d project/config ] && [ -d project/docs ]"),
                _wsl_check_line(1, f"[ ! -e inbox/app.py ] && {_b64_eq_expr('project/src/app.py', _LAB01_APP_PY)}"),
                _wsl_check_line(2, f"[ ! -e inbox/config.ini ] && {_b64_eq_expr('project/config/config.ini', _LAB01_CONFIG_INI)}"),
                _wsl_check_line(
                    3,
                    f"{_b64_eq_expr('project/docs/README.md', _LAB01_README)} && {_b64_eq_expr('inbox/README.md', _LAB01_README)}",
                ),
            ]
        )
    elif lab_id == "lab_02":
        lines.extend(
            [
                _wsl_check_line(0, "[ -f secrets/api.key ] && [ \"$(stat -c '%a' secrets/api.key)\" = '600' ]"),
                _wsl_check_line(1, "[ -f scripts/backup.sh ] && [ \"$(stat -c '%a' scripts/backup.sh)\" = '750' ]"),
                _wsl_check_line(2, "[ -f public/readme.txt ] && [ \"$(stat -c '%a' public/readme.txt)\" = '644' ]"),
            ]
        )
    elif lab_id == "lab_03":
        expected_err = "\n".join(_LAB03_EXPECTED_ERRORS) + "\n"
        expected_err_b64 = base64.b64encode(expected_err.encode("utf-8")).decode("ascii")
        lines.extend(
            [
                _wsl_check_line(
                    0,
                    f"[ -f logs/errors.log ] && [ \"$(grep -v '^[[:space:]]*$' logs/errors.log | base64 -w0 2>/dev/null || grep -v '^[[:space:]]*$' logs/errors.log | base64 | tr -d '\\n')\" = {shlex.quote(expected_err_b64)} ]",
                ),
                _wsl_check_line(1, _b64_eq_expr("logs/app.log", "\n".join(_LAB03_LOG_LINES) + "\n")),
            ]
        )
    elif lab_id == "lab_04":
        lines.extend(
            [
                _wsl_check_line(0, "[ -L current ]"),
                _wsl_check_line(
                    1,
                    "[ -L current ] && [ -d releases/v2 ] && [ \"$(readlink -f current)\" = \"$(readlink -f releases/v2)\" ] && [ -d current ]",
                ),
                _wsl_check_line(
                    2,
                    "[ -f current/VERSION ] && [ \"$(tr -d ' \\t\\r\\n' < current/VERSION)\" = '2.0.0' ]",
                ),
            ]
        )
    elif lab_id == "lab_05":
        lines.extend(
            [
                _wsl_check_line(
                    0,
                    "[ -f webapp_backup.tar.gz ] && gzip -t webapp_backup.tar.gz >/dev/null 2>&1 && tar -tzf webapp_backup.tar.gz >/dev/null 2>&1",
                ),
                _wsl_check_line(
                    1,
                    "[ -f webapp_backup.tar.gz ] && __tl=$(tar -tzf webapp_backup.tar.gz 2>/dev/null) && "
                    "printf '%s\\n' \"$__tl\" | grep -Eq '^(\\./)?(webapp/)?index\\.html$' && "
                    "printf '%s\\n' \"$__tl\" | grep -Eq '^(\\./)?(webapp/)?app\\.js$' && "
                    "printf '%s\\n' \"$__tl\" | grep -Eq '^(\\./)?(webapp/)?assets/style\\.css$'",
                ),
                _wsl_check_line(
                    2,
                    "[ -f webapp_backup.tar.gz ] && __tl=$(tar -tzf webapp_backup.tar.gz 2>/dev/null) && "
                    "[ -n \"$__tl\" ] && ! printf '%s\\n' \"$__tl\" | grep -q '\\.tmp$'",
                ),
            ]
        )
    elif lab_id == "lab_06":
        active_checks = " && ".join(
            _b64_eq_expr(rel, content) for rel, content in _LAB06_ACTIVE_FILES.items()
        )
        lines.extend(
            [
                _wsl_check_line(0, "[ -d configs ] && [ -z \"$(find configs -type f -name '*.bak' 2>/dev/null)\" ]"),
                _wsl_check_line(1, active_checks),
            ]
        )
    elif lab_id == "lab_07":
        expected_ips = "\n".join(_LAB07_EXPECTED_IPS) + "\n"
        expected_ips_b64 = base64.b64encode(expected_ips.encode("utf-8")).decode("ascii")
        lines.append(
            _wsl_check_line(
                0,
                f"[ -f unique_ips.txt ] && [ \"$(sed 's/^[[:space:]]*//; s/[[:space:]]*$//' unique_ips.txt | grep -v '^$' | base64 -w0 2>/dev/null || sed 's/^[[:space:]]*//; s/[[:space:]]*$//' unique_ips.txt | grep -v '^$' | base64 | tr -d '\\n')\" = {shlex.quote(expected_ips_b64)} ]",
            )
        )
    elif lab_id == "lab_08":
        lines.extend(
            [
                _wsl_check_line(
                    0,
                    "[ -f scripts/healthcheck.sh ] && [ \"$(head -n 1 scripts/healthcheck.sh | tr -d '\\r' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')\" = '#!/bin/bash' ]",
                ),
                _wsl_check_line(1, "[ -f scripts/healthcheck.sh ] && [ -x scripts/healthcheck.sh ]"),
                _wsl_check_line(
                    2,
                    "[ -f scripts/healthcheck.sh ] && [ -x scripts/healthcheck.sh ] && "
                    "[ \"$(head -n 1 scripts/healthcheck.sh | tr -d '\\r' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')\" = '#!/bin/bash' ] && "
                    "__out=$(./scripts/healthcheck.sh 2>/dev/null) && [ $? -eq 0 ] && "
                    "[ \"$(printf '%s' \"$__out\" | tr -d ' \\t\\r\\n')\" = 'SYSTEM_OK' ]",
                ),
                _wsl_check_line(
                    3,
                    "[ -f status.out ] && [ \"$(tr -d ' \\t\\r\\n' < status.out)\" = 'SYSTEM_OK' ]",
                ),
            ]
        )
    elif lab_id == "lab_09":
        lines.extend(
            [
                _wsl_check_line(0, _b64_eq_expr("etc_app/service.conf.bak", _LAB09_ORIGINAL_CONF)),
                _wsl_check_line(
                    1,
                    "[ -f etc_app/service.conf ] && "
                    "grep -Eq '^[[:space:]]*APP_NAME=linux-plus-api[[:space:]]*$' etc_app/service.conf && "
                    "grep -Eq '^[[:space:]]*PORT=8443[[:space:]]*$' etc_app/service.conf && "
                    "grep -Eq '^[[:space:]]*DEBUG=false[[:space:]]*$' etc_app/service.conf && "
                    "grep -Eq '^[[:space:]]*LOG_LEVEL=debug[[:space:]]*$' etc_app/service.conf && "
                    "! grep -Eq '^[[:space:]]*PORT=8080[[:space:]]*$' etc_app/service.conf && "
                    "! grep -Eq '^[[:space:]]*DEBUG=true[[:space:]]*$' etc_app/service.conf",
                ),
                _wsl_check_line(2, "[ -f etc_app/service.conf ] && [ \"$(stat -c '%a' etc_app/service.conf)\" = '640' ]"),
            ]
        )
    elif lab_id == "lab_10":
        lines.extend(
            [
                _wsl_check_line(
                    0,
                    "[ -L active.conf ] && [ -f targets/prod.conf ] && [ \"$(readlink -f active.conf)\" = \"$(readlink -f targets/prod.conf)\" ] && [ -f active.conf ]",
                ),
                _wsl_check_line(
                    1,
                    "[ -f sensitive/db.env ] && [ -f sensitive/token.key ] && [ -f sensitive/notes.txt ] && "
                    "[ $(( (0$(stat -c '%a' sensitive/db.env) & 2) )) -eq 0 ] && "
                    "[ $(( (0$(stat -c '%a' sensitive/token.key) & 2) )) -eq 0 ] && "
                    "[ $(( (0$(stat -c '%a' sensitive/notes.txt) & 2) )) -eq 0 ]",
                ),
                _wsl_check_line(
                    2,
                    "[ -f audit_report.txt ] && grep -q 'active\\.conf' audit_report.txt && "
                    "grep -q 'db\\.env' audit_report.txt && grep -q 'token\\.key' audit_report.txt",
                ),
            ]
        )
    return "\n".join(lines) + "\n"
