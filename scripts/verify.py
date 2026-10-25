#!/usr/bin/env python3
"""Fast, deterministic checks for r-offcall's platform-independent core.

Run from the repository root with the project virtual environment active:
``python scripts/verify.py``.
"""

from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


class Model:
    def __init__(self, rows: int):
        self.rows = rows

    def rowCount(self):
        return self.rows

    def index(self, row, column):
        return (row, column)


class DesktopRequest:
    def __init__(self, screens: int = 1, windows: int = 0):
        self._screens = Model(screens)
        self._windows = Model(windows)
        self.selected = None
        self.cancelled = False

    def screensModel(self):
        return self._screens

    def windowsModel(self):
        return self._windows

    def selectScreen(self, index):
        self.selected = ("screen", index)

    def selectWindow(self, index):
        self.selected = ("window", index)

    def cancel(self):
        self.cancelled = True


def check_desktop_capture_setup() -> None:
    import main
    import webview.platforms

    pending = []
    settings = SimpleNamespace(setAttribute=Mock())
    signal = SimpleNamespace(connect=Mock())
    page = SimpleNamespace(settings=lambda: settings, desktopMediaRequested=signal)
    browser = SimpleNamespace(
        webview=SimpleNamespace(page=lambda: page),
        create_window_trigger=SimpleNamespace(emit=pending.append),
    )
    qt = SimpleNamespace(
        BrowserView=SimpleNamespace(instances={"test": browser}),
        QWebEngineSettings=SimpleNamespace(
            WebAttribute=SimpleNamespace(ScreenCaptureEnabled="screen-capture")
        ),
    )
    with (
        patch.dict(sys.modules, {"webview.platforms.qt": qt}),
        patch.object(webview.platforms, "qt", qt, create=True),
        patch.object(main.platform, "system", return_value="Darwin"),
        patch.object(main, "_gui", "qt"),
    ):
        main._hook_desktop_media()
        settings.setAttribute.assert_not_called()
        assert len(pending) == 1  # GUI work must be dispatched, not run here.
        pending.pop()()
        settings.setAttribute.assert_called_with("screen-capture", True)
        signal.connect.assert_called_once_with(main._select_desktop_media)
        main._hook_desktop_media()
        pending.pop()()
        signal.connect.assert_called_once()  # Reload must not duplicate handlers.

        with patch.object(main.platform, "system", return_value="Linux"):
            main._hook_desktop_media()
            assert not pending
        with patch.object(main, "_gui", None):
            main._hook_desktop_media()
            assert not pending


def check_qt_capture_permissions() -> None:
    import main
    import webview.platforms

    class Page:
        setFeaturePermission = Mock()

    original_append = Mock()
    qt = SimpleNamespace(
        environ_append=original_append,
        BrowserView=SimpleNamespace(WebPage=Page),
        QWebPage=SimpleNamespace(
            Feature=SimpleNamespace(
                DesktopVideoCapture="screen", MediaAudioCapture="mic",
                MediaVideoCapture="camera", MediaAudioVideoCapture="camera-mic",
            ),
            PermissionPolicy=SimpleNamespace(
                PermissionGrantedByUser="grant", PermissionDeniedByUser="deny",
            ),
        ),
    )
    with (
        patch.dict(sys.modules, {"webview.platforms.qt": qt}),
        patch.object(webview.platforms, "qt", qt, create=True),
        patch.object(main.platform, "system", return_value="Darwin"),
        patch.object(main, "_gui", "qt"),
    ):
        main.on_initialized("qtwebengine")
        handler = Page.onFeaturePermissionRequested
        append = qt.environ_append
        main.on_initialized("qtwebengine")
        assert Page.onFeaturePermissionRequested is handler
        assert qt.environ_append is append
        qt.environ_append(
            "QTWEBENGINE_CHROMIUM_FLAGS", "--use-fake-ui-for-media-stream",
            "--enable-features=AutoplayIgnoreWebAudio",
        )
        original_append.assert_called_once_with(
            "QTWEBENGINE_CHROMIUM_FLAGS", "--enable-features=AutoplayIgnoreWebAudio", sep=" "
        )
        page = Page()
        origin = SimpleNamespace(scheme=lambda: "http", host=lambda: "127.0.0.1")
        page.onFeaturePermissionRequested(origin, "screen")
        page.setFeaturePermission.assert_called_with(origin, "screen", "grant")
        remote = SimpleNamespace(scheme=lambda: "https", host=lambda: "example.com")
        page.onFeaturePermissionRequested(remote, "screen")
        page.setFeaturePermission.assert_called_with(remote, "screen", "deny")
        for feature in ("mic", "camera", "camera-mic"):
            page.onFeaturePermissionRequested(origin, feature)
            page.setFeaturePermission.assert_called_with(origin, feature, "grant")
        page.onFeaturePermissionRequested(origin, "geolocation")
        page.setFeaturePermission.assert_called_with(origin, "geolocation", "deny")


def check_screen_recording_permissions() -> None:
    import main
    import permissions

    quartz = SimpleNamespace(
        CGPreflightScreenCaptureAccess=Mock(return_value=True),
        CGRequestScreenCaptureAccess=Mock(return_value=False),
    )
    with (
        patch.dict(sys.modules, {"Quartz": quartz}),
        patch.object(permissions.platform, "system", return_value="Darwin"),
        patch.object(permissions, "_set_usage_descriptions"),
        patch.object(permissions, "_request_av_permissions") as request_av,
    ):
        assert permissions.request_screen_capture_permission() == {
            "granted": True, "requested": False
        }
        quartz.CGRequestScreenCaptureAccess.assert_not_called()
        quartz.CGPreflightScreenCaptureAccess.return_value = False
        assert permissions.request_screen_capture_permission() == {
            "granted": False, "requested": True
        }
        quartz.CGRequestScreenCaptureAccess.return_value = True
        assert permissions.request_screen_capture_permission() == {
            "granted": True, "requested": True
        }
        request_av.assert_not_called()  # Screen approval must not alter AV flow.
        with patch.object(main, "_gui", None):
            assert main.JSApi("http://localhost").prepare_screen_capture() == {
                "supported": False, "granted": False, "requested": False
            }
        with patch.object(main, "_gui", "qt"):
            assert main.JSApi("http://localhost").prepare_screen_capture() == {
                "supported": True, "granted": True, "requested": True
            }
        quartz.CGPreflightScreenCaptureAccess.side_effect = RuntimeError("unavailable")
        assert permissions.request_screen_capture_permission() == {
            "granted": False, "requested": False, "error": "unavailable"
        }
        with patch.object(permissions.platform, "system", return_value="Windows"):
            quartz.CGRequestScreenCaptureAccess.reset_mock()
            assert permissions.request_screen_capture_permission() == {
                "granted": True, "requested": False
            }
            quartz.CGRequestScreenCaptureAccess.assert_not_called()


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def check_static_server() -> None:
    from aiohttp import ClientSession, web
    import server

    runner = web.AppRunner(server.app)
    await runner.setup()
    port = available_port()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    try:
        async with ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{port}/") as response:
                body = await response.text()
                assert response.status == 200
                assert "r-offcall" in body
    finally:
        await runner.cleanup()


def main() -> None:
    import py_compile
    import main
    from discovery import SERVICE_TYPE, _service_name_for_host

    for source in SRC.glob("*.py"):
        py_compile.compile(str(source), doraise=True)

    assert _service_name_for_host("Lab Mac #12") == (
        "r-offcall-Lab-Mac--12." + SERVICE_TYPE
    )
    assert _service_name_for_host("---") == "r-offcall-host." + SERVICE_TYPE

    screen_request = DesktopRequest(screens=1)
    assert main._select_desktop_media(screen_request)
    assert screen_request.selected == ("screen", (0, 0))

    window_request = DesktopRequest(screens=0, windows=1)
    assert main._select_desktop_media(window_request)
    assert window_request.selected == ("window", (0, 0))

    empty_request = DesktopRequest(screens=0, windows=0)
    assert not main._select_desktop_media(empty_request)
    assert empty_request.cancelled
    check_desktop_capture_setup()
    check_qt_capture_permissions()
    check_screen_recording_permissions()
    asyncio.run(check_static_server())
    main.on_closed()
    print("Verification passed")


if __name__ == "__main__":
    main()
