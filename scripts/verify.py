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

    def screensModel(self):
        return self._screens

    def windowsModel(self):
        return self._windows

    def selectScreen(self, index):
        self.selected = ("screen", index)

    def selectWindow(self, index):
        self.selected = ("window", index)


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

    assert not main._select_desktop_media(DesktopRequest(screens=0, windows=0))
    asyncio.run(check_static_server())
    main.on_closed()
    print("Verification passed")


if __name__ == "__main__":
    main()
