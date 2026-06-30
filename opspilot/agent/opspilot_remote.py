"""BVTech OpsPilot Agent — Remote Desktop add-on (native WebRTC).

OPTIONAL. Imported lazily by the agent only when a remote session is pending.
Requires the remote extras on the endpoint:

    pip install aiortc websockets mss pyautogui av

When those are present, this connects to Pulse's signaling relay as the device
peer, publishes the screen as a WebRTC video track (P2P to the operator's
browser), and replays the operator's mouse/keyboard sent over a data channel.
If the extras are missing, `is_available()` returns False and the agent simply
logs that the remote add-on isn't installed — telemetry/console keep working.

This module is intentionally self-contained; nothing else imports it at startup.
"""
from __future__ import annotations

import asyncio
import json
import time


def is_available() -> tuple[bool, str]:
    try:
        import aiortc  # noqa: F401
        import websockets  # noqa: F401
        import mss  # noqa: F401
        import av  # noqa: F401
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, f"remote add-on not installed ({e}). Run: pip install aiortc websockets mss pyautogui av"


def run_session(pulse_url: str, token: str, enroll_id: str, agent_key: str,
                log=print) -> None:
    """Blocking: serve one remote session until the operator disconnects."""
    ok, why = is_available()
    if not ok:
        log(f"remote: {why}")
        return
    try:
        asyncio.run(_serve(pulse_url, token, enroll_id, agent_key, log))
    except Exception as e:  # noqa: BLE001
        log(f"remote: session ended ({e})")


async def _serve(pulse_url, token, enroll_id, agent_key, log):
    import fractions
    import numpy as np
    import mss
    from aiortc import (RTCPeerConnection, RTCSessionDescription, RTCIceCandidate,
                        VideoStreamTrack)
    from av import VideoFrame
    import websockets

    try:
        import pyautogui
        pyautogui.FAILSAFE = False
    except Exception:
        pyautogui = None

    ws_proto = "wss" if pulse_url.startswith("https") else "ws"
    host = pulse_url.split("://", 1)[-1]
    ws_url = f"{ws_proto}://{host}/api/remote/ws/{token}?role=agent&enroll_id={enroll_id}&agent_key={agent_key}"

    class ScreenTrack(VideoStreamTrack):
        """Captures the primary monitor at ~12fps and emits it as a video track."""
        def __init__(self):
            super().__init__()
            self._sct = mss.mss()
            self._mon = self._sct.monitors[1]
            self._t0 = time.time()

        async def recv(self):
            pts, time_base = await self.next_timestamp()
            img = self._sct.grab(self._mon)
            arr = np.asarray(img)[:, :, :3][:, :, ::-1]  # BGRA -> RGB
            frame = VideoFrame.from_ndarray(np.ascontiguousarray(arr), format="rgb24")
            frame.pts = pts
            frame.time_base = time_base
            await asyncio.sleep(1 / 12)
            return frame

    pc = RTCPeerConnection()
    pc.addTrack(ScreenTrack())
    screen_w, screen_h = (pyautogui.size() if pyautogui else (1920, 1080))

    # Input channel: operator -> us. We replay mouse/keyboard via pyautogui.
    ch = pc.createDataChannel("input")

    @ch.on("message")
    def on_input(message):  # noqa: ANN001
        if not pyautogui:
            return
        try:
            o = json.loads(message)
            t = o.get("t")
            if t == "move":
                pyautogui.moveTo(int(o["x"] * screen_w), int(o["y"] * screen_h), _pause=False)
            elif t in ("down", "up"):
                btn = {0: "left", 1: "middle", 2: "right"}.get(o.get("b", 0), "left")
                pyautogui.moveTo(int(o["x"] * screen_w), int(o["y"] * screen_h), _pause=False)
                (pyautogui.mouseDown if t == "down" else pyautogui.mouseUp)(button=btn, _pause=False)
            elif t == "scroll":
                pyautogui.scroll(int(-o.get("dy", 0)))
            elif t == "key" and o.get("down"):
                key = (o.get("key") or "").lower()
                if len(key) == 1 or key in ("enter", "tab", "backspace", "esc", "space", "delete",
                                            "up", "down", "left", "right", "home", "end"):
                    pyautogui.press("escape" if key == "esc" else key, _pause=False)
        except Exception:
            pass

    async with websockets.connect(ws_url, max_size=2 ** 22) as ws:
        async def send(obj):
            await ws.send(json.dumps(obj))

        @pc.on("icecandidate")
        async def on_ice(candidate):  # noqa: ANN001
            if candidate:
                await send({"type": "candidate", "candidate": {
                    "candidate": candidate.to_sdp(), "sdpMid": candidate.sdpMid,
                    "sdpMLineIndex": candidate.sdpMLineIndex}})

        # We are the offerer (we own the screen track).
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        log("remote: operator session starting — sending offer")
        await send({"type": "offer", "sdp": {"type": pc.localDescription.type,
                                              "sdp": pc.localDescription.sdp}})
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            mt = msg.get("type")
            if mt == "answer":
                await pc.setRemoteDescription(RTCSessionDescription(**msg["sdp"]))
            elif mt == "candidate" and msg.get("candidate"):
                c = msg["candidate"]
                try:
                    await pc.addIceCandidate(RTCIceCandidate(
                        sdpMid=c.get("sdpMid"), sdpMLineIndex=c.get("sdpMLineIndex"),
                        candidate=c.get("candidate")))
                except Exception:
                    pass
            elif mt == "relay.peer-left":
                break
    await pc.close()
