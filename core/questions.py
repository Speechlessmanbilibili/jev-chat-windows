"""判断题、上下文整理和回复排序题。"""
from .intent import INTENT_QUESTIONS as JUDGE_QUESTIONS, guidance_text


def build_state(messages: list, relationship: str, keep: int = 10,
                reply_to: str | None = None) -> dict:
    """messages: (from, text) / (from, text, name) / dict（name 可选）。from 只认 her/me。

    name = 群里的发言人；有 name 就当群聊（chat.is_group）。reply_to = 群里指定的回复对象。
    """
    cleaned = []
    for item in messages:
        if isinstance(item, dict):
            who, text, name = item.get("from"), item.get("text"), item.get("name")
        else:
            who, text = item[0], item[1]
            name = item[2] if len(item) > 2 else None
        if who not in ("her", "me"):
            raise ValueError(f"message from must be 'her' or 'me', got {who!r}")
        message = {"from": who, "text": str(text)}
        if name:
            message["name"] = str(name)
        cleaned.append(message)
    cleaned = cleaned[-keep:]
    latest_from = cleaned[-1]["from"] if cleaned else "her"
    chat = {
        "relationship": relationship,
        "messages": cleaned,
        "latest_from": latest_from,
        "is_group": any("name" in m for m in cleaned),
    }
    if reply_to:
        chat["reply_to"] = str(reply_to)
    return {"chat": chat}


def build_rank_question(candidates: list[str]) -> dict:
    """Build the best_reply choice question. criteria values stay in original Chinese."""
    if not 2 <= len(candidates) <= 3:
        raise ValueError("build_rank_question expects 2 or 3 candidate replies")
    keys = ("reply_a", "reply_b", "reply_c")[:len(candidates)]
    return {
        "best_reply": {
            "type": "choice",
            "instructions": (
                "Which candidate reply is the most appropriate next message, "
                "given the conversation and the other person's true need? "
                "Prefer a reply that fits the intent and tone of the conversation. "
                "Penalize dismissive, over-promising, or off-topic replies. "
                "If the facts are not yet confirmed, prefer the candidate that looks them up "
                "instead of faking memory or a vague apology."
            ),
            "criteria": {key: text for key, text in zip(keys, candidates)},
        }
    }
