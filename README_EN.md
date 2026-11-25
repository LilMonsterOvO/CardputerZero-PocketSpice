<div align="center">
  <img src="assets/icon_256.png" width="128" alt="PocketSpice Icon" />
  <h1>PocketSpice (<code>cp0-ngspice</code>)</h1>
  <p><strong>Full-Flexibility Pocket NGSPICE Circuit &amp; Power-Electronics Simulator for M5Stack CardputerZero</strong></p>
  <p><a href="README.md">简体中文</a> ｜ English</p>
</div>

---

## Overview

**PocketSpice (`cp0-ngspice`)** brings a real **NGSPICE** shared-library solver (`libngspice` C-ABI) to the **M5Stack CardputerZero** (`arm64` Linux, Raspberry Pi CM0 / 1 GHz Cortex-A53, 512 MB RAM, `320×170` ST7789v3 SPI LCD, 46-key keypad):

- **Direct Hardware Display & Input**: Renders straight to `/dev/fb_lcd` (`320×170` 16-bit RGB565) and reads `/dev/input/by-path/platform-3f804000.i2c-event` (`tca8418c` matrix keypad + M5Stack symbol map) using event-driven `select()` wakeups (~0% idle CPU) without relying on a heavyweight desktop compositor.
- **Full NGSPICE Flexibility**: Supports `.tran`, `.ac` (log-frequency Bode plots), `.dc`, and `.op` analyses, auto-discovery for raw unannotated `.cir`/`.sp` netlists, in-app line-by-line netlist editing, and reusable power semiconductor subcircuits ([lib/power_devices.lib](lib/power_devices.lib)).
- **Published 5-Level Switched-Capacitor Inverter Replication**: Includes [04_5level_sc_inverter.cir](circuits/04_5level_sc_inverter.cir), replicating the 5-level CGSCMLI topology from *IEEE Trans. Power Electron.*, 2026 (`DOI: 10.1109/TPEL.2026.3683439`) with cold-start capacitor self-balancing (`±400V, ±200V, 0V`).
- **Bilingual UI & Local AI / ZClaw Co-Pilot**: Switch seamlessly between Simplified Chinese and English (`L` key), inspect built-in [User](docs/USER_MANUAL.md) and [AI Agent](docs/AI_AGENT_MANUAL.md) manuals, or drive simulations via headless JSON CLI (`cp0-ngspice run ... --json`). Automatically discovers projects in both `$HOME/.config/cp0-ngspice/projects/` and `$HOME/.zeroclaw/agents/zclaw/workspace/pocketspice/`.

---

## Real-Device Benchmarks (CardputerZero, `ngspice-44.2`)

- **5-Level SC Inverter (`40 ms` cold-start transient, `8843` pts)**: `3299.04 ms`, `33.73 MB` RSS, `v(vo) = -399.41 V .. +399.19 V`, `V(C1) = 199.03 V`, `V(C2) = 397.04 V`
- **ZClaw-Synthesized Boost Converter (`15456` pts)**: `2571.75 ms`, `34.41 MB` RSS
- **Unit & Integration Tests**: `11/11` passing (`22.014 s` on CardputerZero, `1.480 s` on Windows desktop)

---

## Build & Run

```bash
# Build arm64 .deb package on CardputerZero / Debian
sudo apt-get update && sudo apt-get install -y libngspice0 python3-pygame python3-numpy python3-psutil
bash packaging/build_deb.sh
sudo apt-get install -y ./dist/cp0-ngspice_0.2.0-1_arm64.deb

# Run unit tests
python3 -m unittest discover -s tests -v

# Headless CLI example
cp0-ngspice list --json
cp0-ngspice run 04_5level_sc_inverter --param Vin=240 --json
```

Licensed under the [MIT License](LICENSE).
