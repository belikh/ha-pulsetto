#!/usr/bin/env python3
"""Standalone Pulsetto BLE probe — run this BEFORE wiring the device into HA.

Implements Juraj Bednár's validated protocol doc
(github.com/jooray/pulse-libre-desktop, docs/PULSETTO_PROTOCOL.md):

Safe, read-only probes (default):
    v  -> fw:1.1.22      firmware
    i  -> Pulsetto_ST_02 identity
    u  -> u\\x011 / u\\x010 charging
    Q  -> Batt:3.97      battery voltage (percent = (v-3.5)/0.4*100)

Destructive path (--stimulate --yes): full documented start sequence
(+,-,[0,5,0 primer],target,D,LED) then the stop sequence (+,-,-). Unplug
the device from your neck before using it.

'U' (DFU reboot) is never sent by this script.

Usage:
    python3 test_ble.py                      # scan + connect + safe probes
    python3 test_ble.py --address XX:XX...   # specific device
    python3 test_ble.py --stimulate --yes --level 3 --time 20
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from bleak import BleakClient, BleakScanner

NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
RX_WRITE = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
TX_NOTIFY = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

CONNECT_TIMEOUT = 30.0

LED_DEFAULT = "F"
SED_WRITE_DELAY = 0.45
START_LEVEL_SETTLE_DELAY = 0.25
START_RAMP_PRIMER_DELAY = 0.25

SAFE_PROBES = [("v", "firmware"), ("i", "identity"), ("u", "charging"), ("Q", "battery")]


def battery_pct(v: float) -> float:
    pct = (v - 3.5) / 0.4 * 100
    return round(max(0.0, min(pct, 100.0)), 1)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--address")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--stimulate", action="store_true",
                        help="run the full start/stop sequences (UNSAFE)")
    parser.add_argument("--yes", action="store_true", required_with="stimulate",
                        help="confirm you unplugged the device")
    parser.add_argument("--level", type=int, default=3)
    parser.add_argument("--time", type=int, default=10,
                        help="seconds to stimulate before stop sequence")
    parser.add_argument("--side", default="D", choices=["A", "C", "D"])
    args = parser.parse_args()

    if args.stimulate and not args.yes:
        sys.exit("--stimulate requires --yes (unplug the device first)")
    if not 1 <= args.level <= 9:
        sys.exit("--level must be 1..9")

    print("scanning for devices named Pulsetto* ...")
    devices = await BleakScanner.discover(timeout=args.timeout)
    pulsett = [d for d in devices if d.name and "Pulsetto" in d.name]
    if not pulsett:
        print("no device advertising as 'Pulsetto*' found; all devices:")
        for d in devices:
            print(f"  {d}")
        return 1
    for d in pulsett:
        print(f"  found: {d.name}  [{d.address}]")
    target = pulsett[0]
    if args.address:
        target = next(d for d in pulsett if d.address == args.address)
    print(f"connecting to {target.name} [{target.address}] ...")

    state = {}

    def on_notify(_h, data):
        text = bytes(data).decode(errors="replace").strip()
        print(f"  <- notify: {text!r}")
        if text.startswith("Batt:"):
            v = float(text[5:])
            state["batt_v"] = v
            print(f"     battery: {v} V  -> {battery_pct(v)}%")
        elif text.startswith("fw:"):
            state["fw"] = text[3:]
        elif text in ("mode:0",):
            state["mode"] = "0"

    async with BleakClient(target.address, timeout=CONNECT_TIMEOUT) as client:
        print("connected")
        await client.start_notify(TX_NOTIFY, on_notify)

        for b, what in SAFE_PROBES:
            print(f"-> {b} ({what})")
            await client.write_gatt_char(RX_WRITE, (b + "\n").encode())
            await asyncio.sleep(1.2)
        print(f"state after probes: {state}")

        if args.stimulate:
            # Per the doc: +,- with response, then 0 -> 5 -> 0 primer, then
            # target level, then side, then LED.
            async def with_resp(b):
                await client.write_gatt_char(RX_WRITE, (b + "\n").encode(),
                                             response=True)
                await asyncio.sleep(0.05)

            async def wo_resp(b, delay=0.0):
                await client.write_gatt_char(RX_WRITE, (b + "\n").encode())
                if delay:
                    await asyncio.sleep(delay)

            print("START: + and - (with response)")
            await with_resp("+")
            await with_resp("-")
            await asyncio.sleep(0.25)
            for lvl in (0, 5, 0):
                print(f"START: primer {lvl}")
                await wo_resp(str(lvl), 0.45)
            print(f"START: target level {args.level}")
            await wo_resp(str(args.level), 0.25)
            print(f"START: side {args.side}")
            await wo_resp(args.side)
            print(f"START: LED {LED_DEFAULT}")
            await wo_resp(LED_DEFAULT)
            print(f"stimulating for {args.time}s...")
            await asyncio.sleep(args.time)
            print("STOP: + then -, -, all with response")
            await with_resp("+")
            await with_resp("-")
            await with_resp("-")
            print("stopped")

    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
