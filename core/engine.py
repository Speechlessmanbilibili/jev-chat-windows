"""意图分析、显式起草与候选排序。过期任务由会话调度层处理。"""
from __future__ import annotations

from datetime import datetime

from . import llm
from .draft import draft_candidates
from .intent import INTENT_QUESTIONS, guidance_text
from .jev_client import JevError, ask
from .providers import DRAFT_PROVIDERS
from .questions import build_rank_question, build_state

_REPLY_KEYS = ("reply_a", "reply_b", "reply_c")


def analyze(messages: list, relationship: str, timeout: float = 30, context: int = 10,
            reply_to: str | None = None, jev_provider: str = "openai",
            jev_model: str | None = None, jev_base_url: str | None = None) -> dict:
    """一次请求完成 29 道评分题，并保存起草与排序使用的同一份状态。"""
    state = build_state(messages, relationship, keep=context, reply_to=reply_to)
    target = state["chat"]["reply_target"]
    if target is None:
        raise JevError("参考上下文中没有分析对象的发言，请增加上下文条数或更换对象。")
    judge = dict(provider=jev_provider, model=jev_model, base_url=jev_base_url, timeout=timeout)
    response = ask(state, INTENT_QUESTIONS, **judge)
    return {"state": state, "judge": judge, "answers": response["answers"],
            "usage": response.get("usage", {}), "refused": response.get("refused", []),
            "reply_to": reply_to, "reply_target": target,
            "analyzed_text": target["text"], "analyzed_sender": target.get("name"),
            "analyzed_at": datetime.now().strftime("%H:%M")}


def generate_replies(analysis: dict, *, model: str | None = None, timeout: float = 30,
                     provider: str = "deepseek", base_url: str | None = None,
                     style: str = "", thinking: bool = False) -> dict:
    """一次起草；排序失败保留候选，但不指定推荐项。"""
    candidates = draft_candidates(analysis["state"], provider=provider, model=model,
                                  base_url=base_url, timeout=timeout, style=style, thinking=thinking,
                                  guidance=guidance_text(analysis["answers"]))
    index, scores, ranking_notice = None, [None] * len(candidates), ""
    if len(candidates) >= 2:
        try:
            ranked = ask(analysis["state"], build_rank_question(candidates), **analysis["judge"])
            best = ranked["answers"]["best_reply"]
            index = _REPLY_KEYS.index(best["choice"])
            if index >= len(candidates):
                raise JevError("排序服务返回了不存在的候选选项。")
            scores = [best["probabilities"][key] for key in _REPLY_KEYS[:len(candidates)]]
        except (JevError, KeyError, ValueError) as exc:
            index = None
            scores = [None] * len(candidates)
            ranking_notice = "候选已生成，排序未完成，请自行选择。"
            ranking_error = str(exc)
        else:
            ranking_error = ""
    else:
        ranking_error = ""
    spec = DRAFT_PROVIDERS[provider]
    notice = (llm.GEMINI_DEFAULT_THINKING_NOTICE if spec.protocol == "gemini" and not thinking
              and llm.gemini_uses_default_thinking(base_url or spec.base, model or spec.default) else "")
    return {**analysis, "candidates": candidates, "best_index": index, "scores": scores,
            "draft_notice": ranking_notice or notice, "ranking_error": ranking_error}
