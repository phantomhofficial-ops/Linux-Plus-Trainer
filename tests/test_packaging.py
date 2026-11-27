"""Unit tests for Desktop Window Mode, frozen auto-launch, and packaging metadata."""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import MagicMock, patch
import urllib.request
import xml.etree.ElementTree as ET

from rich.console import Console

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app as cli_app  # noqa: E402
import desktop_app  # noqa: E402


class AppDesktopModeTests(unittest.TestCase):
    """Verify --desktop CLI flag, startup selector, and frozen binary auto-launch."""

    def test_parse_args_desktop_and_mutual_exclusivity(self) -> None:
        args = cli_app.parse_args(["--desktop"])
        self.assertTrue(args.desktop)
        self.assertFalse(args.terminal)
        self.assertFalse(args.web)

        with self.assertRaises(SystemExit):
            cli_app.parse_args(["--desktop", "--terminal"])
        with self.assertRaises(SystemExit):
            cli_app.parse_args(["--desktop", "--web"])

    def test_main_desktop_flag_and_frozen_auto_launch(self) -> None:
        with patch.object(cli_app, "launch_desktop_mode", return_value=0) as mock_desk:
            rc = cli_app.main(["--desktop"])
            self.assertEqual(rc, 0)
            mock_desk.assert_called_once()

        # Frozen binary with no flags launches desktop mode directly without prompting
        with patch.object(sys, "frozen", True, create=True), patch.object(
            cli_app, "launch_desktop_mode", return_value=0
        ) as mock_desk, patch.object(
            cli_app, "select_startup_mode"
        ) as mock_selector:
            rc = cli_app.main([])
            self.assertEqual(rc, 0)
            mock_desk.assert_called_once()
            mock_selector.assert_not_called()

        # Frozen binary still respects --terminal and --web overrides
        with patch.object(sys, "frozen", True, create=True), patch.object(
            cli_app, "run_terminal_app", return_value=0
        ) as mock_term:
            rc = cli_app.main(["--terminal"])
            self.assertEqual(rc, 0)
            mock_term.assert_called_once()

        with patch.object(sys, "frozen", True, create=True), patch.object(
            cli_app, "launch_web_mode", return_value=0
        ) as mock_web:
            rc = cli_app.main(["--web", "--port", "5051"])
            self.assertEqual(rc, 0)
            mock_web.assert_called_once()
            self.assertEqual(mock_web.call_args.kwargs["port"], 5051)


class DesktopAppTests(unittest.TestCase):
    """Verify LocalServerHandle ephemeral port binding and pywebview/browser fallback."""

    def test_local_server_handle_binds_ephemeral_port_and_serves_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            progress_path = Path(tmpdir) / "progress.json"
            with desktop_app.LocalServerHandle().start(
                questions_dir=PROJECT_ROOT / "data" / "questions",
                progress_path=progress_path,
                port=0,
            ) as handle:
                self.assertGreater(handle.port, 0)
                self.assertTrue(handle.url.startswith("http://127.0.0.1:"))
                with urllib.request.urlopen(f"{handle.url}/api/state", timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    payload = json.loads(resp.read().decode("utf-8"))
                    self.assertGreaterEqual(payload["total_questions"], 45)

    def test_run_desktop_app_uses_pywebview_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            progress_path = Path(tmpdir) / "progress.json"
            fake_webview = MagicMock()
            console = Console(file=io.StringIO(), force_terminal=False)

            with patch.dict(sys.modules, {"webview": fake_webview}), patch.object(
                desktop_app.webbrowser, "open"
            ) as mock_browser:
                rc = desktop_app.run_desktop_app(
                    questions_dir=PROJECT_ROOT / "data" / "questions",
                    progress_path=progress_path,
                    console=console,
                )
                self.assertEqual(rc, 0)
                fake_webview.create_window.assert_called_once()
                fake_webview.start.assert_called_once()
                mock_browser.assert_not_called()

    def test_run_desktop_app_falls_back_to_browser_when_webview_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            progress_path = Path(tmpdir) / "progress.json"
            out = io.StringIO()
            console = Console(file=out, force_terminal=False)
            seen_urls: list[str] = []

            with patch.object(
                desktop_app, "_launch_pywebview", return_value=False
            ), patch.object(
                desktop_app.webbrowser,
                "open",
                side_effect=lambda u: seen_urls.append(u) or True,
            ):
                rc = desktop_app.run_desktop_app(
                    questions_dir=PROJECT_ROOT / "data" / "questions",
                    progress_path=progress_path,
                    open_browser_fallback=True,
                    console=console,
                    wait_for_interrupt=lambda: None,
                )
                self.assertEqual(rc, 0)
                self.assertEqual(len(seen_urls), 1)
                self.assertTrue(seen_urls[0].startswith("http://127.0.0.1:"))
                self.assertIn("http://127.0.0.1:", out.getvalue())


class PackagingMetadataValidationTests(unittest.TestCase):
    """Validate pyproject.toml, GitHub Actions workflow, PyInstaller spec, and OS installers."""

    def test_pyproject_toml_valid_and_defines_console_script(self) -> None:
        pyproject_path = PROJECT_ROOT / "pyproject.toml"
        self.assertTrue(pyproject_path.is_file())
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

        self.assertEqual(data["project"]["name"], "linux-plus-trainer")
        self.assertEqual(data["project"]["scripts"]["linuxplus"], "app:main")
        self.assertIn("rich>=13.0.0", data["project"]["dependencies"])
        self.assertIn("flask>=3.0.0", data["project"]["dependencies"])
        self.assertIn("pywebview>=5.0", data["project"]["optional-dependencies"]["desktop"])
        self.assertIn("pyinstaller>=6.0", data["project"]["optional-dependencies"]["packaging"])

    def test_github_release_workflow_syntax_and_jobs(self) -> None:
        workflow_path = PROJECT_ROOT / ".github" / "workflows" / "release.yml"
        self.assertTrue(workflow_path.is_file())
        content = workflow_path.read_text(encoding="utf-8")

        # YAML forbids literal tab indentation
        self.assertNotIn("\t", content, "release.yml must not contain tab characters")
        for idx, line in enumerate(content.splitlines(), start=1):
            stripped = line.lstrip(" ")
            if stripped and not stripped.startswith("#"):
                indent = len(line) - len(stripped)
                self.assertEqual(
                    indent % 2, 0, f"release.yml line {idx} has odd indentation: {line!r}"
                )

        for expected in (
            "workflow_dispatch:",
            "v*",
            "test:",
            "build-windows:",
            "build-macos:",
            "build-linux:",
            "release:",
            "LinuxPlusTrainer-Setup-Windows.exe",
            "LinuxPlusTrainer-macOS.dmg",
            "LinuxPlusTrainer-x86_64.AppImage",
        ):
            self.assertIn(expected, content)

    def test_packaging_files_and_xml_valid(self) -> None:
        required_files = [
            PROJECT_ROOT / "requirements-packaging.txt",
            PROJECT_ROOT / "PACKAGING.md",
            PROJECT_ROOT / "packaging" / "linux-plus-trainer.spec",
            PROJECT_ROOT / "packaging" / "assets" / "linux-plus-trainer.svg",
            PROJECT_ROOT / "packaging" / "scripts" / "generate_icons.py",
            PROJECT_ROOT / "packaging" / "windows" / "installer.iss",
            PROJECT_ROOT / "packaging" / "linux" / "io.github.linuxplustrainer.LinuxPlusTrainer.desktop",
            PROJECT_ROOT / "packaging" / "linux" / "io.github.linuxplustrainer.LinuxPlusTrainer.metainfo.xml",
            PROJECT_ROOT / "packaging" / "flatpak" / "io.github.linuxplustrainer.LinuxPlusTrainer.yml",
        ]
        for path in required_files:
            self.assertTrue(path.is_file(), f"Missing packaging file: {path}")

        # Validate AppStream XML and SVG XML parse cleanly
        ET.parse(
            PROJECT_ROOT / "packaging" / "linux" / "io.github.linuxplustrainer.LinuxPlusTrainer.metainfo.xml"
        )
        ET.parse(PROJECT_ROOT / "packaging" / "assets" / "linux-plus-trainer.svg")


if __name__ == "__main__":
    unittest.main()
