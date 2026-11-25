"""Bilingual (zh / en) UI strings and persistent language preference."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys


def get_config_path(app_root: Path) -> Path:
    if sys.platform.startswith("linux"):
        cfg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        d = cfg / "cp0-ngspice"
    else:
        d = app_root / "projects"
    d.mkdir(parents=True, exist_ok=True)
    return d / "config.json"


def load_lang_pref(app_root: Path, default: str = "zh") -> str:
    cfg_file = get_config_path(app_root)
    if cfg_file.exists():
        try:
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            lang = str(data.get("lang", default)).lower()
            if lang in ("zh", "en"):
                return lang
        except Exception:
            pass
    return default


def save_lang_pref(app_root: Path, lang: str) -> None:
    cfg_file = get_config_path(app_root)
    data = {}
    if cfg_file.exists():
        try:
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["lang"] = lang
    cfg_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "ready": "Ready (4:Run 6:Net 8:Docs)",
        "raw_hint": "Raw .cir (4:Run or 6:Net edit)",
        "no_wave": "No waveform data",
        "not_sim": "Not simulated yet",
        "op_title": "DC Operating Point (.op)",
        "manual_hdr": "DOCS | {title} (F/X scroll)",
        "bench_hint": "Press [5] Test to benchmark",
        "edit_cancel": "Edit cancelled",
        "type_val": "Type {name} & Enter",
        "edit_line": "Edit line & Enter",
        "invalid_num": "Invalid number",
        "saved": "Saved {name}",
        "cloned": "Cloned -> {name}",
        "nav_circuits": "Run,Edit,Net,Wave,Docs",
        "nav_circuits_sel": "Run,Copy,Net,Wave,Docs",
        "nav_netlist": "Run,Line,+Add,Save,Back",
        "nav_scope": "Run,Ch,Zoom,Parm,Shot",
        "nav_manual": "Back,Prev,Next,Info,Exit",
        "nav_info": "Back,Test,.sav,中/EN,Docs",
        "ch_user": "1.User Manual",
        "ch_ai": "2.AI & CLI Guide",
        "help_title": "CardputerZero Keys (cp0-keys)",
        "help_1": "F/X (Up/Dn)  : Select / scroll",
        "help_2": "Z/C (Lt/Rt)  : Step / switch Ch",
        "help_3": "Enter        : Edit param or line",
        "help_4": "4 ~ 8        : Bottom action bar",
        "help_5": "L / ESC      : Switch Lang / Back",
        "help_6": "1 / 2 / 3    : Desktop zoom (PC)",
    },
    "zh": {
        "ready": "就绪 (4:运行 6:网表 8:手册)",
        "raw_hint": "原生网表 (4:运行 或 6:编辑)",
        "no_wave": "暂无波形数据",
        "not_sim": "尚未运行仿真",
        "op_title": "直流工作点 (.op)",
        "manual_hdr": "手册 | {title} (F/X 翻页)",
        "bench_hint": "按 [5] 压测全部内置电路",
        "edit_cancel": "已取消编辑",
        "type_val": "输入 {name} 后回车",
        "edit_line": "编辑网表行后回车",
        "invalid_num": "无效数值",
        "saved": "已保存 {name}",
        "cloned": "已克隆 -> {name}",
        "nav_circuits": "运行,编辑,网表,波形,手册",
        "nav_circuits_sel": "运行,克隆,网表,波形,手册",
        "nav_netlist": "运行,改行,+行,保存,返回",
        "nav_scope": "重跑,通道,缩放,参数,截图",
        "nav_manual": "返回,上章,下章,信息,退出",
        "nav_info": "返回,压测,裁剪,中/EN,手册",
        "ch_user": "1.用户操作手册",
        "ch_ai": "2.本地AI与CLI手册",
        "help_title": "CardputerZero 键位说明",
        "help_1": "F/X (上/下)  : 选择 / 滚动",
        "help_2": "Z/C (左/右)  : 调参 / 切通道",
        "help_3": "Enter        : 输入数值或编辑行",
        "help_4": "4 ~ 8        : 底部功能栏按键",
        "help_5": "L / ESC      : 切换中英 / 返回",
        "help_6": "1 / 2 / 3    : 桌面端窗口缩放",
    },
}


def tr(lang: str, key: str, **kwargs: object) -> str:
    table = STRINGS.get(lang, STRINGS["en"])
    tmpl = table.get(key, STRINGS["en"].get(key, key))
    return tmpl.format(**kwargs) if kwargs else tmpl
