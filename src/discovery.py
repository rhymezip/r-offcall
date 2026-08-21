import socket
import threading
import ipaddress
from zeroconf import ServiceBrowser, ServiceInfo, Zeroconf

SERVICE_TYPE = "_roffcall._tcp.local."
PORT = 7800


def _service_name_for_host(hostname: str | None = None) -> str:
    """Return an mDNS instance name that does not collide across hosts.

    Service *types* are shared by every r-offcall host. The old fixed instance
    name made a second machine on the same network fail with
    ``NonUniqueNameException``. A readable hostname-based instance keeps hosts
    distinguishable while Zeroconf's name-change fallback covers duplicates.
    """
    raw_name = hostname or socket.gethostname()
    safe_name = "".join(
        character if character.isalnum() or character == "-" else "-"
        for character in raw_name
    ).strip("-")
    safe_name = safe_name[:48] or "host"
    return f"r-offcall-{safe_name}.{SERVICE_TYPE}"


class HostDiscovery:
    def __init__(self):
        self.zeroconf = Zeroconf()
        self._hosts = {}
        self._lock = threading.Lock()
        self._browser = None
        self._registered = False
        self._service_info = None

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
            _service_name_for_host(),
            addresses=[socket.inet_aton(ip)],
            port=PORT,
            properties={"version": "1.0"},
        )
        try:
            # If two computers happen to have the same hostname, Zeroconf
            # renames the advertised instance instead of aborting the app.
            self.zeroconf.register_service(info, allow_name_change=True)
        except Exception as exc:
            # A meeting host is still useful without automatic discovery:
            # participants can join directly with http://<host-ip>:7800.
            print(f"[mDNS] Host registration unavailable: {exc}")
            return False

        self._service_info = info
        self._registered = True
        print(f"[mDNS] Host registered: {info.name} ({ip}:{PORT})")
        return True

    def close(self):
        if self._registered:
            try:
                if self._service_info is not None:
                    self.zeroconf.unregister_service(self._service_info)
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
