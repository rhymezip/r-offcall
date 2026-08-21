<p align="left">
  <a href="./README.md"><img alt="Read in English" src="https://img.shields.io/badge/Language-English-1f6feb?style=for-the-badge"></a>
  <a href="./README.tr.md"><img alt="Türkçe oku" src="https://img.shields.io/badge/Dil-Türkçe-e11d48?style=for-the-badge"></a>
  <a href="./README.ru.md"><img alt="Читать на русском" src="https://img.shields.io/badge/Язык-Русский-6d28d9?style=for-the-badge"></a>
</p>

# r-offcall

> Private, local-network video meetings for classrooms, departments, labs, and offices — without accounts, a cloud service, or a central media server.

**r-offcall** is a lightweight, self-hosted meeting tool for people already on the same trusted network. One computer becomes the host; nearby devices discover it through mDNS and join through the desktop app or a modern browser. Camera and microphone traffic flows directly between participants over WebRTC, while the host only coordinates room state and connection setup.

<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white">
  <img alt="Platforms" src="https://img.shields.io/badge/Platforms-macOS%20%7C%20Windows%20%7C%20Linux-111827">
  <img alt="Network" src="https://img.shields.io/badge/Network-LAN%20first-0f766e">
  <img alt="Media" src="https://img.shields.io/badge/Media-WebRTC-ef4444">
</p>

## Why it exists

Universities, offices, and laboratories sometimes need to start a meeting inside their own network: without creating accounts, sending student data to a third-party service, or depending on internet access during a class.

r-offcall is built for that focused case: a **small, trusted, same-network meeting** where quick setup and local control matter more than enterprise administration.

## Where it fits

| Scenario | How r-offcall helps |
|---|---|
| University classroom | An instructor opens a room; students on the same Wi-Fi join without typing an IP address. |
| Department or faculty meeting | A small group starts an internal call without accounts or a cloud calendar. |
| Computer lab or workshop | Participants share cameras, microphones, and — on supported clients — screens on the local network. |
| Isolated office network | Meetings continue when external services are unavailable, as long as the LAN works. |
| Temporary on-site collaboration | A host creates a password-protected room and moderates the active session. |

## Highlights

- **LAN-first discovery.** Hosts advertise themselves with mDNS/Zeroconf; desktop clients find them automatically.
- **Direct WebRTC media.** Audio and video are peer-to-peer. The host coordinates signaling; it does not relay meeting media.
- **No accounts or cloud dependency.** Room, participant, and moderation data live only in the running host process.
- **Desktop and browser entry.** Use the native app on macOS, Windows, or Linux; browser clients join at `http://<host-ip>:7800`.
- **Simple room controls.** Password-protected rooms, live membership, mute, kick, and session-lifetime bans.
- **Classroom-friendly roles.** Teacher/student roles and optional faculty information make participant tiles easier to read.
- **Platform-aware media.** Native permission handling, Linux Qt6 desktop screen sharing, and browser-based fallback where needed.

## Architecture

```text
                         local network

              mDNS discovery + HTTP/WebSocket signaling
┌───────────────────────────────────────────────────────────────────┐
│  Host computer                                                     │
│  aiohttp + Socket.IO · room state · host discovery · port 7800    │
└───────────────────────────────┬───────────────────────────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
     ┌────▼────┐           ┌────▼────┐           ┌────▼────┐
     │ Client A│◄─────────►│ Client B│◄─────────►│ Client C│
     └─────────┘  WebRTC   └─────────┘  WebRTC   └─────────┘
```

| Traffic | Path | Notes |
|---|---|---|
| Discovery | mDNS / Zeroconf | Finds hosts on the same multicast-capable network. |
| Signaling | Client ↔ host | Room membership, WebRTC offers/answers, ICE candidates, moderation events. |
| Camera / microphone | Participant ↔ participant | WebRTC peer-to-peer media; hosting does not automatically receive media. |
| Screen share | Participant ↔ participant | Linux Qt6 desktop app and compatible browsers. |

## Strengths and trade-offs

This project is intentionally focused. Its limitations are as important as its feature list.

| Strengths | Trade-offs / limits |
|---|---|
| No account system, external SaaS, or cloud media relay is required. | No identity provider, SSO, audit trail, or durable user management. |
| P2P WebRTC reduces load on the host. | Mesh WebRTC is for small groups, not large lectures or an SFU deployment. |
| mDNS makes nearby-host discovery convenient. | VLANs, guest Wi-Fi isolation, VPNs, or multicast restrictions can block discovery. |
| Passwords and moderation provide a lightweight access layer. | Passwords and room state are kept in host memory; this is not enterprise-grade access control. |
| Same-LAN calls can work without internet. | Google STUN is configured as an optional aid; cross-network calls are not supported. |
| The desktop app is cross-platform. | Linux screen sharing requires Qt6 WebEngine; embedded macOS WKWebView does not support `getDisplayMedia`. |
| Browser clients are easy to distribute. | Some browsers restrict camera/microphone on plain HTTP LAN origins; use the desktop app or HTTPS where that policy applies. |

## Security and privacy boundary

r-offcall is for a **trusted local network**, not an untrusted public network.

- WebRTC media is protected with DTLS-SRTP, but built-in signaling uses HTTP and has no TLS, SSO, or certificate management.
- Anyone who can reach a host can attempt to connect. Use room passwords, a controlled network, and firewall rules appropriate to your institution.
- Room names, passwords, bans, and membership state are in memory. Restarting the host clears them.
- Bans are name-based, not identity-based; another display name can bypass one.
- Do not expose port `7800` to the public internet. TURN, hardened authentication, and a production operations model are not included.

For vulnerability reporting, see [SECURITY.md](./SECURITY.md).

## Requirements

- Python **3.10+**
- Devices on the same reachable local network
- A multicast-capable LAN for automatic host discovery
- Camera/microphone permissions on desktop clients that publish media

## Install

```bash
git clone https://github.com/rhymezip/r-offcall.git
cd r-offcall
python -m venv .venv
```

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

| Platform | Run | Notes |
|---|---|---|
| macOS | `python src/main.py` | Approve camera/microphone prompts. Embedded WKWebView cannot share the desktop; use a compatible browser for that feature. |
| Windows | `python src/main.py` | Windows 10/11 should provide WebView2. Enable desktop-app camera/microphone access if media is denied. |
| Linux | `python src/main.py` | Requirements install Qt6 WebEngine. Install  distribution's Qt/XCB runtime packages if the GUI cannot start. Screen sharing is supported. |

## First meeting

1. Start r-offcall on a computer in the target network.
2. If no host is discovered after a short wait, that computer becomes the host on port `7800`.
3. Grant media permissions, enter a name, and select a role.
4. Create a room, optionally with a password.
5. Others launch r-offcall (automatic discovery) or browse to `http://<host-ip>:7800`.

> **Single-machine test:** use a browser tab as the second participant. Multiple desktop instances share device permissions and can conflict with the host port.

## Configuration

| Item | Current behavior |
|---|---|
| Host port | `7800`, defined in `src/discovery.py` |
| mDNS service name | Unique per host; duplicate names are automatically renamed instead of crashing the host |
| Client local UI port | Starts at `7801`; keeps the desktop page on a loopback secure context |
| STUN | `stun.l.google.com:19302` |
| Persistence | None; host restart clears all room state |
| TURN / internet meetings | Not included |
| TLS / HTTPS | Not included |

## Project layout

```text
src/
├── main.py          # Desktop startup, host/client choice, platform bridges
├── server.py        # aiohttp + Socket.IO signaling and moderation
├── discovery.py     # Zeroconf/mDNS host discovery
├── permissions.py   # macOS TCC and WKWebView permission bridge
└── ui/              # Single-page WebRTC client
scripts/
└── verify.py        # Fast deterministic core checks
```

## Verification

```bash
python scripts/verify.py
```

The check compiles Python sources, verifies the local static server, and tests the Linux Qt desktop-media selection path without requiring a camera or display.

## Roadmap ideas

- HTTPS and a locally managed certificate workflow
- Manual host address entry when mDNS is unavailable
- Optional local identities, SSO, or campus-directory integration
- Persistent room policy and audit logs
- TURN/SFU support for larger groups or routed networks
- Signed desktop packages and a macOS screen-sharing-capable renderer

## Contributing and license

See [CONTRIBUTING.md](./CONTRIBUTING.md). No open-source license has been selected yet. Until one is added, the repository is **all rights reserved by default**; do not reuse or redistribute the code without the owner’s permission.
