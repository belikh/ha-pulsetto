"""Connection management for one Pulsetto device over Nordic UART."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)

from . import ble
from .ble import (
    CMD_BATTERY,
    CMD_CHARGING,
    CMD_FIRMWARE,
    CMD_IDENTITY,
    CMD_LEVEL,
    SIDE_COMMANDS,
    SIDE_DEFAULT,
    START_LEVEL_PRIMER,
    START_LEVEL_SETTLE_DELAY,
    START_LEVEL_STEP_DELAY,
    START_RAMP_PRIMER_DELAY,
    STOP_SEQUENCE_COUNT,
    battery_percent,
    parse_reply,
)
from .const import CHAR_RX_WRITE, CHAR_TX_NOTIFY, CONNECT_TIMEOUT, DOMAIN, NOTIF_TIMEOUT

_LOGGER = logging.getLogger(__name__)

WRITE_WO_RESPONSE = "writeWithoutResponse"
WRITE_WITH_RESPONSE = "writeWithResponse"


class PulsettoClient:
    """Owns one Bleak connection plus the TX notify subscription."""

    def __init__(self, hass: Any, address: str) -> None:
        self.hass = hass
        self.address = address
        self._client: BleakClientWithServiceCache | None = None
        self.fw_version: str | None = None
        self.identity: str | None = None
        self.battery_percent: float | None = None
        self.battery_voltage: float | None = None
        self.charging: bool | None = None
        self.session_active: bool = False

    @property
    def connected(self) -> bool:
        return self._client is not None

    async def connect(self) -> None:
        self._client = await establish_connection(
            BleakClientWithServiceCache,
            self.address,
            name=DOMAIN,
            timeout=CONNECT_TIMEOUT,
        )
        await self._client.start_notify(CHAR_TX_NOTIFY, self._on_notify)
        await self._read_device_info()

    async def _read_device_info(self) -> None:
        for cmd in (CMD_FIRMWARE, CMD_IDENTITY):
            try:
                reply = await self._send_wait(cmd)
            except Exception as err:  # bleak disconnect races on info reads
                _LOGGER.debug("%s: info read %s failed: %s", self.address, cmd.payload, err)
                continue
            fields = parse_reply(reply)
            if "fw_version" in fields:
                self.fw_version = str(fields["fw_version"])
            elif reply:
                self.identity = reply

    async def disconnect(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.disconnect()
        finally:
            self._client = None
            self.session_active = False

    def _on_notify(self, _handle: int, payload: bytearray) -> None:
        raw = ble.decode_notification(bytes(payload))
        plain = raw.lstrip("\n")
        if not plain:
            return
        for line in plain.splitlines():
            if not line.strip():
                continue
            self._consume_reply(line.strip())

    def _consume_reply(self, line: str) -> None:
        fields = parse_reply(line)
        if "bat_voltage_v" in fields:
            v = float(fields["bat_voltage_v"])  # type: ignore[arg-type]
            self.battery_voltage = v
            self.battery_percent = battery_percent(v)
        elif "charging" in fields:
            self.charging = bool(fields["charging"])
        elif "fw_version" in fields:
            self.fw_version = str(fields["fw_version"])
        elif "mode" in fields:
            _LOGGER.debug("%s: mode reply %r", self.address, line)

    async def _send_wait(self, cmd, timeout: float = NOTIF_TIMEOUT) -> str:
        """Send a command and wait for one or more notification lines."""
        if self._client is None:
            raise ConnectionError("not connected")
        return await self._write(cmd, wait=timeout)

    async def _write(self, cmd, wait: float = 0.0) -> str:
        if self._client is None:
            raise ConnectionError("not connected")
        retry_ok = False
        for _ in range(2):  # retry a transient write failure once
            try:
                if cmd.with_response:
                    await self._client.write_gatt_char(
                        CHAR_RX_WRITE, cmd.wire(), response=True
                    )
                else:
                    await self._client.write_gatt_char(CHAR_RX_WRITE, cmd.wire())
                retry_ok = True
                break
            except Exception:
                _LOGGER.debug("%s: write %r failed, retrying", self.address, cmd.payload)
                await asyncio.sleep(0.05)
        if not retry_ok:
            raise ConnectionError(f"write {cmd.payload!r} failed repeatedly")

        if not wait:
            return ""
        # Notifications land via _on_notify and update state fields; the
        # waiting style only pads time so async_update callers get a turn.
        await asyncio.sleep(wait)
        return ""

    async def start_session(
        self, level: int, side: str = SIDE_DEFAULT, led: str = ble.LED_DEFAULT
    ) -> None:
        """The documented bring-up sequence, verbatim from the doc.

        1. '+' with response
        2. '-' with response
        3. 250 ms
        4-9. primer 0 -> 5 -> 0 each with 450 ms
        10. target level, 250 ms settle
        11. side (A/C/D)
        12. LED (E/F/G)
        """
        if side not in SIDE_COMMANDS:
            raise ValueError(f"unknown side {side!r}")
        if level not in CMD_LEVEL:
            raise ValueError(f"level {level} out of range")

        await self._write_secondary(ble.CMD_RAMP_UP)
        await self._write_secondary(ble.CMD_RAMP_DOWN)
        await asyncio.sleep(START_RAMP_PRIMER_DELAY)
        for primer in START_LEVEL_PRIMER:
            await self.send_level(primer, wait=False)
            await asyncio.sleep(START_LEVEL_STEP_DELAY)
        await self.send_level(level, wait=False)
        await asyncio.sleep(START_LEVEL_SETTLE_DELAY)
        await self._write_secondary(SIDE_COMMANDS[side])
        await self._write_secondary(
            ble.Command(led, with_response=False)
            if led in (ble.LED_LOW, ble.LED_MED, ble.LED_HIGH)
            else ble.Command(ble.LED_DEFAULT)
        )
        self.session_active = True

    async def stop_session(self) -> None:
        """'+' then '-' twice, all with response."""
        await self._write_secondary(ble.CMD_RAMP_UP)
        for _ in range(STOP_SEQUENCE_COUNT):
            await self._write_secondary(ble.CMD_RAMP_DOWN)
        self.session_active = False

    async def _write_secondary(self, cmd) -> None:
        # Non-notification pathway; no reply bookkeeping needed.
        await self._write(cmd, wait=0.0)

    async def send_level(self, level: int, wait_reply: bool = False) -> None:
        await self._write(CMD_LEVEL[level], wait=0)

    async def send_command(self, cmd, wait_reply: bool = False) -> str:
        return await self._write(cmd, wait=NOTIF_TIMEOUT if wait_reply else 0.0)

    async def poll_status(self) -> None:
        """Doc: poll u and Q every ~3 s during a session, less when idle."""
        await self._write(CMD_CHARGING, wait=0.3)
        await self._write(CMD_BATTERY, wait=0.5)

    # -- legacy API kept so the entity platforms keep working -------------
    async def query_battery(self) -> float | None:
        await self._write(CMD_BATTERY, wait=0.5)
        return self.battery_percent

    async def query_charging(self) -> bool | None:
        reply = await self._write(CMD_CHARGING, wait=0.3)
        if reply:
            fields = parse_reply(reply)
            if "charging" in fields:
                return bool(fields["charging"])
        return self.charging

    async def query_status(self) -> bool:
        await self.poll_status()
        return self.session_active

    async def query_versions(self) -> dict[str, str | None]:
        return {"fw_version": self.fw_version, "identity": self.identity}


def classify_charging(raw: str) -> str:
    if raw == ble.REPLY_CHARGING.decode():
        return "charging"
    if raw == ble.REPLY_NOT_CHARGING.decode():
        return "not_charging"
    return "unknown"
