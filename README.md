# Pulsetto BLE for Home Assistant

Custom component that speaks the Pulsetto neckband's Nordic UART protocol
directly, so HA can stimulate and read state without the phone app.

The wire protocol follows Juraj Bednár's hardware-validated documentation
([PULSETTO_PROTOCOL.md](https://github.com/jooray/pulse-libre-desktop/blob/main/docs/PULSETTO_PROTOCOL.md)),
from his independent PulseLibre / pulse-libre-desktop clients.
Nothing here is sanctioned by Pulsetto.

**Hardware status:** the command sequences follow that document and have not
been verified by this project's author on a device. Run
`scripts/test_ble.py` first and report results in an issue.

## Protocol notes (issuer of truth: the doc above)

- Commands are ASCII + `\n` on the RX characteristic; `+` and `-` use
  write-with-response, everything else write-without-response.
- Start sequence is fixed: `+`, `-` (with response) → 250 ms → primer
  `0`,`5`,`0` (450 ms apart) → target level → side (`A`/`C`/`D`, default
  `D`) → LED (`E`/`F`/`G`). Stop is `+`, `-`, `-`.
- Battery comes from `Q` replies like `Batt:3.97`, percentage =
  `(v − 3.5) / 0.4 × 100` (clamped 0-100). Charging is the binary
  `u\x011`/`u\x010` reply. Firmware via `v` → `fw:1.1.22`. Identity via
  `i` → e.g. `Pulsetto_ST_02`.
- All standard "programs" produce the same waveform; only recommended
  duration and starting LED differ. The integration therefore exposes
  time + intensity, not program selection.
- `U` reboots the device into DFU mode. It is deliberately **not**
  exposed as a button or service anywhere in this integration. DFU
  updates themselves are protected by the bootloader's ECDSA signature
  check (public key published in the protocol doc), so firmware
  integrity is on-device, not app-layer.
- Status polling (`u`, `Q`) runs every 30 s. The integration reconnects
  on the same interval when the device was out of range.

## Safety

This is a stimulator, and the radio has no authentication — any BLE
client in range can drive it. Keep automations conservative:

- cap level, and pair every `pulsetto.stimulate` with a stop
- use `time:` for an auto-stop. The timer lives in memory. Reload,
  unload and a clean Home Assistant shutdown send the stop sequence first;
  a crash or power loss cannot, so the device's own behaviour applies
- the services need an admin user
- validate once with `scripts/test_ble.py` before trusting entities

## Install

Search for **Pulsetto** in HACS, download it and restart Home Assistant.
Until it is listed, add `https://github.com/belikh/ha-pulsetto` as a HACS
custom repository (type Integration). Manual install: copy
`custom_components/pulsetto/` into `<config>/custom_components/`. Discovery triggers on the Nordic UART service UUID; the device
appears under Settings → Devices & Services when powered and in range.

## Privacy

All traffic is local Bluetooth between Home Assistant and the device.
Nothing is sent over the network or to any cloud service.

## Entities

| Platform       | Entity          | Behaviour                                       |
|----------------|-----------------|--------------------------------------------------|
| binary_sensor  | Charging        | `u` probe reply                                  |
| binary_sensor  | Active session  | client-side session state (start/stop sequence)  |
| sensor         | Battery         | percent from `Batt:` voltage, with voltage/fw/identity attributes |
| number         | Intensity       | 0-9 slider; `0` pauses output                    |

Button entities cover the start/stop one-shots (start both/left/right,
stop). LED low/mid/high is available via the `set_led` service.

## Services

```yaml
service: pulsetto.stimulate
data:
  side: both        # left / right / both
  level: 5          # 1-9 (0 pauses instead of stimulating)
  time: 300         # optional auto-stop after 300 s

service: pulsetto.stop
service: pulsetto.set_level
data: { level: 3 }
service: pulsetto.set_led
data: { brightness: mid }   # low / mid / high
```

## Validate first

Run `scripts/test_ble.py` with the device **unplugged from your neck**. It
performs the read-only probes (`v`, `i`, `u`, `Q`) and prints every
notification. With `--stimulate --yes` (and only those), it runs the full
documented start sequence, stimulates for `--time` seconds at `--level`,
then the full stop sequence — the exact behaviour the HA integration
wraps.
