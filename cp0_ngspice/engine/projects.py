"""User project workspace management ($HOME/.config/cp0-ngspice/projects on Linux)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

from cp0_ngspice.engine.templates import CircuitTemplate, load_templates, parse_circuit_file


def get_projects_root(app_root: Path) -> Path:
    override = os.environ.get("CP0_NGSPICE_PROJECTS_DIR")
    if override:
        p = Path(override)
        p.mkdir(parents=True, exist_ok=True)
        return p

    if sys.platform.startswith("linux"):
        cfg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        p = cfg / "cp0-ngspice" / "projects"
    else:
        p = app_root / "projects"
    p.mkdir(parents=True, exist_ok=True)
    return p


def sanitize_project_slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip()).strip("_")
    return slug or "custom_circuit"


def get_extra_project_roots() -> list[Path]:
    """Return read-compatible external AI workspace folders (e.g. ZClaw sandbox) when present."""
    if os.environ.get("CP0_NGSPICE_PROJECTS_DIR"):
        return []
    roots: list[Path] = []
    env_extra = os.environ.get("CP0_NGSPICE_EXTRA_PROJECTS_DIR", "").strip()
    if env_extra:
        roots.append(Path(env_extra))
    if sys.platform.startswith("linux"):
        zclaw_ws = Path.home() / ".zeroclaw" / "agents" / "zclaw" / "workspace" / "pocketspice"
        if zclaw_ws.is_dir():
            roots.append(zclaw_ws)
    return roots


def list_all_circuits(app_root: Path) -> list[CircuitTemplate]:
    lib_dir = app_root / "lib"
    builtins = load_templates(app_root / "circuits", lib_dirs=[lib_dir])
    roots = [get_projects_root(app_root), *get_extra_project_roots()]
    user_items: list[CircuitTemplate] = []
    seen_slugs: set[str] = set()
    for user_root in roots:
        if not user_root.is_dir():
            continue
        for sub in sorted(user_root.iterdir()):
            if not sub.is_dir() or sub.name in seen_slugs:
                continue
            main_cir = sub / "main.cir"
            if not main_cir.exists():
                cirs = sorted(sub.glob("*.cir"))
                if not cirs:
                    continue
                main_cir = cirs[0]
            try:
                tpl = parse_circuit_file(main_cir, is_user_project=True, search_dirs=[sub, lib_dir])
            except Exception:
                continue
            seen_slugs.add(sub.name)
            user_items.append(tpl)
    return builtins + user_items


def create_user_project(
    app_root: Path,
    name: str,
    netlist_text: str,
    source_recipe: str = "custom",
) -> Path:
    slug = sanitize_project_slug(name)
    proj_dir = get_projects_root(app_root) / slug
    proj_dir.mkdir(parents=True, exist_ok=True)
    cir_path = proj_dir / "main.cir"
    cir_path.write_text(netlist_text, encoding="utf-8")

    meta = {
        "project_name": slug,
        "source_recipe": source_recipe,
        "netlist_file": "main.cir",
    }
    (proj_dir / "project.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return cir_path


def clone_template_to_project(app_root: Path, tpl: CircuitTemplate, new_name: str | None = None) -> Path:
    base = new_name or f"{tpl.path.stem}_custom"
    # Ensure unique name if already exists
    user_root = get_projects_root(app_root)
    slug = sanitize_project_slug(base)
    idx = 1
    cand = slug
    while (user_root / cand).exists():
        idx += 1
        cand = f"{slug}_{idx}"
    return create_user_project(app_root, cand, tpl.raw_text, source_recipe=tpl.path.stem)


def save_project_lines(cir_path: Path, lines: list[str]) -> None:
    cir_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
