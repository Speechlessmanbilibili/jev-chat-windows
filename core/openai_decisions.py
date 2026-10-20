# -*- coding: utf-8 -*-
"""将本项目的判断题和答案转换为 OpenAI Decisions API 格式。"""
from __future__ import annotations

import json
import math

from .jev_client import JevError, _fail
from .providers import OPENAI_BASE


def convert_questions(questions: dict) -> list[dict]:
    """保留题目名称和判据，转换谓词、选项及从 0 开始的评分等级。"""
    converted = []
    for name, question in questions.items():
        kind = question["type"]
        criteria = question["criteria"]
        item = {"name": name, "instructions": question["instructions"]}
        if kind == "noul":
            item.update(type="predicate", instructions=(
                item["instructions"] + "\nTrue condition: " + criteria["true"]
                + "\nFalse condition: " + criteria["false"]))
        elif kind == "choice":
            item.update(type="choice", choices=[
                {"value": value, "description": description}
                for value, description in criteria.items()])
        elif kind == "score":
            item.update(type="score", levels=[
                {"label": str(index), "description": description}
                for index, description in enumerate(criteria)])
        else:
            raise JevError(f"不支持的判断题类型：{kind}")
        converted.append(item)
    return converted


def _number(value, lower: float, upper: float) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not lower <= value <= upper or not math.isfinite(value)):
        raise JevError("Decisions 返回了无效数值")
    return float(value)


def normalize_response(response: dict, questions: dict) -> dict:
    """按名称读取答案；拒答保留为空，格式错误交由引擎的错误处理流程处理。"""
    answers, refused, seen = {}, [], set()
    raw_answers = response.get("answers") if isinstance(response, dict) else None
    if not isinstance(raw_answers, list):
        raise JevError("Decisions 响应缺少答案数组")
    for answer in raw_answers:
        if not isinstance(answer, dict):
            raise JevError("Decisions 答案格式错误")
        name = answer.get("name")
        if not isinstance(name, str) or name not in questions or name in seen:
            raise JevError("Decisions 返回了未知或重复的题目名称")
        seen.add(name)
        if answer.get("type") == "refusal":
            refused.append(name)
            continue
        question = questions[name]
        kind = question["type"]
        expected = "predicate" if kind == "noul" else kind
        if answer.get("type") != expected:
            raise JevError("Decisions 答案类型与题目不一致")
        if kind == "noul":
            answers[name] = {"type": "noul", "noul": _number(answer.get("probability"), 0, 1)}
            continue
        probabilities = {}
        raw_probabilities = answer.get("probabilities", [])
        if not isinstance(raw_probabilities, list):
            raise JevError("Decisions 返回的概率列表格式错误")
        for probability in raw_probabilities:
            if not isinstance(probability, dict):
                raise JevError("Decisions 返回的概率项格式错误")
            value = probability.get("value")
            if kind == "choice":
                if not isinstance(value, str) or value not in question["criteria"]:
                    raise JevError("Decisions 返回了无效选项")
            elif (isinstance(value, bool) or not isinstance(value, int)
                  or not 0 <= value < len(question["criteria"])):
                raise JevError("Decisions 返回了无效评分等级")
            key = str(value)
            if key in probabilities:
                raise JevError("Decisions 返回了重复概率项")
            probabilities[key] = _number(probability.get("probability"), 0, 1)
        normalized = {"type": kind, "probabilities": probabilities,
                      "confidence": _number(answer.get("confidence"), 0, 1)}
        if kind == "choice":
            choice = answer.get("choice")
            if not isinstance(choice, str) or choice not in question["criteria"]:
                raise JevError("Decisions 返回了无效推荐选项")
            normalized["choice"] = choice
        else:
            normalized["score"] = _number(answer.get("score"), 0, len(question["criteria"]) - 1)
        answers[name] = normalized
    if seen != set(questions):
        raise JevError("Decisions 响应缺少题目答案")
    if not answers:
        raise JevError("Decisions 拒绝回答本次判断题")
    return {"answers": answers, "usage": response.get("usage") or {}, "refused": refused}


def ask_openai(state: dict, questions: dict, key: str, model: str, timeout: float) -> dict:
    """仅提交聊天文本；官方 SDK 负责认证、连接及超时/限流重试。"""
    import openai

    payload = {"model": model, "input": json.dumps(state, ensure_ascii=False),
               "questions": convert_questions(questions)}
    try:
        with openai.OpenAI(api_key=key, base_url=OPENAI_BASE, timeout=timeout,
                           max_retries=0) as client:
            response = client.decisions.create(**payload).model_dump()
        return normalize_response(response, questions)
    except (openai.APIError, JevError) as exc:
        _fail(exc, "OpenAI Decisions 判断", key)
