# -*- coding: utf-8 -*-
"""查 GitHub 最新 Release，只拿版本号和链接。离线/限流/GFW 一律返回 None，绝不抛异常、绝不重试。"""
from __future__ import annotations

import json
import urllib.request

_API = "https://api.github.com/repos/Speechlessmanbilibili/jev-chat-windows/releases/latest"


def parse_version(v: str) -> tuple[int, ...] | None:
    """"1.2.3" → (1, 2, 3)。哪一段不是纯数字（比如 "0.0.0-dev" 的 "0-dev"）就判不出来，返回 None——
    current 和 latest 标签统一走这条：不是正经版本号就别比了。"""
    segs = v.split(".")
    if not segs or any(not seg.isdigit() for seg in segs):
        return None
    return tuple(int(s) for s in segs)


def check_latest(current: str, timeout=6) -> tuple[str, str] | None:
    """current 不是纯数字版本（源码跑/开发版）→ 直接跳过，不发请求，源码用户不会被打扰。
    latest 比 current 严格新才返回 (最新版本号, Release 页链接)；否则/任何异常都是 None。"""
    cur = parse_version(current)
    if cur is None:
        return None
    try:
        req = urllib.request.Request(_API, headers={
            "User-Agent": f"jev-chat-windows/{current}",
            "Accept": "application/vnd.github+json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
        tag = str(data.get("tag_name") or "")
        tag = tag[1:] if tag.startswith("v") else tag
        url = str(data.get("html_url") or "")
        latest = parse_version(tag)
        if latest is None or not url or latest <= cur:
            return None
        return tag, url
    except Exception:
        return None
