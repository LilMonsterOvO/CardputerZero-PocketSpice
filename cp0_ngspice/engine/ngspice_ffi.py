"""Cross-platform ctypes wrapper around libngspice supporting .tran, .ac, .dc, and .op."""
from __future__ import annotations

import ctypes
from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    c_bool,
    c_char_p,
    c_double,
    c_int,
    c_short,
    c_void_p,
)
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import sys
import threading
import time
import numpy as np

from cp0_ngspice.engine.metrics import get_rss_mb


class NgComplex(Structure):
    _fields_ = [("cx_real", c_double), ("cx_imag", c_double)]


class VectorInfo(Structure):
    _fields_ = [
        ("v_name", c_char_p),
        ("v_type", c_int),
        ("v_flags", c_short),
        ("v_realdata", POINTER(c_double)),
        ("v_compdata", POINTER(NgComplex)),
        ("v_length", c_int),
    ]


SEND_CHAR_CB = CFUNCTYPE(c_int, c_char_p, c_int, c_void_p)
SEND_STAT_CB = CFUNCTYPE(c_int, c_char_p, c_int, c_void_p)
CONTROLLED_EXIT_CB = CFUNCTYPE(c_int, c_int, c_bool, c_bool, c_int, c_void_p)
SEND_DATA_CB = CFUNCTYPE(c_int, c_void_p, c_int, c_int, c_void_p)
SEND_INIT_DATA_CB = CFUNCTYPE(c_int, c_void_p, c_int, c_void_p)
BG_RUNNING_CB = CFUNCTYPE(c_int, c_bool, c_int, c_void_p)


@dataclass
class SimResult:
    ok: bool
    time: np.ndarray
    signals: dict[str, np.ndarray]
    elapsed_ms: float
    rss_before_mb: float
    rss_after_mb: float
    analysis_type: str = "tran"  # tran | ac | dc | op
    x_label: str = "s"
    op_table: list[tuple[str, float]] = field(default_factory=list)
    available_vectors: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    error: str = ""


def _find_ngspice_library() -> Path | str:
    env_override = os.environ.get("NGSPICE_LIB_PATH")
    if env_override and Path(env_override).exists():
        return Path(env_override)

    if sys.platform.startswith("win"):
        candidates = [
            Path(sys.prefix) / "Library" / "bin" / "ngspice.dll",
            Path(sys.prefix) / "ngspice.dll",
        ]
        for cand in candidates:
            if cand.exists():
                return cand
        return "ngspice.dll"

    linux_candidates = [
        "/usr/lib/aarch64-linux-gnu/libngspice.so.0",
        "/usr/lib/x86_64-linux-gnu/libngspice.so.0",
        "/usr/lib/libngspice.so.0",
        "/usr/local/lib/libngspice.so",
    ]
    for cand in linux_candidates:
        if Path(cand).exists():
            return cand
    return "libngspice.so.0"


_DLL_LOCK = threading.RLock()
_SHARED_LIB: ctypes.CDLL | None = None
_SHARED_VERSION: str = "ngspice (shared)"
_ACTIVE_ENGINE: "NgspiceEngine | None" = None


def _dispatch_char(msg: bytes, ident: int, user_data: c_void_p) -> int:
    eng = _ACTIVE_ENGINE
    return eng._on_char(msg, ident, user_data) if eng is not None else 0


def _dispatch_stat(msg: bytes, ident: int, user_data: c_void_p) -> int:
    return 0


def _dispatch_exit(
    status: int, immediate: bool, exit_on_quit: bool, ident: int, user_data: c_void_p
) -> int:
    eng = _ACTIVE_ENGINE
    return eng._on_exit(status, immediate, exit_on_quit, ident, user_data) if eng is not None else 0


def _dispatch_bg(running: bool, ident: int, user_data: c_void_p) -> int:
    return 0


# Keep permanent module-level references so ctypes trampolines are never garbage-collected.
_GLOBAL_CB_CHAR = SEND_CHAR_CB(_dispatch_char)
_GLOBAL_CB_STAT = SEND_STAT_CB(_dispatch_stat)
_GLOBAL_CB_EXIT = CONTROLLED_EXIT_CB(_dispatch_exit)
_GLOBAL_CB_BG = BG_RUNNING_CB(_dispatch_bg)


class NgspiceEngine:
    """In-process libngspice runner with strict plot cleanup for 512MB RAM targets."""

    def __init__(self) -> None:
        global _SHARED_LIB, _SHARED_VERSION, _ACTIVE_ENGINE
        self._logs: list[str] = []
        self._exit_error: str = ""

        with _DLL_LOCK:
            _ACTIVE_ENGINE = self
            if _SHARED_LIB is None:
                self._configure_spice_env()
                lib_path = _find_ngspice_library()
                if sys.platform.startswith("win") and isinstance(lib_path, Path):
                    os.add_dll_directory(str(lib_path.parent))
                lib = ctypes.CDLL(str(lib_path))
                self._bind_functions(lib)

                rc = lib.ngSpice_Init(
                    _GLOBAL_CB_CHAR,
                    _GLOBAL_CB_STAT,
                    _GLOBAL_CB_EXIT,
                    SEND_DATA_CB(0),
                    SEND_INIT_DATA_CB(0),
                    _GLOBAL_CB_BG,
                    None,
                )
                if rc != 0:
                    raise RuntimeError(f"ngSpice_Init failed with code {rc}")

                self._logs.clear()
                lib.ngSpice_Command(b"version -s")
                ver = "ngspice (shared)"
                for line in self._logs:
                    m = re.search(r"ngspice[- ]+\d+[^\s]*", line, re.I)
                    if m:
                        ver = m.group(0)
                        break
                self._logs.clear()
                _SHARED_LIB = lib
                _SHARED_VERSION = ver

        self.lib = _SHARED_LIB
        self._version_cached = _SHARED_VERSION

    @staticmethod
    def _configure_spice_env() -> None:
        if sys.platform.startswith("win"):
            scripts_dir = Path(sys.prefix) / "Library" / "share" / "ngspice" / "scripts"
            if scripts_dir.exists():
                os.environ.setdefault("SPICE_SCRIPTS", str(scripts_dir))

    @staticmethod
    def _bind_functions(lib: ctypes.CDLL) -> None:
        lib.ngSpice_Init.argtypes = [
            SEND_CHAR_CB,
            SEND_STAT_CB,
            CONTROLLED_EXIT_CB,
            SEND_DATA_CB,
            SEND_INIT_DATA_CB,
            BG_RUNNING_CB,
            c_void_p,
        ]
        lib.ngSpice_Init.restype = c_int
        lib.ngSpice_Command.argtypes = [c_char_p]
        lib.ngSpice_Command.restype = c_int
        lib.ngSpice_Circ.argtypes = [POINTER(c_char_p)]
        lib.ngSpice_Circ.restype = c_int
        lib.ngSpice_CurPlot.argtypes = []
        lib.ngSpice_CurPlot.restype = c_char_p
        lib.ngSpice_AllVecs.argtypes = [c_char_p]
        lib.ngSpice_AllVecs.restype = POINTER(c_char_p)
        lib.ngGet_Vec_Info.argtypes = [c_char_p]
        lib.ngGet_Vec_Info.restype = POINTER(VectorInfo)

    def _on_char(self, msg: bytes, ident: int, user_data: c_void_p) -> int:
        if msg:
            txt = msg.decode("utf-8", errors="replace").strip()
            for prefix in ("stdout ", "stderr "):
                if txt.startswith(prefix):
                    txt = txt[len(prefix) :]
                    break
            if txt:
                self._logs.append(txt)
        return 0

    def _on_stat(self, msg: bytes, ident: int, user_data: c_void_p) -> int:
        return 0

    def _on_exit(
        self, status: int, immediate: bool, exit_on_quit: bool, ident: int, user_data: c_void_p
    ) -> int:
        if not exit_on_quit:
            self._exit_error = f"ngspice error exit (status={status})"
        return 0

    def _on_data(self, vecs: c_void_p, count: int, ident: int, user_data: c_void_p) -> int:
        return 0

    def _on_init(self, info: c_void_p, ident: int, user_data: c_void_p) -> int:
        return 0

    def _on_bg(self, running: bool, ident: int, user_data: c_void_p) -> int:
        return 0

    def version_str(self) -> str:
        return self._version_cached

    def _list_plot_vecs(self, plot_name: bytes) -> list[str]:
        ptr = self.lib.ngSpice_AllVecs(plot_name)
        if not ptr:
            return []
        out: list[str] = []
        idx = 0
        while ptr[idx]:
            out.append(ptr[idx].decode("utf-8", errors="replace"))
            idx += 1
        return out

    def _read_vec_array(self, vec_name: str, is_ac: bool = False) -> np.ndarray | None:
        info_ptr = self.lib.ngGet_Vec_Info(vec_name.encode("utf-8"))
        if not info_ptr:
            return None
        info = info_ptr.contents
        n = int(info.v_length)
        if n <= 0:
            return None
        if info.v_realdata:
            arr = np.ctypeslib.as_array(info.v_realdata, shape=(n,))
            return np.array(arr, dtype=np.float64, copy=True)
        if info.v_compdata:
            comp_view = np.ctypeslib.as_array(
                ctypes.cast(info.v_compdata, POINTER(c_double)), shape=(n * 2,)
            )
            re_v = comp_view[0::2]
            im_v = comp_view[1::2]
            mag = np.hypot(re_v, im_v)
            if is_ac and vec_name.lower() != "frequency":
                return 20.0 * np.log10(np.maximum(mag, 1e-12))
            return np.array(re_v if vec_name.lower() == "frequency" else mag, dtype=np.float64, copy=True)
        return None

    @staticmethod
    def _resolve_vector_key(req: str, available: list[str]) -> str | None:
        low_map = {v.lower(): v for v in available}
        r = req.strip().lower()
        if r in low_map:
            return low_map[r]
        m_v = re.match(r"^v\(([^,)]+)\)$", r)
        if m_v:
            node = m_v.group(1).strip()
            for cand in (f"v({node})", node):
                if cand in low_map:
                    return low_map[cand]
        m_i = re.match(r"^i\(([^)]+)\)$", r)
        if m_i:
            src = m_i.group(1).strip()
            for cand in (f"i({src})", f"{src}#branch"):
                if cand in low_map:
                    return low_map[cand]
        return None

    @staticmethod
    def _detect_analysis_from_plot(plot_name: str, avail: list[str]) -> tuple[str, str, str]:
        p = plot_name.lower()
        low_set = {v.lower() for v in avail}
        if p.startswith("ac") or "frequency" in low_set:
            return ("ac", "frequency", "Hz")
        if p.startswith("dc") or "v-sweep" in low_set or "i-sweep" in low_set:
            x_key = "v-sweep" if "v-sweep" in low_set else ("i-sweep" if "i-sweep" in low_set else avail[0])
            return ("dc", x_key, "V" if "v-sweep" in low_set else "A")
        if p.startswith("op"):
            return ("op", "", "")
        return ("tran", "time", "s")

    def run_netlist(
        self, netlist_lines: list[str], requested_signals: list[str] | None = None
    ) -> SimResult:
        global _ACTIVE_ENGINE
        with _DLL_LOCK:
            _ACTIVE_ENGINE = self
            return self._run_netlist_locked(netlist_lines, requested_signals)

    def _run_netlist_locked(
        self, netlist_lines: list[str], requested_signals: list[str] | None = None
    ) -> SimResult:
        rss_before = get_rss_mb()
        self._logs.clear()
        self._exit_error = ""

        self.lib.ngSpice_Command(b"destroy all")
        self.lib.ngSpice_Command(b"remcirc")

        t0 = time.perf_counter()
        encoded = [line.encode("utf-8") for line in netlist_lines]
        arr_type = c_char_p * (len(encoded) + 1)
        c_lines = arr_type(*encoded, None)

        rc_circ = self.lib.ngSpice_Circ(c_lines)
        if rc_circ != 0 or self._exit_error:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            err = self._exit_error or self._extract_error() or f"ngSpice_Circ failed ({rc_circ})"
            return SimResult(
                ok=False,
                time=np.array([], dtype=np.float64),
                signals={},
                elapsed_ms=elapsed_ms,
                rss_before_mb=rss_before,
                rss_after_mb=get_rss_mb(),
                logs=list(self._logs),
                error=err,
            )

        rc_run = self.lib.ngSpice_Command(b"run")
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        cur_plot = self.lib.ngSpice_CurPlot()
        if rc_run != 0 or self._exit_error or not cur_plot:
            err = self._exit_error or self._extract_error() or f"Simulation failed ({rc_run})"
            self.lib.ngSpice_Command(b"destroy all")
            self.lib.ngSpice_Command(b"remcirc")
            return SimResult(
                ok=False,
                time=np.array([], dtype=np.float64),
                signals={},
                elapsed_ms=elapsed_ms,
                rss_before_mb=rss_before,
                rss_after_mb=get_rss_mb(),
                logs=list(self._logs),
                error=err,
            )

        plot_str = cur_plot.decode("utf-8", errors="replace")
        avail = self._list_plot_vecs(cur_plot)
        analysis_type, x_vec_name, x_label = self._detect_analysis_from_plot(plot_str, avail)
        is_ac = analysis_type == "ac"

        if analysis_type == "op":
            op_table: list[tuple[str, float]] = []
            for vname in avail:
                arr = self._read_vec_array(vname, is_ac=False)
                if arr is not None and arr.size > 0:
                    op_table.append((vname, float(arr[0])))
            self.lib.ngSpice_Command(b"destroy all")
            self.lib.ngSpice_Command(b"remcirc")
            return SimResult(
                ok=bool(op_table),
                time=np.array([0.0], dtype=np.float64),
                signals={k: np.array([val], dtype=np.float64) for k, val in op_table},
                elapsed_ms=elapsed_ms,
                rss_before_mb=rss_before,
                rss_after_mb=get_rss_mb(),
                analysis_type="op",
                x_label="",
                op_table=op_table,
                available_vectors=avail,
                logs=list(self._logs),
                error="" if op_table else "No OP vectors returned",
            )

        x_key = self._resolve_vector_key(x_vec_name, avail) or (avail[0] if avail else "")
        x_arr = self._read_vec_array(x_key, is_ac=is_ac) if x_key else None
        if x_arr is None or x_arr.size == 0:
            self.lib.ngSpice_Command(b"destroy all")
            self.lib.ngSpice_Command(b"remcirc")
            return SimResult(
                ok=False,
                time=np.array([], dtype=np.float64),
                signals={},
                elapsed_ms=elapsed_ms,
                rss_before_mb=rss_before,
                rss_after_mb=get_rss_mb(),
                available_vectors=avail,
                logs=list(self._logs),
                error=self._extract_error() or "No sweep/time vector produced",
            )

        signals: dict[str, np.ndarray] = {}
        targets = requested_signals or [v for v in avail if v.lower() != x_key.lower()]
        for req in targets:
            m_diff = re.match(r"^v\(([^,]+),([^)]+)\)$", req.strip(), re.I)
            if m_diff:
                k1 = self._resolve_vector_key(f"v({m_diff.group(1).strip()})", avail)
                k2 = self._resolve_vector_key(f"v({m_diff.group(2).strip()})", avail)
                a1 = self._read_vec_array(k1, is_ac=is_ac) if k1 else None
                a2 = self._read_vec_array(k2, is_ac=is_ac) if k2 else None
                if a1 is not None and a2 is not None and a1.size == a2.size:
                    signals[req] = a1 - a2
                continue
            key = self._resolve_vector_key(req, avail)
            if key:
                arr = self._read_vec_array(key, is_ac=is_ac)
                if arr is not None:
                    label = f"{req}(dB)" if is_ac and not req.endswith("(dB)") else req
                    signals[label] = arr

        # Fallback: if explicit requested_signals missed, capture all non-axis vectors
        if not signals and requested_signals:
            for v in avail:
                if v.lower() == x_key.lower():
                    continue
                arr = self._read_vec_array(v, is_ac=is_ac)
                if arr is not None:
                    label = f"{v}(dB)" if is_ac else v
                    signals[label] = arr

        self.lib.ngSpice_Command(b"destroy all")
        self.lib.ngSpice_Command(b"remcirc")

        rss_after = get_rss_mb()
        if not signals:
            return SimResult(
                ok=False,
                time=x_arr,
                signals={},
                elapsed_ms=elapsed_ms,
                rss_before_mb=rss_before,
                rss_after_mb=rss_after,
                analysis_type=analysis_type,
                x_label=x_label,
                available_vectors=avail,
                logs=list(self._logs),
                error=f"No output vectors found in {avail}",
            )

        return SimResult(
            ok=True,
            time=x_arr,
            signals=signals,
            elapsed_ms=elapsed_ms,
            rss_before_mb=rss_before,
            rss_after_mb=rss_after,
            analysis_type=analysis_type,
            x_label=x_label,
            available_vectors=avail,
            logs=list(self._logs),
        )

    def _extract_error(self) -> str:
        for line in reversed(self._logs):
            low = line.lower()
            if "error" in low or "timestep too small" in low or "abort" in low:
                return line
        return self._logs[-1] if self._logs else ""
