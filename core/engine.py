"""独立的意图分析和按需回复生成入口。"""
from __future__ import annotations

from .draft import draft_candidates
from .intent import INTENT_QUESTIONS, guidance_text
from .jev_client import JevError, ask
from .questions import build_rank_question, build_state

_REPLY_IDX = {"reply_a": 0, "reply_b": 1, "reply_c": 2}


def analyze(messages: list, relationship: str, timeout: float = 30, context: int = 10,
            reply_to: str | None = None, jev_provider: str = "openai",
            jev_model: str | None = None) -> dict:
    """一次请求评估 18 项意图、10 项语气和紧张度，无起草调用。"""
    response = ask(build_state(messages, relationship, keep=context, reply_to=reply_to),
                   INTENT_QUESTIONS, timeout=timeout, provider=jev_provider, model=jev_model)
    return {"answers": response.get("answers") or {}, "usage": response.get("usage") or {},
            "refused": response.get("refused") or [], "reply_to": reply_to}


def generate_replies(messages: list, relationship: str, analysis: dict,
                     model: str | None = None, timeout: float = 30, context: int = 10,
                     provider: str = "deepseek", base_url: str | None = None,
                     style: str = "", thinking: bool = False,
                     jev_provider: str = "openai", jev_model: str | None = None) -> dict:
    """显式生成候选并排序；失败由调用方显示在起草区域。"""
    reply_to = analysis.get("reply_to")
    candidates = draft_candidates(messages, relationship, provider=provider, model=model,
                                  base_url=base_url, timeout=timeout, keep=context,
                                  reply_to=reply_to, style=style, thinking=thinking,
                                  guidance=guidance_text(analysis.get("answers") or {}))
    if not candidates:
        raise JevError("起草结果没有可用候选回复")
    ranked = {}
    if len(candidates) >= 2:
        ranked = ask(build_state(messages, relationship, keep=context, reply_to=reply_to),
                     build_rank_question(candidates), timeout=timeout,
                     provider=jev_provider, model=jev_model)
    best = (ranked.get("answers") or {}).get("best_reply") or {}
    index = _REPLY_IDX.get(best.get("choice"), 0)
    if index >= len(candidates):
        index = 0
    probabilities = best.get("probabilities") or {}
    scores = [probabilities.get(key, 0) for key in _REPLY_IDX][:len(candidates)]
    return {**analysis, "candidates": candidates, "best_index": index,
            "best_reply": candidates[index], "scores": scores,
            "draft_usage": ranked.get("usage") or {}}
