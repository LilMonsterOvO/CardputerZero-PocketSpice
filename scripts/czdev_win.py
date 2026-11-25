"""Windows launcher for czdev (CardputerZero AppBuilder) using bsdtar (tar.exe) for .deb inspection."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def _resolve_appbuilder_scripts() -> Path:
    env_dir = os.environ.get("CP0_APPBUILDER_DIR", "").strip()
    candidates = [
        Path(env_dir) / "scripts" if env_dir else None,
        Path(__file__).resolve().parents[2] / "AppBuilder" / "scripts",
    ]
    for cand in candidates:
        if cand is not None and cand.is_dir():
            return cand
    raise FileNotFoundError(
        "CardputerZero/AppBuilder not found. Clone it next to this repo or set CP0_APPBUILDER_DIR."
    )


APPBUILDER_SCRIPTS = _resolve_appbuilder_scripts()
if str(APPBUILDER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(APPBUILDER_SCRIPTS))

from czdev import __main__ as czdev_main
from czdev import auth, publish


def _extract_deb_member_tar_bytes(deb_path: str, prefix: str) -> bytes:
    names = subprocess.run(
        ["tar.exe", "-tf", deb_path], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    member = next((n.strip() for n in names if n.strip().startswith(prefix)), None)
    if not member:
        raise FileNotFoundError(f"{prefix}* not found in {deb_path}")
    return subprocess.run(
        ["tar.exe", "-xOf", deb_path, member], capture_output=True, check=True
    ).stdout


def _win_check_desktop(deb_path: str) -> bool:
    comp = _extract_deb_member_tar_bytes(deb_path, "data.tar")
    proc = subprocess.run(["tar.exe", "-tf", "-"], input=comp, capture_output=True, check=True)
    lines = proc.stdout.decode("utf-8", errors="replace").splitlines()
    return any(line.strip().endswith(".desktop") for line in lines)


def _win_find_root_services(deb_path: str) -> list:
    comp = _extract_deb_member_tar_bytes(deb_path, "data.tar")
    proc = subprocess.run(["tar.exe", "-tf", "-"], input=comp, capture_output=True, check=True)
    lines = [ln.strip().lstrip("./") for ln in proc.stdout.decode("utf-8", errors="replace").splitlines()]
    offenders = []
    for name in lines:
        if name.endswith(".service") and name.startswith(publish._SYSTEMD_SYSTEM_DIRS):
            svc = subprocess.run(
                ["tar.exe", "-xOf", "-", f"./{name}"], input=comp, capture_output=True
            ).stdout.decode("utf-8", errors="replace")
            if publish.service_runs_as_root(svc):
                offenders.append(name)
    return offenders


def _win_extract_metadata(deb_path: str) -> dict:
    comp = _extract_deb_member_tar_bytes(deb_path, "control.tar")
    ctrl_bytes = subprocess.run(
        ["tar.exe", "-xOf", "-", "./control"], input=comp, capture_output=True, check=True
    ).stdout
    text = ctrl_bytes.decode("utf-8", errors="replace")
    values: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            values[k.strip()] = v.strip()
    maintainer = values.get("Maintainer", "")
    return {
        "package": values.get("Package", ""),
        "version": values.get("Version", ""),
        "architecture": values.get("Architecture", ""),
        "maintainer": maintainer,
        "maintainer_email": publish.extract_email(maintainer),
    }


def _win_git_run_cmd_in(cwd: Path, cmd: list):
    """Run git using user's czdev OAuth token over HTTPS instead of requiring GitHub SSH keys."""
    env = dict(os.environ)
    cred_path = auth.credentials_path()
    token = ""
    if cred_path.exists():
        import json
        token = json.loads(cred_path.read_text(encoding="utf-8")).get("github_token", "")

    entries = [
        ("http.proxy", ""),
        ("https.proxy", ""),
    ]
    if token:
        entries.append((f"url.https://x-access-token:{token}@github.com/.insteadOf", "git@github.com:"))

    env["GIT_CONFIG_COUNT"] = str(len(entries))
    for i, (k, v) in enumerate(entries):
        env[f"GIT_CONFIG_KEY_{i}"] = k
        env[f"GIT_CONFIG_VALUE_{i}"] = v

    result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, env=env)
    if result.returncode != 0:
        safe_cmd = " ".join(cmd)
        err = result.stderr.replace(token, "***") if token else result.stderr
        print(f"ERROR: {safe_cmd} failed:\n{err}", file=sys.stderr)
        sys.exit(1)


publish.check_desktop = _win_check_desktop
publish.find_root_services = _win_find_root_services
publish.extract_metadata = _win_extract_metadata
publish.run_cmd_in = _win_git_run_cmd_in


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--preflight":
        deb = sys.argv[2]
        assert publish.check_desktop(deb), "Missing .desktop"
        assert not publish.find_root_services(deb), "Root systemd service found"
        meta = publish.extract_metadata(deb)
        assert publish.is_valid_package_name(meta["package"]), "Invalid package name"
        publish.check_version_newer(meta)
        raw, app_dir = publish.load_app_builder(Path.cwd())
        sm = publish.store_meta_from(raw)
        User = type("U", (), {"login": "lilmonster", "email": ""})
        meta_out = publish.build_merged_meta(sm, meta, User())
        publish.precheck_store_meta(meta_out, app_dir, sm, meta["package"], deb_maintainer=meta["maintainer"])
        print("ALL PREFLIGHT CHECKS PASSED:", meta)
        raise SystemExit(0)
    czdev_main.main()
