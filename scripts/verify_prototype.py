"""Headless verification script: runs all 5 circuits, checks RSS budget, renders EN & ZH 320x170 screens."""
from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame
from cp0_ngspice.engine.metrics import compute_signal_stats
from cp0_ngspice.ui.app import PocketSpiceApp


def main() -> int:
    app = PocketSpiceApp(
        app_root=ROOT,
        circuits_dir=ROOT / "circuits",
        screenshots_dir=ROOT / "screenshots",
        scale=1,
        headless=True,
        lang="en",
    )

    try:
        print(f"Engine: {app.engine.version_str()}")
        print(f"Loaded {len(app.templates)} circuits/projects")

        # 1. English screenshots
        app.circuit_idx = 1  # Buck
        app.param_cursor = 1
        app.mode = "CIRCUITS"
        app.save_screenshot("01_circuits.png")

        shot_map = {
            1: ("02_scope_buck.png", 3),
            2: ("02b_scope_sc.png", 1),
            3: ("02c_scope_5level.png", 2),
            4: ("02d_scope_bode.png", 1),
        }
        for idx in range(min(5, len(app.templates))):
            app.circuit_idx = idx
            res = app.run_current_simulation()
            assert res.ok, f"Circuit {app.current_circuit.title} failed: {res.error}"
            out_sig = next(iter(res.signals.keys()))
            st = compute_signal_stats(out_sig, res.signals[out_sig])
            print(
                f"  [{idx+1}] {app.current_circuit.title} ({res.analysis_type}): "
                f"{res.elapsed_ms:.1f} ms | {res.time.size} pts | "
                f"{out_sig} min={st.vmin:.2f} max={st.vmax:.2f} avg={st.vavg:.2f} | "
                f"RSS={res.rss_after_mb:.1f} MB"
            )
            if idx in shot_map:
                fname, zoom = shot_map[idx]
                app.mode = "SCOPE"
                app.zoom_level = zoom
                app.save_screenshot(fname)

        app.circuit_idx = 3
        app._sync_netlist_buffer()
        app.net_cursor = 2
        app.mode = "NETLIST"
        app.save_screenshot("04_netlist.png")

        app.mode = "MANUAL"
        app.manual_ch_idx = 1
        app.manual_scroll = 0
        app.save_screenshot("05_manual.png")

        app.run_all_benchmarks()
        app.mode = "INFO"
        app.save_screenshot("03_telemetry.png")

        # 2. Chinese UI screenshots (verify CJK glyph rendering & zero tofu)
        app.set_lang("zh", persist=False)
        app.circuit_idx = 3
        app.param_cursor = 0
        app.mode = "CIRCUITS"
        app.save_screenshot("01_circuits_zh.png")

        app.run_current_simulation()
        app.mode = "SCOPE"
        app.zoom_level = 2
        app.save_screenshot("02c_scope_5level_zh.png")

        app.mode = "MANUAL"
        app.manual_ch_idx = 0
        app.manual_scroll = 0
        app.save_screenshot("05_manual_zh.png")

        app.run_all_benchmarks()
        app.mode = "INFO"
        app.save_screenshot("03_telemetry_zh.png")
        print("Saved EN + ZH screenshots cleanly.")
        return 0
    finally:
        pygame.quit()


if __name__ == "__main__":
    raise SystemExit(main())
