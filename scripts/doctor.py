#!/usr/bin/env python3
"""Report local prerequisites without exposing credentials."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import sys
from pathlib import Path

from runtime_paths import default_config_path, default_credentials_path, state_root


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 Skill、本地依赖和飞书配置状态。")
    parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config_path = default_config_path()
    credentials_path = default_credentials_path()
    config = {}
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config = {}
    env_credentials = bool(os.environ.get("FEISHU_ACCESS_TOKEN") or (os.environ.get("FEISHU_APP_ID") and os.environ.get("FEISHU_APP_SECRET")))
    result = {
        "python": {"version": platform.python_version(), "supported": sys.version_info >= (3, 10)},
        "skill": {"root": str(root), "manifest": (root / "SKILL.md").is_file()},
        "dependencies": {
            "requests": importlib.util.find_spec("requests") is not None,
            "playwright": importlib.util.find_spec("playwright") is not None,
        },
        "state_root": str(state_root()),
        "feishu": {
            "config_path": str(config_path),
            "target_configured": bool(config.get("bitable") or config.get("document")),
            "track_configured": bool(config.get("track")),
            "credentials_configured": env_credentials or credentials_path.is_file(),
            "credentials_source": "environment" if env_credentials else ("local-protected-file" if credentials_path.is_file() else "missing"),
        },
    }
    result["ready_for_collection"] = bool(result["python"]["supported"] and result["skill"]["manifest"] and result["dependencies"]["playwright"])
    result["ready_for_feishu"] = bool(result["ready_for_collection"] and result["dependencies"]["requests"] and result["feishu"]["target_configured"] and result["feishu"]["track_configured"] and result["feishu"]["credentials_configured"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready_for_collection"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
