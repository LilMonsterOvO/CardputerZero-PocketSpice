"""Headless CLI & Local-AI Integration Interface for PocketSpice (cp0-ngspice)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from cp0_ngspice.engine.metrics import compute_signal_stats
from cp0_ngspice.engine.ngspice_ffi import NgspiceEngine
from cp0_ngspice.engine.projects import (
    create_user_project,
    get_projects_root,
    list_all_circuits,
)
from cp0_ngspice.engine.templates import parse_circuit_file


def get_app_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_target(app_root: Path, target: str) -> Path | None:
    cand = Path(target)
    if cand.exists() and cand.is_file():
        return cand
    for tpl in list_all_circuits(app_root):
        if tpl.path.stem == target or tpl.path.parent.name == target or tpl.title == target:
            return tpl.path
    return None


def cmd_manual(args: argparse.Namespace) -> int:
    docs_dir = get_app_root() / "docs"
    sfx = "_ZH" if getattr(args, "lang", "en") == "zh" else ""
    if args.topic == "user":
        print((docs_dir / f"USER_MANUAL{sfx}.md").read_text(encoding="utf-8"))
    elif args.topic == "ai":
        print((docs_dir / f"AI_AGENT_MANUAL{sfx}.md").read_text(encoding="utf-8"))
    elif args.topic == "recipes":
        print((docs_dir / "recipes.json").read_text(encoding="utf-8"))
    else:
        for fname in (f"USER_MANUAL{sfx}.md", f"AI_AGENT_MANUAL{sfx}.md"):
            print(f"===== {fname} =====")
            print((docs_dir / fname).read_text(encoding="utf-8"))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    root = get_app_root()
    items = list_all_circuits(root)
    payload = {
        "projects_dir": str(get_projects_root(root)),
        "lib_dir": str(root / "lib"),
        "docs_dir": str(root / "docs"),
        "circuits": [
            {
                "id": t.path.parent.name if t.is_user_project else t.path.stem,
                "title": t.title,
                "analysis": t.detect_analysis(),
                "is_user_project": t.is_user_project,
                "path": str(t.path),
                "params": [p.name for p in t.params],
                "signals": t.signals,
            }
            for t in items
        ],
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Projects dir: {payload['projects_dir']}")
        for c in payload["circuits"]:
            tag = "[USER]" if c["is_user_project"] else "[BUILTIN]"
            print(f"  {tag:<10} {c['id']:<26} ({c['analysis']}) -> {c['title']}")
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    root = get_app_root()
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
        source_tag = Path(args.file).name
    elif args.stdin:
        text = sys.stdin.read()
        source_tag = "stdin"
    elif args.source:
        src_path = _resolve_target(root, args.source)
        if src_path is None:
            print(f"Source template/project not found: {args.source}", file=sys.stderr)
            return 2
        text = src_path.read_text(encoding="utf-8")
        source_tag = args.source
    else:
        text = (
            f"* {args.name}\n"
            ".include power_devices.lib\n"
            "V1 in 0 5\n"
            "R1 in out 1k\n"
            "C1 out 0 1u IC=0\n"
            ".tran 20u 5m uic\n"
            ".save v(in) v(out)\n"
            ".end\n"
        )
        source_tag = "blank_rc"

    out_path = create_user_project(root, args.name, text, source_recipe=source_tag)
    print(json.dumps({"ok": True, "project_file": str(out_path)}, ensure_ascii=False))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    root = get_app_root()
    p = _resolve_target(root, args.target)
    if p is None:
        print(json.dumps({"ok": False, "error": f"Not found: {args.target}"}))
        return 2
    tpl = parse_circuit_file(p, search_dirs=[p.parent, root / "lib"])
    lines = tpl.render_netlist(enforce_save=True, lib_dirs=[root / "lib"])
    has_save = any(ln.lower().startswith(".save") for ln in lines)
    has_end = bool(lines and lines[-1].lower() == ".end")
    has_analysis = any(
        re.match(r"^\.(tran|ac|dc|op)\b", ln.strip().lower()) for ln in lines
    )
    print(
        json.dumps(
            {
                "ok": has_end and has_analysis,
                "title": tpl.title,
                "analysis": tpl.detect_analysis(),
                "rendered_lines": len(lines),
                "has_save_pruning": has_save,
                "has_analysis": has_analysis,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if (has_end and has_analysis) else 1


def cmd_run(args: argparse.Namespace) -> int:
    root = get_app_root()
    p = _resolve_target(root, args.target)
    if p is None:
        out = {"ok": False, "error": f"Target not found: {args.target}"}
        print(json.dumps(out, ensure_ascii=False))
        return 2

    tpl = parse_circuit_file(p, search_dirs=[p.parent, root / "lib"])
    for assign in args.param or []:
        if "=" not in assign:
            continue
        k, v = assign.split("=", 1)
        for prm in tpl.params:
            if prm.name == k.strip():
                prm.value = float(v)

    lines = tpl.render_netlist(
        enforce_save=not args.no_save_prune, lib_dirs=[root / "lib"]
    )
    eng = NgspiceEngine()
    res = eng.run_netlist(lines, requested_signals=tpl.signals or None)

    stats = {}
    for k, arr in res.signals.items():
        st = compute_signal_stats(k, arr)
        stats[k] = {
            "min": round(st.vmin, 6),
            "max": round(st.vmax, 6),
            "avg_tail": round(st.vavg, 6),
            "pp_tail": round(st.vpp_tail, 6),
            "samples": st.samples,
        }

    payload = {
        "ok": res.ok,
        "engine": eng.version_str(),
        "title": tpl.title,
        "analysis_type": res.analysis_type,
        "elapsed_ms": round(res.elapsed_ms, 2),
        "points": int(res.time.size),
        "rss_after_mb": round(res.rss_after_mb, 2),
        "available_vectors": res.available_vectors,
        "signals_stats": stats,
        "op_table": res.op_table,
        "error": res.error,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(
            f"[{tpl.title}] ok={res.ok} type={res.analysis_type} "
            f"time={res.elapsed_ms:.1f}ms pts={res.time.size} rss={res.rss_after_mb:.1f}MB"
        )
        for k, s in stats.items():
            print(f"  {k}: min={s['min']} max={s['max']} avg_tail={s['avg_tail']} pp_tail={s['pp_tail']}")
        if not res.ok:
            print("  ERROR:", res.error)
    return 0 if res.ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cp0-ngspice", description="PocketSpice CLI & Local-AI Runner")
    sub = p.add_subparsers(dest="cmd", required=True)

    pm = sub.add_parser("manual", help="Print bundled User/AI manuals or recipes")
    pm.add_argument("--topic", choices=("all", "user", "ai", "recipes"), default="all")
    pm.add_argument("--lang", choices=("en", "zh"), default="en")
    pm.set_defaults(func=cmd_manual)

    pl = sub.add_parser("list", help="List available built-in circuits and user projects")
    pl.add_argument("--json", action="store_true")
    pl.set_defaults(func=cmd_list)

    pn = sub.add_parser("new", help="Create a new user NGSPICE project")
    pn.add_argument("name", help="Project slug name")
    pn.add_argument("--from", dest="source", help="Clone from built-in circuit/project id")
    pn.add_argument("--file", help="Import an existing .cir file")
    pn.add_argument("--stdin", action="store_true", help="Read netlist text from stdin")
    pn.set_defaults(func=cmd_new)

    pv = sub.add_parser("validate", help="Validate netlist syntax and .save memory hygiene")
    pv.add_argument("target")
    pv.set_defaults(func=cmd_validate)

    pr = sub.add_parser("run", help="Simulate a circuit or user project headlessly")
    pr.add_argument("target", help="Circuit id, project name, or .cir path")
    pr.add_argument("--param", action="append", help="Override parameter e.g. --param Duty=0.6")
    pr.add_argument("--no-save-prune", action="store_true")
    pr.add_argument("--json", action="store_true")
    pr.set_defaults(func=cmd_run)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
