#!/usr/bin/env python3
"""Append a Markdown topic report and evidence images to a fixed Feishu Docx."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests

from feishu_credentials import load_credentials
from runtime_paths import default_config_path


API_BASE = "https://open.feishu.cn/open-apis"
TOKEN_URL = "https://accounts.feishu.cn/oauth/v3/token"
MAX_BLOCKS_PER_CALL = 50
MAX_TEXT_LENGTH = 1800
SESSION = requests.Session()
SESSION.trust_env = False


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def extract_document_id(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    match = re.search(r"/docx/([A-Za-z0-9_-]+)", value)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{8,}", value):
        return value
    if "/wiki/" in value:
        raise ValueError("知识库 wiki 链接不是 document_id；请提供打开文档后的 /docx/ 链接。")
    raise ValueError("无法从 --document 解析飞书 document_id。")


def check_response(response: requests.Response, action: str) -> dict:
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{action}失败：HTTP {response.status_code}，响应不是 JSON。") from exc
    if not response.ok:
        raise RuntimeError(f"{action}失败：HTTP {response.status_code}，{payload}")
    code = payload.get("code")
    if code not in (None, 0):
        raise RuntimeError(f"{action}失败：code={code}，msg={payload.get('msg') or payload.get('error_description')}")
    return payload


def get_access_token() -> str:
    direct = os.environ.get("FEISHU_ACCESS_TOKEN", "").strip()
    if direct:
        return direct
    app_id, app_secret = load_credentials()
    response = SESSION.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": app_id,
            "client_secret": app_secret,
        },
        timeout=30,
    )
    payload = check_response(response, "获取 tenant_access_token")
    token = payload.get("access_token") or payload.get("tenant_access_token")
    if not token:
        raise RuntimeError("飞书令牌响应中没有 access_token。")
    return token


def api_json(method: str, path: str, token: str, action: str, body: dict | None = None) -> dict:
    response = SESSION.request(
        method,
        API_BASE + path,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
        json=body,
        timeout=60,
    )
    return check_response(response, action)


def create_document(token: str, title: str, folder_token: str | None) -> str:
    body = {"title": title}
    if folder_token:
        body["folder_token"] = folder_token
    payload = api_json("POST", "/docx/v1/documents", token, "创建飞书文档", body)
    document = payload.get("data", {}).get("document", {})
    document_id = document.get("document_id")
    if not document_id:
        raise RuntimeError("创建文档成功响应中没有 document_id。")
    return document_id


def get_raw_content(token: str, document_id: str) -> str:
    payload = api_json(
        "GET",
        f"/docx/v1/documents/{quote(document_id)}/raw_content",
        token,
        "读取飞书文档纯文本",
    )
    return str(payload.get("data", {}).get("content") or "")


def split_text(text: str, limit: int = MAX_TEXT_LENGTH) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks = []
    while len(text) > limit:
        cut = max(text.rfind("\n", 0, limit), text.rfind("。", 0, limit), text.rfind(" ", 0, limit))
        if cut < limit // 2:
            cut = limit
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        chunks.append(text)
    return chunks


def rich_block(block_type: int, key: str, content: str) -> dict:
    return {
        "block_type": block_type,
        key: {"elements": [{"text_run": {"content": content}}]},
    }


def markdown_to_blocks(markdown: str, run_key: str, include_header: bool = True) -> list[dict]:
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    blocks: list[dict] = []
    if include_header:
        blocks.extend(
            [
                rich_block(4, "heading2", f"评论区选题研究 · {timestamp}"),
                rich_block(2, "text", f"VTMRUN:{run_key}:START"),
            ]
        )
    paragraph: list[str] = []
    code_lines: list[str] = []
    in_code = False

    def flush_paragraph() -> None:
        if not paragraph:
            return
        joined = "\n".join(paragraph).strip()
        paragraph.clear()
        for chunk in split_text(joined):
            blocks.append(rich_block(2, "text", chunk))

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.startswith("```"):
            if in_code:
                for chunk in split_text("\n".join(code_lines)):
                    blocks.append(rich_block(14, "code", chunk))
                code_lines.clear()
                in_code = False
            else:
                flush_paragraph()
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not line.strip():
            flush_paragraph()
            continue
        if re.fullmatch(r"\s*([-*_])(?:\s*\1){2,}\s*", line):
            flush_paragraph()
            blocks.append({"block_type": 22, "divider": {}})
            continue
        heading = re.match(r"^(#{1,9})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            for chunk in split_text(heading.group(2)):
                blocks.append(rich_block(2 + level, f"heading{level}", chunk))
            continue
        bullet = re.match(r"^\s*[-*+]\s+(.+)$", line)
        if bullet:
            flush_paragraph()
            for chunk in split_text(bullet.group(1)):
                blocks.append(rich_block(12, "bullet", chunk))
            continue
        ordered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if ordered:
            flush_paragraph()
            for chunk in split_text(ordered.group(1)):
                blocks.append(rich_block(13, "ordered", chunk))
            continue
        quote_match = re.match(r"^\s*>\s?(.*)$", line)
        if quote_match:
            flush_paragraph()
            for chunk in split_text(quote_match.group(1)):
                blocks.append(rich_block(15, "quote", chunk))
            continue
        paragraph.append(line)

    flush_paragraph()
    if code_lines:
        for chunk in split_text("\n".join(code_lines)):
            blocks.append(rich_block(14, "code", chunk))
    return blocks


def append_blocks(token: str, document_id: str, blocks: list[dict]) -> list[dict]:
    created: list[dict] = []
    for start in range(0, len(blocks), MAX_BLOCKS_PER_CALL):
        batch = blocks[start : start + MAX_BLOCKS_PER_CALL]
        payload = api_json(
            "POST",
            f"/docx/v1/documents/{quote(document_id)}/blocks/{quote(document_id)}/children?document_revision_id=-1",
            token,
            "追加飞书文档块",
            {"index": -1, "children": batch},
        )
        created.extend(payload.get("data", {}).get("children", []))
        time.sleep(0.4)
    return created


def upload_image(token: str, document_id: str, image_path: Path, caption_text: str | None = None) -> dict:
    caption = rich_block(2, "text", caption_text or f"证据截图：{image_path.name}")
    append_blocks(token, document_id, [caption])
    created = append_blocks(token, document_id, [{"block_type": 27, "image": {}}])
    if not created or not created[0].get("block_id"):
        raise RuntimeError(f"创建图片块失败：{image_path}")
    block_id = created[0]["block_id"]

    mime = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    with image_path.open("rb") as handle:
        response = SESSION.post(
            API_BASE + "/drive/v1/medias/upload_all",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "file_name": image_path.name,
                "parent_type": "docx_image",
                "parent_node": block_id,
                "size": str(image_path.stat().st_size),
            },
            files={"file": (image_path.name, handle, mime)},
            timeout=120,
        )
    upload = check_response(response, f"上传图片 {image_path.name}")
    file_token = upload.get("data", {}).get("file_token")
    if not file_token:
        raise RuntimeError(f"上传图片成功响应中没有 file_token：{image_path}")

    api_json(
        "PATCH",
        f"/docx/v1/documents/{quote(document_id)}/blocks/{quote(block_id)}?document_revision_id=-1",
        token,
        f"绑定图片块 {image_path.name}",
        {"replace_image": {"token": file_token}},
    )
    time.sleep(0.4)
    return {"path": str(image_path), "block_id": block_id, "file_token": file_token}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="把选题 Markdown 与证据截图追加到固定飞书文档。")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--markdown", type=Path)
    source.add_argument("--topic-bundle", type=Path, help="按选题卡交错写入原评论截图和选题正文。")
    parser.add_argument("--config", type=Path, default=default_config_path())
    parser.add_argument("--document", help="临时覆盖固定文档 URL 或 document_id。")
    parser.add_argument("--create-title", help="经用户授权后创建一个新固定文档。")
    parser.add_argument("--folder-token")
    parser.add_argument("--image", action="append", type=Path, default=[])
    parser.add_argument("--run-key", help="由规范化视频链接生成的稳定批次键。")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--result-json", type=Path)
    return parser.parse_args()


def load_topic_bundle(path: Path) -> tuple[str, list[dict], list[Path]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("topics"), list):
        raise ValueError("topic bundle 必须是含 topics 数组的 JSON 对象。")
    intro = str(payload.get("intro_markdown") or "")
    cards: list[dict] = []
    all_images: list[Path] = []
    for index, item in enumerate(payload["topics"], 1):
        if not isinstance(item, dict):
            raise ValueError(f"topics[{index}] 必须是对象。")
        topic_id = str(item.get("topic_id") or "").strip()
        markdown = str(item.get("markdown") or "").strip()
        image_values = item.get("images")
        if not topic_id or not markdown or not isinstance(image_values, list) or not image_values:
            raise ValueError(f"topics[{index}] 必须包含 topic_id、markdown 和非空 images。")
        images = [(path.parent / str(value)).resolve() for value in image_values]
        cards.append({"topic_id": topic_id, "markdown": markdown, "images": images})
        all_images.extend(images)
    return intro, cards, all_images


def emit_result(result: dict, path: Path | None) -> None:
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    print(rendered, end="")
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")


def main() -> int:
    args = parse_args()
    topic_cards: list[dict] = []
    if args.markdown:
        markdown_path = args.markdown.resolve()
        if not markdown_path.is_file():
            raise SystemExit(f"Markdown 文件不存在：{markdown_path}")
        markdown = markdown_path.read_text(encoding="utf-8")
        images = [path.resolve() for path in args.image]
        blocks = markdown_to_blocks(markdown, "PENDING")
    else:
        if args.image:
            raise SystemExit("--topic-bundle 已声明每个选题的原图，不能再传 --image。")
        bundle_path = args.topic_bundle.resolve()
        if not bundle_path.is_file():
            raise SystemExit(f"Topic bundle 不存在：{bundle_path}")
        intro_markdown, topic_cards, images = load_topic_bundle(bundle_path)
        markdown = bundle_path.read_text(encoding="utf-8")
        blocks = markdown_to_blocks(intro_markdown, "PENDING")
        for card in topic_cards:
            card["blocks"] = markdown_to_blocks(card["markdown"], "PENDING", include_header=False)
    for path in images:
        if not path.is_file():
            raise SystemExit(f"图片不存在：{path}")
        if path.stat().st_size > 20 * 1024 * 1024:
            raise SystemExit(f"图片超过 20 MB：{path}")

    config = load_config(args.config.resolve())
    configured_document = str(config.get("document") or "")
    document_value = args.document or configured_document
    if args.create_title and document_value:
        raise SystemExit("--create-title 与固定/显式 --document 不能同时使用。")
    if not args.create_title and not document_value:
        raise SystemExit("尚未配置固定飞书文档。先运行 configure.py，或传入 --document。")

    run_key = args.run_key or hashlib.sha256(markdown.encode("utf-8")).hexdigest()[:20]
    if not re.fullmatch(r"[A-Za-z0-9._-]{6,80}", run_key):
        raise SystemExit("--run-key 仅允许 6–80 位字母、数字、点、下划线或连字符。")
    if topic_cards:
        blocks = markdown_to_blocks(intro_markdown, run_key)
        for card in topic_cards:
            card["blocks"] = markdown_to_blocks(card["markdown"], run_key, include_header=False)
    else:
        blocks = markdown_to_blocks(markdown, run_key)
    document_id = extract_document_id(document_value) if document_value else ""

    result = {
        "status": "dry_run" if args.dry_run else "pending",
        "document_id": document_id,
        "configured_document": configured_document,
        "track": config.get("track", ""),
        "categories": config.get("categories", []),
        "run_key": run_key,
        "text_blocks": len(blocks) + sum(len(card.get("blocks", [])) for card in topic_cards),
        "topic_cards": len(topic_cards),
        "images": [str(path) for path in images],
    }
    if args.dry_run:
        emit_result(result, args.result_json)
        return 0

    token = get_access_token()
    created_new = False
    if args.create_title:
        document_id = create_document(token, args.create_title, args.folder_token)
        created_new = True
        result["document_id"] = document_id

    start_marker = f"VTMRUN:{run_key}:START"
    done_marker = f"VTMRUN:{run_key}:DONE"
    existing = get_raw_content(token, document_id)
    if done_marker in existing:
        result.update({"status": "skipped_duplicate", "document_url": f"https://feishu.cn/docx/{document_id}"})
        emit_result(result, args.result_json)
        return 0
    if start_marker in existing:
        result.update(
            {
                "status": "blocked_partial_run",
                "document_url": f"https://feishu.cn/docx/{document_id}",
                "message": "检测到同批次 START 但没有 DONE。请先检查文档中的部分写入，避免重复追加。",
            }
        )
        emit_result(result, args.result_json)
        return 4

    uploaded: list[dict] = []
    try:
        append_blocks(token, document_id, blocks)
        if topic_cards:
            for card in topic_cards:
                for image_path in card["images"]:
                    uploaded_image = upload_image(
                        token,
                        document_id,
                        image_path,
                        f"{card['topic_id']} 原评论截图：{image_path.name}",
                    )
                    uploaded_image["topic_id"] = card["topic_id"]
                    uploaded.append(uploaded_image)
                append_blocks(token, document_id, card["blocks"])
        else:
            for image_path in images:
                uploaded.append(upload_image(token, document_id, image_path))
        append_blocks(token, document_id, [rich_block(2, "text", done_marker)])
    except Exception as exc:
        result.update(
            {
                "status": "partial_failure",
                "created_new_document": created_new,
                "uploaded_images": uploaded,
                "error": str(exc),
                "document_url": f"https://feishu.cn/docx/{document_id}",
            }
        )
        emit_result(result, args.result_json)
        return 1

    result.update(
        {
            "status": "success",
            "created_new_document": created_new,
            "uploaded_images": uploaded,
            "document_url": f"https://feishu.cn/docx/{document_id}",
        }
    )
    emit_result(result, args.result_json)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("操作已取消。", file=sys.stderr)
        raise SystemExit(130)

