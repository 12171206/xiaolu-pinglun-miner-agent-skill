#!/usr/bin/env python3
"""Create the topic schema and append evidence-backed topics to a Feishu Base."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import requests

from feishu_credentials import load_credentials
from runtime_paths import default_config_path


API_BASE = "https://open.feishu.cn/open-apis"
TOKEN_URL = "https://accounts.feishu.cn/oauth/v3/token"
MAX_IMAGE_BYTES = 20 * 1024 * 1024
SESSION = requests.Session()
SESSION.trust_env = False

FIELD_SPECS = [
    ("赛道", 1),
    ("内容分类", 1),
    ("评论截图", 17),
    ("评论原文", 1),
    ("选题依据", 1),
    ("爆款理由", 1),
    ("三秒钩子", 1),
    ("内容结构", 1),
    ("来源平台", 1),
    ("视频标题", 1),
    ("视频链接", 1),
    ("评论ID", 1),
    ("选题ID", 1),
    ("批次ID", 1),
    ("采集时间", 1),
    ("证据哈希", 1),
    ("状态", 1),
]


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_config(path: Path, config: dict) -> None:
    config["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    response: requests.Response | None = None
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = SESSION.post(
                TOKEN_URL,
                data={"grant_type": "client_credentials", "client_id": app_id, "client_secret": app_secret},
                timeout=30,
            )
            break
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 2:
                raise RuntimeError(f"连接飞书令牌服务失败：{exc}") from exc
            time.sleep(1.5 * (attempt + 1))
    if response is None:
        raise RuntimeError(f"连接飞书令牌服务失败：{last_error}")
    payload = check_response(response, "获取 tenant_access_token")
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("飞书令牌响应中没有 access_token。")
    return token


def api_json(
    method: str,
    path: str,
    token: str,
    action: str,
    *,
    body: dict | None = None,
    params: dict | None = None,
) -> dict:
    last_error: Exception | None = None
    for attempt in range(3):
        response = SESSION.request(
            method,
            API_BASE + path,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
            json=body,
            params=params,
            timeout=60,
        )
        try:
            return check_response(response, action)
        except RuntimeError as exc:
            last_error = exc
            retryable = any(marker in str(exc) for marker in ("1254290", "1254291", "1254607", "1255040"))
            if not retryable or attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(str(last_error) if last_error else f"{action}失败。")


def parse_target(value: str) -> dict:
    value = (value or "").strip()
    if not value:
        raise ValueError("缺少飞书多维表格链接。")
    table_id = ""
    if "://" in value:
        parsed = urlparse(value)
        query = parse_qs(parsed.query)
        table_id = str((query.get("table") or query.get("table_id") or [""])[0])
        wiki = re.search(r"/wiki/([A-Za-z0-9_-]+)", parsed.path)
        if wiki:
            return {"kind": "wiki", "token": wiki.group(1), "table_id": table_id, "url": value}
        base = re.search(r"/(?:base|bitable)/([A-Za-z0-9_-]+)", parsed.path)
        if base:
            return {"kind": "base", "token": base.group(1), "table_id": table_id, "url": value}
    if re.fullmatch(r"[A-Za-z0-9_-]{8,}", value):
        return {"kind": "base", "token": value, "table_id": table_id, "url": value}
    raise ValueError("无法识别飞书多维表格链接；支持 /wiki/、/base/ 链接或 app_token。")


def resolve_app_token(token: str, target: dict) -> str:
    if target["kind"] == "base":
        return target["token"]
    payload = api_json(
        "GET",
        "/wiki/v2/spaces/get_node",
        token,
        "解析知识库中的多维表格",
        params={"token": target["token"]},
    )
    node = payload.get("data", {}).get("node", {})
    obj_token = str(node.get("obj_token") or "").strip()
    obj_type = str(node.get("obj_type") or "").lower()
    if not obj_token:
        raise RuntimeError("知识库节点响应中没有 obj_token。")
    if obj_type and obj_type not in {"bitable", "base"}:
        raise RuntimeError(f"该知识库节点不是多维表格，类型为 {obj_type}。")
    return obj_token


def list_all(token: str, path: str, action: str, page_size: int = 100) -> list[dict]:
    items: list[dict] = []
    page_token = ""
    while True:
        params = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token
        payload = api_json("GET", path, token, action, params=params)
        data = payload.get("data", {})
        items.extend(data.get("items") or [])
        if not data.get("has_more"):
            break
        page_token = str(data.get("page_token") or "")
        if not page_token:
            raise RuntimeError(f"{action}返回 has_more=true 但没有 page_token。")
    return items


def list_tables(token: str, app_token: str) -> list[dict]:
    return list_all(token, f"/bitable/v1/apps/{quote(app_token)}/tables", "读取多维表格中的数据表")


def resolve_table(token: str, app_token: str, requested_id: str, requested_name: str) -> dict:
    tables = list_tables(token, app_token)
    if not tables:
        raise RuntimeError("该多维表格中没有数据表。")
    if requested_id:
        for item in tables:
            if item.get("table_id") == requested_id:
                return item
        raise RuntimeError(f"没有找到 table_id={requested_id}。")
    if requested_name:
        for item in tables:
            if item.get("name") == requested_name:
                return item
        raise RuntimeError(f"没有找到名为“{requested_name}”的数据表。")
    if len(tables) == 1:
        return tables[0]
    names = "、".join(str(item.get("name") or item.get("table_id")) for item in tables)
    raise RuntimeError(f"多维表格包含多个数据表，请配置 --table-id 或 --table-name。可选：{names}")


def table_name_for_track(track: str) -> str:
    name = re.sub(r"\s+", " ", track.strip())
    name = re.sub(r"[/\\?*:\[\]]", "-", name)
    name = re.sub(r"-{2,}", "-", name).strip("- ")
    if not name:
        raise ValueError("赛道名称不能只包含空格或数据表禁用字符。")
    return name[:100]


def create_table(token: str, app_token: str, name: str) -> dict:
    payload = api_json(
        "POST",
        f"/bitable/v1/apps/{quote(app_token)}/tables",
        token,
        f"创建赛道数据表 {name}",
        body={"table": {"name": name}},
    )
    data = payload.get("data", {})
    table_id = str(data.get("table_id") or "").strip()
    if not table_id:
        raise RuntimeError(f"创建数据表“{name}”成功响应中没有 table_id。")
    return {"table_id": table_id, "name": name}


def rename_table(token: str, app_token: str, table_id: str, name: str) -> dict:
    api_json(
        "PATCH",
        f"/bitable/v1/apps/{quote(app_token)}/tables/{quote(table_id)}",
        token,
        f"将数据表重命名为 {name}",
        body={"name": name},
    )
    return {"table_id": table_id, "name": name}


def value_has_content(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(value_has_content(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(value_has_content(item) for item in value)
    return True


def table_is_effectively_empty(records: list[dict]) -> bool:
    return not any(value_has_content(record.get("fields") or {}) for record in records)


def resolve_track_table(
    token: str,
    app_token: str,
    track: str,
    config: dict,
    *,
    apply: bool,
) -> tuple[dict | None, str]:
    track = track.strip()
    if not track:
        raise ValueError("缺少赛道名称，无法按赛道分表。")
    target_name = table_name_for_track(track)
    tables = list_tables(token, app_token)
    by_id = {str(item.get("table_id") or ""): item for item in tables}
    mapped_id = str((config.get("track_tables") or {}).get(track) or "")
    if mapped_id and mapped_id in by_id:
        return by_id[mapped_id], "mapped"
    for table in tables:
        if str(table.get("name") or "") == target_name:
            return table, "existing"

    default_names = {"数据表", "Table", "table", "Sheet1"}
    if len(tables) == 1 and str(tables[0].get("name") or "") in default_names:
        default_table = tables[0]
        table_id = str(default_table.get("table_id") or "")
        if table_is_effectively_empty(list_records(token, app_token, table_id)):
            if not apply:
                return None, "would_rename_default"
            return rename_table(token, app_token, table_id, target_name), "renamed_default"

    if not apply:
        return None, "would_create"
    return create_table(token, app_token, target_name), "created"


def remember_track_table(config_path: Path, config: dict, track: str, table: dict) -> None:
    mapping = dict(config.get("track_tables") or {})
    mapping[track] = str(table.get("table_id") or "")
    config["track_tables"] = mapping
    if not str(config.get("track") or "").strip():
        config["track"] = track
    if config.get("track") == track:
        config["table_id"] = mapping[track]
        config["table_name"] = str(table.get("name") or table_name_for_track(track))
    save_config(config_path, config)


def list_fields(token: str, app_token: str, table_id: str) -> list[dict]:
    return list_all(
        token,
        f"/bitable/v1/apps/{quote(app_token)}/tables/{quote(table_id)}/fields",
        "读取数据表字段",
    )


def ensure_schema(token: str, app_token: str, table_id: str, *, apply: bool) -> dict:
    fields = list_fields(token, app_token, table_id)
    by_name = {str(item.get("field_name") or ""): item for item in fields}
    primary = next((item for item in fields if item.get("is_primary")), fields[0] if fields else None)
    if not primary:
        raise RuntimeError("数据表没有主字段。")
    actions: list[dict] = []
    primary_name = str(primary.get("field_name") or "")
    if primary_name != "选题标题" and int(primary.get("type") or 0) == 1:
        actions.append({"action": "rename_primary", "from": primary_name, "to": "选题标题"})
        if apply:
            api_json(
                "PUT",
                f"/bitable/v1/apps/{quote(app_token)}/tables/{quote(table_id)}/fields/{quote(str(primary['field_id']))}",
                token,
                "重命名主字段",
                body={"field_name": "选题标题", "type": 1},
            )
            primary_name = "选题标题"
            time.sleep(0.3)
    for field_name, field_type in FIELD_SPECS:
        if field_name in by_name:
            actual = int(by_name[field_name].get("type") or 0)
            if actual != field_type:
                raise RuntimeError(f"字段“{field_name}”类型不匹配：当前 {actual}，期望 {field_type}。")
            continue
        actions.append({"action": "create_field", "field_name": field_name, "type": field_type})
        if apply:
            api_json(
                "POST",
                f"/bitable/v1/apps/{quote(app_token)}/tables/{quote(table_id)}/fields",
                token,
                f"创建字段 {field_name}",
                body={"field_name": field_name, "type": field_type},
            )
            time.sleep(0.3)
    final_fields = list_fields(token, app_token, table_id) if apply and actions else fields
    final_primary = next((item for item in final_fields if item.get("is_primary")), primary)
    return {
        "actions": actions,
        "primary_field": str(final_primary.get("field_name") or primary_name),
        "fields": final_fields,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_bundle(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("topics"), list):
        raise ValueError("写入包必须是含 topics 数组的 JSON 对象。")
    topics: list[dict] = []
    for index, raw in enumerate(payload["topics"], 1):
        if not isinstance(raw, dict):
            raise ValueError(f"topics[{index}] 必须是对象。")
        topic_id = str(raw.get("topic_id") or "").strip()
        title = str(raw.get("title") or raw.get("topic") or "").strip()
        comment_text = str(raw.get("comment_text") or raw.get("comment") or "").strip()
        evidence_fit = str(raw.get("evidence_fit") or "").strip()
        image_values = raw.get("images")
        if not topic_id or not title or not comment_text or not evidence_fit:
            raise ValueError(f"topics[{index}] 必须包含 topic_id、title、comment_text、evidence_fit。")
        if not isinstance(image_values, list) or not image_values:
            raise ValueError(f"topics[{index}] 必须至少包含一张原评论截图。")
        images = [(path.parent / str(value)).resolve() for value in image_values]
        for image in images:
            if not image.is_file():
                raise ValueError(f"截图不存在：{image}")
            if image.stat().st_size > MAX_IMAGE_BYTES:
                raise ValueError(f"截图超过 20 MB：{image}")
        item = dict(raw)
        item.update(
            {
                "topic_id": topic_id,
                "title": title,
                "comment_text": comment_text,
                "evidence_fit": evidence_fit,
                "images": images,
            }
        )
        topics.append(item)
    return topics


def upload_bitable_image(token: str, app_token: str, image_path: Path) -> str:
    mime = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    with image_path.open("rb") as handle:
        response = SESSION.post(
            API_BASE + "/drive/v1/medias/upload_all",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "file_name": image_path.name,
                "parent_type": "bitable_image",
                "parent_node": app_token,
                "size": str(image_path.stat().st_size),
            },
            files={"file": (image_path.name, handle, mime)},
            timeout=120,
        )
    payload = check_response(response, f"上传评论截图 {image_path.name}")
    file_token = str(payload.get("data", {}).get("file_token") or "").strip()
    if not file_token:
        raise RuntimeError(f"上传截图成功响应中没有 file_token：{image_path.name}")
    return file_token


def list_records(token: str, app_token: str, table_id: str) -> list[dict]:
    return list_all(
        token,
        f"/bitable/v1/apps/{quote(app_token)}/tables/{quote(table_id)}/records",
        "读取已有选题记录",
        page_size=500,
    )


def record_fields(topic: dict, config: dict, primary_field: str, run_key: str, file_tokens: list[str]) -> dict:
    evidence_hashes = [sha256_file(path) for path in topic["images"]]
    collected_at = str(topic.get("collected_at") or datetime.now().astimezone().isoformat(timespec="seconds"))
    return {
        primary_field: topic["title"],
        "赛道": str(topic.get("track") or config.get("track") or ""),
        "内容分类": str(topic.get("category") or ""),
        "评论截图": [{"file_token": value} for value in file_tokens],
        "评论原文": topic["comment_text"],
        "选题依据": topic["evidence_fit"],
        "爆款理由": str(topic.get("viral_reason") or ""),
        "三秒钩子": str(topic.get("hook") or ""),
        "内容结构": str(topic.get("outline") or ""),
        "来源平台": str(topic.get("source_platform") or ""),
        "视频标题": str(topic.get("video_title") or ""),
        "视频链接": str(topic.get("source_url") or topic.get("video_url") or ""),
        "评论ID": str(topic.get("comment_id") or ""),
        "选题ID": topic["topic_id"],
        "批次ID": f"{run_key}:{topic['topic_id']}",
        "采集时间": collected_at,
        "证据哈希": "\n".join(evidence_hashes),
        "状态": str(topic.get("status") or "待创作"),
    }


def create_record(token: str, app_token: str, table_id: str, fields: dict, dedupe_key: str) -> dict:
    # Feishu validates the UUID version bits and currently requires UUID v4.
    # Cross-run idempotency is enforced by the persisted 批次ID field before
    # this request; client_token protects only this individual API attempt.
    client_token = str(uuid.uuid4())
    payload = api_json(
        "POST",
        f"/bitable/v1/apps/{quote(app_token)}/tables/{quote(table_id)}/records",
        token,
        "写入选题记录",
        body={"fields": fields},
        params={"client_token": client_token},
    )
    return payload.get("data", {}).get("record", {})


def emit_result(result: dict, path: Path | None) -> None:
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    print(rendered, end="")
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="接入飞书多维表格并写入评论证据选题。")
    parser.add_argument("--config", type=Path, default=default_config_path())
    parser.add_argument("--target", help="临时覆盖配置中的固定飞书多维表格链接。")
    parser.add_argument("--table-id")
    parser.add_argument("--table-name")
    parser.add_argument("--track", help="赛道名称；默认读取配置或写入包中的 track。")
    parser.add_argument("--test-connection", action="store_true", help="只读取目标表和字段，不修改。")
    parser.add_argument("--ensure-schema", action="store_true", help="创建缺少的字段并重命名默认主字段。")
    parser.add_argument(
        "--ensure-track-table",
        action="store_true",
        help="按赛道查找数据表；不存在时新建同结构数据表。首次使用可复用空白默认表。",
    )
    parser.add_argument("--bundle", type=Path, help="写入结构化 topic bundle。")
    parser.add_argument("--run-key")
    parser.add_argument("--dry-run", action="store_true", help="只校验本地输入，不调用飞书。")
    parser.add_argument("--result-json", type=Path)
    args = parser.parse_args()
    if not any((args.test_connection, args.ensure_schema, args.ensure_track_table, args.bundle, args.dry_run)):
        parser.error("至少选择 --test-connection、--ensure-schema、--ensure-track-table、--bundle 或 --dry-run。")
    return args


def main() -> int:
    args = parse_args()
    config_path = args.config.resolve()
    config = load_config(config_path)
    target_value = str(args.target or config.get("bitable") or config.get("document") or "")
    target = parse_target(target_value)
    requested_table = str(args.table_id or target.get("table_id") or "")
    table_name = str(args.table_name or "")
    topics: list[dict] = []
    run_key = str(args.run_key or "").strip()
    if args.bundle:
        bundle_path = args.bundle.resolve()
        if not bundle_path.is_file():
            raise SystemExit(f"写入包不存在：{bundle_path}")
        topics = load_bundle(bundle_path)
        if not run_key:
            run_key = hashlib.sha256(bundle_path.read_bytes()).hexdigest()[:20]
    if not run_key:
        run_key = "connection-check"
    if not re.fullmatch(r"[A-Za-z0-9._-]{6,80}", run_key):
        raise SystemExit("--run-key 仅允许 6–80 位字母、数字、点、下划线或连字符。")

    fallback_track = str(args.track or config.get("track") or "").strip()
    track_groups: dict[str, list[dict]] = {}
    for topic in topics:
        track = str(topic.get("track") or fallback_track).strip()
        if not track:
            raise SystemExit(f"选题 {topic['topic_id']} 缺少 track，且配置中没有主赛道。")
        topic["track"] = track
        track_groups.setdefault(track, []).append(topic)
    requested_tracks = list(track_groups)
    if not requested_tracks and fallback_track:
        requested_tracks = [fallback_track]
    if args.ensure_track_table and not requested_tracks:
        raise SystemExit("--ensure-track-table 需要 --track、配置中的主赛道或写入包中的 track。")

    result = {
        "status": "dry_run" if args.dry_run else "pending",
        "target_kind": target["kind"],
        "target_token": target["token"],
        "requested_table_id": requested_table,
        "table_name": table_name,
        "tracks": requested_tracks,
        "run_key": run_key,
        "topics": len(topics),
        "planned_fields": [{"field_name": name, "type": field_type} for name, field_type in FIELD_SPECS],
    }
    if args.dry_run:
        emit_result(result, args.result_json)
        return 0

    token = get_access_token()
    app_token = resolve_app_token(token, target)
    result["app_token"] = app_token
    written: list[dict] = []
    skipped: list[str] = []
    table_results: list[dict] = []

    if requested_tracks:
        apply_table = bool(topics or args.ensure_schema or args.ensure_track_table)
        for track in requested_tracks:
            table, table_action = resolve_track_table(token, app_token, track, config, apply=apply_table)
            if table is None:
                table_results.append(
                    {
                        "track": track,
                        "table_name": table_name_for_track(track),
                        "table_action": table_action,
                        "status": "missing",
                    }
                )
                continue
            table_id = str(table.get("table_id") or "")
            schema = ensure_schema(token, app_token, table_id, apply=apply_table)
            if apply_table:
                remember_track_table(config_path, config, track, table)
            table_result = {
                "track": track,
                "table_id": table_id,
                "table_name": str(table.get("name") or table_name_for_track(track)),
                "table_action": table_action,
                "schema_actions": schema["actions"],
                "primary_field": schema["primary_field"],
                "field_count": len(schema["fields"]),
            }
            table_results.append(table_result)

            group_topics = track_groups.get(track, [])
            if not group_topics:
                continue
            existing = list_records(token, app_token, table_id)
            existing_keys = {
                str((item.get("fields") or {}).get("批次ID") or "")
                for item in existing
                if isinstance(item.get("fields"), dict)
            }
            for topic in group_topics:
                dedupe_key = f"{run_key}:{topic['topic_id']}"
                if dedupe_key in existing_keys:
                    skipped.append(topic["topic_id"])
                    continue
                uploaded = [upload_bitable_image(token, app_token, path) for path in topic["images"]]
                fields = record_fields(topic, config, schema["primary_field"], run_key, uploaded)
                record = create_record(token, app_token, table_id, fields, dedupe_key)
                written.append(
                    {
                        "track": track,
                        "topic_id": topic["topic_id"],
                        "record_id": record.get("record_id", ""),
                        "images": len(uploaded),
                    }
                )
                existing_keys.add(dedupe_key)
                time.sleep(0.35)
    else:
        requested_table = requested_table or str(config.get("table_id") or "")
        table_name = table_name or str(config.get("table_name") or "")
        table = resolve_table(token, app_token, requested_table, table_name)
        table_id = str(table.get("table_id") or "")
        schema = ensure_schema(token, app_token, table_id, apply=bool(args.ensure_schema or topics))
        table_results.append(
            {
                "table_id": table_id,
                "table_name": str(table.get("name") or ""),
                "table_action": "direct",
                "schema_actions": schema["actions"],
                "primary_field": schema["primary_field"],
                "field_count": len(schema["fields"]),
            }
        )

    result["tables"] = table_results
    if len(table_results) == 1 and table_results[0].get("table_id"):
        result.update(
            {
                "table_id": table_results[0]["table_id"],
                "resolved_table_name": table_results[0]["table_name"],
                "schema_actions": table_results[0].get("schema_actions", []),
                "primary_field": table_results[0].get("primary_field", ""),
                "field_count": table_results[0].get("field_count", 0),
            }
        )
    if topics:
        result.update({"status": "success", "written": written, "skipped_duplicates": skipped})
    elif any(item.get("status") == "missing" for item in table_results):
        result["status"] = "track_table_missing"
    elif apply_table if requested_tracks else args.ensure_schema:
        result["status"] = "schema_ready"
    else:
        result["status"] = "connected"
    emit_result(result, args.result_json)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("操作已取消。", file=sys.stderr)
        raise SystemExit(130)
