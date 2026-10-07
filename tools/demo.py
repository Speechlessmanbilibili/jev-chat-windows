"""用合成对话执行真实 API 验证，调用会产生 API 用量。

默认只分析意图和语气。--cases 验证多个场景，--draft 额外生成回复。
"""
from __future__ import annotations

import argparse
from app import settings
from core.engine import analyze, generate_replies
from core.intent import ratings
from core.jev_client import JevError

CASES = (
    ("问候", "friends", [("her", "你好，好久不见！最近过得怎么样？")]),
    ("问责", "colleagues", [("me", "我答应今天交报告。"),
                            ("her", "昨天已经提醒过你了，为什么还没交？你到底有没有负责？")]),
    ("询问进度", "colleagues", [("her", "报告目前进度怎么样？我想安排后面的工作。")]),
    ("提醒和感谢", "colleagues", [("her", "谢谢你整理的资料！记得明天上午十点前把附件发给我。")]),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", action="store_true", help="分析全部合成场景")
    parser.add_argument("--draft", action="store_true", help="额外调用起草模型和排序")
    args = parser.parse_args()
    # 设置模块也能读取 Windows 用户环境中保存的密钥。
    settings.jev_key()
    if args.draft:
        settings.llm_key()
    cases = CASES if args.cases else CASES[:1]
    for title, relationship, messages in cases:
        print(f"\n场景：{title}")
        for who, text in messages:
            print(f"  {who}: {text}")
        try:
            result = analyze(messages, relationship, jev_provider=settings.jev_provider(),
                             jev_model=settings.jev_model() or None)
            for kind, label in (("intent", "意图"), ("tone", "语气")):
                print(label + "：" + "、".join(f"{name} {value}%" if value is not None else f"{name} —"
                                             for name, value in ratings(result["answers"], kind)[:4]))
            print(f"评分项：{len(result['answers'])}；拒答项：{result['refused']}")
            if args.draft:
                result = generate_replies(messages, relationship, result,
                                          provider=settings.draft_provider(), model=settings.draft_model() or None,
                                          base_url=settings.draft_base_url() or None, style=settings.style(),
                                          thinking=settings.thinking(), jev_provider=settings.jev_provider(),
                                          jev_model=settings.jev_model() or None)
                for index, text in enumerate(result["candidates"]):
                    print(f"  {'★' if index == result['best_index'] else '·'} {text}")
        except JevError as error:
            print(f"失败：{error}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
