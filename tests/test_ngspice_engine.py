"""Comprehensive unit & integration tests for PocketSpice NGSPICE engine, raw .cir, 5-level inverter, and CLI."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cp0_ngspice import cli
from cp0_ngspice.engine.metrics import compute_signal_stats
from cp0_ngspice.engine.ngspice_ffi import NgspiceEngine
from cp0_ngspice.engine.projects import create_user_project, list_all_circuits
from cp0_ngspice.engine.templates import load_templates, parse_circuit_file


class TestNgspicePrototype(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = NgspiceEngine()
        cls.templates = {t.path.stem: t for t in load_templates(ROOT / "circuits", lib_dirs=[ROOT / "lib"])}

    def test_rc_step_steady_state(self) -> None:
        tpl = self.templates["01_rc_step"]
        res = self.engine.run_netlist(tpl.render_netlist(enforce_save=True), tpl.signals)
        self.assertTrue(res.ok, msg=res.error + "\n" + "\n".join(res.logs))
        stats = compute_signal_stats("v(out)", res.signals["v(out)"])
        self.assertGreater(stats.vavg, 4.95)
        self.assertLess(res.rss_after_mb, 150.0)

    def test_buck_converter_output_voltage(self) -> None:
        tpl = self.templates["02_buck_converter"]
        res = self.engine.run_netlist(tpl.render_netlist(enforce_save=True), tpl.signals)
        self.assertTrue(res.ok, msg=res.error + "\n" + "\n".join(res.logs))
        stats = compute_signal_stats("v(out)", res.signals["v(out)"])
        self.assertGreater(stats.vavg, 5.0)
        self.assertLess(stats.vavg, 6.2)

    def test_sc_doubler_step_up(self) -> None:
        tpl = self.templates["03_sc_doubler"]
        res = self.engine.run_netlist(tpl.render_netlist(enforce_save=True), tpl.signals)
        self.assertTrue(res.ok, msg=res.error + "\n" + "\n".join(res.logs))
        stats = compute_signal_stats("v(out)", res.signals["v(out)"])
        self.assertGreater(stats.vavg, 18.0)
        self.assertLess(stats.vavg, 24.5)

    def test_5level_sc_inverter_simulink_replication(self) -> None:
        tpl = self.templates["04_5level_sc_inverter"]
        res = self.engine.run_netlist(
            tpl.render_netlist(enforce_save=True, lib_dirs=[ROOT / "lib"]), tpl.signals
        )
        self.assertTrue(res.ok, msg=res.error + "\n" + "\n".join(res.logs))
        vo = res.signals["v(vo)"]
        vc1 = res.signals["v(c1_p,c1_n)"]
        vc2 = res.signals["v(c2_p,vo)"]
        tail = slice(int(vo.size * 0.5), None)
        vo_tail = vo[tail]
        # Must reach all 5 levels: -2Vin(-400), -Vin(-200), 0, +Vin(+200), +2Vin(+400)
        self.assertLess(float(np.min(vo_tail)), -375.0)
        self.assertGreater(float(np.max(vo_tail)), 375.0)
        self.assertTrue(np.any((vo_tail > 170.0) & (vo_tail < 220.0)))
        self.assertTrue(np.any((vo_tail > -220.0) & (vo_tail < -170.0)))
        self.assertTrue(np.any(np.abs(vo_tail) < 30.0))
        # Self-balanced flying capacitors: C1 ~ 200V, C2 ~ 400V
        self.assertGreater(float(np.mean(vc1[tail])), 188.0)
        self.assertGreater(float(np.mean(vc2[tail])), 385.0)
        self.assertLess(res.rss_after_mb, 150.0)

    def test_ac_bode_sweep(self) -> None:
        tpl = self.templates["05_bode_rlc_filter"]
        res = self.engine.run_netlist(tpl.render_netlist(enforce_save=True), tpl.signals)
        self.assertTrue(res.ok, msg=res.error + "\n" + "\n".join(res.logs))
        self.assertEqual(res.analysis_type, "ac")
        vout_db = res.signals["v(out)(dB)"]
        # DC gain ~ 0 dB, high-freq attenuation < -30 dB
        self.assertGreater(float(vout_db[0]), -1.0)
        self.assertLess(float(vout_db[-1]), -30.0)

    def test_arbitrary_raw_dc_and_op_netlists_without_annotations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CP0_NGSPICE_PROJECTS_DIR"] = tmp
            try:
                # Raw .dc diode sweep (no @param, no @signals)
                dc_net = (
                    "* Raw Diode DC Sweep\n"
                    ".include power_devices.lib\n"
                    ".param Rser = 10\n"
                    "V1 in 0 0\n"
                    "R1 in a {Rser}\n"
                    "X1 a 0 POWER_DIODE\n"
                    ".dc V1 0 2 0.05\n"
                    ".save v(a) i(V1)\n"
                    ".end\n"
                )
                dc_path = create_user_project(ROOT, "raw_diode_dc", dc_net)
                tpl_dc = parse_circuit_file(dc_path, is_user_project=True, search_dirs=[ROOT / "lib"])
                self.assertEqual([p.name for p in tpl_dc.params], ["Rser"])
                res_dc = self.engine.run_netlist(
                    tpl_dc.render_netlist(enforce_save=True, lib_dirs=[ROOT / "lib"]), None
                )
                self.assertTrue(res_dc.ok, msg=res_dc.error)
                self.assertEqual(res_dc.analysis_type, "dc")

                # Raw .op voltage divider
                op_net = (
                    "* Raw Divider OP\n"
                    "V1 in 0 10\n"
                    "R1 in mid 2k\n"
                    "R2 mid 0 3k\n"
                    ".op\n"
                    ".end\n"
                )
                op_path = create_user_project(ROOT, "raw_div_op", op_net)
                tpl_op = parse_circuit_file(op_path, is_user_project=True)
                res_op = self.engine.run_netlist(tpl_op.render_netlist(enforce_save=False), None)
                self.assertTrue(res_op.ok, msg=res_op.error)
                self.assertEqual(res_op.analysis_type, "op")
                op_dict = dict(res_op.op_table)
                mid_val = op_dict.get("v(mid)", op_dict.get("mid"))
                self.assertIsNotNone(mid_val)
                self.assertAlmostEqual(mid_val, 6.0, places=3)

                all_items = list_all_circuits(ROOT)
                self.assertTrue(any(t.is_user_project and t.path.parent.name == "raw_diode_dc" for t in all_items))
            finally:
                os.environ.pop("CP0_NGSPICE_PROJECTS_DIR", None)

    def test_cli_workflow_validate_and_run_json(self) -> None:
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(["run", "04_5level_sc_inverter", "--param", "Vin=100", "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["ok"])
        self.assertGreater(payload["signals_stats"]["v(vo)"]["max"], 180.0)
        self.assertLess(payload["signals_stats"]["v(vo)"]["max"], 210.0)

    def test_repeated_runs_do_not_leak_memory(self) -> None:
        tpl = self.templates["02_buck_converter"]
        net = tpl.render_netlist(enforce_save=True)
        first = self.engine.run_netlist(net, tpl.signals)
        self.assertTrue(first.ok, msg=first.error)
        rss_start = first.rss_after_mb
        for _ in range(15):
            r = self.engine.run_netlist(net, tpl.signals)
            self.assertTrue(r.ok, msg=r.error)
        self.assertLess(r.rss_after_mb - rss_start, 20.0)

    def test_bilingual_i18n_and_titles(self) -> None:
        from cp0_ngspice.ui.i18n import tr

        tpl = self.templates["04_5level_sc_inverter"]
        self.assertIn("TPEL26", tpl.display_title("en"))
        self.assertIn("五电平", tpl.display_title("zh"))
        self.assertIn("Docs", tr("en", "nav_circuits"))
        self.assertNotIn("Man", tr("en", "nav_circuits"))
        self.assertIn("手册", tr("zh", "nav_circuits"))

    def test_fbdev_rgb565_and_m5stack_keymap(self) -> None:
        import struct
        import pygame
        from cp0_ngspice.ui.fb_backend import FbdevBackend, decode_evdev_key

        self.assertEqual(decode_evdev_key(71), (pygame.K_MINUS, "-"))
        self.assertEqual(decode_evdev_key(91), (pygame.K_PERIOD, "."))
        self.assertEqual(decode_evdev_key(73), (pygame.K_EQUALS, "="))
        self.assertEqual(decode_evdev_key(30, shift=False), (pygame.K_a, "a"))
        self.assertEqual(decode_evdev_key(30, shift=True), (pygame.K_a, "A"))
        self.assertEqual(decode_evdev_key(103), (pygame.K_UP, ""))

        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        with tempfile.TemporaryDirectory() as tmpdir:
            fb_path = Path(tmpdir) / "fb0"
            fb_path.write_bytes(b"\x00" * (320 * 170 * 2))
            backend = FbdevBackend(320, 170, fb_path=str(fb_path), kbd_path=str(Path(tmpdir) / "nokbd"))
            surf = pygame.Surface((320, 170))
            surf.fill((255, 0, 0))
            backend.present(surf)
            backend.close()
            raw = fb_path.read_bytes()
            self.assertEqual(len(raw), 320 * 170 * 2)
            px0, = struct.unpack("<H", raw[:2])
            self.assertEqual(px0, 0xF800)

    def test_spice_suffix_in_param_and_boost_project_discovery(self) -> None:
        boost_net = """* Boost Converter (ZClaw style)
* @title: Boost 12V->24V
* @param: Vin | 12 | 5 | 48 | 1 | V | Input voltage
* @param: Fsw | 100k | 20k | 500k | 10k | Hz | Switching frequency
* @param: D | 0.5 | 0.05 | 0.95 | 0.01 | - | Duty cycle
* @param: L | 100u | 10u | 1m | 10u | H | Boost inductor
* @param: Cout | 100u | 10u | 1m | 10u | F | Output capacitor
* @signals: v(out)
.include power_devices.lib
.param Vin = 12
.param Fsw = 100e3
.param D = 0.5
.param L = 100e-6
.param Cout = 100e-6
.param Tsw = '1.0 / Fsw'
.param Ton = 'D * Tsw'
Vin vin_in 0 {Vin}
L_boost vin_in sw_node {L}
X_mos sw_node 0 gate MOSFET_SW
X_di sw_node out POWER_DIODE
Cout out 0 {Cout}
Rload out 0 50
Vgate gate 0 PULSE(0 5 0 1n 1n {Ton} {Tsw})
.tran 200n 3m 2m 200n uic
.options method=gear reltol=2e-3
.save v(out)
.end
"""
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CP0_NGSPICE_PROJECTS_DIR"] = tmp
            try:
                p = create_user_project(ROOT, "zclaw_boost", boost_net)
                tpl = parse_circuit_file(p, is_user_project=True, search_dirs=[p.parent, ROOT / "lib"])
                self.assertAlmostEqual(tpl.params[1].default, 100000.0)
                self.assertAlmostEqual(tpl.params[3].default, 100e-6)
                # Verify modifying D updates BOTH {D} and .param D = ...
                tpl.params[2].value = 0.6
                rendered = "\n".join(tpl.render_netlist(lib_dirs=[ROOT / "lib"]))
                self.assertIn(".param D = 0.6", rendered)
                tpl.params[2].reset()
                res = self.engine.run_netlist(tpl.render_netlist(lib_dirs=[ROOT / "lib"]), tpl.signals)
                self.assertTrue(res.ok, msg=res.error)
                self.assertGreater(float(np.mean(res.signals["v(out)"])), 20.0)

                # Bad user file must not break list_all_circuits
                bad_dir = Path(tmp) / "broken_dir"
                bad_dir.mkdir()
                (bad_dir / "main.cir").write_bytes(b"\xff\xfe\x00")
                items = list_all_circuits(ROOT)
                self.assertTrue(any(t.path.parent.name == "zclaw_boost" for t in items))
            finally:
                os.environ.pop("CP0_NGSPICE_PROJECTS_DIR", None)


if __name__ == "__main__":
    unittest.main()
