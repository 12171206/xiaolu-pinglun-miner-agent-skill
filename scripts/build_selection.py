#!/usr/bin/env python3
"""Build selected-comments.json from reviewed comment IDs grouped by category."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_jsonl(path: Path) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: JSON 无效: {exc}") from exc
        comment_id = str(item.get("comment_id") or "")
        if not comment_id:
            raise ValueError(f"{path}:{line_number}: 缺少 comment_id")
        result[comment_id] = item
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="根据已审核的分类计划生成入选评论清单。")
    parser.add_argument("--comments", required=True, type=Path, help="原始 comments.jsonl。")
    parser.add_argument("--plan", required=True, type=Path, help="含 categories 数组的筛选计划 JSON。")
    parser.add_argument("--out", required=True, type=Path, help="输出 selected-comments.json。")
    args = parser.parse_args()

    comments = load_jsonl(args.comments.resolve())
    plan_path = args.plan.resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise ValueError("筛选计划必须是对象。")
    base_plan_value = plan.get("base_plan")
    if base_plan_value:
        base_plan_path = (plan_path.parent / str(base_plan_value)).resolve()
        base_plan = json.loads(base_plan_path.read_text(encoding="utf-8"))
        if not isinstance(base_plan, dict):
            raise ValueError("base_plan 必须指向 JSON 对象。")
        categories = base_plan.get("categories")
    else:
        categories = plan.get("categories")
    if not isinstance(categories, list):
        raise ValueError("筛选计划必须包含 categories 数组。")

    exclusions = plan.get("exclusions") or []
    if not isinstance(exclusions, list):
        raise ValueError("exclusions 必须是数组。")
    excluded_ids: set[str] = set()
    for item in exclusions:
        if not isinstance(item, dict) or not item.get("comment_id") or not item.get("reason"):
            raise ValueError("每条 exclusion 必须包含 comment_id 和 reason。")
        excluded_ids.add(str(item["comment_id"]))

    selected: list[dict] = []
    used: set[str] = set()
    missing: list[str] = []
    for group in categories:
        if not isinstance(group, dict):
            raise ValueError("categories 中的每项必须是对象。")
        category = str(group.get("name") or "").strip()
        reason = str(group.get("reason") or "").strip()
        ids = group.get("comment_ids")
        if not category or not reason or not isinstance(ids, list):
            raise ValueError("每个分类必须包含 name、reason 和 comment_ids。")
        for value in ids:
            comment_id = str(value)
            if comment_id in excluded_ids:
                continue
            if comment_id in used:
                raise ValueError(f"重复入选 comment_id: {comment_id}")
            used.add(comment_id)
            source = comments.get(comment_id)
            if source is None:
                missing.append(comment_id)
                continue
            selected.append(
                {
                    "comment_id": comment_id,
                    "selection_reason": reason,
                    "proposed_category": category,
                    "question_summary": str(source.get("content") or source.get("raw_text") or "").strip(),
                    "source_url": str(source.get("source_url") or ""),
                }
            )

    if missing:
        raise ValueError("原始评论中找不到这些 comment_id: " + ", ".join(missing))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(selected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    unused_exclusions = sorted(excluded_ids - used - set(comments))
    if unused_exclusions:
        raise ValueError("这些 exclusion 不在原始评论中: " + ", ".join(unused_exclusions))
    print(
        json.dumps(
            {
                "selected_comments": len(selected),
                "excluded_from_base": len(excluded_ids),
                "categories": len(categories),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
