from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "release"
ARTIFACT_DIR = RELEASE_DIR / "artifacts"


def load_version() -> str:
    version_path = ROOT / "version.json"
    if version_path.exists():
        try:
            with version_path.open("r", encoding="utf-8") as handle:
                return json.load(handle).get("version", "1.0.0")
        except (json.JSONDecodeError, OSError):
            pass
    return "1.0.0"


def run_command(command: list[str], cwd: Optional[Path] = None) -> None:
    print("Running:", " ".join(command))
    subprocess.run(command, cwd=str(cwd or ROOT), check=True)


def build_executable() -> Path:
    run_command([sys.executable, "-m", "PyInstaller", "budget.spec"], cwd=ROOT)
    dist_exe = ROOT / "dist" / "budget.exe"
    if not dist_exe.exists():
        raise FileNotFoundError(f"Expected build output at {dist_exe}")
    return dist_exe


def create_stage(version: str) -> Path:
    stage_dir = ARTIFACT_DIR / f"FamilBudget-v{version}"
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)

    exe_src = ROOT / "dist" / "budget.exe"
    if not exe_src.exists():
        raise FileNotFoundError(f"Missing required file: {exe_src}")
    shutil.copy2(exe_src, stage_dir / "budget.exe")

    for name in ["budget.db", "version.json"]:
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, stage_dir / name)
        else:
            raise FileNotFoundError(f"Missing required file: {src}")

    installer_candidates = [
        ROOT / "installer" / "FamilBudgetSetup.exe",
        ROOT / "installer" / "BudgetManagerSetup.exe",
    ]
    installer_src = next((path for path in installer_candidates if path.exists()), None)
    if installer_src is not None:
        shutil.copy2(installer_src, stage_dir / installer_src.name)

    release_notes = RELEASE_DIR / "release-notes-template.md"
    if release_notes.exists():
        content = release_notes.read_text(encoding="utf-8")
        content = content.replace("{{VERSION}}", version)
        content = content.replace("{{DATE}}", datetime.now().strftime("%Y-%m-%d"))
        (stage_dir / "RELEASE_NOTES.md").write_text(content, encoding="utf-8")

    readme = stage_dir / "README.txt"
    readme.write_text(
        "FamilBudget release package\n"
        "==========================\n\n"
        "- budget.exe: portable desktop application\n"
        "- budget.db: local data store\n"
        "- version.json: release metadata\n"
        "- RELEASE_NOTES.md: release notes\n",
        encoding="utf-8",
    )

    return stage_dir


def create_zip(stage_dir: Path, version: str) -> Path:
    archive_path = ARTIFACT_DIR / f"FamilBudget-v{version}.zip"
    if archive_path.exists():
        archive_path.unlink()

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(stage_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(stage_dir))

    return archive_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and package the FamilBudget release")
    parser.add_argument("--version", default=None, help="Override the version from version.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    version = args.version or load_version()

    print(f"Preparing release for FamilBudget v{version}")
    build_executable()
    stage_dir = create_stage(version)
    archive_path = create_zip(stage_dir, version)

    print(f"Built stage: {stage_dir}")
    print(f"Built archive: {archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
