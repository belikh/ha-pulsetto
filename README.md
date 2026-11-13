<p align="right">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/belikh/design/latest/packages/graphics/logo/jupiter-logo-dark.svg">
    <img alt="jupiter.au" src="https://raw.githubusercontent.com/belikh/design/latest/packages/graphics/logo/jupiter-logo-light.svg" width="260">
  </picture>
</p>

# Pulsetto BLE for Home Assistant

A Home Assistant custom component that controls a Pulsetto vagus nerve neckband over Bluetooth LE, without the phone app. It starts and stops stimulation, sets intensity and LED brightness, and reads battery, charging state and firmware.

It speaks the device's Nordic UART protocol directly. The protocol follows Juraj Bednár's documentation ([PULSETTO_PROTOCOL.md](https://github.com/jooray/pulse-libre-desktop/blob/main/docs/PULSETTO_PROTOCOL.md)) from his PulseLibre / pulse-libre-desktop clients. Pulsetto does not endorse this project.

> [!WARNING]
> The command sequences follow that document and have not been verified on a device by this project's author. Run `scripts/test_ble.py` first, with the device off your neck, and report the result in an issue.

<p>
  <a href="#install">Install</a> ·
  <a href="#safety">Safety</a> ·
  <a href="#entities">Entities</a> ·
  <a href="#services">Services</a> ·
  <a href="#validate-with-the-script">Validate with the script</a> ·
  <a href="#protocol-notes">Protocol notes</a> ·
  <a href="#licence">Licence</a>
</p>

<br>

---

<br>

## Install

Search for **Pulsetto** in HACS, download it and restart Home Assistant. If it is not listed, add `https://github.com/belikh/ha-pulsetto` as a HACS custom repository with type Integration.

To install by hand, copy `custom_components/pulsetto/` into `<config>/custom_components/` and restart.

Discovery matches the Nordic UART service UUID. With the device powered and in range, it appears under **Settings > Devices & Services**.

All traffic is local Bluetooth between Home Assistant and the device. Nothing goes to the network or to a cloud service.

<br>

## Safety

This is a stimulator, and the radio has no authentication: any BLE client in range can drive it. Keep automations conservative.

- Cap the level, and pair every `pulsetto.stimulate` with a stop.
- Use `time:` for an auto-stop. The timer lives in memory. Reload, unload and a clean Home Assistant shutdown send the stop sequence first. A crash or power loss cannot, so the device's own behaviour applies.
- The services need an admin user.
- Validate once with `scripts/test_ble.py` before trusting the entities.

<br>

## Entities

| Platform | Entity | Behaviour |
|---|---|---|
| `binary_sensor` | Charging | Reply to the `u` probe |
| `binary_sensor` | Active session | Client-side state of the start and stop sequence |
| `sensor` | Battery | Percent from the `Batt:` voltage, with voltage, firmware and identity as attributes |
| `number` | Intensity | Slider from 0 to 9. `0` pauses output |

Button entities cover start (both, left, right) and stop. LED low, mid and high is set with the `set_led` service.

<br>

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

<br>

## Validate with the script

Run `scripts/test_ble.py` with the device unplugged from your neck. By default it sends only the read-only probes (`v`, `i`, `u`, `Q`) and prints every notification. With `--stimulate --yes` it runs the full start sequence, stimulates for `--time` seconds at `--level`, then runs the stop sequence. That is the same behaviour the integration wraps.

```sh
python3 scripts/test_ble.py                                   # scan, connect, read-only probes
python3 scripts/test_ble.py --address XX:XX:XX:XX:XX:XX       # a specific device
python3 scripts/test_ble.py --stimulate --yes --level 3 --time 20
```

<br>

## Protocol notes

<details><summary><b>Commands, timing and polling</b></summary>

- Commands are ASCII plus `\n` on the RX characteristic. `+` and `-` use write-with-response. Everything else uses write-without-response.
- The start sequence is fixed: `+`, `-` (with response), a 250 ms wait, the primer `0`, `5`, `0` (450 ms apart), the target level, the side (`A`, `C` or `D`, default `D`), then the LED (`E`, `F` or `G`). Stop is `+`, `-`, `-`.
- Battery comes from `Q` replies such as `Batt:3.97`. Percentage is `(v - 3.5) / 0.4 * 100`, clamped to 0-100. Charging is the binary reply `u\x011` or `u\x010`. Firmware comes from `v` (`fw:1.1.22`). Identity comes from `i` (for example `Pulsetto_ST_02`).
- All standard programs produce the same waveform. Only the recommended duration and starting LED differ, so the integration exposes time and intensity and not program selection.
- `U` reboots the device into DFU mode. The integration never exposes it as a button or service. DFU updates are protected by the bootloader's ECDSA signature check (the public key is in the protocol document), so firmware integrity is checked on the device.
- Status polling (`u`, `Q`) runs every 30 s. The integration reconnects on the same interval when the device was out of range.

</details>

<br>

## Licence

MIT. See [LICENSE](LICENSE).

<br>

<p align="right"><sub>jupiter.au</sub></p>
