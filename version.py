from __future__ import annotations

import json
import os
from pathlib import Path


def _load_manifest() -> dict:
    manifest_path = Path(__file__).with_name("version.json")
    if manifest_path.exists():
        try:
            with manifest_path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


MANIFEST = _load_manifest()
APP_NAME = MANIFEST.get("app_name", "FamilBudget")
APP_VERSION = MANIFEST.get("version", "1.0.0")
RELEASE_REPO = os.environ.get("FAMILBUDGET_REPO", MANIFEST.get("repository", "your-org/familbudget"))
RELEASE_ASSET_NAME = os.environ.get("FAMILBUDGET_ASSET_NAME", MANIFEST.get("asset_name", "budget.exe"))
RELEASE_API_URL = os.environ.get("FAMILBUDGET_RELEASE_API_URL", MANIFEST.get("release_api_url", f"https://api.github.com/repos/{RELEASE_REPO}/releases/latest"))
