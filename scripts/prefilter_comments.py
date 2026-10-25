#!/usr/bin/env python3
"""Create a compact, conservative candidate set before model review."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


REACTION_ONLY = re.compile(
    r"^(?:(?:已经)?中招了[，, ]*(?:(?:这个|这种)?(?:怎么办|怎么破))?|哈+|哈哈哈+|呵呵+|笑死|说得对|太真实了|学到了|收藏了|点赞|支持|路过|同问|蹲|我也是|我也一样|一样|怎么办|怎么破|这个怎么办|这种怎么办|然后呢|真的假的|真的吗)[!！。,.，？?~～\s]*$",
    re.IGNORECASE,
)
PROMO = re.compile(r"(?:加微|加v|私信我|主页联系|扫码|vx|v信|微信号|代理|招生|带货)", re.IGNORECASE)
PHONE_OR_URL = re.compile(r"(?:https?://|www\.|(?<!\d)1[3-9]\d{9}(?!\d))", re.IGNORECASE)
MEANINGFUL = re.compile(r"[\w\u3400-\u9fff]", re.UNICODE)


def normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalized_key(text: str) -> str:
    return re.sub(r"[^\w\u3400-\u9fff]+", "", text).lower()


def load_jsonl(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{number}: JSON 无效: {exc}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"{path}:{number}: 每行必须是 JSON 对象")
            rows.append(item)
    return rows


def rejection_reason(text: str) -> str | None:
    compact = normalized_key(text)
    if not compact:
        return "空白或只有符号表情"
    if len(compact) < 3:
        return "信息过少"
    if REACTION_ONLY.fullmatch(text):
        return "纯反应或缺少讨论对象"
    if PROMO.search(text) and PHONE_OR_URL.search(text):
        return "疑似广告引流"
    if not MEANINGFUL.search(text):
        return "没有可审核文本"
    return None


def compact_candidate(item: dict, text: str) -> dict:
    result = {
        "comment_id": normalize(item.get("comment_id")),
        "content": text,
    }
    for source, target in (
        ("parent_text", "parent_text"),
        ("like_count_raw", "likes"),
        ("source_url", "source_url"),
        ("platform", "platform"),
    ):
        value = normalize(item.get(source))
        if value:
            result[target] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="本地去重并生成供模型审核的紧凑候选评论。")
    parser.add_argument("--comments", required=True, nargs="+", type=Path, help="一个或多个 comments.jsonl。")
    parser.add_argument("--out", required=True, type=Path, help="候选评论 JSON。")
    parser.add_argument("--rejected", required=True, type=Path, help="确定淘汰项 JSON。")
    parser.add_argument("--summary", type=Path, help="可选汇总 JSON。")
    args = parser.parse_args()

    rows = load_jsonl([path.resolve() for path in args.comments])
    candidates: list[dict] = []
    rejected: list[dict] = []
    seen_ids: set[str] = set()
    seen_text: set[str] = set()
    reasons: Counter[str] = Counter()

    for item in rows:
        comment_id = normalize(item.get("comment_id"))
        text = normalize(item.get("content") or item.get("raw_text"))
        if not comment_id:
            reason = "缺少 comment_id"
        elif comment_id in seen_ids:
            reason = "重复 comment_id"
        else:
            key = normalized_key(text)
            reason = rejection_reason(text)
            if not reason and key in seen_text:
                reason = "重复评论文本"
        if reason:
            rejected.append({"comment_id": comment_id, "content": text, "reason": reason})
            reasons[reason] += 1
            if comment_id:
                seen_ids.add(comment_id)
            continue
        seen_ids.add(comment_id)
        seen_text.add(normalized_key(text))
        candidates.append(compact_candidate(item, text))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.rejected.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(candidates, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    args.rejected.write_text(json.dumps({"exclusions": rejected}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "input_rows": len(rows),
        "candidate_rows": len(candidates),
        "rejected_rows": len(rejected),
        "rejection_reasons": dict(reasons),
        "hard_limit_applied": False,
    }
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
