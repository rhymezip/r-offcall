import socket
import threading
import ipaddress
from zeroconf import ServiceBrowser, ServiceInfo, Zeroconf

SERVICE_TYPE = "_roffcall._tcp.local."
SERVICE_NAME = "r-offcall._roffcall._tcp.local."
PORT = 7800


class HostDiscovery:
    def __init__(self):
        self.zeroconf = Zeroconf()
        self._hosts = {}
        self._lock = threading.Lock()
        self._browser = None
        self._registered = False

    def get_local_ip(self):
        candidates = []
        try:
            name = socket.gethostname()
            for info in socket.getaddrinfo(name, None, socket.AF_INET):
                ip = info[4][0]
                addr = ipaddress.ip_address(ip)
                if not addr.is_loopback and not addr.is_link_local:
                    candidates.append(ip)
        except Exception:
            pass

        if candidates:
            return candidates[0]

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"

    def start_browsing(self):
        listener = _Listener(self._hosts, self._lock)
        self._browser = ServiceBrowser(self.zeroconf, SERVICE_TYPE, listener)

    def get_hosts(self):
        with self._lock:
            return dict(self._hosts)

    def register_as_host(self):
        ip = self.get_local_ip()
        info = ServiceInfo(
            SERVICE_TYPE,
            SERVICE_NAME,
            addresses=[socket.inet_aton(ip)],
            port=PORT,
            properties={"version": "1.0"},
        )
        self.zeroconf.register_service(info)
        self._registered = True
        print(f"[mDNS] Host registered: {ip}:{PORT}")

    def close(self):
        if self._registered:
            try:
                ip = self.get_local_ip()
                info = ServiceInfo(
                    SERVICE_TYPE,
                    SERVICE_NAME,
                    addresses=[socket.inet_aton(ip)],
                    port=PORT,
                    properties={"version": "1.0"},
                )
                self.zeroconf.unregister_service(info)
            except Exception:
                pass
        self.zeroconf.close()


class _Listener:
    def __init__(self, hosts, lock):
        self._hosts = hosts
        self._lock = lock

    def add_service(self, zc, type_, name):
        info = zc.get_service_info(type_, name)
        if info and info.addresses:
            ip = socket.inet_ntoa(info.addresses[0])
            port = info.port
            with self._lock:
                self._hosts[name] = (ip, port)
            print(f"[mDNS] Found host: {ip}:{port}")

    def remove_service(self, zc, type_, name):
        with self._lock:
            self._hosts.pop(name, None)
        print(f"[mDNS] Host lost: {name}")

    def update_service(self, zc, type_, name):
        self.add_service(zc, type_, name)
