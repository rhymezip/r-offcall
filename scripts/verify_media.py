#!/usr/bin/env python3
"""Check real UI SDP, stream routing and layout in two hidden Qt frames.

Run with the project environment: python scripts/verify_media.py.
No camera, microphone, screen-recording permissions or external server needed.
Uses synthetic media; does not verify received frames or a real Mac/Linux call.
"""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    + " --autoplay-policy=no-user-gesture-required"
    + " --disable-features=WebRtcHideLocalIpsWithMdns"
)

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineCore import QWebEnginePage

ROOT = Path(__file__).resolve().parents[1]
ui = (ROOT / "src/ui/index.html").read_text()
ui = ui[:ui.index("window.addEventListener('DOMContentLoaded'")]
ui += """
window.testApp={S,ICE,makePeer,configurePeerMedia,togScreen,stopScreen,dropAllPeers,renderGrid,
  togCam,togMic, setSocket:value=>_sk=value};
</script></body></html>
"""
driver = "<html><body><script>" + Path(__file__).with_name("verify_media.js").read_text() + "</script></body></html>"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/app":
            body, kind = ui.encode(), "text/html; charset=utf-8"
        elif self.path == "/socket.io.min.js":
            body, kind = (ROOT / "src/ui/socket.io.min.js").read_bytes(), "application/javascript"
        else:
            body, kind = driver.encode(), "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class Page(QWebEnginePage):
    passed = False

    def javaScriptConsoleMessage(self, level, message, line, source):
        if message.startswith("MEDIA_RESULT "):
            result = json.loads(message[len("MEDIA_RESULT "):])
            for check in result["checks"]:
                print(("PASS " if check["ok"] else "FAIL ") + check["name"], flush=True)
            if result.get("error"):
                print(result["error"], flush=True)
            self.passed = result["passed"]
            app.quit()
        elif message.startswith("MEDIA_PROGRESS "):
            print(message, flush=True)


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
app = QApplication(sys.argv)
page = Page()
page.load(QUrl(f"http://127.0.0.1:{server.server_port}/"))
QTimer.singleShot(90000, app.quit)
app.exec()
server.shutdown()
sys.exit(0 if page.passed else 1)
