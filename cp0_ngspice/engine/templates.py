"""Universal SPICE netlist loader: supports @param templates, raw .cir, and .include resolution."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re


@dataclass
class CircuitParam:
    name: str
    default: float
    min_val: float
    max_val: float
    step: float
    unit: str
    description: str
    value: float
    is_raw_param: bool = False

    def nudge(self, direction: int) -> None:
        nxt = round(self.value + direction * self.step, 8)
        self.value = max(self.min_val, min(self.max_val, nxt))

    def reset(self) -> None:
        self.value = self.default

    def format_value(self) -> str:
        if abs(self.value) >= 100:
            s = f"{self.value:.1f}"
        elif abs(self.value) >= 1:
            s = f"{self.value:.3f}"
        elif abs(self.value) >= 1e-3:
            s = f"{self.value:.6f}"
        else:
            return f"{self.value:.3g}"
        return s.rstrip("0").rstrip(".")


@dataclass
class CircuitTemplate:
    path: Path
    title: str
    title_zh: str
    description: str
    params: list[CircuitParam]
    signals: list[str]
    raw_text: str
    is_user_project: bool = False
    search_dirs: list[Path] = field(default_factory=list)

    def display_title(self, lang: str = "en") -> str:
        if lang == "zh" and self.title_zh:
            return self.title_zh
        return self.title

    def detect_analysis(self) -> str:
        for line in self.raw_text.splitlines():
            low = line.strip().lower()
            if not low or low.startswith("*"):
                continue
            m = re.match(r"^\.(tran|ac|dc|op)\b", low)
            if m:
                return m.group(1)
        return "tran"

    def _expand_includes(
        self, lines: list[str], extra_dirs: list[Path], visited: set[Path]
    ) -> list[str]:
        out: list[str] = []
        for line in lines:
            stripped = line.strip()
            m_inc = re.match(r"^\.include\s+[\"']?([^\"'\s]+)[\"']?", stripped, re.I)
            if m_inc:
                inc_name = m_inc.group(1)
                resolved = self._resolve_include_path(inc_name, extra_dirs)
                if resolved is not None and resolved not in visited:
                    visited.add(resolved)
                    inc_lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
                    out.append(f"* --- begin include: {resolved.name} ---")
                    out.extend(self._expand_includes(inc_lines, [resolved.parent, *extra_dirs], visited))
                    out.append(f"* --- end include: {resolved.name} ---")
                    continue
            out.append(line)
        return out

    def _resolve_include_path(self, inc_name: str, dirs: list[Path]) -> Path | None:
        cand = Path(inc_name)
        if cand.is_absolute() and cand.exists():
            return cand.resolve()
        for d in dirs:
            p = d / inc_name
            if p.exists():
                return p.resolve()
        return None

    def render_netlist(
        self,
        enforce_save: bool = True,
        lib_dirs: list[Path] | None = None,
    ) -> list[str]:
        """Render executable NGSPICE lines with parameter substitution & .include expansion."""
        text = self.raw_text
        for p in self.params:
            text = re.sub(
                rf"(^\s*\.param\s+{re.escape(p.name)}\s*=\s*)([^\s*]+)",
                lambda m, val=p.value: f"{m.group(1)}{val:g}",
                text,
                flags=re.I | re.M,
            )
            if not p.is_raw_param:
                text = text.replace(f"{{{p.name}}}", f"{p.value:g}")

        dirs = [self.path.parent, *self.search_dirs, *(lib_dirs or [])]
        expanded = self._expand_includes(text.splitlines(), dirs, {self.path.resolve()})

        lines: list[str] = [f"* {self.title}"]
        has_save = False
        for raw_line in expanded:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("*"):
                continue
            low = stripped.lower()
            if low.startswith(".save"):
                has_save = True
                if not enforce_save:
                    continue
            if low == ".end":
                continue
            lines.append(stripped)

        if enforce_save and not has_save and self.signals:
            save_tokens: list[str] = []
            for sig in self.signals:
                m = re.match(r"^v\(([^,]+),([^)]+)\)$", sig.strip(), re.I)
                if m:
                    save_tokens.extend([f"v({m.group(1).strip()})", f"v({m.group(2).strip()})"])
                else:
                    save_tokens.append(sig.strip())
            lines.append(".save " + " ".join(dict.fromkeys(save_tokens)))

        lines.append(".end")
        return lines

    def editable_lines(self) -> list[str]:
        return self.raw_text.splitlines()


def _parse_numeric_literal(raw: str) -> float | None:
    suffixes = {
        "t": 1e12,
        "g": 1e9,
        "meg": 1e6,
        "k": 1e3,
        "m": 1e-3,
        "u": 1e-6,
        "n": 1e-9,
        "p": 1e-12,
        "f": 1e-15,
    }
    s = raw.strip().lower()
    m = re.match(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)(meg|[tgkmunpf])?$", s)
    if not m:
        return None
    val = float(m.group(1))
    suf = m.group(2)
    if suf:
        val *= suffixes[suf]
    return val


def parse_circuit_file(
    path: Path,
    is_user_project: bool = False,
    search_dirs: list[Path] | None = None,
) -> CircuitTemplate:
    raw = path.read_text(encoding="utf-8")
    title = path.stem
    title_zh = ""
    desc = ""
    params: list[CircuitParam] = []
    signals: list[str] = []

    raw_lines = raw.splitlines()
    for line in raw_lines:
        s = line.strip()
        if not s.startswith("*"):
            continue
        body = s.lstrip("*").strip()
        if body.startswith("@title:"):
            title = body.split(":", 1)[1].strip()
        elif body.startswith("@title_zh:"):
            title_zh = body.split(":", 1)[1].strip()
        elif body.startswith("@desc:"):
            desc = body.split(":", 1)[1].strip()
        elif body.startswith("@signals:"):
            sig_str = body.split(":", 1)[1].strip()
            signals = [tok.strip() for tok in re.split(r",(?![^()]*\))", sig_str) if tok.strip()]
        elif body.startswith("@param:"):
            parts = [p.strip() for p in body.split(":", 1)[1].split("|")]
            if len(parts) >= 7:
                name = parts[0]
                nums = [_parse_numeric_literal(parts[i]) for i in (1, 2, 3, 4)]
                if all(v is not None for v in nums):
                    default, min_val, max_val, step = (float(v) for v in nums if v is not None)
                    params.append(
                        CircuitParam(
                            name=name,
                            default=default,
                            min_val=min_val,
                            max_val=max_val,
                            step=step,
                            unit=parts[5],
                            description=parts[6],
                            value=default,
                            is_raw_param=False,
                        )
                    )

    # Fallback: if no @param annotations exist, auto-discover numeric .param lines
    if not params:
        for line in raw_lines:
            s = line.strip()
            m_p = re.match(r"^\.param\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^\s*]+)", s, re.I)
            if m_p:
                pname = m_p.group(1)
                num = _parse_numeric_literal(m_p.group(2))
                if num is not None:
                    span = abs(num) if num != 0 else 1.0
                    params.append(
                        CircuitParam(
                            name=pname,
                            default=num,
                            min_val=0.0 if num >= 0 else -span * 10.0,
                            max_val=max(span * 10.0, 1.0),
                            step=max(span * 0.1, 1e-6),
                            unit="",
                            description="Raw .param literal",
                            value=num,
                            is_raw_param=True,
                        )
                    )
        if title == path.stem and raw_lines and raw_lines[0].strip().startswith("*"):
            first_title = raw_lines[0].strip().lstrip("*").strip()
            if first_title and not first_title.startswith("@"):
                title = first_title[:32]

    return CircuitTemplate(
        path=path,
        title=title,
        title_zh=title_zh or title,
        description=desc,
        params=params,
        signals=signals,
        raw_text=raw,
        is_user_project=is_user_project,
        search_dirs=list(search_dirs or []),
    )


def load_templates(circuits_dir: Path, lib_dirs: list[Path] | None = None) -> list[CircuitTemplate]:
    files = sorted(circuits_dir.glob("*.cir"))
    return [parse_circuit_file(f, is_user_project=False, search_dirs=lib_dirs) for f in files]
