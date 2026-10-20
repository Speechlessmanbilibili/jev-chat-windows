# -*- coding: utf-8 -*-
"""三种接口协议的薄适配层，一律走官方 SDK：
OpenAI Chat Completions（`openai`）/ Anthropic Messages（`anthropic`）/ Gemini（`google-genai`）。

只做两件事：chat() 发一轮对话拿文本，list_models() 列模型。base_url / key / model 全由调用方传，
这里不认识任何「来源」——来源表在 core/providers.py。出错一律转成 JevError，消息过脱敏。

SDK 都在函数里 import：桌面端一次只用到其中一家，启动时没必要把另外两家的依赖也拖起来。
"""
from __future__ import annotations
from contextlib import closing
import re
from threading import Lock

from .jev_client import JevError, _fail

# Anthropic 开思考模式时的预算：起草三句话用不上更多；max_tokens 必须比它大，下面会兜住
_THINK_BUDGET = 2048
_GEMINI_DEFAULT_THINKING: set[tuple[str, str]] = set()
_GEMINI_THINKING_LOCK = Lock()
GEMINI_DEFAULT_THINKING_NOTICE = "这个模型不支持当前的思考设置，本次回复使用了模型默认设置。"


def _gemini_key(base_url, model):
    return ((base_url or "").rstrip("/"), model.removeprefix("models/"))


def gemini_uses_default_thinking(base_url, model):
    """按服务地址和模型记录兼容结果，避免不同代理共用能力判断。"""
    with _GEMINI_THINKING_LOCK:
        return _gemini_key(base_url, model) in _GEMINI_DEFAULT_THINKING


def _zero_thinking_rejected(exc):
    """只处理明确指向思考配置的 400，其他参数或服务错误直接交给调用方。"""
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if str(status) != "400":
        return False
    detail = str(getattr(exc, "message", None) or exc).lower()
    if not re.search(r"thinking[_.\s-]*(?:budget|config)", detail):
        return False
    unsupported = re.search(
        r"unsupported|not supported|does not support|cannot|can't|disable|minimum|positive|at least|greater than|between",
        detail)
    invalid_zero = re.search(r"\b(?:0|zero)\b", detail) and re.search(r"invalid|not allowed|must", detail)
    return bool(unsupported or invalid_zero)


def _turns(user_turns: list[str], assistant: str = "assistant") -> list[dict]:
    """[user, assistant, user, …] 交替；第一条和最后一条都是用户。"""
    return [{"role": assistant if i % 2 else "user", "content": text}
            for i, text in enumerate(user_turns)]


def chat(protocol: str, base_url: str | None, api_key: str, model: str, system: str,
         user_turns: list[str], *, temperature: float = 1.0, max_tokens: int = 400,
         thinking: bool = False, extra_body: dict | None = None,
         headers: dict | None = None, timeout: float = 30) -> str:
    """发一轮对话，返回模型输出的纯文本。

    user_turns: 用户/助手交替的文本，奇数条，首尾都是用户说的。
    thinking: 思考模式。OpenAI 协议没有统一字段，各家自己的开关由调用方经 extra_body 带进来；
              anthropic / gemini 是协议自带的参数，这里直接处理。
    """
    if protocol == "anthropic":
        return _anthropic(base_url, api_key, model, system, user_turns,
                          temperature, max_tokens, thinking, timeout)
    if protocol == "gemini":
        return _gemini(base_url, api_key, model, system, user_turns,
                       temperature, max_tokens, thinking, timeout)
    return _openai(base_url, api_key, model, system, user_turns,
                   temperature, max_tokens, thinking, extra_body, headers, timeout)


def _openai(base_url, api_key, model, system, user_turns, temperature, max_tokens,
            thinking, extra_body, headers, timeout) -> str:
    import openai

    options = {"temperature": temperature, "max_tokens": max_tokens}
    if model == "gpt-6-luna" or model.startswith("gpt-6-luna-"):
        # Luna 默认会推理；开启时省略采样温度，关闭时显式指定 none。
        options = {"max_completion_tokens": max_tokens,
                   "reasoning_effort": "medium" if thinking else "none"}
        if not thinking:
            options["temperature"] = temperature
    try:
        with closing(openai.OpenAI(base_url=base_url or None, api_key=api_key,
                               timeout=timeout, max_retries=0,
                               **({"default_headers": headers} if headers else {}))) as client:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}] + _turns(user_turns),
                **options, stream=False,
                **({"extra_body": extra_body} if extra_body else {}))
        if not resp.choices:
            raise JevError("起草服务未返回候选内容，请重新生成。")
        choice = resp.choices[0]
        if getattr(choice, "finish_reason", None) == "length":
            raise JevError("起草输出已达到长度上限，请关闭思考模式或更换模型后重试。")
        if getattr(choice.message, "refusal", None):
            raise JevError("起草服务未接受本次请求，请调整上下文后重试。")
        return choice.message.content or ""
    except (openai.APIError, JevError) as exc:
        _fail(exc, "起草", api_key)


def _anthropic(base_url, api_key, model, system, user_turns, temperature, max_tokens,
               thinking, timeout) -> str:
    import anthropic

    extra = {}
    if thinking:
        extra["thinking"] = {"type": "enabled", "budget_tokens": _THINK_BUDGET}
        max_tokens = max(max_tokens, _THINK_BUDGET + 1024)  # max_tokens 得装得下思考 + 正文
    try:
        with closing(anthropic.Anthropic(base_url=base_url or None, api_key=api_key,
                                         timeout=timeout, max_retries=0)) as client:
            message = client.messages.create(model=model, system=system,
                                             messages=_turns(user_turns), max_tokens=max_tokens,
                                             **extra)
        if getattr(message, "stop_reason", None) == "max_tokens":
            raise JevError("起草输出已达到长度上限，请关闭思考模式或更换模型后重试。")
        return "".join(b.text for b in message.content if getattr(b, "type", "") == "text")
    except (anthropic.APIError, JevError) as exc:
        _fail(exc, "起草", api_key)


def _gemini_client(base_url, api_key, timeout):
    from google import genai
    from google.genai import types

    # HttpOptions.timeout 的单位是毫秒，不是秒
    options = types.HttpOptions(timeout=int(timeout * 1000))
    if base_url:
        options.base_url = base_url
    return genai.Client(api_key=api_key, http_options=options), types


def _gemini(base_url, api_key, model, system, user_turns, temperature, max_tokens,
            thinking, timeout) -> str:
    from google.genai.errors import APIError
    from httpx2 import HTTPError

    try:
        client, types = _gemini_client(base_url, api_key, timeout)
        config_args = dict(system_instruction=system, temperature=temperature, max_output_tokens=max_tokens)
        disable = not thinking and not gemini_uses_default_thinking(base_url, model)
        config = types.GenerateContentConfig(**config_args,
            **({"thinking_config": types.ThinkingConfig(thinking_budget=0)} if disable else {}))
        contents = [types.Content(role=m["role"], parts=[types.Part(text=m["content"])])
                    for m in _turns(user_turns, assistant="model")]  # Gemini 那边助手叫 model
        with closing(client):
            try:
                resp = client.models.generate_content(model=model, contents=contents, config=config)
            except APIError as exc:
                if not disable or not _zero_thinking_rejected(exc):
                    raise
                resp = client.models.generate_content(model=model, contents=contents,
                                                      config=types.GenerateContentConfig(**config_args))
                # 兼容请求成功后才缓存；失败时下次仍按用户选择尝试。
                with _GEMINI_THINKING_LOCK:
                    _GEMINI_DEFAULT_THINKING.add(_gemini_key(base_url, model))
        return resp.text or ""
    except (APIError, HTTPError, JevError) as exc:
        _fail(exc, "起草", api_key)


def list_models(protocol: str, base_url: str | None, api_key: str,
                timeout: float = 10, headers: dict | None = None) -> list[str]:
    """某个地址上能用的模型 id，去重排序。失败抛 JevError，消息直接显示在设置页上。"""
    if protocol == "anthropic":
        import anthropic

        try:
            with closing(anthropic.Anthropic(base_url=base_url or None, api_key=api_key,
                                             timeout=timeout, max_retries=0)) as client:
                ids = [m.id for m in client.models.list()]
        except anthropic.APIError as exc:
            _fail(exc, "取模型列表", api_key)
    elif protocol == "gemini":
        from google.genai.errors import APIError
        from httpx2 import HTTPError

        try:
            client, _ = _gemini_client(base_url, api_key, timeout)
            # 名字带 models/ 前缀，调用时用不上，剥掉
            with closing(client):
                ids = [str(m.name).removeprefix("models/") for m in client.models.list() if m.name]
        except (APIError, HTTPError) as exc:
            _fail(exc, "取模型列表", api_key)
    else:
        import openai

        try:
            with closing(openai.OpenAI(base_url=base_url or None, api_key=api_key,
                                   timeout=timeout, max_retries=0,
                                   **({"default_headers": headers} if headers else {}))) as client:
                ids = [m.id for m in client.models.list()]
        except openai.APIError as exc:
            _fail(exc, "取模型列表", api_key)
    return sorted(set(ids))
