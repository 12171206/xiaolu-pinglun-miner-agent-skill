#!/usr/bin/env python3
"""Load Feishu credentials safely without logging secrets."""

from __future__ import annotations

import argparse
import base64
import ctypes
import getpass
import json
import os
from ctypes import wintypes
from pathlib import Path

from runtime_paths import default_credentials_path


class DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


CRYPTPROTECT_UI_FORBIDDEN = 0x01


def _input_blob(data: bytes) -> tuple[DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    blob = DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _output_bytes(blob: DataBlob) -> bytes:
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob.pbData)


def protect(secret: str) -> str:
    if os.name != "nt":
        raise RuntimeError("安全凭证文件当前仅支持 Windows；其他系统请使用环境变量。")
    source, keepalive = _input_blob(secret.encode("utf-8"))
    _ = keepalive
    output = DataBlob()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source),
        "Agent Skill Feishu credential",
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output),
    )
    if not ok:
        raise ctypes.WinError()
    return base64.b64encode(_output_bytes(output)).decode("ascii")


def unprotect(encoded: str) -> str:
    if os.name != "nt":
        raise RuntimeError("安全凭证文件当前仅支持 Windows；其他系统请使用环境变量。")
    source, keepalive = _input_blob(base64.b64decode(encoded))
    _ = keepalive
    output = DataBlob()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output),
    )
    if not ok:
        raise ctypes.WinError()
    return _output_bytes(output).decode("utf-8")


def save_credentials(app_id: str, app_secret: str, path: Path | None = None) -> Path:
    app_id = app_id.strip()
    app_secret = app_secret.strip()
    if not app_id.startswith("cli_"):
        raise ValueError("App ID 应以 cli_ 开头。")
    if not app_secret:
        raise ValueError("App Secret 不能为空。")
    target = (path or default_credentials_path()).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "app_id": app_id, "protected_secret": protect(app_secret)}
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def load_credentials(path: Path | None = None) -> tuple[str, str]:
    env_id = os.environ.get("FEISHU_APP_ID", "").strip()
    env_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if env_id and env_secret:
        return env_id, env_secret
    target = (path or default_credentials_path()).resolve()
    if not target.is_file():
        raise RuntimeError("尚未保存飞书凭证。请先运行 feishu_credentials.py --save。")
    payload = json.loads(target.read_text(encoding="utf-8"))
    app_id = str(payload.get("app_id") or "").strip()
    protected = str(payload.get("protected_secret") or "").strip()
    if not app_id or not protected:
        raise RuntimeError("飞书凭证文件不完整，请重新保存。")
    return app_id, unprotect(protected)


def main() -> int:
    parser = argparse.ArgumentParser(description="在本机安全保存飞书应用凭证。")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--save", action="store_true", help="交互输入并保存凭证。")
    action.add_argument("--show", action="store_true", help="只显示配置状态，不显示密钥。")
    action.add_argument("--clear", action="store_true", help="删除本机保存的凭证。")
    parser.add_argument("--app-id", help="飞书 App ID；保存时必填。")
    parser.add_argument("--credentials", type=Path, default=default_credentials_path())
    args = parser.parse_args()

    path = args.credentials.resolve()
    if args.show:
        if not path.is_file():
            print(json.dumps({"configured": False, "credentials_path": str(path)}, ensure_ascii=False, indent=2))
            return 2
        payload = json.loads(path.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {
                    "configured": bool(payload.get("app_id") and payload.get("protected_secret")),
                    "app_id": payload.get("app_id", ""),
                    "credentials_path": str(path),
                    "secret": "已由 Windows 当前用户加密保存",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.clear:
        if path.exists():
            path.unlink()
        print(json.dumps({"configured": False, "credentials_path": str(path)}, ensure_ascii=False, indent=2))
        return 0
    if not args.app_id:
        raise SystemExit("--save 需要同时提供 --app-id。")
    secret = getpass.getpass("请粘贴新生成的 App Secret（输入不会显示）：")
    confirmation = getpass.getpass("请再次输入 App Secret：")
    if secret != confirmation:
        raise SystemExit("两次输入不一致，未保存。")
    saved = save_credentials(args.app_id, secret, path)
    print(
        json.dumps(
            {
                "configured": True,
                "app_id": args.app_id.strip(),
                "credentials_path": str(saved),
                "secret": "已由 Windows 当前用户加密保存",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
