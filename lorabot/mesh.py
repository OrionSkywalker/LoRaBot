"""Meshtastic transport, private-channel filtering, queueing, and throttling."""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from lorabot.assistant import AssistantEngine
from lorabot.config import Settings
from lorabot.text import split_mesh_text

LOGGER = logging.getLogger(__name__)
BROADCAST_NUM = 0xFFFFFFFF


@dataclass(frozen=True)
class Request:
    node_id: str
    text: str
    channel_index: int


class RateLimiter:
    def __init__(self, requests_per_hour: int):
        self.limit = requests_per_hour
        self.events: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, node_id: str, now: float | None = None) -> bool:
        now = now if now is not None else time.monotonic()
        with self.lock:
            events = self.events[node_id]
            while events and now - events[0] >= 3600:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True


class MeshBot:
    def __init__(self, settings: Settings, assistant: AssistantEngine):
        self.settings = settings
        self.assistant = assistant
        self.requests: queue.Queue[Request] = queue.Queue(maxsize=settings.radio.queue_size)
        self.rate_limiter = RateLimiter(settings.radio.requests_per_hour)
        self.interface = None
        self.last_receive = 0.0
        self.last_send = 0.0
        self.send_lock = threading.Lock()

    def _node_id(self, packet: dict) -> str:
        node_id = str(packet.get("fromId", "")).strip()
        if node_id:
            return node_id
        node_num = packet.get("from")
        return f"!{int(node_num):08x}" if node_num is not None else ""

    @staticmethod
    def _is_broadcast(packet: dict) -> bool:
        return packet.get("toId") == "^all" or packet.get("to") == BROADCAST_NUM

    def _strip_wake_word(self, text: str) -> str | None:
        wake_word = self.settings.meshtastic.wake_word
        if not wake_word:
            return text
        if not text.lower().startswith(wake_word.lower()):
            return None
        return text[len(wake_word) :].lstrip(" ,:-")

    def on_receive(self, packet: dict, interface) -> None:
        try:
            channel = int(packet.get("channel", 0))
            if channel != self.settings.meshtastic.channel_index:
                return
            local_node = getattr(getattr(interface, "localNode", None), "nodeNum", None)
            if local_node is not None and packet.get("from") == local_node:
                return
            if self.settings.meshtastic.require_direct_message and self._is_broadcast(packet):
                return

            node_id = self._node_id(packet)
            if not node_id:
                return
            allowed = self.settings.meshtastic.allowed_node_ids
            if allowed and node_id.lower() not in allowed:
                return

            text = str(packet.get("decoded", {}).get("text", "")).strip()
            text = self._strip_wake_word(text)
            if not text:
                return

            self.last_receive = time.monotonic()
            if not self.rate_limiter.allow(node_id):
                self._send("LoRaBot: hourly request limit reached.", node_id, channel)
                return
            try:
                self.requests.put_nowait(Request(node_id, text, channel))
            except queue.Full:
                self._send("LoRaBot is busy; please retry shortly.", node_id, channel)
                return

            if self.settings.assistant.thinking_message:
                self._send(self.settings.assistant.thinking_message, node_id, channel, wait=False)
        except Exception:
            LOGGER.exception("Could not process incoming packet")

    def _wait_for_radio(self) -> None:
        while True:
            now = time.monotonic()
            since_send = now - self.last_send
            since_receive = now - self.last_receive
            send_wait = self.settings.radio.message_delay_seconds - since_send
            quiet_wait = self.settings.radio.channel_quiet_seconds - since_receive
            wait = max(send_wait, quiet_wait)
            if wait <= 0:
                return
            time.sleep(min(wait, 0.5))

    def _send(
        self,
        text: str,
        node_id: str,
        channel_index: int,
        *,
        wait: bool = True,
    ) -> None:
        if self.interface is None:
            return
        with self.send_lock:
            if wait:
                self._wait_for_radio()
            self.interface.sendText(
                text,
                destinationId=node_id,
                channelIndex=channel_index,
                wantAck=self.settings.radio.want_ack,
            )
            self.last_send = time.monotonic()
            LOGGER.info("Sent to %s on channel %s: %s", node_id, channel_index, text)

    def _worker(self) -> None:
        while True:
            request = self.requests.get()
            try:
                reply = self.assistant.respond(request.node_id, request.text)
                chunks = split_mesh_text(
                    reply.text,
                    self.settings.assistant.chunk_bytes,
                    self.settings.assistant.max_chunks,
                )
                for chunk in chunks:
                    self._send(chunk, request.node_id, request.channel_index)
            except Exception:
                LOGGER.exception("Request failed")
                self._send(
                    "LoRaBot hit an internal error; check the service log.",
                    request.node_id,
                    request.channel_index,
                )
            finally:
                self.requests.task_done()

    def run(self) -> None:
        from meshtastic.serial_interface import SerialInterface
        from pubsub import pub

        pub.subscribe(self.on_receive, "meshtastic.receive.text")
        serial_port = self.settings.meshtastic.serial_port
        LOGGER.info("Connecting to Meshtastic radio on %s", serial_port or "auto-detected port")
        self.interface = SerialInterface(serial_port) if serial_port else SerialInterface()
        threading.Thread(target=self._worker, name="lorabot-worker", daemon=True).start()
        LOGGER.info("Listening on private channel index %s", self.settings.meshtastic.channel_index)
        try:
            while self.interface.isConnected.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            LOGGER.info("Stopping")
        finally:
            self.interface.close()
