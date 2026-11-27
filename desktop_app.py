"""Native desktop window launcher backed by an ephemeral localhost Flask server."""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Callable
import webbrowser

from rich.console import Console
from rich.panel import Panel
from werkzeug.serving import BaseWSGIServer, make_server

from web_app import create_app

APP_TITLE = "CompTIA Linux+ (XK0-006 / V8) Study Trainer"


class LocalServerHandle:
    """Manages a background Werkzeug/Flask HTTP server bound to an ephemeral port."""

    def __init__(self) -> None:
        self.server: BaseWSGIServer | None = None
        self.thread: threading.Thread | None = None
        self.flask_app = None
        self.host: str = "127.0.0.1"
        self.port: int = 0
        self.url: str = ""

    def start(
        self,
        questions_dir: Path | None = None,
        progress_path: Path | None = None,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> LocalServerHandle:
        """Create the Flask app, bind to (host, port), and start serving in a daemon thread."""
        flask_app = create_app(questions_dir=questions_dir, progress_path=progress_path)
        server = make_server(host, int(port), flask_app, threaded=True)
        self.flask_app = flask_app
        self.server = server
        self.host = host
        self.port = int(server.server_port)
        self.url = f"http://{host}:{self.port}"
        self.thread = threading.Thread(
            target=server.serve_forever,
            name="linux-plus-desktop-server",
            daemon=True,
        )
        self.thread.start()
        return self

    def stop(self) -> None:
        """Shut down the HTTP server and clean up any active sandbox lab sessions."""
        if self.server is not None:
            try:
                self.server.shutdown()
            except Exception:
                pass
            try:
                self.server.server_close()
            except Exception:
                pass
            self.server = None
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        self.thread = None
        if self.flask_app is not None:
            lab_sessions = self.flask_app.extensions.get("lab_sessions", {})
            for sb in list(lab_sessions.values()):
                try:
                    sb.cleanup()
                except Exception:
                    pass
            lab_sessions.clear()
            self.flask_app = None

    def __enter__(self) -> LocalServerHandle:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.stop()


def _launch_pywebview(url: str, title: str, width: int, height: int) -> bool:
    """Open url in a pywebview native window. Returns False if unavailable or failed."""
    try:
        import webview  # type: ignore[import-not-found]
    except ImportError:
        return False

    try:
        webview.create_window(
            title,
            url,
            width=width,
            height=height,
            min_size=(960, 640),
        )
        webview.start()
        return True
    except Exception:
        return False


def _safe_open_browser(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception:
        pass


def run_desktop_app(
    questions_dir: Path | None = None,
    progress_path: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 0,
    open_browser_fallback: bool = True,
    title: str = APP_TITLE,
    width: int = 1280,
    height: int = 840,
    console: Console | None = None,
    wait_for_interrupt: Callable[[], None] | None = None,
) -> int:
    """Start the local Flask server and display the trainer in a native desktop window.

    Falls back to opening the default web browser if pywebview or a system WebView
    backend is unavailable.
    """
    active_console = console or Console()
    handle = LocalServerHandle().start(
        questions_dir=questions_dir,
        progress_path=progress_path,
        host=host,
        port=port,
    )
    try:
        if _launch_pywebview(handle.url, title=title, width=width, height=height):
            return 0

        active_console.print(
            Panel(
                f"[bold white]Native WebView unavailable; opening in your default browser:[/bold white]\n"
                f"[bold cyan]{handle.url}[/bold cyan]\n\n"
                "[bold yellow]Press Ctrl+C to stop the trainer server.[/bold yellow]",
                title="[bold magenta]Desktop Window Fallback[/bold magenta]",
                border_style="magenta",
                padding=(1, 2),
            )
        )
        if open_browser_fallback:
            _safe_open_browser(handle.url)

        if wait_for_interrupt is not None:
            wait_for_interrupt()
        else:
            try:
                while handle.thread is not None and handle.thread.is_alive():
                    handle.thread.join(timeout=0.5)
            except KeyboardInterrupt:
                active_console.print("\n[yellow]Trainer server stopped.[/yellow]")
        return 0
    finally:
        handle.stop()


if __name__ == "__main__":
    raise SystemExit(run_desktop_app())
