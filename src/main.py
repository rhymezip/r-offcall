import sys
import os

# Her kosulda calisir — cwd, venv, symlink farketmez
SRC  = os.path.dirname(os.path.realpath(os.path.abspath(__file__)))
ROOT = os.path.dirname(SRC)
if SRC  not in sys.path: sys.path.insert(0, SRC)
if ROOT not in sys.path: sys.path.insert(0, ROOT)

import threading
import time
import asyncio
import platform
import webview

from discovery import HostDiscovery, PORT
import permissions

discovery = HostDiscovery()
is_host   = False
_window   = None


def _pick_gui():
    # Linux: QtWebEngine (Chromium) supports getDisplayMedia.
    if platform.system() != "Linux":
        return None
    for mod in ("PyQt6.QtWebEngineWidgets",):
        try:
            import importlib
            importlib.import_module(mod)
            print(f"[App] Linux: Qt backend ({mod})")
            return "qt"
        except ImportError:
            continue
    print("[App] Linux: QtWebEngine bulunamadı")
    return None


# ── Host / Client ────────────────────────────────────────────────
LOCAL_UI_PORT = PORT + 1  # client modunda UI loopback'ta sunulur (guvenli origin)


def _pick_local_port():
    import socket
    for port in range(LOCAL_UI_PORT, LOCAL_UI_PORT + 10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return LOCAL_UI_PORT


def find_or_become_host():
    global is_host
    discovery.start_browsing()
    time.sleep(2)
    hosts = discovery.get_hosts()
    if hosts:
        ip, port = list(hosts.values())[0]
        print(f"[App] Host found: {ip}:{port}")
        ui_port = _pick_local_port()
        # UI'yi loopback'ten sun — Chromium http://<LAN-ip> originlerini
        # guvenli saymaz (navigator.mediaDevices yok), loopback ise guvenlidir.
        _start_server("127.0.0.1", ui_port)
        return f"http://127.0.0.1:{ui_port}", f"http://{ip}:{port}"
    print("[App] No host — becoming host")
    is_host = True
    _start_server()
    discovery.register_as_host()
    return f"http://127.0.0.1:{PORT}", f"http://{discovery.get_local_ip()}:{PORT}"


# ── Server ───────────────────────────────────────────────────────
def _start_server(bind_host="0.0.0.0", port=PORT):
    """Start the local signaling/static server and wait until it listens."""
    started = threading.Event()
    failure = []

    def run():
        import server as srv
        from aiohttp import web
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def start():
            runner = web.AppRunner(srv.app)
            await runner.setup()
            try:
                site = web.TCPSite(runner, bind_host, port)
                await site.start()
                print(f"[Server] Running on {bind_host}:{port}")
            except Exception as exc:
                failure.append(exc)
            finally:
                started.set()

            if failure:
                await runner.cleanup()
                return
            while True:
                await asyncio.sleep(3600)

        try:
            loop.run_until_complete(start())
        except Exception as exc:
            failure.append(exc)
            started.set()

    threading.Thread(target=run, daemon=True).start()
    if not started.wait(timeout=8):
        raise RuntimeError(f"Server did not start on {bind_host}:{port}")
    if failure:
        raise RuntimeError(f"Could not start server on {bind_host}:{port}: {failure[0]}")


# ── Window events ────────────────────────────────────────────────
def _screen_capture_supported() -> bool:
    """QtWebEngine 6.x+ ekran paylasimini (getDisplayMedia) destekler;
    Qt 5.15 / WebKitGTK / WKWebView desteklemez."""
    if platform.system() != "Linux":
        return False
    try:
        import webview.platforms.qt as qtmod
        return bool(getattr(qtmod, "_qt6", False))
    except Exception:
        return False


def _select_desktop_media(req):
    """Select the first available screen (or window) for a Qt request.

    Qt exposes desktop choices through list models. Passing ``0`` directly is
    invalid; the API needs ``model.index(0, 0)``.
    """
    try:
        model = req.screensModel()
        if model is None or model.rowCount() < 1:
            raise RuntimeError("No screen is available")
        req.selectScreen(model.index(0, 0))
        print("[App] Screen capture: primary screen selected")
        return True
    except Exception as screen_error:
        try:
            model = req.windowsModel()
            if model is None or model.rowCount() < 1:
                raise RuntimeError("No window is available")
            req.selectWindow(model.index(0, 0))
            print("[App] Screen capture: first window selected")
            return True
        except Exception as window_error:
            print(f"[App] Screen capture secilemedi: {screen_error} / {window_error}")
            return False


def _hook_desktop_media():
    """Connect Qt 6's desktop-media signal after the page has loaded."""
    if not _screen_capture_supported():
        return

    try:
        import webview.platforms.qt as qtmod
        for bv in list(qtmod.BrowserView.instances.values()):
            # pywebview 5 calls this ``view``; version 6 calls it ``webview``.
            view = getattr(bv, "webview", None) or getattr(bv, "view", None)
            if view is None:
                continue
            page = view.page()
            if hasattr(page, "desktopMediaRequested"):
                if getattr(page, "_roffcall_desktop_hooked", False):
                    continue
                page.desktopMediaRequested.connect(_select_desktop_media)
                page._roffcall_desktop_hooked = True
                print("[App] desktopMediaRequested hook OK")
    except Exception as e:
        print(f"[App] desktopMedia hook: {e}")


def on_loaded():
    global _window
    system = platform.system()
    print(f"[App] Loaded ({system})")

    if system == "Linux":
        _hook_desktop_media()


def on_closed():
    discovery.close()


# ── JS API ───────────────────────────────────────────────────────
class JSApi:
    def __init__(self, server_url, real_ip_url=None):
        self._url = server_url
        self._real_url = real_ip_url or server_url

    def get_server_url(self):  return self._real_url
    def get_local_ip(self):    return discovery.get_local_ip()
    def get_is_host(self):     return is_host
    def exit_app(self):
        # JS-API thread'inden destroy cagirmak bazi surumlerde kilitlenebiliyor.
        # Cagriyi hemen dondur, kapamayi ayri thread'de yap; 2sn icinde
        # kapanmazsa zorla cik.
        global _window

        def _close():
            try:
                if _window:
                    _window.destroy()
            except Exception as e:
                print(f"[App] exit_app destroy: {e}")

        threading.Thread(target=_close, daemon=True).start()
        threading.Timer(2.0, lambda: os._exit(0)).start()
        return True
    def prepare_permissions(self):
        return permissions.setup_blocking(_window, delay=0.0)
    def get_permission_status(self):
        return permissions.status()
    def screen_share_supported(self):
        return _screen_capture_supported()


# ── Main ─────────────────────────────────────────────────────────
def main():
    global _window
    server_url, real_ip_url = find_or_become_host()
    url = server_url.rstrip("/") + "/"
    print(f"[App] Loading: {url}")

    _window = webview.create_window(
        "r-offcall",
        url=url,
        width=1280,
        height=800,
        min_size=(960, 640),
        background_color="#0f0f0f",
        js_api=JSApi(server_url, real_ip_url),
    )
    _window.events.loaded += on_loaded
    _window.events.closed += on_closed

    # Must run before pywebview creates the WKWebView; doing this from JS after
    # a capture request is too late and causes silent denials on macOS clients.
    permissions.install_webview_permissions()
    webview.start(debug=False, gui=_pick_gui())


if __name__ == "__main__":
    main()
