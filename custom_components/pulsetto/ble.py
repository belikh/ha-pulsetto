"""Pulsetto BLE protocol layer.

Wire format per Juraj Bednár's protocol documentation
(github.com/jooray/pulse-libre-desktop, docs/PULSETTO_PROTOCOL.md), which is
empirically validated against Lite and Fit hardware:

- Commands are ASCII strings terminated by "\\n" on the RX characteristic.
- '+' (ramp up) and '-' (ramp down / stop) are written with response; every
  other command uses write-without-response.
- The official app wraps its writes in {"Base64Data": ...}; the firmware
  evidently accepts plain ASCII as well, which is what we use.
- Replies arrive on TX as plain text (occasionally the app-side wrapper is
  seen; the client decodes defensively).

Key semantics from the doc:
- 'U' REBOOTS THE DEVICE INTO DFU MODE. It is deliberately not exposed
  anywhere as a routine command.
- 'Q' returns battery voltage, e.g. `Batt:3.97`.
- 'i' returns the device identity string, e.g. `Pulsetto_ST_02`.
- 'v' returns firmware version, e.g. `fw:1.1.22`.
- Session "programs" (Stress/Sleep/...) are identical waveforms; only
  recommended duration and initial LED level differ.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

TERMINATOR = b"\n"

LED_LOW = "E"
LED_MED = "F"
LED_HIGH = "G"
LED_DEFAULT = LED_MED


@dataclass(frozen=True)
class Command:
    """An ASCII command plus the write mode the device expects."""

    payload: str
    with_response: bool = False

    def wire(self) -> bytes:
        return self.payload.encode() + TERMINATOR


CMD_RAMP_UP = Command("+", with_response=True)
CMD_RAMP_DOWN = Command("-", with_response=True)  # stop / ramp down / pause
CMD_DFU_REBOOT = Command("U", with_response=True)  # NEVER a routine command
CMD_LEFT = Command("A")
CMD_RIGHT = Command("C")
CMD_BOTH = Command("D")
CMD_BATTERY = Command("Q")  # -> Batt:3.97 (voltage)
CMD_CHARGING = Command("u")  # -> u\x011 / u\x010
CMD_FIRMWARE = Command("v")  # -> fw:1.1.22
CMD_IDENTITY = Command("i")  # -> Pulsetto_ST_02

CMD_LEVEL: dict[int, Command] = {
    lvl: Command(str(lvl)) for lvl in range(10)
}

SIDE_COMMANDS = {
    "left": CMD_LEFT,
    "right": CMD_RIGHT,
    "both": CMD_BOTH,
}
SIDE_DEFAULT = "both"

# Doc's recommended startup sequence: the 0 -> 5 -> 0 -> target pattern
# is part of normal device bring-up, not optional. Delays in seconds.
START_RAMP_PRIMER_DELAY = 0.250
START_LEVEL_STEP_DELAY = 0.450
START_LEVEL_SETTLE_DELAY = 0.250
START_LEVEL_PRIMER = (0, 5, 0)

# Stop sequence: '+', '-', '-' all with response.
STOP_SEQUENCE_COUNT = 2  # '-' after the initial '+'

REPLY_BATT_PREFIX = "Batt:"
REPLY_FW_PREFIX = "fw:"
REPLY_MODE_PREFIX = "mode:"

BATT_EMPTY_V = 3.5
BATT_FULL_V = 3.9

REPLY_CHARGING = b"u\x011"
REPLY_NOT_CHARGING = b"u\x010"


def battery_percent(voltage: float) -> float:
    """Doc formula: (v - 3.5) / 0.4 * 100, clamped to 0-100."""
    if voltage <= 0:  # no reading yet
        return 0.0
    pct = (voltage - BATT_EMPTY_V) / (BATT_FULL_V - BATT_EMPTY_V) * 100.0
    return round(max(0.0, min(pct, 100.0)), 1)


def parse_reply(raw: str) -> dict[str, float | bool | str]:
    """Classify one notification line into a field dict."""
    out: dict[str, float | bool | str] = {}
    if raw.startswith(REPLY_BATT_PREFIX):
        try:
            out["bat_voltage_v"] = float(raw[len(REPLY_BATT_PREFIX):])
        except ValueError:
            pass
    elif raw.startswith(REPLY_FW_PREFIX):
        out["fw_version"] = raw[len(REPLY_FW_PREFIX):]
    elif raw.startswith(REPLY_MODE_PREFIX):
        out["mode"] = raw[len(REPLY_MODE_PREFIX):]
    elif raw.startswith("BR:"):
        out["power"] = raw[3:]
    elif raw.encode(errors="ignore") in (REPLY_CHARGING, REPLY_NOT_CHARGING):
        out["charging"] = raw.endswith("1")
    return out


def decode_notification(payload: bytes) -> str:
    """Decode a TX notification payload defensively (plain text first)."""
    text = payload.decode(errors="replace")
    if text.startswith('{"Base64D'):
        # Official-app-style wrapper: {"Base64Data": "<b64>"}
        try:
            import json

            token = json.loads(text)["Base64Data"]
            return base64.b64decode(token).decode(errors="replace")
        except Exception:
            pass
    return text
