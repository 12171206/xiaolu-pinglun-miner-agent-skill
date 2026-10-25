#!/usr/bin/env python3
"""Install this Agent Skill into a supported user-level skill directory."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


TARGETS = {
    "codex": Path(".codex/skills"),
    "claude": Path(".claude/skills"),
    "cursor": Path(".cursor/skills"),
    "gemini": Path(".gemini/skills"),
    "copilot": Path(".copilot/skills"),
    "agents": Path(".agents/skills"),
}
SKIP_PARTS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "research", "evidence", "screenshots"}
SKIP_NAMES = {".env", "credentials.json", "config.json"}


def ignored(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in SKIP_PARTS or name in SKIP_NAMES or name.endswith((".pyc", ".pyo"))}


def main() -> int:
    parser = argparse.ArgumentParser(description="把当前 Skill 安装到常见 AI Agent 的用户级技能目录。")
    parser.add_argument("--agent", required=True, choices=sorted(TARGETS))
    parser.add_argument("--target-dir", type=Path, help="测试或自定义安装目录；指定后忽略默认客户端目录。")
    parser.add_argument("--force", action="store_true", help="允许更新已存在的同名 Skill 文件。")
    args = parser.parse_args()

    source = Path(__file__).resolve().parents[1]
    parent = args.target_dir.expanduser().resolve() if args.target_dir else (Path.home() / TARGETS[args.agent]).resolve()
    target = parent / source.name
    if target.exists() and not args.force:
        raise SystemExit(f"目标已存在：{target}\n如需更新，请重新运行并添加 --force。")
    parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=args.force, ignore=ignored)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
