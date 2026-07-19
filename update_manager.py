from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from version import APP_NAME, APP_VERSION, RELEASE_API_URL, RELEASE_ASSET_NAME


class UpdateInfo:
    def __init__(self, version: str, url: str, asset_name: str):
        self.version = version
        self.url = url
        self.asset_name = asset_name


class UpdateManager:
    def __init__(self, current_version: str = APP_VERSION):
        self.current_version = current_version
        self.latest_info: Optional[UpdateInfo] = None

    def check_for_update(self) -> Optional[UpdateInfo]:
        try:
            request = urllib.request.Request(
                RELEASE_API_URL,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": f"{APP_NAME}/updater",
                },
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            return None

        tag_name = payload.get("tag_name", "")
        version = tag_name.lstrip("v") if tag_name else ""
        if not version:
            return None

        if self._compare_versions(version, self.current_version) <= 0:
            return None

        assets = payload.get("assets", [])
        asset = None
        for item in assets:
            name = (item.get("name") or "").lower()
            desired = RELEASE_ASSET_NAME.lower()
            if name == desired or desired in name:
                asset = item
                break

        if asset is None and assets:
            asset = assets[0]

        if not asset:
            return None

        return UpdateInfo(version=version, url=asset.get("browser_download_url", ""), asset_name=asset.get("name", ""))

    def check_for_update_async(self, callback: Callable[[Optional[UpdateInfo]], None]) -> None:
        thread = threading.Thread(target=self._check_for_update_thread, args=(callback,), daemon=True)
        thread.start()

    def _check_for_update_thread(self, callback: Callable[[Optional[UpdateInfo]], None]) -> None:
        self.latest_info = self.check_for_update()
        callback(self.latest_info)

    def download_update(self, info: UpdateInfo) -> Optional[Path]:
        if not info.url:
            return None

        temp_dir = Path(tempfile.gettempdir()) / APP_NAME.lower()
        temp_dir.mkdir(parents=True, exist_ok=True)
        destination = temp_dir / (info.asset_name or f"{APP_NAME}.exe")

        try:
            request = urllib.request.Request(
                info.url,
                headers={
                    "Accept": "application/octet-stream",
                    "User-Agent": f"{APP_NAME}/updater",
                },
            )
            with urllib.request.urlopen(request, timeout=60) as response, open(destination, "wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
        except (urllib.error.URLError, TimeoutError, OSError):
            if destination.exists():
                destination.unlink()
            return None

        return destination

    def install_update(self, downloaded_path: Path) -> bool:
        current_exe = self._resolve_current_executable()
        if not current_exe:
            return False

        if not downloaded_path.exists():
            return False

        if os.name == "nt":
            if sys.frozen:
                command = [str(current_exe), "--self-update", "--source", str(downloaded_path), "--target", str(current_exe)]
            else:
                budget_script = Path(__file__).resolve().with_name("budget.py")
                command = [sys.executable, str(budget_script), "--self-update", "--source", str(downloaded_path), "--target", str(current_exe)]
        else:
            command = [sys.executable, str(Path(__file__).resolve().with_name("budget.py")), "--self-update", "--source", str(downloaded_path), "--target", str(current_exe)]

        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    def _resolve_current_executable(self) -> Optional[Path]:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve()

        script_path = Path(__file__).resolve().with_name("budget.py")
        if script_path.exists():
            return script_path.resolve()
        return None

    def _compare_versions(self, left: str, right: str) -> int:
        left_parts = [int(part) for part in re.findall(r"\d+", left)]
        right_parts = [int(part) for part in re.findall(r"\d+", right)]

        max_len = max(len(left_parts), len(right_parts))
        left_parts.extend([0] * (max_len - len(left_parts)))
        right_parts.extend([0] * (max_len - len(right_parts)))

        if left_parts < right_parts:
            return -1
        if left_parts > right_parts:
            return 1
        return 0
