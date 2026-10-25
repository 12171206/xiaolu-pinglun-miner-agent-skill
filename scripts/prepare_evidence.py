#!/usr/bin/env python3
"""Merge comment JSONL files into a deduplicated, analysis-ready evidence set."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


EXPLICIT = re.compile(r"[?？]|为什么|怎么|怎样|如何|哪里|哪个|哪些|多少|多久|能不能|可不可以|是否|有没有|怎么办|该不该")
IMPLICIT = re.compile(r"不会|不懂|不知道|没办法|卡住|卡在|失败|担心|害怕|纠结|太难|求教程|求推荐|求方法|请教")
INTENT = re.compile(r"价格|多少钱|收费|购买|哪里买|推荐|选择|对比|报名|咨询|服务|课程|工具|软件|流程|案例|风险|多久|时间|适合")


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    return re.sub(r"\s+", " ", value).strip()


def resolve_inputs(values: list[Path]) -> list[Path]:
    files: list[Path] = []
    for value in values:
        value = value.resolve()
        if value.is_dir():
            files.extend(sorted(value.rglob("comments.jsonl")))
        elif value.is_file():
            files.append(value)
        else:
            raise FileNotFoundError(value)
    return list(dict.fromkeys(files))


def main() -> int:
    parser = argparse.ArgumentParser(description="合并评论证据并标记问题与行动意图信号。")
    parser.add_argument("inputs", nargs="+", type=Path, help="comments.jsonl 文件或包含它们的目录。")
    parser.add_argument("--out", required=True, type=Path, help="输出 evidence.jsonl。")
    args = parser.parse_args()

    input_files = resolve_inputs(args.inputs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    seen: set[tuple[str, str, str]] = set()
    author_alias: dict[tuple[str, str], str] = {}
    records: list[dict] = []
    counters = Counter()

    for input_file in input_files:
        for line_number, line in enumerate(input_file.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{input_file}:{line_number}: JSON 无效: {exc}") from exc

            content = normalize(str(item.get("content") or item.get("raw_text") or ""))
            source_url = normalize(str(item.get("source_url") or ""))
            author = normalize(str(item.get("author") or ""))
            if not content or not source_url:
                counters["skipped_incomplete"] += 1
                continue
            key = (source_url, author.casefold(), content.casefold())
            if key in seen:
                counters["duplicates"] += 1
                continue
            seen.add(key)

            alias_key = (source_url, author.casefold() or item.get("comment_id", ""))
            if alias_key not in author_alias:
                author_alias[alias_key] = f"评论者-{len(author_alias) + 1:04d}"

            screenshot = str(item.get("screenshot") or "")
            screenshot_abs = ""
            if screenshot:
                screenshot_abs = str((input_file.parent / screenshot).resolve())

            explicit = bool(EXPLICIT.search(content))
            implicit = bool(IMPLICIT.search(content))
            intent = bool(INTENT.search(content))
            enriched = dict(item)
            enriched.update(
                {
                    "content": content,
                    "anonymous_author": author_alias[alias_key],
                    "evidence_source_file": str(input_file),
                    "screenshot_absolute": screenshot_abs,
                    "question_signal": "explicit" if explicit else ("implicit" if implicit else "none"),
                    "intent_signal": intent,
                }
            )
            records.append(enriched)
            counters["explicit_questions" if explicit else "other_comments"] += 1
            if implicit and not explicit:
                counters["implicit_questions"] += 1
            if intent:
                counters["intent_signals"] += 1

    with args.out.open("w", encoding="utf-8", newline="\n") as handle:
        for item in records:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    summary = {
        "input_files": [str(path) for path in input_files],
        "unique_comments": len(records),
        **dict(counters),
    }
    summary_path = args.out.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

