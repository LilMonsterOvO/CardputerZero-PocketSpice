# PocketSpice User Manual (CardputerZero)

## 1. Key Controls (46-Key Layout)
- 4 ~ 8 : Bottom 5 action buttons
- F / X : Move Up / Down (or scroll)
- Z / C : Move Left / Right (step value / switch channel)
- Enter : Edit active parameter or netlist line
- H     : Toggle keymap help overlay
- ESC   : Return to Circuits screen / Exit app

## 2. Five Screens Overview
1) CIRCUITS:
   - Row 0 (< [i/N] Title >): Z/C switch circuit.
   - Key 5 on Row 0: Clone circuit to User Project.
   - Param rows: Z/C nudge, Enter/5 direct type.
   - Key 4:Run | 5:Edit | 6:Net | 7:Wave | 8:Man
2) NETLIST (Raw NGSPICE Editor):
   - Supports any valid NGSPICE .cir syntax!
   - Key 4:Save+Run | 5:Edit Line | 6:+Add | 7:Save
   - Non-template raw .cir files work directly:
     .tran, .ac, .dc, and .op are auto-detected.
3) SCOPE:
   - Plots .tran, .ac (log-Hz dB), .dc, or .op table.
   - Key 4:Run | 5:Ch | 6:Zoom | 7:Parm | 8:Shot
4) MANUAL:
   - Key 5:Prev | 6:Next chapter | F/X scroll | 7:Info
5) INFO (512MB RAM Telemetry):
   - Key 5:Bench all circuits | 6:Toggle .save prune

## 3. Built-in Circuits & 5-Level Inverter
- 01_rc_step: First-order RC charging check.
- 02_buck_converter: PWM Buck DC-DC ripple & current.
- 03_sc_doubler: 2x Switched-Cap charge pump.
- 04_5level_sc_inverter: 11-IGBT 2-SC 5-level CGSCMLI
  (Dou et al., IEEE TPEL 2026,
   DOI: 10.1109/TPEL.2026.3683439, +-400V/+-200V/0V).
- 05_bode_rlc_filter: 2nd-order LC filter (.ac Bode).

## 4. User Projects & .include Library
- User projects live in:
  Linux: $HOME/.config/cp0-ngspice/projects/<name>/main.cir
  Win:   <app>/projects/<name>/main.cir
- Use `.include power_devices.lib` in any project
  to access IGBT_DIODE, BIDIR_IGBT, MOSFET_SW,
  and POWER_DIODE subcircuits.

## 5. 512 MB RAM Rules
- Always include `.save v(...) i(...)` in long
  transient runs to prevent RAM bloat.
- Keep transient points <= 50,000 when possible.
- Never run PocketSpice as root.
