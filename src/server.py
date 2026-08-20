import os
import uuid
import socketio
import aiohttp_cors
from aiohttp import web

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sio = socketio.AsyncServer(
    async_mode="aiohttp",
    cors_allowed_origins="*",
    ping_timeout=60,
    ping_interval=25,
)
app = web.Application()
sio.attach(app)


# ── Static ──────────────────────────────────────────────────────
async def serve_index(request):
    path = os.path.join(ROOT, "src", "ui", "index.html")
    with open(path, "r", encoding="utf-8") as f:
        return web.Response(text=f.read(), content_type="text/html")


async def serve_socket_client(request):
    path = os.path.join(ROOT, "src", "ui", "socket.io.min.js")
    return web.FileResponse(path)


app.router.add_get("/", serve_index)
app.router.add_get("/index.html", serve_index)
app.router.add_get("/socket.io.min.js", serve_socket_client)


# ── State ────────────────────────────────────────────────────────
# users[sid] = {sid, name, role, faculty}
users = {}

# rooms[rid] = {id, name, password|None, owner_sid, members:{sid:user}, banned:[...]}
rooms = {}

# bans_by_name[room_name] = [{name, role, faculty}] — RAM'de tutulur; oda kapatılıp
# aynı isimle yeniden açılırsa engeller taşınır (DB yok, bu yüzden isim eşleşmesi yeterli)
bans_by_name = {}


def _is_banned(room, user):
    for b in room.get("banned", []):
        if b["name"] == user["name"]:
            return True
    return False


def _room_for_member(sid):
    for rid, room in rooms.items():
        if sid in room["members"]:
            return rid, room
    return None, None


def _same_room(a_sid, b_sid):
    _, room = _room_for_member(a_sid)
    return bool(room and b_sid in room["members"])


def _pub(room):
    return {
        "id":           room["id"],
        "name":         room["name"],
        "locked":       bool(room["password"]),
        "owner_sid":    room["owner_sid"],
        "member_count": len(room["members"]),
        "members":      list(room["members"].values()),
    }


async def _bcast():
    await sio.emit("rooms_list", [_pub(r) for r in rooms.values()])


# ── Connection ───────────────────────────────────────────────────
@sio.event
async def connect(sid, environ):
    print(f"[+] {sid}")


@sio.event
async def disconnect(sid):
    print(f"[-] {sid}")
    users.pop(sid, None)
    for rid, room in list(rooms.items()):
        if sid not in room["members"]:
            continue
        del room["members"][sid]
        await sio.leave_room(sid, rid)
        await sio.emit("peer_left", {"sid": sid}, room=rid)
        if room["owner_sid"] == sid:
            del rooms[rid]
            await sio.emit("room_closed", {"room_id": rid}, room=rid)
        await _bcast()
        break


# ── User ─────────────────────────────────────────────────────────
@sio.event
async def register_user(sid, data):
    users[sid] = {
        "sid":     sid,
        "name":    (data.get("name") or "Anonim")[:50],
        "role":    data.get("role", "student"),
        "faculty": data.get("faculty", ""),
    }
    await sio.emit("registered", {"sid": sid}, to=sid)
    await _bcast()


# ── Room CRUD ────────────────────────────────────────────────────
@sio.event
async def get_rooms(sid, data=None):
    await sio.emit("rooms_list", [_pub(r) for r in rooms.values()], to=sid)


@sio.event
async def create_room(sid, data):
    if sid not in users:
        await sio.emit("error", {"msg": "Önce giriş yapın."}, to=sid)
        return
    rid = str(uuid.uuid4())[:8]
    room_name = (data.get("room_name") or "Oda")[:60]
    room = {
        "id":        rid,
        "name":      room_name,
        "password":  data.get("password") or None,
        "owner_sid": sid,
        "members":   {sid: users[sid]},
        "banned":    list(bans_by_name.get(room_name, [])),
    }
    rooms[rid] = room
    await sio.enter_room(sid, rid)
    await sio.emit("room_created", _pub(room), to=sid)
    await _bcast()


@sio.event
async def join_room(sid, data):
    if sid not in users:
        await sio.emit("error", {"msg": "Önce giriş yapın."}, to=sid)
        return
    rid = data.get("room_id")
    if rid not in rooms:
        await sio.emit("error", {"msg": "Oda bulunamadı."}, to=sid)
        return
    room = rooms[rid]
    if room["password"] and room["password"] != data.get("password", ""):
        await sio.emit("error", {"msg": "Yanlış şifre."}, to=sid)
        return
    if _is_banned(room, users[sid]):
        await sio.emit("error", {"msg": "Bu odadan engellendiniz."}, to=sid)
        return
    room["members"][sid] = users[sid]
    await sio.enter_room(sid, rid)
    await sio.emit("room_joined", _pub(room), to=sid)
    await sio.emit("peer_joined", {"sid": sid, "user": users[sid]}, room=rid, skip_sid=sid)
    await _bcast()


@sio.event
async def leave_room(sid, data):
    rid = data.get("room_id")
    if rid not in rooms:
        return
    room = rooms[rid]
    room["members"].pop(sid, None)
    await sio.leave_room(sid, rid)
    await sio.emit("peer_left", {"sid": sid}, room=rid)
    if room["owner_sid"] == sid:
        del rooms[rid]
        await sio.emit("room_closed", {"room_id": rid}, room=rid)
    await _bcast()


@sio.event
async def close_room(sid, data):
    rid = data.get("room_id")
    if rid not in rooms:
        return
    if rooms[rid]["owner_sid"] != sid:
        await sio.emit("error", {"msg": "Sadece oda sahibi kapatabilir."}, to=sid)
        return
    del rooms[rid]
    await sio.emit("room_closed", {"room_id": rid}, room=rid)
    await _bcast()


# ── Moderation ───────────────────────────────────────────────────
@sio.event
async def kick_user(sid, data):
    rid = data.get("room_id")
    target = data.get("target_sid")
    if rid not in rooms or rooms[rid]["owner_sid"] != sid:
        return
    if target not in rooms[rid]["members"]:
        return
    rooms[rid]["members"].pop(target, None)
    await sio.leave_room(target, rid)
    await sio.emit("kicked", {"room_id": rid}, to=target)
    await sio.emit("peer_left", {"sid": target}, room=rid)
    await _bcast()


@sio.event
async def mute_user(sid, data):
    rid = data.get("room_id")
    target = data.get("target_sid")
    if rid not in rooms or rooms[rid]["owner_sid"] != sid:
        return
    if target not in rooms[rid]["members"]:
        return
    await sio.emit("force_mute", {"muted": bool(data.get("muted", True))}, to=target)


@sio.event
async def ban_user(sid, data):
    rid = data.get("room_id")
    target = data.get("target_sid")
    if rid not in rooms or rooms[rid]["owner_sid"] != sid:
        return
    if target not in rooms[rid]["members"]:
        return
    room = rooms[rid]
    member = room["members"][target]
    record = {"name": member["name"], "role": member["role"], "faculty": member["faculty"]}
    room.setdefault("banned", []).append(record)
    bans_by_name.setdefault(room["name"], []).append(record)
    room["members"].pop(target, None)
    await sio.leave_room(target, rid)
    await sio.emit("kicked", {"room_id": rid, "reason": "banned"}, to=target)
    await sio.emit("peer_left", {"sid": target}, room=rid)
    await _bcast()


@sio.event
async def set_force_mute(sid, data):
    rid = data.get("room_id")
    if rid not in rooms or rooms[rid]["owner_sid"] != sid:
        return
    await sio.emit("force_mute", {"muted": bool(data.get("muted", True))}, room=rid, skip_sid=sid)


# ── WebRTC Signaling ─────────────────────────────────────────────
@sio.event
async def webrtc_offer(sid, data):
    target = data.get("target_sid")
    offer = data.get("offer")
    if not target or not offer or not _same_room(sid, target):
        return
    await sio.emit("webrtc_offer", {"from_sid": sid, "offer": offer}, to=target)


@sio.event
async def webrtc_answer(sid, data):
    target = data.get("target_sid")
    answer = data.get("answer")
    if not target or not answer or not _same_room(sid, target):
        return
    await sio.emit("webrtc_answer", {"from_sid": sid, "answer": answer}, to=target)


@sio.event
async def webrtc_ice(sid, data):
    target = data.get("target_sid")
    candidate = data.get("candidate")
    if not target or not candidate or not _same_room(sid, target):
        return
    await sio.emit("webrtc_ice", {"from_sid": sid, "candidate": candidate}, to=target)


@sio.event
async def media_state(sid, data):
    rid = data.get("room_id")
    if rid not in rooms or sid not in rooms[rid]["members"]:
        return
    await sio.emit("peer_media_state", {
        "sid":    sid,
        "cam":    data.get("cam", False),
        "mic":    data.get("mic", False),
        "screen": data.get("screen", False),
    }, room=rid, skip_sid=sid)


# ── CORS ─────────────────────────────────────────────────────────
cors = aiohttp_cors.setup(app, defaults={
    "*": aiohttp_cors.ResourceOptions(
        allow_credentials=True,
        expose_headers="*",
        allow_headers="*",
    )
})
