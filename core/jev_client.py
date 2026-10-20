# -*- coding: utf-8 -*-
"""云端判断和 LM Studio 原生 SystemOne 接口，共用答案格式。"""
from __future__ import annotations

import os
from typing import NoReturn

import httpx

from .providers import (ENV_VARS, JEV_ENV, JEV_PROVIDERS, LEGACY, LMSTUDIO_BASE,
                        OPENROUTER_DECISIONS, OPENROUTER_KEY_URL, TYPESAFE_BASE, key_env)


class JevError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def redact_secrets(text: str, *extra_keys: str) -> str:
    """清除环境中的密钥和本次请求使用的未保存密钥。"""
    if not isinstance(text, str):
        text = str(text)
    keys = {key for key in (*extra_keys, *(os.environ.get(env) for env in ENV_VARS)) if key}
    for key in sorted(keys, key=len, reverse=True):
        text = text.replace(key, "[REDACTED]")
    return text


def _status_of(exc: Exception) -> int | None:
    """各家 SDK 放 HTTP 状态码的属性名不一样：openai/anthropic 是 status_code，
    google-genai 是 code（它的 status 是 'NOT_FOUND' 这种字符串），typesafe 是 status。"""
    for name in ("status_code", "code", "status"):
        value = getattr(exc, name, None)
        if isinstance(value, int):
            return value
    return None


def _fail(exc: Exception, what: str, key: str = "") -> NoReturn:
    """SDK 抛的异常 → 一句人话的 JevError。消息过脱敏，绝不把 key 带出来。"""
    if isinstance(exc, JevError):
        raise JevError(redact_secrets(str(exc), key), exc.status) from None
    status = _status_of(exc)
    hint = {401: "密钥被拒", 403: "没有权限", 404: "模型或地址不对", 422: "请求被拒",
            429: "被限流", 529: "服务过载"}.get(status, "")
    detail = redact_secrets(str(exc), key).strip()[:300]
    head = f"{what} HTTP {status}" if status else f"{what}失败"
    raise JevError(f"{head}: {hint or detail or type(exc).__name__}", status) from None


def _api_key(env: str = JEV_ENV) -> str:
    """读取指定密钥变量；原有判断和起草变量兼容旧名称。"""
    key = ((os.environ.get(env) or "").strip()
           or (os.environ.get(LEGACY.get(env, "")) or "").strip())
    if not key:
        raise JevError(
            f"{env} is not set. Export it in the environment; "
            "do not put the key in a file."
        )
    return key


def _request(method: str, url: str, key: str, timeout: float, **kwargs) -> dict:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.request(method, url, headers=headers, **kwargs)
            if response.is_error:
                raise JevError(f"判断服务 HTTP {response.status_code}: "
                               + redact_secrets(response.text, key)[:300], response.status_code)
            return response.json()
    except (httpx.HTTPError, ValueError, JevError) as exc:
        _fail(exc, "判断请求", key)


def ask(state: dict, questions: dict, timeout: float = 30,
        provider: str = "openai", model: str | None = None,
        base_url: str | None = None) -> dict:
    """每次业务操作只提交一轮题目，本地认证令牌可选。"""
    spec = JEV_PROVIDERS[provider]
    model = model or spec.default
    if provider == "lmstudio":
        key = os.environ.get(key_env(provider, "jev"), "").strip()
        return _request("POST", (base_url or LMSTUDIO_BASE).rstrip("/") + "/v1/systemone",
                        key, timeout, json={"model": model, "state": state, "questions": questions})
    key = _api_key(key_env(provider, "jev"))
    if provider == "openai":
        from .openai_decisions import ask_openai
        return ask_openai(state, questions, key, model, timeout)
    if provider == "typesafe":
        import typesafe_sdk
        try:
            with typesafe_sdk.TypeSafeClient(api_key=key, base_url=TYPESAFE_BASE, model=model,
                    timeout=timeout, retry=typesafe_sdk.RetryPolicy(max_retries=0)) as client:
                result = client.system_one(state, questions, model=model)
        except typesafe_sdk.TypeSafeError as exc:
            _fail(exc, "TypeSafe 判断", key)
        return {"answers": {name: {**answer.model_dump(), "probabilities":
                {str(k): v for k, v in answer.probabilities.items()}}
                for name, answer in result.answers.items()},
                "usage": result.usage.model_dump()}
    return _request("POST", OPENROUTER_DECISIONS, key, timeout,
                    json={"model": model, "state": state, "questions": questions})


def list_models(provider: str, key: str, timeout: float = 10,
                base_url: str | None = None) -> list[str]:
    """列出当前来源的决策模型，不混入普通聊天模型。"""
    if provider == "lmstudio":
        data = _request("GET", (base_url or LMSTUDIO_BASE).rstrip("/") + "/api/v1/models", key, timeout)
        return sorted({name for m in data["models"] if m["type"] == "decision"
                       for name in ([i["id"] for i in m.get("loaded_instances", [])] or [m["key"]])})
    if provider == "openai":
        import openai
        try:
            with openai.OpenAI(api_key=key, base_url="https://api.openai.com/v1",
                               timeout=timeout, max_retries=0) as client:
                client.models.retrieve(JEV_PROVIDERS[provider].default)
        except openai.APIError as exc:
            _fail(exc, "获取 Decisions 模型", key)
        return [JEV_PROVIDERS[provider].default]
    if provider == "typesafe":
        import typesafe_sdk
        try:
            with typesafe_sdk.TypeSafeClient(api_key=key, base_url=TYPESAFE_BASE, timeout=timeout,
                    retry=typesafe_sdk.RetryPolicy(max_retries=0)) as client:
                return sorted({m.name for m in client.models.list().models})
        except typesafe_sdk.TypeSafeError as exc:
            _fail(exc, "获取决策模型", key)
    _request("GET", OPENROUTER_KEY_URL, key, timeout)
    return ["~typesafe/jev-latest", "typesafe/jev-1.13"]
