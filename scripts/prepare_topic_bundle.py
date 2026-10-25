#!/usr/bin/env python3
"""Re-audit selected comments and build a Feishu-ready topic bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


OUTLINE_BY_CATEGORY = {
    "恋爱转账与赠与返还边界": "1. 先区分借款、赠与、共同消费与附条件给付；2. 对照转账备注、聊天约定和资金用途；3. 给出起诉或应诉前的证据清单。",
    "过错、欺诈与结婚目的": "1. 区分感情过错、民事返还与刑事诈骗；2. 判断结婚目的或虚假承诺是否有证据；3. 说明可主张的请求与举证风险。",
    "威胁、报警与名誉侵害": "1. 识别催款、报警、上门和公开诋毁的边界；2. 立即固定聊天、通话和发布记录；3. 分情况选择报警、平台投诉或民事维权。",
    "证据、时效与诉讼程序": "1. 明确谁主张、谁举证；2. 梳理转账记录、聊天记录、备注和资金用途；3. 说明时效、律师函、起诉与应诉步骤。",
    "婚外关系与第三人返还": "1. 确认转款人婚姻状态与资金来源；2. 区分个人财产和夫妻共同财产；3. 说明配偶、转款人和收款人的主张路径。",
    "女性出资与性别反向争议": "1. 先说明法律判断不以男女为前提；2. 区分女性出资中的借款、赠与和共同消费；3. 给出相同标准下的证据与维权步骤。",
}

SUFFIX_BY_CATEGORY = {
    "恋爱转账与赠与返还边界": "分手后这笔钱到底要不要还？",
    "过错、欺诈与结婚目的": "这是感情纠纷，还是可能涉及诈骗？",
    "威胁、报警与名誉侵害": "遇到威胁、报警或曝光该怎么留证？",
    "证据、时效与诉讼程序": "走到起诉这一步，哪些证据最关键？",
    "婚外关系与第三人返还": "婚外转账究竟由谁来追回？",
    "女性出资与性别反向争议": "换成女性出钱，返还标准会变吗？",
}

PLATFORM_PREFIX = {
    "douyin": "dy",
    "xiaohongshu": "xhs",
    "bilibili": "bili",
    "youtube": "yt",
    "kuaishou": "ks",
    "generic": "web",
}

PLATFORM_LABEL = {
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "bilibili": "B站",
    "youtube": "YouTube",
    "kuaishou": "快手",
    "generic": "网页",
}


def normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def load_evidence(paths: list[Path]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            item = json.loads(line)
            comment_id = normalize(item.get("comment_id"))
            screenshot = normalize(item.get("screenshot"))
            if not comment_id or not screenshot:
                continue
            image = (path.parent / screenshot).resolve()
            if not image.is_file():
                raise ValueError(f"{path}:{line_number} 的截图不存在：{image}")
            actual_hash = sha256_file(image)
            expected_hash = normalize(item.get("screenshot_sha256"))
            if expected_hash and expected_hash != actual_hash:
                raise ValueError(f"截图哈希不匹配：{image}")
            enriched = dict(item)
            enriched["screenshot_absolute"] = str(image)
            enriched["screenshot_sha256"] = actual_hash
            result[comment_id] = enriched
    return result


def make_title(question: str, category: str) -> str:
    question = normalize(question).rstrip("。；;，, ")
    if len(question) <= 48:
        if question.endswith(("?", "？")):
            return question
        return question + "，法律上怎么判断？"
    prefix = question[:44].rstrip("。；;，, ")
    suffix = SUFFIX_BY_CATEGORY.get(category, "这类纠纷该怎么处理？")
    return f"{prefix}……{suffix}"


def make_hook(question: str, category: str) -> str:
    excerpt = normalize(question)[:42].rstrip("。；;，, ")
    if category == "威胁、报警与名誉侵害":
        return f"“{excerpt}”——先别被吓住，第一步不是争辩，而是固定证据。"
    if category == "过错、欺诈与结婚目的":
        return f"“{excerpt}”——感情里有过错，不等于法律上当然返还或构成诈骗。"
    if category in OUTLINE_BY_CATEGORY:
        return f"“{excerpt}”——先别急着下结论，真正要看的是具体事实、约定和证据。"
    return f"“{excerpt}”——这条评论真正值得讲清的是判断标准和下一步做法。"


def make_outline(category: str) -> str:
    return OUTLINE_BY_CATEGORY.get(category, "1. 还原评论中的具体场景；2. 给出判断标准与常见误区；3. 提供可执行步骤和例外提醒。")


def detect_platform(source: dict) -> tuple[str, str]:
    key = normalize(source.get("platform")).lower()
    url = normalize(source.get("source_url")).lower()
    if not key:
        for candidate, marker in (
            ("douyin", "douyin.com"),
            ("xiaohongshu", "xiaohongshu.com"),
            ("bilibili", "bilibili.com"),
            ("youtube", "youtube.com"),
            ("kuaishou", "kuaishou.com"),
        ):
            if marker in url:
                key = candidate
                break
    key = key or "generic"
    return PLATFORM_PREFIX.get(key, re.sub(r"[^a-z0-9]+", "", key)[:8] or "web"), PLATFORM_LABEL.get(key, key)


def main() -> int:
    parser = argparse.ArgumentParser(description="把重新审核后的评论与原图生成飞书选题写入包。")
    parser.add_argument("--selected", required=True, type=Path)
    parser.add_argument("--comments", required=True, nargs="+", type=Path)
    parser.add_argument("--exclusions", required=True, type=Path)
    parser.add_argument(
        "--title-overrides",
        type=Path,
        help="可选：comment_id 到标题字符串，或 title/hook/outline/viral_reason/evidence_fit 对象的 JSON 映射。",
    )
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--track", required=True)
    parser.add_argument("--video-title", default="")
    args = parser.parse_args()

    selected = load_json(args.selected.resolve())
    exclusions_payload = load_json(args.exclusions.resolve())
    if not isinstance(selected, list):
        raise ValueError("selected 必须是数组。")
    exclusions = exclusions_payload.get("exclusions") if isinstance(exclusions_payload, dict) else None
    if not isinstance(exclusions, list):
        raise ValueError("exclusions 文件必须包含 exclusions 数组。")
    exclusion_map = {
        normalize(item.get("comment_id")): normalize(item.get("reason"))
        for item in exclusions
        if isinstance(item, dict) and item.get("comment_id") and item.get("reason")
    }
    topic_overrides: dict[str, dict] = {}
    if args.title_overrides:
        raw_overrides = load_json(args.title_overrides.resolve())
        if not isinstance(raw_overrides, dict):
            raise ValueError("title-overrides 必须是 JSON 对象。")
        for key, value in raw_overrides.items():
            comment_id = normalize(key)
            if isinstance(value, dict):
                topic_overrides[comment_id] = {normalize(field): normalize(content) for field, content in value.items()}
            else:
                topic_overrides[comment_id] = {"title": normalize(value)}
    evidence = load_evidence([path.resolve() for path in args.comments])
    reviewed: list[dict] = []
    evidence_index: list[dict] = []
    topics: list[dict] = []
    missing: list[str] = []

    for item in selected:
        comment_id = normalize(item.get("comment_id"))
        if not comment_id or comment_id in exclusion_map:
            continue
        source = evidence.get(comment_id)
        if source is None:
            missing.append(comment_id)
            continue
        question = normalize(item.get("question_summary") or source.get("content") or source.get("raw_text"))
        original = normalize(source.get("content") or source.get("raw_text"))
        category = normalize(item.get("proposed_category"))
        override = topic_overrides.get(comment_id, {})
        title = override.get("title") or make_title(question, category)
        platform_prefix, platform_label = detect_platform(source)
        image = source["screenshot_absolute"]
        reviewed.append(item)
        evidence_index.append(
            {
                "comment_id": comment_id,
                "original_comment": original,
                "source_url": normalize(source.get("source_url")),
                "category": category,
                "screenshot_path": image,
                "screenshot_sha256": source["screenshot_sha256"],
            }
        )
        topics.append(
            {
                "topic_id": f"{platform_prefix}-{comment_id}",
                "title": title,
                "track": args.track.strip(),
                "category": category,
                "comment_text": original,
                "evidence_fit": override.get("evidence_fit") or f"原评论截图明确呈现“{question[:70]}”，直接支持该选题的事实场景；超出原文的判断须在内容中条件化表达。",
                "viral_reason": override.get("viral_reason") or "真实评论包含明确问题、痛点、选择冲突或行动意图，具有代入和收藏价值；属于评论样本信号，不承诺流量结果。",
                "hook": override.get("hook") or make_hook(question, category),
                "outline": override.get("outline") or make_outline(category),
                "source_platform": platform_label,
                "source_url": normalize(source.get("source_url")),
                "video_title": args.video_title.strip(),
                "comment_id": comment_id,
                "collected_at": normalize(source.get("collected_at")),
                "images": [image],
                "status": "待创作",
            }
        )

    if missing:
        raise ValueError("这些入选评论没有匹配原图：" + ", ".join(missing))
    unknown_exclusions = sorted(set(exclusion_map) - {normalize(item.get("comment_id")) for item in selected})
    if unknown_exclusions:
        raise ValueError("这些排除项不在原选清单中：" + ", ".join(unknown_exclusions))

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "selected-comments-reviewed.json").write_text(
        json.dumps(reviewed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "selected-evidence.json").write_text(
        json.dumps(evidence_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "topic-bundle.json").write_text(
        json.dumps({"topics": topics}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    review_log = {
        "original_selected": len(selected),
        "excluded": len(exclusion_map),
        "approved": len(topics),
        "exclusions": exclusions,
    }
    (out_dir / "review-log.json").write_text(
        json.dumps(review_log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(review_log | {"evidence_images": len(evidence_index)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
