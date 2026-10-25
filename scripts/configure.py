#!/usr/bin/env python3
"""Store the fixed Feishu target and niche taxonomy in local Agent Skill state."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from runtime_paths import default_config_path

def read_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="配置固定飞书文档/多维表格和赛道分类。")
    parser.add_argument("--config", type=Path, default=default_config_path())
    parser.add_argument("--show", action="store_true", help="显示当前配置。")
    parser.add_argument("--document", help="固定飞书 docx URL 或 document_id。")
    parser.add_argument("--bitable", help="固定飞书多维表格 /wiki/ 或 /base/ URL。")
    parser.add_argument("--table-id", help="兼容选项：直接指定数据表；按赛道分表时通常不需要。")
    parser.add_argument("--table-name", help="兼容选项：直接指定数据表名称；按赛道分表时通常不需要。")
    parser.add_argument("--track", help="主赛道或账号定位。")
    parser.add_argument("--audience", help="目标受众。")
    parser.add_argument("--category", action="append", help="固定内容栏目；可重复传入。")
    parser.add_argument("--comments-per-video", type=int)
    parser.add_argument("--topic-count", type=int)
    parser.add_argument("--upload-screenshots", choices=("cited", "all", "none"))
    args = parser.parse_args()

    path = args.config.resolve()
    config = read_config(path)
    has_updates = any(
        value is not None
        for value in (
            args.document,
            args.bitable,
            args.table_id,
            args.table_name,
            args.track,
            args.audience,
            args.category,
            args.comments_per_video,
            args.topic_count,
            args.upload_screenshots,
        )
    )

    if args.show and not has_updates:
        if not config:
            print(json.dumps({"configured": False, "config_path": str(path)}, ensure_ascii=False, indent=2))
            return 2
        missing = []
        if not (config.get("bitable") or config.get("document")):
            missing.append("固定飞书目标")
        if not config.get("track"):
            missing.append("主赛道")
        print(
            json.dumps(
                {"configured": not missing, "missing": missing, "config_path": str(path), **config},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.document is not None:
        config["document"] = args.document.strip()
    if args.bitable is not None:
        config["bitable"] = args.bitable.strip()
    if args.table_id is not None:
        config["table_id"] = args.table_id.strip()
    if args.table_name is not None:
        config["table_name"] = args.table_name.strip()
    if args.track is not None:
        config["track"] = args.track.strip()
    if args.audience is not None:
        config["audience"] = args.audience.strip()
    if args.category is not None:
        config["categories"] = [item.strip() for item in args.category if item.strip()]
    if args.comments_per_video is not None:
        if args.comments_per_video < 0:
            raise SystemExit("--comments-per-video 不能小于 0；0 表示不设上限。")
        config["comments_per_video"] = None if args.comments_per_video == 0 else args.comments_per_video
    if args.topic_count is not None:
        if args.topic_count < 1:
            raise SystemExit("--topic-count 必须大于 0。")
        config["topic_count"] = args.topic_count
    if args.upload_screenshots is not None:
        config["upload_screenshots"] = args.upload_screenshots

    config.setdefault("categories", [])
    config.setdefault("comments_per_video", None)
    config.setdefault("topic_count", 20)
    config.setdefault("upload_screenshots", "cited")
    config["updated_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    missing = []
    if not (config.get("bitable") or config.get("document")):
        missing.append("固定飞书目标")
    if not config.get("track"):
        missing.append("主赛道")
    print(
        json.dumps(
            {"configured": not missing, "missing": missing, "config_path": str(path), **config},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

