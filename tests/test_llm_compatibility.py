"""用真实 SDK 请求结构和明确的服务错误验证兼容分支。"""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import anthropic
import httpx2 as httpx
from google.genai import errors, types

from core import llm
from core.jev_client import JevError


def budget_error():
    return errors.ClientError(400, {"error": {
        "status": "INVALID_ARGUMENT", "message": "thinking_budget=0 is not supported for this model"}})


class LlmCompatibilityTests(unittest.TestCase):
    def test_anthropic_real_sdk_accepts_requests_with_and_without_thinking(self):
        for thinking in (False, True):
            with self.subTest(thinking=thinking):
                requests = []
                def respond(request):
                    requests.append(json.loads(request.content))
                    return httpx.Response(200, json={
                        "id": "msg_audit", "type": "message", "role": "assistant",
                        "model": "audit-model", "content": [{"type": "text", "text": "回复内容"}],
                        "stop_reason": "end_turn", "stop_sequence": None,
                        "usage": {"input_tokens": 1, "output_tokens": 1}})
                client = anthropic.Anthropic(api_key="synthetic-key", max_retries=0,
                    http_client=httpx.Client(transport=httpx.MockTransport(respond)))
                with patch.object(anthropic, "Anthropic", return_value=client):
                    text = llm.chat("anthropic", "", "synthetic-key", "audit-model", "说明", ["你好"],
                                    thinking=thinking)
                self.assertEqual(text, "回复内容")
                self.assertEqual(len(requests), 1)
                self.assertNotIn("temperature", requests[0])
                self.assertEqual("thinking" in requests[0], thinking)
                if thinking:
                    self.assertGreater(requests[0]["max_tokens"], requests[0]["thinking"]["budget_tokens"])
                self.assertTrue(client.is_closed())

    def test_gemini_retries_explicit_budget_error_and_caches_per_endpoint(self):
        client = Mock()
        client.models.generate_content.side_effect = [budget_error(), SimpleNamespace(text="回复"),
                                                      SimpleNamespace(text="回复")]
        with patch.object(llm, "_GEMINI_DEFAULT_THINKING", set()), \
                patch.object(llm, "_gemini_client", return_value=(client, types)):
            for _ in range(2):
                self.assertEqual(llm.chat("gemini", "", "key", "audit-model", "说明", ["你好"]), "回复")
            configs = [call.kwargs["config"] for call in client.models.generate_content.call_args_list]
            self.assertEqual(configs[0].thinking_config.thinking_budget, 0)
            self.assertIsNone(configs[1].thinking_config)
            self.assertIsNone(configs[2].thinking_config)
            self.assertTrue(llm.gemini_uses_default_thinking("", "audit-model"))
            client.models.generate_content.side_effect = None
            client.models.generate_content.return_value = SimpleNamespace(text="回复")
            llm.chat("gemini", "https://other.example", "key", "audit-model", "说明", ["你好"])
            self.assertEqual(client.models.generate_content.call_args.kwargs["config"].thinking_config.thinking_budget, 0)
            self.assertFalse(llm.gemini_uses_default_thinking("https://other.example", "audit-model"))
        self.assertEqual(client.close.call_count, 3)

    def test_gemini_does_not_retry_unrelated_errors(self):
        failures = [
            errors.ClientError(400, {"error": {"message": "INVALID_ARGUMENT: malformed request"}}),
            errors.ClientError(400, {"error": {"message": "temperature must be between 0 and 1"}}),
            errors.ServerError(503, {"error": {"message": "thinking_budget=0 is not supported"}}),
        ]
        for failure in failures:
            with self.subTest(error=str(failure)):
                client = Mock()
                client.models.generate_content.side_effect = failure
                with patch.object(llm, "_GEMINI_DEFAULT_THINKING", set()), \
                        patch.object(llm, "_gemini_client", return_value=(client, types)), self.assertRaises(JevError):
                    llm.chat("gemini", "", "key", "audit-model", "说明", ["你好"])
                client.models.generate_content.assert_called_once()
                client.close.assert_called_once()

    def test_failed_gemini_retry_does_not_cache_compatibility(self):
        client = Mock()
        client.models.generate_content.side_effect = [budget_error(), errors.ServerError(
            503, {"error": {"message": "service unavailable"}})]
        with patch.object(llm, "_GEMINI_DEFAULT_THINKING", set()), \
                patch.object(llm, "_gemini_client", return_value=(client, types)):
            with self.assertRaises(JevError):
                llm.chat("gemini", "", "key", "audit-model", "说明", ["你好"])
            self.assertFalse(llm.gemini_uses_default_thinking("", "audit-model"))
        self.assertEqual(client.models.generate_content.call_count, 2)
        client.close.assert_called_once()
