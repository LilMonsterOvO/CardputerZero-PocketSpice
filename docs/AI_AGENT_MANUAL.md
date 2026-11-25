# PocketSpice AI Agent Manual (NGSPICE on CardputerZero)

## 1. Purpose & Paths
This manual enables a local LLM or CLI agent on CardputerZero to select, generate, validate, and simulate ANY NGSPICE circuit project safely within 512 MB RAM.

- Installed App Share: /usr/share/cp0-ngspice/
- Reusable Device Lib: /usr/share/cp0-ngspice/lib/power_devices.lib
- Reference Circuits:  /usr/share/cp0-ngspice/circuits/
- Recipes JSON Index:  /usr/share/cp0-ngspice/docs/recipes.json
- User Projects Dir:   $HOME/.config/cp0-ngspice/projects/<slug>/main.cir
- ZClaw Sandbox Dir:   $HOME/.zeroclaw/agents/zclaw/workspace/pocketspice/<slug>/main.cir (auto-discovered if $HOME/.config is sandbox-blocked)

## 2. CLI Commands (Machine-Readable JSON)
Run via `cp0-ngspice <cmd>` (or `python3 -m cp0_ngspice.cli <cmd>`):

1. Inspect manuals & recipes:
   cp0-ngspice manual --topic ai
   cp0-ngspice manual --topic recipes
2. List existing circuits and user projects:
   cp0-ngspice list --json
3. Create a new project from recipe or stdin:
   cp0-ngspice new my_buck --from 02_buck_converter
   cat custom.cir | cp0-ngspice new my_custom --stdin
4. Validate syntax & .save memory hygiene:
   cp0-ngspice validate my_custom
5. Run simulation & read numeric results:
   cp0-ngspice run my_custom --json
   cp0-ngspice run 04_5level_sc_inverter --param Vin=240 --param ModIdx=0.9 --json

## 3. Mandatory NGSPICE v41 Syntax Rules
1. Line 1 MUST be a title comment (e.g. `* My Converter`). Never put `.param` on line 1.
2. `.param` RHS expressions must NOT use outer `{}`:
   CORRECT: `.param Tsw = '1.0 / 50000'` or `.param Vin = 200`
   WRONG:   `.param Tsw = {1.0 / 50000}`
3. Use `{param}` in element values, PWL/PULSE, and `.tran`.
4. Always terminate netlist with `.end`.
5. Zero-volt source current sensing: insert `V_sns node_a node_b 0` and read `i(V_sns)`.
6. Prefer `.include power_devices.lib` for switching topologies:
   - `X_sw c e g IGBT_DIODE` (Collector c, Emitter e, Gate g; diode e->c)
   - `X_bi a b g BIDIR_IGBT` (Anti-series common-collector bidirectional switch)
   - `X_mos d s g MOSFET_SW` (Drain d, Source s, Gate g)
   - `X_di a k POWER_DIODE` (Anode a, Cathode k)

## 4. Power Electronics Convergence Cookbook
- Use smooth switch transitions (`Vh=-0.2` in `.model SW`) and finite `Ron` (>= 1m..50m ohm) and parallel snubber `R_snub` (1e5 ohm) to prevent singular matrices.
- Add `.options method=gear reltol=2e-3 abstol=1e-8 vntol=1e-4` for multi-switch converters.
- For floating nodes in switched-capacitor stages, add `R_bleed node 0 1e7` to ground.
- For SPWM carriers, use `PWL(0 y0 t1 y1 t2 y2 Per y0) r=0` so NGSPICE places exact breakpoints on carrier peaks/valleys.

## 5. 512 MB Memory Guardrails (CardputerZero)
- Always add `.save v(...) i(...)` for ONLY the nodes/currents to plot.
- Target <= 30,000 time steps per run (`(tstop - tstart) / dt <= 30000`).
- For steady-state ripple on slow loops, use `.tran dt tstop tstart dt uic` to discard startup samples.
- Optional UI metadata headers (for slider tuning in 320x170 GUI):
  `* @title: Short Name`
  `* @param: Name | default | min | max | step | unit | desc`
  `* @signals: v(out), i(V_sns)`
  (If omitted, PocketSpice still auto-discovers raw `.param` literals and all plot vectors.)
