"""Native media-permission support for the desktop application.

macOS has two gates for ``getUserMedia``: application-level TCC approval and
WKWebView's per-origin capture decision. The WebKit delegate has to be ready
before the view exists; installing it after JavaScript has asked for media is
racy and can result in a silent denial.
"""

from __future__ import annotations

import platform
import threading
from typing import Any


_STATUS: dict[str, Any] = {
    "platform": platform.system(),
    "delegate_installed": False,
    "camera": "unknown",
    "microphone": "unknown",
    "error": None,
}
_delegate_installed = False


def install_webview_permissions() -> dict[str, Any]:
    """Install the macOS WKWebView delegate before ``webview.start``.

    It deliberately does nothing on non-macOS platforms, keeping the desktop
    startup path identical on macOS, Windows, and Linux.
    """
    global _delegate_installed
    if platform.system() != "Darwin" or _delegate_installed:
        return dict(_STATUS)

    try:
        import objc
        import WebKit
        from webview.platforms.cocoa import BrowserView

        _set_usage_descriptions()

        def grant_media_capture(_self, _webview, _origin, _frame, capture_type, handler):
            try:
                decision = getattr(WebKit, "WKPermissionDecisionGrant", 1)
                try:
                    # Modern PyObjC/WebKit carries this block's type metadata.
                    handler(decision)
                except TypeError:
                    # pywebview 5 / older PyObjC may expose an untyped block.
                    # Build the same ``void (^)(NSInteger)`` signature used by
                    # pywebview's old Cocoa implementation and retry once.
                    _set_decision_handler_signature(handler)
                    handler(decision)
                print(f"[Perm] WKWebView media capture granted (type={capture_type})")
            except Exception as exc:
                # Never leave WebKit waiting if PyObjC changes block handling.
                print(f"[Perm] WKWebView decision failed: {exc}")

        class ROffcallBrowserDelegate(BrowserView.BrowserDelegate):
            pass

        ROffcallBrowserDelegate.webView_requestMediaCapturePermissionForOrigin_initiatedByFrame_type_decisionHandler_ = objc.selector(
            grant_media_capture,
            signature=b"v@:@@@q@?",
        )
        BrowserView.BrowserDelegate = ROffcallBrowserDelegate
        _delegate_installed = True
        _STATUS["delegate_installed"] = True
        _STATUS["error"] = None
        print("[Perm] WKWebView media delegate installed")
    except Exception as exc:
        _STATUS["error"] = str(exc)
        print(f"[Perm] Could not install WKWebView media delegate: {exc}")
    return dict(_STATUS)


def setup_blocking(_pywebview_window=None, delay: float = 0.0) -> dict[str, Any]:
    """Request camera and microphone TCC permissions and wait for a response.

    pywebview dispatches JavaScript API calls on a worker thread. AVFoundation
    requests are therefore scheduled on Cocoa's main loop while this worker
    waits, allowing macOS's permission sheet to remain responsive.
    """
    del delay  # Kept for the existing JS API signature.
    if platform.system() != "Darwin":
        return dict(_STATUS)

    install_webview_permissions()
    _request_av_permissions()
    return dict(_STATUS)


def status() -> dict[str, Any]:
    return dict(_STATUS)


def _set_decision_handler_signature(handler) -> None:
    """Give old PyObjC an explicit ``void (^)(NSInteger)`` block signature."""
    try:
        import ctypes
        from objc import _objc

        runtime = ctypes.cdll.LoadLibrary(_objc.__file__)
        make_signature = runtime.PyObjCMethodSignature_WithMetaData
        make_signature.restype = ctypes.py_object
        handler.__block_signature__ = make_signature(
            ctypes.create_string_buffer(b"v@q"), None, False
        )
    except Exception as exc:
        raise RuntimeError(f"Could not type the WebKit decision handler: {exc}") from exc


def _set_usage_descriptions() -> None:
    """Add useful privacy strings for script-launched macOS applications."""
    try:
        import AppKit

        info = AppKit.NSBundle.mainBundle().infoDictionary()
        if info is None:
            return
        descriptions = {
            "NSCameraUsageDescription": "r-offcall needs camera access for local video meetings.",
            "NSMicrophoneUsageDescription": "r-offcall needs microphone access for local audio meetings.",
            "NSScreenCaptureUsageDescription": "r-offcall needs screen recording access when you share your screen.",
        }
        for key, value in descriptions.items():
            if not info.objectForKey_(key):
                info.setObject_forKey_(value, key)
    except Exception as exc:
        print(f"[Perm] Could not set usage descriptions: {exc}")


def _request_av_permissions() -> None:
    try:
        import AVFoundation

        for media_type, key, label in (
            (AVFoundation.AVMediaTypeVideo, "camera", "Camera"),
            (AVFoundation.AVMediaTypeAudio, "microphone", "Microphone"),
        ):
            _request_one(AVFoundation.AVCaptureDevice, media_type, key, label)
    except Exception as exc:
        _STATUS["error"] = str(exc)
        print(f"[Perm] AVFoundation setup failed: {exc}")


def _request_one(capture_device, media_type, key: str, label: str) -> None:
    # AVAuthorizationStatus: 0 = not determined, 1 = restricted,
    # 2 = denied, 3 = authorized.
    try:
        state = int(capture_device.authorizationStatusForMediaType_(media_type))
    except Exception as exc:
        _STATUS[key] = "unavailable"
        print(f"[Perm] {label} status failed: {exc}")
        return

    if state == 3:
        _STATUS[key] = "granted"
        return
    if state in (1, 2):
        _STATUS[key] = "denied"
        print(f"[Perm] {label} is denied in macOS Privacy & Security")
        return

    completed = threading.Event()

    def completion(granted: bool) -> None:
        _STATUS[key] = "granted" if granted else "denied"
        print(f"[Perm] {label}: {_STATUS[key]}")
        completed.set()

    def request_on_main_thread() -> None:
        try:
            capture_device.requestAccessForMediaType_completionHandler_(media_type, completion)
        except Exception as exc:
            _STATUS[key] = "unavailable"
            _STATUS["error"] = str(exc)
            completed.set()

    if threading.current_thread() is threading.main_thread():
        request_on_main_thread()
    else:
        try:
            from PyObjCTools import AppHelper
            AppHelper.callAfter(request_on_main_thread)
        except Exception:
            request_on_main_thread()

    if not completed.wait(timeout=60):
        _STATUS[key] = "timed_out"
        print(f"[Perm] {label} permission request timed out")
