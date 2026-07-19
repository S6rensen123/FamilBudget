from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def run_self_update(source_path: str, target_path: str, restart_delay: int = 5) -> bool:
    source = Path(source_path).resolve()
    target = Path(target_path).resolve()

    if not source.exists():
        print("Update source does not exist")
        return False

    if not target.exists():
        print("Target executable does not exist")
        return False

    time.sleep(restart_delay)

    backup_path = target.with_suffix(target.suffix + ".bak")
    if backup_path.exists():
        backup_path.unlink()

    for _ in range(20):
        try:
            shutil.copy2(source, backup_path)
            os.replace(source, target)
            break
        except PermissionError:
            time.sleep(1)
        except FileNotFoundError:
            time.sleep(1)
        except OSError:
            time.sleep(1)
    else:
        return False

    if target.exists():
        if os.name == "nt" and target.suffix.lower() == ".exe":
            subprocess.Popen([str(target)], cwd=str(target.parent))
        else:
            subprocess.Popen([sys.executable, str(target)], cwd=str(target.parent))
        return True

    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-update", action="store_true")
    parser.add_argument("--source", dest="source_path")
    parser.add_argument("--target", dest="target_path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_update and args.source_path and args.target_path:
        run_self_update(args.source_path, args.target_path)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
