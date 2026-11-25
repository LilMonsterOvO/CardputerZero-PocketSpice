"""PocketSpice 320x170 CardputerZero Simulator UI (Bilingual zh/en, Netlist Editor, Scope, Docs)."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import textwrap
import time
import pygame

from cp0_ngspice.engine.metrics import get_rss_mb
from cp0_ngspice.engine.ngspice_ffi import NgspiceEngine, SimResult
from cp0_ngspice.engine.projects import (
    clone_template_to_project,
    list_all_circuits,
    save_project_lines,
)
from cp0_ngspice.engine.templates import CircuitTemplate
from cp0_ngspice.ui import theme
from cp0_ngspice.ui.fb_backend import FbdevBackend, should_use_fbdev
from cp0_ngspice.ui.fonts import FontPack, has_cjk
from cp0_ngspice.ui.i18n import load_lang_pref, save_lang_pref, tr
from cp0_ngspice.ui.scope import draw_scope


class PocketSpiceApp:
    """Native 320x170 UI with cp0-keys mapping, zh/en i18n, raw netlist editor, and in-app docs."""

    def __init__(
        self,
        app_root: Path | None = None,
        circuits_dir: Path | None = None,
        screenshots_dir: Path | None = None,
        scale: int = 3,
        headless: bool = False,
        lang: str | None = None,
    ) -> None:
        self.app_root = app_root or Path(__file__).resolve().parents[2]
        self.circuits_dir = circuits_dir or (self.app_root / "circuits")
        if screenshots_dir is not None:
            self.screenshots_dir = screenshots_dir
        elif os.access(self.app_root, os.W_OK):
            self.screenshots_dir = self.app_root / "screenshots"
        else:
            self.screenshots_dir = Path.home() / "Pictures" / "PocketSpice"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.scale = max(1, min(4, scale))
        self.headless = headless
        self.lang = lang if lang in ("zh", "en") else load_lang_pref(self.app_root, default="zh")
        self.fb_backend: FbdevBackend | None = None
        self.fullscreen = False

        if should_use_fbdev(headless=headless):
            os.environ["SDL_VIDEODRIVER"] = "dummy"

        pygame.display.init()
        pygame.font.init()
        if headless:
            self.window = None
        elif should_use_fbdev(headless=headless):
            self.scale = 1
            self.fullscreen = True
            self.window = None
            self.fb_backend = FbdevBackend(theme.SCREEN_W, theme.SCREEN_H)
        elif sys.platform.startswith("linux") and os.environ.get("CP0_WINDOWED") != "1":
            self.scale = 1
            self.fullscreen = True
            self.window = pygame.display.set_mode(
                (theme.SCREEN_W, theme.SCREEN_H),
                pygame.FULLSCREEN | pygame.NOFRAME,
            )
            pygame.mouse.set_visible(False)
        else:
            pygame.display.set_caption("PocketSpice (CardputerZero 320x170 + NGSPICE)")
            self.window = pygame.display.set_mode(
                (theme.SCREEN_W * self.scale, theme.SCREEN_H * self.scale)
            )

        self.canvas = pygame.Surface((theme.SCREEN_W, theme.SCREEN_H))
        self.fonts = FontPack()
        self.clock = pygame.time.Clock()

        self.templates: list[CircuitTemplate] = list_all_circuits(self.app_root)
        self.circuit_idx = 3 if len(self.templates) > 3 else 0
        self.param_cursor = 0
        self.param_scroll = 0
        self.mode = "CIRCUITS"  # CIRCUITS | NETLIST | SCOPE | MANUAL | INFO
        self.show_help = False
        self.enforce_save = True

        self.edit_buffer: str | None = None
        self.edit_target: str = "param"

        self.net_lines: list[str] = []
        self.net_cursor = 0
        self.net_scroll = 0

        self.manual_chapters = self._load_manual_chapters()
        self.manual_ch_idx = 0
        self.manual_scroll = 0

        self.active_ch = 0
        self.zoom_level = 1
        self.status_msg = tr(self.lang, "ready")

        self.engine = NgspiceEngine()
        self.last_result: SimResult | None = None
        self.bench_summary: list[tuple[str, float, float, int]] = []
        self.running = True
        self._dirty = True
        self._cached_rss_mb = get_rss_mb()
        self._last_rss_time = time.monotonic()

    def _get_rss_throttled(self) -> float:
        now = time.monotonic()
        if now - self._last_rss_time >= 2.5:
            self._cached_rss_mb = get_rss_mb()
            self._last_rss_time = now
        return self._cached_rss_mb

    def set_lang(self, new_lang: str, persist: bool = True) -> None:
        self.lang = "zh" if new_lang == "zh" else "en"
        if persist:
            save_lang_pref(self.app_root, self.lang)
        self.manual_chapters = self._load_manual_chapters()
        self.manual_ch_idx = min(self.manual_ch_idx, len(self.manual_chapters) - 1)
        self.manual_scroll = 0
        self.status_msg = tr(self.lang, "ready")

    def toggle_lang(self) -> None:
        self.set_lang("en" if self.lang == "zh" else "zh")

    def _load_manual_chapters(self) -> list[tuple[str, list[tuple[str, bool]]]]:
        docs_dir = self.app_root / "docs"
        if self.lang == "zh":
            files = [
                (tr("zh", "ch_user"), docs_dir / "USER_MANUAL_ZH.md"),
                (tr("zh", "ch_ai"), docs_dir / "AI_AGENT_MANUAL_ZH.md"),
            ]
        else:
            files = [
                (tr("en", "ch_user"), docs_dir / "USER_MANUAL.md"),
                (tr("en", "ch_ai"), docs_dir / "AI_AGENT_MANUAL.md"),
            ]

        chapters: list[tuple[str, list[tuple[str, bool]]]] = []
        for label, fpath in files:
            if not fpath.exists():
                continue
            raw_lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
            wrapped: list[tuple[str, bool]] = []
            for ln in raw_lines:
                s = ln.strip()
                if not s:
                    wrapped.append(("", False))
                    continue
                is_hdr = s.startswith("#")
                clean = s.lstrip("#").strip() if is_hdr else s
                width = 25 if has_cjk(clean) else 44
                for chunk in textwrap.wrap(clean, width=width) or [clean]:
                    wrapped.append((chunk, is_hdr))
            chapters.append((label, wrapped))
        if not chapters:
            chapters.append(("Docs", [("Docs not found", True)]))
        return chapters

    @property
    def current_circuit(self) -> CircuitTemplate:
        return self.templates[self.circuit_idx]

    def reload_circuits(self, select_path: Path | None = None) -> None:
        self.templates = list_all_circuits(self.app_root)
        if select_path is not None:
            for idx, tpl in enumerate(self.templates):
                if tpl.path.resolve() == select_path.resolve():
                    self.circuit_idx = idx
                    break
        self.circuit_idx = max(0, min(len(self.templates) - 1, self.circuit_idx))
        self.param_cursor = -1 if not self.current_circuit.params else 0
        self.param_scroll = 0

    def _sync_netlist_buffer(self) -> None:
        self.net_lines = self.current_circuit.editable_lines()
        self.net_cursor = 0
        self.net_scroll = 0

    def _draw_simulating_banner(self, label: str) -> None:
        if self.headless:
            return
        box = pygame.Rect(26, 58, theme.SCREEN_W - 52, 48)
        pygame.draw.rect(self.canvas, (14, 22, 34), box, border_radius=6)
        pygame.draw.rect(self.canvas, theme.ACCENT_AMBER, box, 2, border_radius=6)
        msg = "正在仿真 NGSPICE..." if self.lang == "zh" else "Running NGSPICE..."
        f1 = self.fonts.pick(msg, "sm", bold=True)
        t1 = self.fonts.render_cached(f1, msg, theme.ACCENT_AMBER)
        self.canvas.blit(t1, (box.centerx - t1.get_width() // 2, box.y + 6))
        f2 = self.fonts.pick(label, "xs")
        sub = self._fit_text(f2, label, box.width - 16)
        t2 = self.fonts.render_cached(f2, sub, theme.TEXT_PRIMARY)
        self.canvas.blit(t2, (box.centerx - t2.get_width() // 2, box.y + 26))
        self._flush_display()

    def run_current_simulation(self) -> SimResult:
        tpl = self.current_circuit
        self._draw_simulating_banner(tpl.display_title(self.lang))
        netlist = tpl.render_netlist(
            enforce_save=self.enforce_save, lib_dirs=[self.app_root / "lib"]
        )
        res = self.engine.run_netlist(netlist, requested_signals=tpl.signals or None)
        self.last_result = res
        self._cached_rss_mb = res.rss_after_mb
        self._last_rss_time = time.monotonic()
        self.active_ch = 0
        if res.ok:
            self.status_msg = f"OK {res.elapsed_ms:.1f}ms | RSS {res.rss_after_mb:.1f}MB"
        else:
            self.status_msg = f"ERR: {res.error[:36]}"
        self._dirty = True
        return res

    def run_all_benchmarks(self) -> None:
        summary: list[tuple[str, float, float, int]] = []
        for idx, tpl in enumerate(self.templates[:5]):
            self._draw_simulating_banner(f"[{idx+1}/5] {tpl.display_title(self.lang)}")
            netlist = tpl.render_netlist(
                enforce_save=self.enforce_save, lib_dirs=[self.app_root / "lib"]
            )
            res = self.engine.run_netlist(netlist, requested_signals=tpl.signals or None)
            pts = int(res.time.size)
            short_title = tpl.display_title(self.lang).split("(")[0].strip()
            summary.append((short_title, res.elapsed_ms, res.rss_after_mb, pts))
        self.bench_summary = summary
        self._cached_rss_mb = get_rss_mb()
        self._last_rss_time = time.monotonic()
        self.status_msg = f"Test {len(summary)} OK"
        self._dirty = True

    def save_screenshot(self, filename: str | None = None) -> Path:
        self.render()
        if filename is None:
            stamp = time.strftime("%H%M%S")
            filename = f"cp0_{self.mode.lower()}_{stamp}.png"
        out = self.screenshots_dir / filename
        pygame.image.save(self.canvas, str(out))
        self.status_msg = tr(self.lang, "saved", name=out.name)
        return out

    def handle_key(self, key: int, unicode_char: str = "") -> None:
        if self.edit_buffer is not None:
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._commit_edit_buffer()
            elif key == pygame.K_ESCAPE:
                self.edit_buffer = None
                self.status_msg = tr(self.lang, "edit_cancel")
            elif key == pygame.K_BACKSPACE:
                self.edit_buffer = self.edit_buffer[:-1]
            elif unicode_char and unicode_char.isprintable():
                if self.edit_target == "param" and unicode_char not in "0123456789.-":
                    return
                max_len = 64 if self.edit_target == "netline" else 12
                if len(self.edit_buffer) < max_len:
                    self.edit_buffer += unicode_char
            return

        if key == pygame.K_h:
            self.show_help = not self.show_help
            return
        if key == pygame.K_l:
            self.toggle_lang()
            return

        if self.show_help:
            if key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.show_help = False
            return

        if self.window is not None and not self.fullscreen and key in (pygame.K_1, pygame.K_2, pygame.K_3):
            self.scale = int(key - pygame.K_0)
            self.window = pygame.display.set_mode(
                (theme.SCREEN_W * self.scale, theme.SCREEN_H * self.scale)
            )
            self.status_msg = f"Zoom {self.scale}x"
            return

        if key == pygame.K_ESCAPE:
            if self.mode != "CIRCUITS":
                self.mode = "CIRCUITS"
            else:
                self.running = False
            return

        if key == pygame.K_4:
            self._action_key_4()
        elif key == pygame.K_5:
            self._action_key_5()
        elif key == pygame.K_6:
            self._action_key_6()
        elif key == pygame.K_7:
            self._action_key_7()
        elif key == pygame.K_8:
            self._action_key_8()
        elif key in (pygame.K_f, pygame.K_UP):
            self._nav_vertical(-1)
        elif key in (pygame.K_x, pygame.K_DOWN):
            self._nav_vertical(1)
        elif key in (pygame.K_z, pygame.K_LEFT):
            self._nav_horizontal(-1)
        elif key in (pygame.K_c, pygame.K_RIGHT):
            self._nav_horizontal(1)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if self.mode == "CIRCUITS" and self.param_cursor >= 0:
                self._start_param_edit()
            elif self.mode == "NETLIST":
                self._start_netline_edit()
            elif self.mode == "CIRCUITS":
                self._action_key_4()

    def _action_key_4(self) -> None:
        if self.mode == "CIRCUITS":
            res = self.run_current_simulation()
            if res.ok:
                self.mode = "SCOPE"
        elif self.mode == "NETLIST":
            self._persist_netlist_if_needed(auto_clone=True)
            res = self.run_current_simulation()
            if res.ok:
                self.mode = "SCOPE"
        elif self.mode == "SCOPE":
            self.run_current_simulation()
        elif self.mode in ("MANUAL", "INFO"):
            self.mode = "CIRCUITS"

    def _action_key_5(self) -> None:
        if self.mode == "CIRCUITS":
            if self.param_cursor >= 0:
                self._start_param_edit()
            else:
                new_cir = clone_template_to_project(self.app_root, self.current_circuit)
                self.reload_circuits(select_path=new_cir)
                self.status_msg = tr(self.lang, "cloned", name=new_cir.parent.name)
        elif self.mode == "NETLIST":
            self._start_netline_edit()
        elif self.mode == "SCOPE":
            if self.last_result and self.last_result.signals:
                self.active_ch = (self.active_ch + 1) % len(self.last_result.signals)
        elif self.mode == "MANUAL":
            self.manual_ch_idx = (self.manual_ch_idx - 1) % len(self.manual_chapters)
            self.manual_scroll = 0
        elif self.mode == "INFO":
            self.run_all_benchmarks()

    def _action_key_6(self) -> None:
        if self.mode == "CIRCUITS":
            self._sync_netlist_buffer()
            self.mode = "NETLIST"
        elif self.mode == "NETLIST":
            if self.net_lines:
                self.net_lines.insert(self.net_cursor + 1, "* new spice line")
                self.net_cursor += 1
                self._adjust_net_scroll()
        elif self.mode == "SCOPE":
            self.zoom_level = (self.zoom_level % 3) + 1
            lbl = {1: "Full", 2: "Last 50%", 3: "Last 20%"}[self.zoom_level]
            self.status_msg = f"Zoom: {lbl}"
        elif self.mode == "MANUAL":
            self.manual_ch_idx = (self.manual_ch_idx + 1) % len(self.manual_chapters)
            self.manual_scroll = 0
        elif self.mode == "INFO":
            self.enforce_save = not self.enforce_save
            self.status_msg = f".save: {'ON' if self.enforce_save else 'OFF'}"

    def _action_key_7(self) -> None:
        if self.mode == "CIRCUITS":
            if self.last_result is None:
                self.run_current_simulation()
            self.mode = "SCOPE"
        elif self.mode == "NETLIST":
            saved_path = self._persist_netlist_if_needed(auto_clone=True)
            self.status_msg = tr(self.lang, "saved", name=saved_path.parent.name)
        elif self.mode == "SCOPE":
            self.mode = "CIRCUITS"
        elif self.mode == "MANUAL":
            self.mode = "INFO"
        elif self.mode == "INFO":
            self.toggle_lang()

    def _action_key_8(self) -> None:
        if self.mode == "CIRCUITS":
            self.mode = "MANUAL"
        elif self.mode == "NETLIST":
            self.mode = "CIRCUITS"
        elif self.mode == "SCOPE":
            self.save_screenshot()
        elif self.mode == "MANUAL":
            self.running = False
        elif self.mode == "INFO":
            self.mode = "MANUAL"

    def _persist_netlist_if_needed(self, auto_clone: bool = True) -> Path:
        tpl = self.current_circuit
        if tpl.is_user_project:
            save_project_lines(tpl.path, self.net_lines)
            self.reload_circuits(select_path=tpl.path)
            return tpl.path
        if auto_clone:
            new_cir = clone_template_to_project(self.app_root, tpl)
            save_project_lines(new_cir, self.net_lines)
            self.reload_circuits(select_path=new_cir)
            return new_cir
        return tpl.path

    def _adjust_net_scroll(self) -> None:
        if self.net_cursor < self.net_scroll:
            self.net_scroll = self.net_cursor
        elif self.net_cursor >= self.net_scroll + 6:
            self.net_scroll = self.net_cursor - 5

    def _nav_vertical(self, delta: int) -> None:
        if self.mode == "CIRCUITS":
            n_params = len(self.current_circuit.params)
            self.param_cursor = max(-1, min(n_params - 1, self.param_cursor + delta))
            if self.param_cursor >= 0:
                if self.param_cursor < self.param_scroll:
                    self.param_scroll = self.param_cursor
                elif self.param_cursor >= self.param_scroll + 4:
                    self.param_scroll = self.param_cursor - 3
        elif self.mode == "NETLIST":
            if self.net_lines:
                self.net_cursor = max(0, min(len(self.net_lines) - 1, self.net_cursor + delta))
                self._adjust_net_scroll()
        elif self.mode == "MANUAL":
            _, lines = self.manual_chapters[self.manual_ch_idx]
            max_scroll = max(0, len(lines) - 7)
            self.manual_scroll = max(0, min(max_scroll, self.manual_scroll + delta))
        elif self.mode == "SCOPE":
            self.circuit_idx = (self.circuit_idx + delta) % len(self.templates)
            self.param_cursor = -1 if not self.current_circuit.params else 0
            self.param_scroll = 0
            self.run_current_simulation()

    def _nav_horizontal(self, delta: int) -> None:
        if self.mode == "CIRCUITS":
            if self.param_cursor < 0:
                self.circuit_idx = (self.circuit_idx + delta) % len(self.templates)
                self.param_cursor = -1
                self.param_scroll = 0
            else:
                p = self.current_circuit.params[self.param_cursor]
                p.nudge(delta)
                self.status_msg = f"{p.name} = {p.format_value()} {p.unit}"
        elif self.mode == "SCOPE":
            if self.last_result and self.last_result.signals:
                self.active_ch = (self.active_ch + delta) % len(self.last_result.signals)
        elif self.mode == "MANUAL":
            self.manual_ch_idx = (self.manual_ch_idx + delta) % len(self.manual_chapters)
            self.manual_scroll = 0

    def _start_param_edit(self) -> None:
        p = self.current_circuit.params[self.param_cursor]
        self.edit_target = "param"
        self.edit_buffer = p.format_value()
        self.status_msg = tr(self.lang, "type_val", name=p.name)

    def _start_netline_edit(self) -> None:
        if not self.net_lines:
            return
        self.edit_target = "netline"
        self.edit_buffer = self.net_lines[self.net_cursor]
        self.status_msg = tr(self.lang, "edit_line")

    def _commit_edit_buffer(self) -> None:
        assert self.edit_buffer is not None
        if self.edit_target == "param":
            p = self.current_circuit.params[self.param_cursor]
            try:
                val = float(self.edit_buffer)
                p.value = max(p.min_val, min(p.max_val, val))
                self.status_msg = f"{p.name} = {p.format_value()} {p.unit}"
            except ValueError:
                self.status_msg = tr(self.lang, "invalid_num")
        else:
            self.net_lines[self.net_cursor] = self.edit_buffer
            self.status_msg = f"L{self.net_cursor + 1} OK"
        self.edit_buffer = None

    def _fit_text(self, font: pygame.font.Font, text: str, max_px: int) -> str:
        return self.fonts.fit_text(font, text, max_px)

    def _flush_display(self) -> None:
        if self.fb_backend is not None:
            self.fb_backend.present(self.canvas)
        elif self.window is not None:
            if self.scale == 1:
                self.window.blit(self.canvas, (0, 0))
            else:
                scaled = pygame.transform.scale(
                    self.canvas, (theme.SCREEN_W * self.scale, theme.SCREEN_H * self.scale)
                )
                self.window.blit(scaled, (0, 0))
            pygame.display.flip()

    def render(self) -> None:
        self.canvas.fill(theme.BG_COLOR)
        self._draw_header()
        if self.mode == "CIRCUITS":
            self._draw_circuits_view()
        elif self.mode == "NETLIST":
            self._draw_netlist_view()
        elif self.mode == "SCOPE":
            self._draw_scope_view()
        elif self.mode == "MANUAL":
            self._draw_manual_view()
        else:
            self._draw_info_view()
        self._draw_navbar()
        if self.show_help:
            self._draw_help_overlay()
        self._flush_display()

    def _draw_header(self) -> None:
        pygame.draw.rect(self.canvas, theme.HEADER_BG, (0, 0, theme.SCREEN_W, theme.HEADER_H))
        pygame.draw.line(self.canvas, theme.ACCENT_BLUE, (0, 0), (theme.SCREEN_W, 0))
        pygame.draw.line(
            self.canvas, theme.BORDER_COLOR, (0, theme.HEADER_H - 1), (theme.SCREEN_W, theme.HEADER_H - 1)
        )
        rss = self._get_rss_throttled()
        rss_color = theme.ACCENT_GREEN if rss < 120 else (theme.ACCENT_AMBER if rss < 250 else theme.ACCENT_RED)
        rss_lbl = self.fonts.render_cached(self.fonts.mono_xs, f"{rss:.0f}M", rss_color)
        lang_tag = "中" if self.lang == "zh" else "EN"
        lang_lbl = self.fonts.render_cached(self.fonts.pick(lang_tag, "xs"), lang_tag, theme.ACCENT_CYAN)
        right_w = rss_lbl.get_width() + lang_lbl.get_width() + 18

        tag = "[U]" if self.current_circuit.is_user_project else ""
        raw_hdr = f"SPICE{tag} | {self.current_circuit.display_title(self.lang)}"
        hdr_txt = self._fit_text(self.fonts.ui_md, raw_hdr, theme.SCREEN_W - right_w - 10)
        title = self.fonts.render_cached(self.fonts.ui_md, hdr_txt, theme.TEXT_PRIMARY)
        self.canvas.blit(title, (6, 1))
        self.canvas.blit(lang_lbl, (theme.SCREEN_W - right_w + 2, 2))
        self.canvas.blit(rss_lbl, (theme.SCREEN_W - rss_lbl.get_width() - 6, 3))

    def _draw_circuits_view(self) -> None:
        y = theme.CONTENT_TOP + 3
        sel_active = self.param_cursor == -1
        sel_rect = pygame.Rect(4, y, theme.SCREEN_W - 8, 20)
        pygame.draw.rect(self.canvas, (32, 46, 64) if sel_active else theme.PANEL_BG, sel_rect, border_radius=3)
        pygame.draw.rect(
            self.canvas, theme.ACCENT_BLUE if sel_active else theme.BORDER_COLOR, sel_rect, 1, border_radius=3
        )
        tag = "USR:" if self.current_circuit.is_user_project else ""
        nav_raw = f"< [{self.circuit_idx+1}/{len(self.templates)}] {tag}{self.current_circuit.display_title(self.lang)} >"
        nav_txt = self._fit_text(self.fonts.ui_sm, nav_raw, sel_rect.width - 12)
        lbl = self.fonts.render_cached(self.fonts.ui_sm, nav_txt, theme.TEXT_PRIMARY)
        self.canvas.blit(lbl, (10, y + 2))

        row_y = y + 23
        params = self.current_circuit.params
        if not params:
            hint_txt = tr(self.lang, "raw_hint")
            empty_msg = self.fonts.render_cached(self.fonts.pick(hint_txt, "xs"), hint_txt, theme.TEXT_MUTED)
            self.canvas.blit(empty_msg, (10, row_y + 16))
        else:
            visible = params[self.param_scroll : self.param_scroll + 4]
            for i, p in enumerate(visible):
                real_idx = self.param_scroll + i
                active = real_idx == self.param_cursor
                r = pygame.Rect(4, row_y + i * 21, theme.SCREEN_W - 8, 19)
                pygame.draw.rect(self.canvas, (30, 42, 58) if active else theme.PANEL_BG, r, border_radius=2)
                if active:
                    pygame.draw.rect(self.canvas, theme.ACCENT_CYAN, r, 1, border_radius=2)
                name_lbl = self.fonts.render_cached(
                    self.fonts.mono_sm, f"{p.name}", theme.TEXT_PRIMARY if active else theme.TEXT_MUTED
                )
                self.canvas.blit(name_lbl, (10, r.y + 3))
                val_str = (
                    self.edit_buffer + "_"
                    if (active and self.edit_target == "param" and self.edit_buffer is not None)
                    else f"{p.format_value()} {p.unit}"
                )
                val_col = theme.ACCENT_AMBER if (active and self.edit_buffer is not None) else theme.ACCENT_GREEN
                val_lbl = self.fonts.render_cached(self.fonts.mono_sm, val_str, val_col)
                self.canvas.blit(val_lbl, (theme.SCREEN_W - val_lbl.get_width() - 12, r.y + 3))

        st_font = self.fonts.pick(self.status_msg, "xs")
        st_txt = self._fit_text(st_font, self.status_msg, theme.SCREEN_W - 12)
        self.canvas.blit(self.fonts.render_cached(st_font, st_txt, theme.TEXT_MUTED), (6, theme.CONTENT_BOTTOM - 14))

    def _draw_netlist_view(self) -> None:
        y = theme.CONTENT_TOP + 3
        vis = self.net_lines[self.net_scroll : self.net_scroll + 6]
        for i, line in enumerate(vis):
            idx = self.net_scroll + i
            active = idx == self.net_cursor
            r = pygame.Rect(4, y + i * 18, theme.SCREEN_W - 8, 17)
            pygame.draw.rect(self.canvas, (30, 42, 58) if active else theme.PANEL_BG, r)
            if active:
                pygame.draw.rect(self.canvas, theme.ACCENT_CYAN, r, 1)
            txt = (
                self.edit_buffer + "_"
                if (active and self.edit_target == "netline" and self.edit_buffer is not None)
                else line
            )
            col = theme.ACCENT_AMBER if (active and self.edit_buffer is not None) else (
                theme.TEXT_PRIMARY if active else theme.TEXT_MUTED
            )
            line_font = self.fonts.pick(txt, "xs")
            line_str = self._fit_text(line_font, f"{idx+1:02d} {txt}", r.width - 6)
            self.canvas.blit(self.fonts.render_cached(line_font, line_str, col), (7, r.y + 2))

        st_font = self.fonts.pick(self.status_msg, "xs")
        st_txt = self._fit_text(st_font, self.status_msg, theme.SCREEN_W - 12)
        self.canvas.blit(self.fonts.render_cached(st_font, st_txt, theme.TEXT_MUTED), (6, theme.CONTENT_BOTTOM - 14))

    def _draw_scope_view(self) -> None:
        rect = pygame.Rect(2, theme.CONTENT_TOP + 2, theme.SCREEN_W - 4, theme.CONTENT_H - 4)
        if self.last_result is None or not self.last_result.ok:
            pygame.draw.rect(self.canvas, theme.PANEL_BG, rect)
            err = self.last_result.error if self.last_result else tr(self.lang, "not_sim")
            ef = self.fonts.pick(err, "sm")
            msg = ef.render(self._fit_text(ef, err, rect.width - 20), True, theme.ACCENT_RED)
            self.canvas.blit(msg, (10, rect.y + 45))
            return

        traces = list(self.last_result.signals.items())
        draw_scope(
            self.canvas,
            rect,
            self.last_result.time,
            traces,
            self.active_ch,
            self.zoom_level,
            self.fonts,
            lang=self.lang,
            analysis_type=self.last_result.analysis_type,
            x_label=self.last_result.x_label,
            op_table=self.last_result.op_table,
        )

    def _draw_manual_view(self) -> None:
        ch_title, lines = self.manual_chapters[self.manual_ch_idx]
        hdr_txt = tr(self.lang, "manual_hdr", title=ch_title)
        hf = self.fonts.pick(hdr_txt, "sm")
        self.canvas.blit(
            self.fonts.render_cached(hf, self._fit_text(hf, hdr_txt, theme.SCREEN_W - 12), theme.ACCENT_CYAN),
            (6, theme.CONTENT_TOP + 2),
        )
        y = theme.CONTENT_TOP + 20
        for ln, is_hdr in lines[self.manual_scroll : self.manual_scroll + 7]:
            col = theme.ACCENT_AMBER if is_hdr else theme.TEXT_PRIMARY
            lf = self.fonts.pick(ln, "xs")
            self.canvas.blit(
                self.fonts.render_cached(lf, self._fit_text(lf, ln, theme.SCREEN_W - 12), col),
                (6, y),
            )
            y += 14

    def _draw_info_view(self) -> None:
        y = theme.CONTENT_TOP + 4
        rss = self._get_rss_throttled()
        ver = self.engine.version_str()
        last_str = (
            f"{self.last_result.elapsed_ms:.1f}ms ({self.last_result.analysis_type})"
            if self.last_result
            else "N/A"
        )
        lines = [
            (f"Engine: {ver} | Lib: power_devices.lib", theme.TEXT_PRIMARY),
            (f"RAM RSS: {rss:.1f} MB / 512 MB ({rss/512*100:.1f}%)", theme.ACCENT_GREEN),
            (f".save: {'ON' if self.enforce_save else 'OFF'} | Last: {last_str}", theme.ACCENT_CYAN),
        ]
        for text, col in lines:
            tf = self.fonts.pick(text, "xs")
            self.canvas.blit(
                self.fonts.render_cached(tf, self._fit_text(tf, text, theme.SCREEN_W - 12), col),
                (6, y),
            )
            y += 15

        bar_bg = pygame.Rect(6, y + 1, theme.SCREEN_W - 12, 7)
        pygame.draw.rect(self.canvas, theme.GRID_COLOR, bar_bg)
        fill_w = max(2, int((rss / 512.0) * bar_bg.width))
        pygame.draw.rect(self.canvas, theme.ACCENT_GREEN, (bar_bg.x, bar_bg.y, fill_w, bar_bg.height))
        y += 12

        if self.bench_summary:
            for name, ms, b_rss, pts in self.bench_summary[:4]:
                nf = self.fonts.pick(name, "xs")
                name_fit = self._fit_text(nf, name, 130)
                self.canvas.blit(self.fonts.render_cached(nf, name_fit, theme.TEXT_PRIMARY), (6, y))
                metrics_str = f"{ms:5.1f}ms {pts:5d}pt {b_rss:4.0f}M"
                self.canvas.blit(
                    self.fonts.render_cached(self.fonts.mono_xs, metrics_str, theme.ACCENT_CYAN),
                    (144, y),
                )
                y += 13
        else:
            hint_txt = tr(self.lang, "bench_hint")
            hf = self.fonts.pick(hint_txt, "sm")
            self.canvas.blit(self.fonts.render_cached(hf, hint_txt, theme.TEXT_MUTED), (6, y + 6))

    def _draw_navbar(self) -> None:
        pygame.draw.rect(
            self.canvas, theme.NAV_BG, (0, theme.CONTENT_BOTTOM, theme.SCREEN_W, theme.NAVBAR_H)
        )
        pygame.draw.line(
            self.canvas, theme.BORDER_COLOR, (0, theme.CONTENT_BOTTOM), (theme.SCREEN_W, theme.CONTENT_BOTTOM)
        )

        if self.mode == "CIRCUITS":
            key = "nav_circuits_sel" if self.param_cursor < 0 else "nav_circuits"
            colors = (theme.ACCENT_GREEN, theme.ACCENT_BLUE, theme.ACCENT_AMBER, theme.ACCENT_CYAN, theme.TEXT_PRIMARY)
        elif self.mode == "NETLIST":
            key = "nav_netlist"
            colors = (theme.ACCENT_GREEN, theme.ACCENT_BLUE, theme.ACCENT_AMBER, theme.ACCENT_CYAN, theme.TEXT_PRIMARY)
        elif self.mode == "SCOPE":
            key = "nav_scope"
            colors = (theme.ACCENT_GREEN, theme.ACCENT_AMBER, theme.ACCENT_BLUE, theme.TEXT_PRIMARY, theme.ACCENT_CYAN)
        elif self.mode == "MANUAL":
            key = "nav_manual"
            colors = (theme.TEXT_PRIMARY, theme.ACCENT_BLUE, theme.ACCENT_BLUE, theme.ACCENT_CYAN, theme.ACCENT_RED)
        else:
            key = "nav_info"
            colors = (theme.TEXT_PRIMARY, theme.ACCENT_GREEN, theme.ACCENT_AMBER, theme.ACCENT_CYAN, theme.TEXT_MUTED)

        labels = tr(self.lang, key).split(",")
        for idx, (cx, label, col) in enumerate(zip(theme.NAV_CENTERS_X, labels, colors)):
            key_num = theme.NAV_KEYS_LABELS[idx]
            box = pygame.Rect(cx - 24, theme.NAV_ICON_Y - 10, 48, 20)
            pygame.draw.rect(self.canvas, (26, 34, 46), box, border_radius=4)
            pygame.draw.rect(self.canvas, theme.BORDER_COLOR, box, 1, border_radius=4)
            pygame.draw.line(self.canvas, col, (box.x + 5, box.y + 1), (box.right - 6, box.y + 1), 1)
            full_lbl = f"{key_num}:{label}"
            bf = self.fonts.pick(full_lbl, "xs")
            txt = self.fonts.render_cached(bf, full_lbl, col)
            self.canvas.blit(txt, (cx - txt.get_width() // 2, theme.NAV_ICON_Y - txt.get_height() // 2 + 1))
            pygame.draw.line(self.canvas, col, (cx, theme.SCREEN_H - 4), (cx, theme.SCREEN_H - 1), 1)

    def _draw_help_overlay(self) -> None:
        overlay = pygame.Surface((theme.SCREEN_W - 20, theme.SCREEN_H - 36))
        overlay.set_alpha(238)
        overlay.fill((16, 22, 30))
        pygame.draw.rect(overlay, theme.ACCENT_BLUE, overlay.get_rect(), 1)
        help_lines = [
            tr(self.lang, "help_title"),
            tr(self.lang, "help_1"),
            tr(self.lang, "help_2"),
            tr(self.lang, "help_3"),
            tr(self.lang, "help_4"),
            tr(self.lang, "help_5"),
            tr(self.lang, "help_6"),
        ]
        y = 7
        for idx, line in enumerate(help_lines):
            col = theme.ACCENT_CYAN if idx == 0 else theme.TEXT_PRIMARY
            hf = self.fonts.pick(line, "xs")
            overlay.blit(self.fonts.render_cached(hf, line, col), (8, y))
            y += 17
        self.canvas.blit(overlay, (10, 18))

    def loop(self) -> None:
        try:
            self.render()
            self._dirty = False
            while self.running:
                had_event = False
                for ev in pygame.event.get():
                    if ev.type == pygame.QUIT:
                        self.running = False
                        had_event = True
                    elif ev.type == pygame.KEYDOWN:
                        self.handle_key(ev.key, ev.unicode)
                        had_event = True
                if self.fb_backend is not None:
                    wait_s = 0.0 if (had_event or self._dirty) else 0.015
                    for ev_key, ev_char in self.fb_backend.poll_keys(timeout=wait_s):
                        self.handle_key(ev_key, ev_char)
                        had_event = True
                if had_event or self._dirty:
                    self.render()
                    self._dirty = False
                elif self.fb_backend is None:
                    self.clock.tick(30)
        finally:
            if self.fb_backend is not None:
                self.fb_backend.close()
            pygame.quit()


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    app = PocketSpiceApp(app_root=root, scale=3)
    app.loop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
