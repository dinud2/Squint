"""Stand-in laptop bus (UDP multicast on loopback).

Part B owns the real `bus` library. This file only exists so Part C can run
before B's version lands. It follows the contract in the build plan:

    bus.init("vision")              # name used for the automatic `alive` beat
    bus.send({"type": "bottle_seen", "med": "warfarin", "confidence": 0.93})
    bus.on("enroll_start", handler) # handler(msg) runs on a background thread
    bus.run_forever()               # optional: block the main thread

Every message gets a `time` field (epoch seconds, float) added on send.
When B's library arrives, delete this file (or put B's on PYTHONPATH first);
no other Part C code changes.
"""
import json
import os
import socket
import struct
import threading
import time

GROUP = os.environ.get("SQUINT_BUS_GROUP", "239.255.77.77")
PORT = int(os.environ.get("SQUINT_BUS_PORT", "47777"))
ALIVE_PERIOD = 0.5

_handlers = {}
_lock = threading.Lock()
_name = None
_tx = None
_rx_started = False


def _tx_sock():
    global _tx
    if _tx is None:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 0)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton("127.0.0.1"))
        _tx = s
    return _tx


def send(event):
    msg = dict(event)
    msg.setdefault("time", time.time())
    if _name and "from" not in msg:
        msg["from"] = _name
    _tx_sock().sendto(json.dumps(msg).encode(), (GROUP, PORT))
    return msg


def _rx_loop():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    s.bind(("", PORT))
    mreq = struct.pack("4s4s", socket.inet_aton(GROUP), socket.inet_aton("127.0.0.1"))
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    while True:
        data, _ = s.recvfrom(65535)
        try:
            msg = json.loads(data)
        except ValueError:
            continue
        with _lock:
            hs = list(_handlers.get(msg.get("type"), ())) + list(_handlers.get("*", ()))
        for h in hs:
            try:
                h(msg)
            except Exception as e:  # a bad handler must not kill the bus
                print(f"[bus] handler error for {msg.get('type')}: {e}")


def _ensure_rx():
    global _rx_started
    if not _rx_started:
        _rx_started = True
        threading.Thread(target=_rx_loop, daemon=True).start()
        time.sleep(0.05)  # let the socket join the group


def on(event_type, handler):
    """Run handler(msg) for every message of this type ("*" = all)."""
    with _lock:
        _handlers.setdefault(event_type, []).append(handler)
    _ensure_rx()


def _alive_loop():
    while True:
        send({"type": "alive", "name": _name})
        time.sleep(ALIVE_PERIOD)


def init(name):
    """Name this program and start its automatic `alive` heartbeat."""
    global _name
    _name = name
    threading.Thread(target=_alive_loop, daemon=True).start()


def run_forever():
    _ensure_rx()
    while True:
        time.sleep(3600)
