#!/usr/bin/env python3
"""Capture visible video comments and one evidence screenshot per comment.

The collector intentionally uses the page a human can see. It does not call
private endpoints, bypass login challenges, or import a person's normal browser
profile. Platform markup changes often, so every selector can be overridden.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from runtime_paths import default_browser_profile_path


PLATFORMS = {
    "youtube": {
        "hosts": ("youtube.com", "youtu.be"),
        "comments": ("ytd-comment-thread-renderer #comment", "ytd-comment-view-model"),
        "anchor": ("#comments",),
        "author": ("#author-text span", "#author-text"),
        "content": ("#content-text", "yt-attributed-string#content-text"),
        "time": ("#published-time-text", "a#published-time-text"),
        "likes": ("#vote-count-middle",),
    },
    "bilibili": {
        "hosts": ("bilibili.com", "b23.tv"),
        "comments": ("bili-comment-thread-renderer", ".reply-item", ".sub-reply-item"),
        "anchor": ("#comment", ".comment-container", "bili-comments"),
        "author": (".user-name", ".user-info .name", ".nickname"),
        "content": (".reply-content", ".root-reply .content", ".sub-reply .content"),
        "time": (".reply-time", ".time", ".pubdate"),
        "likes": (".like span", ".like-count"),
    },
    "douyin": {
        "hosts": ("douyin.com", "iesdouyin.com"),
        "comments": ("[data-e2e='comment-item']", "[data-e2e='comment-list'] > div", ".comment-item"),
        "anchor": ("[data-e2e='comment-list']", ".comment-list"),
        "author": (
            "[data-e2e='comment-username']",
            ":scope > div:nth-child(2) > div > div:first-child a[href*='/user/']",
            ".author-name",
            ".name",
        ),
        "content": (
            "[data-e2e='comment-content']",
            ":scope > div:nth-child(2) > div > div:nth-child(2)",
            ".comment-content",
            ".content",
        ),
        "time": (
            "[data-e2e='comment-time']",
            ":scope > div:nth-child(2) > div > div:nth-child(3)",
            ".comment-time",
            ".time",
        ),
        "likes": (
            "[data-e2e='comment-like-count']",
            ":scope > div:nth-child(2) > div > div:nth-child(4) .comment-item-stats-container > div:first-child p:first-child span",
            ".like-count",
        ),
    },
    "xiaohongshu": {
        "hosts": ("xiaohongshu.com", "xhslink.com"),
        "comments": (".comments-container .comment-item", ".parent-comment", ".comment-item"),
        "anchor": (".comments-container", ".comment-list"),
        "author": (".author .name", ".user-name", ".name"),
        "content": (".content", ".comment-content", ".note-text"),
        "time": (".date", ".time"),
        "likes": (".like-wrapper .count", ".like-count"),
    },
    "kuaishou": {
        "hosts": ("kuaishou.com", "v.kuaishou.com"),
        "comments": ("[data-testid='comment-item']", ".comment-item"),
        "anchor": ("[data-testid='comment-list']", ".comment-list"),
        "author": (".user-name", ".author-name", ".name"),
        "content": (".comment-content", ".content"),
        "time": (".comment-time", ".time"),
        "likes": (".like-count",),
    },
    "generic": {
        "hosts": (),
        "comments": (".comment-item", "[data-comment-id]", "article.comment"),
        "anchor": ("#comments", ".comments", ".comment-list"),
        "author": (".author", ".user-name", ".username", ".name"),
        "content": (".comment-content", ".comment-text", ".content", ".text"),
        "time": ("time", ".time", ".date"),
        "likes": (".like-count", ".likes", ".vote-count"),
    },
}

EXPAND_TEXT = re.compile(
    r"^(展开|展开更多|查看回复|查看全部回复|更多回复|more replies|view replies|show more)$",
    re.IGNORECASE,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    return re.sub(r"\s+", " ", value).strip()


def detect_platform(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for name, config in PLATFORMS.items():
        if name != "generic" and any(host == item or host.endswith("." + item) for item in config["hosts"]):
            return name
    return "generic"


def first_text(container, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        try:
            node = container.locator(selector).first
            if node.count() and node.is_visible():
                text = normalize_text(node.inner_text(timeout=1500))
                if text:
                    return text
        except Exception:
            continue
    return ""


def choose_selector(page, selectors: tuple[str, ...]) -> tuple[str, int]:
    best = (selectors[0], 0)
    for selector in selectors:
        try:
            count = page.locator(selector).count()
        except Exception:
            count = 0
        if count > best[1]:
            best = (selector, count)
    return best


def click_expanders(page, limit: int = 12) -> int:
    clicked = 0
    try:
        buttons = page.get_by_text(EXPAND_TEXT)
        count = min(buttons.count(), limit)
        for index in range(count):
            try:
                button = buttons.nth(index)
                if button.is_visible() and button.is_enabled():
                    button.click(timeout=1200)
                    clicked += 1
            except Exception:
                continue
    except Exception:
        pass
    return clicked


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def comment_key(url: str, author: str, content: str, raw_text: str) -> str:
    stable = "\n".join((url, normalize_text(author), normalize_text(content or raw_text)))
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:20]


def load_selected_ids(path: Path | None) -> set[str]:
    if path is None:
        return set()
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return set()
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            payload = payload.get("comments") or payload.get("selected_comments") or []
        if not isinstance(payload, list):
            raise ValueError("JSON 顶层必须是数组，或包含 comments 数组。")
        values = payload
    except json.JSONDecodeError:
        values = [json.loads(line) for line in text.splitlines() if line.strip()]
    result = set()
    for item in values:
        if isinstance(item, str):
            result.add(item)
        elif isinstance(item, dict) and item.get("comment_id"):
            result.add(str(item["comment_id"]))
    return result


def launch_context(playwright, profile: Path, headless: bool, channel: str):
    base = {
        "user_data_dir": str(profile),
        "headless": headless,
        "viewport": {"width": 1440, "height": 1000},
        "locale": "zh-CN",
    }
    candidates = [channel] if channel != "auto" else ["msedge", "chrome", "bundled"]
    errors = []
    for candidate in candidates:
        try:
            if candidate == "bundled":
                return playwright.chromium.launch_persistent_context(**base), "bundled"
            return playwright.chromium.launch_persistent_context(channel=candidate, **base), candidate
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")
    raise RuntimeError("无法启动 Chromium 浏览器：" + " | ".join(errors))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="采集可见视频评论并逐条截图留证。")
    parser.add_argument("url", help="视频页面 URL；也支持 file: 或 data: URL 用于测试。")
    parser.add_argument("--out", required=True, type=Path, help="该视频的输出目录。")
    parser.add_argument("--platform", choices=tuple(PLATFORMS), default="generic", help="平台；默认按 URL 自动识别。")
    parser.add_argument("--max-comments", type=int, default=0, help="评论条数上限；0 表示不限。")
    parser.add_argument("--max-scrolls", type=int, default=0, help="滚动轮数上限；0 表示不限。")
    parser.add_argument("--stale-rounds", type=int, default=5, help="连续多少轮无新增评论后停止。")
    parser.add_argument("--settle-ms", type=int, default=1200)
    parser.add_argument("--navigation-timeout-ms", type=int, default=60000)
    parser.add_argument("--headful", action="store_true", help="显示浏览器，用于登录或人工观察。")
    parser.add_argument("--browser-channel", choices=("auto", "msedge", "chrome", "bundled"), default="auto")
    parser.add_argument("--profile", type=Path, help="独立浏览器资料目录。")
    parser.add_argument("--cdp-url", help="连接用户已打开的 Chromium 调试端口，例如 http://127.0.0.1:9223。")
    parser.add_argument("--use-current-page", action="store_true", help="使用已打开页面，不再次导航；需配合 --cdp-url。")
    parser.add_argument("--comment-selector")
    parser.add_argument("--author-selector")
    parser.add_argument("--content-selector")
    parser.add_argument("--time-selector")
    parser.add_argument("--like-selector")
    parser.add_argument("--sample-mode", default="visible_order", choices=("visible_order", "top", "latest"))
    parser.add_argument(
        "--screenshot-mode",
        choices=("none", "selected", "all"),
        default="none",
        help="默认不截图；筛选后用 selected 只截入选评论。",
    )
    parser.add_argument("--selected-ids", type=Path, help="入选评论 JSON/JSONL，用 comment_id 指定要截图的评论。")
    parser.add_argument("--wait-before-collect", type=int, default=0, help="页面打开后额外等待的秒数。")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    if args.max_comments < 0 or args.max_scrolls < 0 or args.stale_rounds < 1:
        raise SystemExit("--max-comments 和 --max-scrolls 不能为负数，--stale-rounds 必须大于 0。")
    if args.use_current_page and not args.cdp_url:
        raise SystemExit("--use-current-page 需要配合 --cdp-url。")
    selected_ids = load_selected_ids(args.selected_ids)
    if args.screenshot_mode == "selected" and not selected_ids:
        raise SystemExit("--screenshot-mode selected 需要非空的 --selected-ids。")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("缺少 Playwright。请先运行: py -m pip install playwright", file=sys.stderr)
        return 3

    platform = detect_platform(args.url) if args.platform == "generic" else args.platform
    config = PLATFORMS[platform]
    comment_selectors = (args.comment_selector,) if args.comment_selector else config["comments"]
    author_selectors = (args.author_selector,) if args.author_selector else config["author"]
    content_selectors = (args.content_selector,) if args.content_selector else config["content"]
    time_selectors = (args.time_selector,) if args.time_selector else config["time"]
    like_selectors = (args.like_selector,) if args.like_selector else config["likes"]

    out_dir = args.out.resolve()
    shots_dir = out_dir / "screenshots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    profile = (args.profile or default_browser_profile_path()).resolve()
    profile.mkdir(parents=True, exist_ok=True)

    started = now_iso()
    records: list[dict] = []
    seen: set[str] = set()
    seen_raw: set[str] = set()
    warnings: list[str] = []
    scrolls = 0
    selected_selector = comment_selectors[0]
    final_url = args.url
    page_title = ""
    browser_channel = ""

    with sync_playwright() as playwright:
        owns_context = not bool(args.cdp_url)
        if args.cdp_url:
            browser = playwright.chromium.connect_over_cdp(args.cdp_url)
            if not browser.contexts:
                raise RuntimeError("CDP 浏览器没有可用的上下文。")
            context = browser.contexts[0]
            browser_channel = "cdp"
        else:
            context, browser_channel = launch_context(playwright, profile, not args.headful, args.browser_channel)
        page = context.pages[-1] if context.pages else context.new_page()
        page.set_default_timeout(8000)
        try:
            if args.use_current_page:
                if page.url in ("", "about:blank"):
                    raise RuntimeError("当前浏览器页为空；请先在该窗口打开视频并完成人工验证。")
            else:
                page.goto(args.url, wait_until="domcontentloaded", timeout=args.navigation_timeout_ms)
                page.wait_for_timeout(2500)
            if args.wait_before_collect:
                page.wait_for_timeout(args.wait_before_collect * 1000)
            final_url = page.url
            page_title = page.title()

            for anchor in config["anchor"]:
                try:
                    candidate = page.locator(anchor).first
                    if candidate.count():
                        candidate.scroll_into_view_if_needed(timeout=2500)
                        page.wait_for_timeout(args.settle_ms)
                        break
                except Exception:
                    continue

            stale_rounds = 0
            round_index = 0
            while True:
                click_expanders(page)
                selected_selector, count = choose_selector(page, comment_selectors)
                locator = page.locator(selected_selector)
                new_this_round = 0

                scan_count = count if args.max_comments == 0 else min(count, args.max_comments * 3)
                for index in range(scan_count):
                    if args.max_comments and len(records) >= args.max_comments:
                        break
                    node = locator.nth(index)
                    try:
                        if not node.is_visible():
                            continue
                        raw_text = normalize_text(node.inner_text(timeout=2000))
                    except Exception:
                        continue
                    if len(raw_text) < 2:
                        continue
                    if raw_text in seen_raw:
                        continue
                    seen_raw.add(raw_text)

                    author = first_text(node, author_selectors)
                    content = first_text(node, content_selectors) or raw_text
                    published_at = first_text(node, time_selectors)
                    like_count = first_text(node, like_selectors)
                    key = comment_key(final_url, author, content, raw_text)
                    if key in seen:
                        continue

                    screenshot_rel = ""
                    screenshot_hash = ""
                    should_capture = args.screenshot_mode == "all" or (
                        args.screenshot_mode == "selected" and key in selected_ids
                    )
                    if should_capture:
                        shot_path = shots_dir / f"comment-{len(records) + 1:04d}-{key[:8]}.png"
                        try:
                            node.scroll_into_view_if_needed(timeout=2500)
                            node.screenshot(path=str(shot_path), timeout=8000)
                            screenshot_rel = shot_path.relative_to(out_dir).as_posix()
                            screenshot_hash = sha256_file(shot_path)
                        except Exception as exc:
                            warnings.append(f"评论 {key} 截图失败: {type(exc).__name__}")

                    seen.add(key)
                    records.append(
                        {
                            "comment_id": key,
                            "author": author,
                            "content": content,
                            "published_at": published_at,
                            "like_count_raw": like_count,
                            "raw_text": raw_text,
                            "source_url": final_url,
                            "platform": platform,
                            "sample_mode": args.sample_mode,
                            "selected_for_topic": key in selected_ids,
                            "screenshot": screenshot_rel,
                            "screenshot_sha256": screenshot_hash,
                            "collected_at": now_iso(),
                        }
                    )
                    new_this_round += 1

                print(
                    f"第 {round_index + 1} 轮：页面节点 {count}，新增 {new_this_round}，累计 {len(records)}",
                    file=sys.stderr,
                    flush=True,
                )

                if args.max_comments and len(records) >= args.max_comments:
                    break
                stale_rounds = stale_rounds + 1 if new_this_round == 0 else 0
                if stale_rounds >= args.stale_rounds:
                    break
                if args.max_scrolls and round_index >= args.max_scrolls:
                    break

                try:
                    if count:
                        locator.nth(count - 1).scroll_into_view_if_needed(timeout=2500)
                    page.mouse.wheel(0, 2200)
                except Exception:
                    page.evaluate("window.scrollBy(0, Math.max(1200, window.innerHeight * 1.8))")
                page.wait_for_timeout(args.settle_ms)
                scrolls = round_index + 1
                round_index += 1

            try:
                page.screenshot(path=str(out_dir / "page-overview.png"), full_page=False)
            except Exception as exc:
                warnings.append(f"页面概览截图失败: {type(exc).__name__}")
        except Exception as exc:
            warnings.append(f"页面采集失败: {type(exc).__name__}: {exc}")
        finally:
            if owns_context:
                context.close()

    comments_path = out_dir / "comments.jsonl"
    with comments_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    missing_selected = sorted(selected_ids - {item["comment_id"] for item in records})
    if missing_selected:
        warnings.append(f"有 {len(missing_selected)} 条入选评论未在本次页面加载中找到。")
    manifest = {
        "requested_url": args.url,
        "final_url": final_url,
        "page_title": page_title,
        "platform": platform,
        "sample_mode": args.sample_mode,
        "started_at": started,
        "finished_at": now_iso(),
        "max_comments": args.max_comments,
        "max_scrolls": args.max_scrolls,
        "stale_rounds_required": args.stale_rounds,
        "unique_comments": len(records),
        "screenshots_ok": sum(bool(item["screenshot"]) for item in records),
        "screenshot_mode": args.screenshot_mode,
        "selected_ids_requested": len(selected_ids),
        "selected_ids_missing": missing_selected,
        "scroll_rounds": scrolls,
        "comment_selector": selected_selector,
        "browser_channel": browser_channel,
        "profile_directory": str(profile),
        "warnings": warnings,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if not records:
        print("未识别到评论。请确认已登录、评论已展开，或传入 --comment-selector。", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

