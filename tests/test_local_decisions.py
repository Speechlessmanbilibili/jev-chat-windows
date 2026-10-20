"""本地决策接口、无推荐候选及配置失败的行为验证。"""
import json
import os
from pathlib import Path
from unittest.mock import patch

import httpx
import httpx2
import typesafe_sdk

from app import settings
from core import engine, jev_client
from core.questions import build_state
from support import SettingsTestCase


class LocalDecisionsTests(SettingsTestCase):
    def test_systemone_contract_optional_auth_and_model_filter(self):
        requests = []
        state = build_state([('her', '明天下午三点见')], 'friends')
        question = {'time': {'type': 'score', 'instructions': '是否确认时间', 'criteria': ['否', '是']}}
        def handler(request):
            requests.append(request)
            if request.method == 'GET':
                return httpx.Response(200, json={'models': [
                    {'type': 'decision', 'key': 'vllm-d3-mini', 'loaded_instances': [{'id': 'd3-mini'}]},
                    {'type': 'llm', 'key': 'chat'}]})
            return httpx.Response(200, json={'answers': {'time': {'type': 'score', 'score': 1}}})
        factory = httpx.Client
        with patch.object(jev_client.httpx, 'Client', side_effect=lambda **kw:
                factory(**kw, transport=httpx.MockTransport(handler))), \
                patch.dict(os.environ, {'LMSTUDIO_API_TOKEN': ''}):
            result = jev_client.ask(state, question, provider='lmstudio', base_url='http://localhost:1234/')
            self.assertEqual(result['answers']['time']['score'], 1)
            self.assertEqual(str(requests[-1].url), 'http://localhost:1234/v1/systemone')
            self.assertNotIn('authorization', requests[-1].headers)
            self.assertEqual(json.loads(requests[-1].content)['state'], state)
            os.environ['LMSTUDIO_API_TOKEN'] = 'local-token'
            self.assertEqual(jev_client.list_models('lmstudio', 'local-token'), ['d3-mini'])
            self.assertEqual(requests[-1].headers['authorization'], 'Bearer local-token')

    def test_typesafe_real_sdk_preserves_numeric_score_keys(self):
        question = {'score': {'type': 'score', 'instructions': '测试', 'criteria': ['低', '高']}}
        requests = []
        def handler(request):
            requests.append(request)
            return httpx2.Response(200, json={'model': 'jev-latest', 'usage': {}, 'answers': {
                'score': {'type': 'score', 'score': 0.8, 'confidence': 0.8,
                          'legend': {'0': '低', '1': '高'}, 'probabilities': {'0': 0.2, '1': 0.8}}}})
        factory = typesafe_sdk.TypeSafeClient
        with patch('typesafe_sdk.TypeSafeClient', side_effect=lambda **kw:
                factory(**kw, transport=httpx2.MockTransport(handler))), \
                patch.dict(os.environ, {'JEV_API_KEY': 'judge-key'}):
            result = jev_client.ask({}, question, provider='typesafe')
        self.assertEqual(result['answers']['score']['probabilities'], {'0': 0.2, '1': 0.8})
        self.assertEqual(len(requests), 1)

    def test_ranking_failure_and_single_candidate_have_no_recommendation(self):
        analysis = {'state': {}, 'judge': {}, 'answers': {}}
        for candidates in (['甲'], ['甲', '乙', '丙']):
            with self.subTest(candidates=candidates), \
                    patch.object(engine, 'draft_candidates', return_value=candidates) as draft, \
                    patch.object(engine, 'ask', side_effect=jev_client.JevError('排序离线')) as ask:
                result = engine.generate_replies(analysis)
                self.assertIsNone(result['best_index'])
                self.assertEqual(result['scores'], [None] * len(candidates))
                self.assertEqual(result['candidates'], candidates)
                draft.assert_called_once()
                self.assertEqual(ask.call_count, int(len(candidates) > 1))
                if len(candidates) > 1:
                    self.assertIn('排序未完成', result['draft_notice'])

    def test_config_load_cache_and_error_keep_original(self):
        config = Path(settings._CONFIG)
        config.write_text('{"style":"原文"}', encoding='utf-8')
        self.assertEqual(settings.style(), '原文')
        config.write_text('{损坏', encoding='utf-8')
        self.assertEqual(settings.style(), '原文')
        with self.assertRaises(settings.ConfigError):
            settings.load(reload=True)
        self.assertEqual(config.read_text(encoding='utf-8'), '{损坏')
        self.assertEqual(settings.style(), '原文')
        for value in ('[]', 'null'):
            config.write_text(value, encoding='utf-8')
            with self.assertRaises(settings.ConfigError):
                settings.load(reload=True)
