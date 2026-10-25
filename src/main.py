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

discovery = None
is_host = False
_window = None
_gui = None


def _discovery() -> HostDiscovery:
    """Create the mDNS client only when the desktop app actually starts.

    This keeps importing the module safe for deterministic checks and tools
    that do not have permission to open multicast sockets.
    """
    global discovery
    if discovery is None:
        discovery = HostDiscovery()
    return discovery


def _pick_gui():
    """Use Qt6 WebEngine where desktop screen capture is supported.

    macOS defaults to WKWebView in pywebview. Its media-capture delegate
    interferes with getDisplayMedia on affected WebKit versions, so macOS uses
    the same Chromium-based Qt renderer as the supported desktop path.
    """
    system = platform.system()
    if system not in ("Linux", "Darwin"):
        return None
    for mod in ("PyQt6.QtWebEngineWidgets",):
        try:
            import importlib
            importlib.import_module(mod)
            print(f"[App] {system}: Qt backend ({mod})")
            return "qt"
        except ImportError:
            continue
    print(f"[App] {system}: QtWebEngine bulunamadı")
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
    host_discovery = _discovery()
    host_discovery.start_browsing()
    time.sleep(2)
    hosts = host_discovery.get_hosts()
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
    host_discovery.register_as_host()
    return f"http://127.0.0.1:{PORT}", f"http://{host_discovery.get_local_ip()}:{PORT}"


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
def on_initialized(renderer):
    """Keep Qt's real desktop picker and permit capture for our loopback UI."""
    if platform.system() != "Darwin" or _gui != "qt" or renderer != "qtwebengine":
        return
    import webview.platforms.qt as qtmod

    if getattr(qtmod, "_roffcall_capture_configured", False):
        return
    original_append = qtmod.environ_append

    def append_flags(key, *values, sep=" "):
        if key == "QTWEBENGINE_CHROMIUM_FLAGS":
            # pywebview adds this for AV permission automation. Chromium also
            # uses it for display capture, bypassing Qt's desktop picker.
            values = tuple(v for v in values if v != "--use-fake-ui-for-media-stream")
        original_append(key, *values, sep=sep)

    def media_permission(page, origin, feature):
        feature_type = qtmod.QWebPage.Feature
        policy = qtmod.QWebPage.PermissionPolicy
        if feature == feature_type.DesktopVideoCapture:
            local = origin.scheme() in ("http", "https") and origin.host() in (
                "127.0.0.1", "localhost", "::1"
            )
            page.setFeaturePermission(
                origin, feature,
                policy.PermissionGrantedByUser if local else policy.PermissionDeniedByUser,
            )
            print(f"[App] Qt desktop permission: {'granted' if local else 'denied'}")
        elif feature in (
            feature_type.MediaAudioCapture,
            feature_type.MediaVideoCapture,
            feature_type.MediaAudioVideoCapture,
        ):
            # Same AV policy as pywebview, using Qt6's required enum instead
            # of its integer policy (which PyQt6 rejects).
            page.setFeaturePermission(origin, feature, policy.PermissionGrantedByUser)
        else:
            page.setFeaturePermission(origin, feature, policy.PermissionDeniedByUser)

    qtmod.environ_append = append_flags
    qtmod.BrowserView.WebPage.onFeaturePermissionRequested = media_permission
    qtmod._roffcall_capture_configured = True
    print("[App] Qt native desktop capture configured")


def _screen_capture_supported() -> bool:
    """Screen sharing via getDisplayMedia is supported on macOS (WKWebView or Qt)."""
    return platform.system() == "Darwin"


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
            if hasattr(req, "cancel"):
                req.cancel()
            return False

def _hook_desktop_media():
    """Enable Qt screen capture and install its handler on Qt's GUI thread."""
    if not _screen_capture_supported() or _gui != "qt":
        return

    try:
        import webview.platforms.qt as qtmod

        def configure(bv):
            try:
                # pywebview 5 calls this ``view``; version 6 calls it ``webview``.
                view = getattr(bv, "webview", None) or getattr(bv, "view", None)
                if view is None:
                    return
                page = view.page()
                if not hasattr(page, "desktopMediaRequested"):
                    print("[App] Qt WebEngine does not support desktop capture")
                    return
                # Qt disables getDisplayMedia by default, even with a handler.
                page.settings().setAttribute(
                    qtmod.QWebEngineSettings.WebAttribute.ScreenCaptureEnabled, True
                )
                if not getattr(page, "_roffcall_desktop_hooked", False):
                    page.desktopMediaRequested.connect(_select_desktop_media)
                    page._roffcall_desktop_hooked = True
                    print("[App] Desktop capture enabled and handler ready")
            except Exception as exc:
                print(f"[App] Desktop capture setup failed: {exc}")

        # The loaded event runs on a pywebview worker. Use its existing Qt
        # dispatcher so both settings and the signal receiver live on the GUI
        # thread; a worker-thread receiver otherwise has no Qt event loop.
        for bv in list(qtmod.BrowserView.instances.values()):
            bv.create_window_trigger.emit(lambda bv=bv: configure(bv))
    except Exception as exc:
        print(f"[App] desktopMedia hook: {exc}")


def on_loaded():
    global _window
    system = platform.system()
    print(f"[App] Loaded ({system})")

    if system == "Darwin":
        _hook_desktop_media()


def on_closed():
    if discovery is not None:
        discovery.close()


# ── JS API ───────────────────────────────────────────────────────
class JSApi:
    def __init__(self, server_url, real_ip_url=None):
        self._url = server_url
        self._real_url = real_ip_url or server_url

    def get_server_url(self):  return self._real_url
    def get_local_ip(self):    return _discovery().get_local_ip()
    def get_is_host(self):     return is_host
    def get_platform(self):    return platform.system()
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
    def prepare_screen_capture(self):
        if platform.system() == "Darwin" and _gui != "qt":
            return {"supported": False, "granted": False, "requested": False}
        return {"supported": True, **permissions.request_screen_capture_permission()}
    def screen_share_supported(self):
        return _screen_capture_supported()


# ── Main ─────────────────────────────────────────────────────────
def main():
    global _window, _gui
    server_url, real_ip_url = find_or_become_host()
    _gui = _pick_gui()
    permissions.configure_backend(_gui)
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
    _window.events.initialized += on_initialized
    _window.events.loaded += on_loaded
    _window.events.closed += on_closed

    # Only the WKWebView fallback needs this delegate. Qt WebEngine grants
    # camera/microphone requests itself and handles display capture separately.
    permissions.install_webview_permissions()
    webview.start(debug=False, gui=_gui)


if __name__ == "__main__":
    main()
