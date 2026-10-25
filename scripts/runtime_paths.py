#!/usr/bin/env python3
"""Portable local-state paths shared by the bundled scripts."""

from __future__ import annotations

import os
from pathlib import Path


APP_DIR = "feishu-video-topic-miner"


def state_root() -> Path:
    override = os.environ.get("VIDEO_TOPIC_MINER_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        return base / "AgentSkills" / APP_DIR
    xdg_state = os.environ.get("XDG_STATE_HOME", "").strip()
    base = Path(xdg_state).expanduser() if xdg_state else Path.home() / ".local" / "state"
    return base / "agent-skills" / APP_DIR


def default_config_path() -> Path:
    return state_root() / "config.json"


def default_credentials_path() -> Path:
    return state_root() / "credentials.json"


def default_browser_profile_path() -> Path:
    return state_root() / "browser-profile"
