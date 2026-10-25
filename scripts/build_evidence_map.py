#!/usr/bin/env python3
"""Link every selected comment to its exact original screenshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_jsonl(paths: list[Path]) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for path in paths:
        path = path.resolve()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: JSON 无效: {exc}") from exc
            comment_id = str(item.get("comment_id") or "")
            screenshot = str(item.get("screenshot") or "")
            if not comment_id or not screenshot:
                continue
            screenshot_path = (path.parent / screenshot).resolve()
            if not screenshot_path.is_file():
                continue
            enriched = dict(item)
            enriched["screenshot_absolute"] = str(screenshot_path)
            records[comment_id] = enriched
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="把入选评论与对应原评论截图建立一一映射。")
    parser.add_argument("--selected", required=True, type=Path)
    parser.add_argument("--comments", required=True, nargs="+", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    selected = json.loads(args.selected.read_text(encoding="utf-8"))
    if not isinstance(selected, list):
        raise ValueError("selected 必须是数组。")
    evidence_by_id = read_jsonl(args.comments)
    output: list[dict] = []
    missing: list[str] = []
    for item in selected:
        if not isinstance(item, dict) or not item.get("comment_id"):
            raise ValueError("selected 中每项必须包含 comment_id。")
        comment_id = str(item["comment_id"])
        evidence = evidence_by_id.get(comment_id)
        if evidence is None:
            missing.append(comment_id)
            continue
        output.append(
            {
                "comment_id": comment_id,
                "original_comment": str(evidence.get("content") or evidence.get("raw_text") or ""),
                "source_url": str(evidence.get("source_url") or ""),
                "proposed_category": str(item.get("proposed_category") or ""),
                "question_summary": str(item.get("question_summary") or ""),
                "screenshot_path": evidence["screenshot_absolute"],
                "screenshot_sha256": str(evidence.get("screenshot_sha256") or ""),
            }
        )

    if missing:
        raise ValueError("这些入选评论没有原图: " + ", ".join(missing))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"selected": len(selected), "evidence_images": len(output), "missing": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
