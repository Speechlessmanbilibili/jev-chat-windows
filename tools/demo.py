# -*- coding: utf-8 -*-
"""用合成对话验证判断、起草和排序，打印结果。

默认使用 OpenAI Decisions 判断、DeepSeek 起草，需设置 OPENAI_API_KEY 和 LLM_API_KEY。
运行：python -X utf8 -m tools.demo。调用会产生 API 用量。
"""
from __future__ import annotations

import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from core.engine import analyze
from core.jev_client import JevError
from core.questions import guidance_text

MESSAGES = [
    ("her", "你今天是不是又忘了我跟你说过什么？"),
    ("me", "记得，你先别提示我，让我自己说。"),
    ("her", "那你说。"),
    ("me", "等一下，我想说完整一点。"),
    ("her", "你最好是。"),
]
RELATIONSHIP = "romantic partners"
PROVIDER = "deepseek"        # 起草来源，见 core.providers.DRAFT_PROVIDERS
JEV_PROVIDER = "openai"  # 判断来源：openai / openrouter / typesafe


def fmt(name: str, ans: dict) -> str:
    t = ans.get("type")
    if t == "noul":
        return f"{name}: {ans.get('noul'):.2f}"
    if t == "choice":
        return f"{name}: {ans.get('choice')} (conf {ans.get('confidence'):.2f})"
    if t == "score":
        return f"{name}: {ans.get('score'):.1f}/9 (conf {ans.get('confidence'):.2f})"
    return f"{name}: {ans}"


def main() -> int:
    print("对话:")
    for w, t in MESSAGES:
        print(f"  {w}: {t}")
    try:
        r = analyze(MESSAGES, RELATIONSHIP, provider=PROVIDER, jev_provider=JEV_PROVIDER)
    except JevError as e:
        print(f"\n失败: {e}")
        return 1

    print("\n判断:")
    for name in ("literal_question", "true_intent", "danger_level",
                 "should_reply_now", "best_action", "she_needs", "tension_resolved"):
        if name in r["answers"]:
            print("  " + fmt(name, r["answers"][name]))

    block = guidance_text(r["answers"])  # 起草时喂进去的那张小抄
    if block:
        print("\n" + block)

    print("\n候选（判断模型排序，★ = 推荐）:")
    scores = r.get("scores")
    for i, c in enumerate(r["candidates"]):
        pct = f"  {scores[i]:.0%}" if scores else ""
        print(f"  {'★' if i == r['best_index'] else ' '} {c}{pct}")

    u = r["usage"]
    if u:
        print(f"\nusage: in={u.get('input_tokens')} out={u.get('output_tokens')} "
              f"cost=${u.get('cost')}")
    print("\n期望核对: true_intent≈confirm_you_care, best_action≈check_history, danger_level 中高档")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
