"""High-contrast 320x170 waveform oscilloscope & .ac/.dc/.op renderer."""
from __future__ import annotations

import numpy as np
import pygame

from cp0_ngspice.engine.metrics import compute_signal_stats, format_eng
from cp0_ngspice.ui import theme
from cp0_ngspice.ui.fonts import FontPack
from cp0_ngspice.ui.i18n import tr


def draw_scope(
    surf: pygame.Surface,
    rect: pygame.Rect,
    x_arr: np.ndarray,
    traces: list[tuple[str, np.ndarray]],
    active_idx: int,
    zoom_level: int,
    fonts: FontPack,
    lang: str = "zh",
    analysis_type: str = "tran",
    x_label: str = "s",
    op_table: list[tuple[str, float]] | None = None,
) -> None:
    """Render .tran, .ac (log-freq Bode), .dc sweep, or .op table inside 320x170 plot area."""
    pygame.draw.rect(surf, theme.PANEL_BG, rect)
    pygame.draw.rect(surf, theme.BORDER_COLOR, rect, 1)

    if analysis_type == "op" and op_table:
        op_title = tr(lang, "op_title")
        hdr = fonts.pick(op_title, "sm").render(op_title, True, theme.ACCENT_CYAN)
        surf.blit(hdr, (rect.x + 6, rect.y + 4))
        y = rect.y + 22
        for name, val in op_table[:6]:
            unit = "A" if ("branch" in name.lower() or name.lower().startswith("i(")) else "V"
            row = fonts.mono_xs.render(f"{name:<20} = {format_eng(val, unit)}", True, theme.TEXT_PRIMARY)
            surf.blit(row, (rect.x + 8, y))
            y += 16
        return

    if x_arr.size < 2 or not traces:
        txt = tr(lang, "no_wave")
        msg = fonts.pick(txt, "sm").render(txt, True, theme.TEXT_MUTED)
        surf.blit(msg, (rect.x + 12, rect.y + rect.height // 2 - 6))
        return

    n_total = x_arr.size
    if analysis_type == "tran":
        if zoom_level == 2:
            start_i = int(n_total * 0.5)
        elif zoom_level == 3:
            start_i = int(n_total * 0.8)
        else:
            start_i = 0
    else:
        start_i = 0

    x_slice = x_arr[start_i:]
    if x_slice.size < 2:
        start_i = 0
        x_slice = x_arr

    hud_h = 17
    plot = pygame.Rect(rect.x + 2, rect.y + hud_h, rect.width - 4, rect.height - hud_h - 2)

    for gx in range(1, 4):
        x = plot.x + (plot.width * gx) // 4
        pygame.draw.line(surf, theme.GRID_COLOR, (x, plot.y), (x, plot.bottom - 1), 1)
    for gy in range(1, 4):
        y = plot.y + (plot.height * gy) // 4
        pygame.draw.line(surf, theme.GRID_COLOR, (plot.x, y), (plot.right - 1, y), 1)

    pri_name, pri_arr = traces[active_idx % len(traces)]
    pri_slice = pri_arr[start_i:]
    stats = compute_signal_stats(pri_name, pri_slice)

    w_px = max(2, plot.width)
    if analysis_type == "ac" and np.all(x_slice > 0):
        log_x = np.log10(x_slice)
        targets = np.linspace(log_x[0], log_x[-1], num=w_px)
        x_coords = np.searchsorted(log_x, targets).clip(0, x_slice.size - 1)
    else:
        x_coords = np.linspace(0, x_slice.size - 1, num=w_px, dtype=np.int32)

    if len(traces) > 1:
        sec_idx = (active_idx + 1) % len(traces)
        _, sec_arr = traces[sec_idx]
        sec_slice = sec_arr[start_i:]
        _plot_trace(surf, plot, sec_slice, x_coords, (72, 110, 140))

    _plot_trace(surf, plot, pri_slice, x_coords, theme.CH_COLORS[active_idx % len(theme.CH_COLORS)])

    # Top HUD bar (subtle dark header strip so waveform never overlaps text)
    pygame.draw.rect(surf, (18, 24, 34), (rect.x + 1, rect.y + 1, rect.width - 2, hud_h - 1))
    pygame.draw.line(surf, theme.GRID_COLOR, (rect.x + 1, rect.y + hud_h - 1), (rect.right - 2, rect.y + hud_h - 1))

    if analysis_type == "ac" or pri_name.endswith("(dB)"):
        unit = "dB"
        short_sig = pri_name.replace("(dB)", "")
        hud_txt = (
            f"{short_sig} pk:{stats.vmax:.1f}dB "
            f"[{format_eng(float(x_slice[0]), 'Hz')}..{format_eng(float(x_slice[-1]), 'Hz')}]"
        )
    else:
        unit = "A" if ("branch" in pri_name.lower() or pri_name.lower().startswith("i(")) else "V"
        x_span = float(x_slice[-1] - x_slice[0])
        is_bipolar = (stats.vmin < -0.1 * max(1.0, abs(stats.vmax))) and (stats.vmax > 0.1 * max(1.0, abs(stats.vmin)))
        stat_tag = f"rms:{format_eng(stats.vrms, unit)}" if is_bipolar else f"avg:{format_eng(stats.vavg, unit)}"
        hud_txt = f"{pri_name} {stat_tag} pp:{format_eng(stats.vpp_tail, unit)} dx:{format_eng(x_span, x_label)}"

    lbl = fonts.mono_xs.render(hud_txt[:48], True, theme.TEXT_PRIMARY)
    surf.blit(lbl, (rect.x + 5, rect.y + 3))

    # Bottom-left scale pill with dark backdrop so dense PWM edges remain crisp
    scale_str = f"{format_eng(stats.vmin, unit)} .. {format_eng(stats.vmax, unit)}"
    scale_lbl = fonts.mono_xs.render(scale_str, True, theme.TEXT_PRIMARY)
    pill_rect = pygame.Rect(plot.x + 2, plot.bottom - 14, scale_lbl.get_width() + 8, 13)
    pill_surf = pygame.Surface((pill_rect.width, pill_rect.height))
    pill_surf.set_alpha(210)
    pill_surf.fill((12, 16, 22))
    surf.blit(pill_surf, pill_rect.topleft)
    pygame.draw.rect(surf, theme.BORDER_COLOR, pill_rect, 1)
    surf.blit(scale_lbl, (pill_rect.x + 4, pill_rect.y + 1))


def _plot_trace(
    surf: pygame.Surface,
    plot: pygame.Rect,
    arr: np.ndarray,
    x_coords: np.ndarray,
    color: tuple[int, int, int],
) -> None:
    if arr.size < 2:
        return
    vmin = float(np.min(arr))
    vmax = float(np.max(arr))
    span = vmax - vmin
    if span < 1e-12:
        mid_y = plot.y + plot.height // 2
        pygame.draw.line(surf, color, (plot.x, mid_y), (plot.right - 1, mid_y), 1)
        return

    pad = span * 0.08
    lo = vmin - pad
    hi = vmax + pad
    rng = hi - lo

    vals = arr[x_coords]
    norm = (vals - lo) / rng
    pys = np.clip(
        (plot.bottom - 1 - norm * (plot.height - 2)).astype(np.int32),
        plot.y,
        plot.bottom - 1,
    )
    pxs = np.arange(plot.x, plot.x + x_coords.size, dtype=np.int32)
    pts = np.column_stack((pxs, pys)).tolist()

    if len(pts) >= 2:
        pygame.draw.lines(surf, color, False, pts, 1)
