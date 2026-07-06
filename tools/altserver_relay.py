"""Minimal free AltServer broker (relay) — lets you run AltTester WITHOUT the
license-gated AltTester Desktop.

Why this works: the app's AltTester SDK (GPL, keyless) executes every command
itself; the "server" only *routes* messages between the app and the driver. So a
tiny WebSocket relay that pairs them by app name is a complete, free replacement
for the broker.

Wire protocol (AltTester 2.3.x), reverse-engineered from the SDK + Python client:
  - app command channel :  ws://host:13000/altws/app?appName=NAME&...
  - app notifications   :  ws://host:13000/altws/live-update/app?appName=NAME&...
  - driver (single conn):  ws://host:13000/altws?appName=NAME&driverType=python_...
The relay:
  - registers the app + driver by appName,
  - sends the driver a `driverRegistered` notification once its app is present
    (the driver blocks on this before proceeding),
  - pipes command traffic app<->driver and forwards app notifications to the driver.

Run it, then (adb reverse tcp:13000 already handled by the suite) connect with
AltDriver(port=13000) or `alttester connect`.

    python tools/altserver_relay.py            # listen on 0.0.0.0:13000
    python tools/altserver_relay.py --port 13000
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from urllib.parse import urlparse, parse_qs

import websockets
from websockets.asyncio.server import serve

# Line-buffered stdout so logs appear immediately (important when run in background).
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass
# Surface websocket handshake problems (e.g. an app whose upgrade we reject).
logging.basicConfig(level=logging.INFO, format="[ws] %(message)s")

DRIVER_REGISTERED = json.dumps(
    {"commandName": "driverRegistered", "isNotification": True, "messageId": "", "data": ""}
)


class Hub:
    """One entry per appName: the app's two sockets + the driver's socket."""

    def __init__(self):
        self.app_cmd: dict[str, object] = {}
        self.app_note: dict[str, object] = {}
        self.driver: dict[str, object] = {}

    async def register_and_maybe_pair(self, app_name: str):
        """If both an app command channel and a driver are present, tell the
        driver it is registered so it stops waiting and starts sending commands."""
        drv = self.driver.get(app_name)
        if drv is not None and self.app_cmd.get(app_name) is not None:
            try:
                await drv.send(DRIVER_REGISTERED)
                print(f"[relay] paired driver<->app for '{app_name}' (driverRegistered sent)")
            except Exception as exc:
                print(f"[relay] failed to send driverRegistered: {exc}")


HUB = Hub()


def _app_name(query: str) -> str:
    qs = parse_qs(query)
    vals = qs.get("appName") or ["__default__"]
    return vals[0]


async def _pump(src, dst_getter, label):
    """Forward every message from src to whatever dst_getter() currently returns."""
    n = 0
    async for message in src:
        n += 1
        dst = dst_getter()
        if dst is None:
            print(f"[relay] {label} msg#{n} DROPPED (no peer): {str(message)[:80]}")
            continue
        if n <= 3:
            print(f"[relay] {label} msg#{n}: {str(message)[:100]}")
        try:
            await dst.send(message)
        except Exception as exc:
            print(f"[relay] {label} forward dropped: {exc}")


async def handler(websocket):
    raw_path = websocket.request.path
    parsed = urlparse(raw_path)
    path = parsed.path.rstrip("/")
    app_name = _app_name(parsed.query)
    peer = f"{path}?appName={app_name}"
    print(f"[relay] + connect {peer}")

    try:
        if path == "/altws/app":
            HUB.app_cmd[app_name] = websocket
            await HUB.register_and_maybe_pair(app_name)
            await _pump(websocket, lambda: HUB.driver.get(app_name), "app->driver")

        elif path == "/altws/live-update/app":
            HUB.app_note[app_name] = websocket
            await _pump(websocket, lambda: HUB.driver.get(app_name), "note->driver")

        elif path == "/altws":
            HUB.driver[app_name] = websocket
            await HUB.register_and_maybe_pair(app_name)
            await _pump(websocket, lambda: HUB.app_cmd.get(app_name), "driver->app")

        elif path == "/altws/live-update":
            # driver-side notification channel (if the client opens one); accept + idle.
            async for _ in websocket:
                pass
        else:
            print(f"[relay] ! unknown path {raw_path} — closing")
    except websockets.ConnectionClosed:
        pass
    finally:
        for reg in (HUB.app_cmd, HUB.app_note, HUB.driver):
            if reg.get(app_name) is websocket:
                del reg[app_name]
        print(f"[relay] - disconnect {peer}")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=13000)
    args = ap.parse_args()
    print(f"[relay] AltServer relay listening on ws://{args.host}:{args.port}")
    print("[relay] endpoints: /altws (driver)  /altws/app  /altws/live-update/app")
    # compression=None and ping_interval=None: AltWebSocketSharp (the app's client)
    # interops poorly with permessage-deflate and server-initiated pings — either
    # can make it drop the connection right after the handshake.
    async with serve(
        handler, args.host, args.port,
        max_size=None, compression=None, ping_interval=None,
    ):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[relay] stopped.")
