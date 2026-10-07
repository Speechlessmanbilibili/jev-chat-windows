"""验证 Decisions 的 HTTP 契约、答案转换、密钥隔离和引擎集成。"""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import openai

from app import settings
from core import engine
from core.jev_client import JevError, _api_key, ask, list_models, redact_secrets
from core.openai_decisions import convert_questions, normalize_response
from core.providers import key_env
from core.questions import JUDGE_QUESTIONS, build_rank_question, build_state


def response_for(questions):
    answers = []
    for name, question in questions.items():
        kind = question['type']
        if kind == 'noul':
            answer = dict(type='predicate', probability=0.9)
        elif kind == 'choice':
            values = list(question['criteria'])
            chosen = 'reply_b' if name == 'best_reply' else values[0]
            answer = dict(type='choice', choice=chosen, confidence=0.8,
                          probabilities=[dict(value=v, probability=0.8 if v == chosen else 0.1)
                                         for v in values])
        else:
            answer = dict(type='score', score=4.2, confidence=0.7,
                          probabilities=[dict(value=4, label='4', probability=0.8),
                                         dict(value=5, label='5', probability=0.2)])
        answers.append(dict(name=name, **answer))
    return dict(answers=answers, model='gpt-6-luna', usage=dict(input_tokens=20, output_tokens=0))


class DecisionsTests(unittest.TestCase):
    def setUp(self):
        self.state = build_state([('her', '明天下午三点开会')], 'colleagues')
        self.questions = dict(JUDGE_QUESTIONS, **build_rank_question(['甲', '乙', '丙']))

    def test_question_conversion_preserves_criteria_and_order(self):
        original = copy.deepcopy(self.questions)
        converted = convert_questions(self.questions)
        self.assertEqual([q['name'] for q in converted], list(self.questions))
        predicate = converted[0]
        self.assertEqual(predicate['type'], 'predicate')
        for criterion in original['literal_question']['criteria'].values():
            self.assertIn(criterion, predicate['instructions'])
        levels = next(q['levels'] for q in converted if q['type'] == 'score')
        self.assertEqual([l['label'] for l in levels], list(map(str, range(10))))
        self.assertEqual(converted[-1]['choices'][1], dict(value='reply_b', description='乙'))
        self.assertEqual(self.questions, original)

    def test_response_mapping_by_name_and_refusal(self):
        response = response_for(self.questions)
        response['answers'].reverse()
        result = normalize_response(response, self.questions)
        self.assertEqual(result['answers']['literal_question']['noul'], 0.9)
        self.assertEqual(result['answers']['danger_level']['score'], 4.2)
        self.assertEqual(result['answers']['danger_level']['probabilities']['4'], 0.8)
        self.assertEqual(result['answers']['best_reply']['probabilities']['reply_b'], 0.8)
        response['answers'][0] = dict(type='refusal', name='best_reply')
        result = normalize_response(response, self.questions)
        self.assertNotIn('best_reply', result['answers'])
        self.assertEqual(result['refused'], ['best_reply'])

    def test_invalid_and_missing_answers_fail(self):
        for mutation in ('missing', 'duplicate', 'unknown', 'invalid_number', 'invalid_choice'):
            response = response_for(self.questions)
            if mutation == 'missing':
                response['answers'].pop()
            elif mutation == 'duplicate':
                response['answers'].append(response['answers'][0])
            elif mutation == 'unknown':
                response['answers'][0]['name'] = 'unknown'
            elif mutation == 'invalid_number':
                response['answers'][0]['probability'] = float('nan')
            else:
                response['answers'][-1]['choice'] = 'not_a_candidate'
            with self.subTest(mutation=mutation), self.assertRaises(JevError):
                normalize_response(response, self.questions)
        response = dict(answers=[dict(name=n, type='refusal') for n in self.questions])
        with self.assertRaises(JevError):
            normalize_response(response, self.questions)

    def test_sdk_http_contract_and_retry(self):
        requests = []
        def handler(request):
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(429, headers={'retry-after-ms': '1'},
                                      json={'error': {'message': 'limited'}})
            return httpx.Response(200, json=response_for(self.questions))
        factory = openai.OpenAI
        def client(**kwargs):
            return factory(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'official-test', 'JEV_API_KEY': 'other-test'}), \
                patch('openai.OpenAI', side_effect=client):
            result = ask(self.state, self.questions)
        self.assertEqual(len(requests), 2)
        self.assertEqual(str(requests[-1].url), 'https://api.openai.com/v1/decisions')
        self.assertEqual(requests[-1].headers['authorization'], 'Bearer official-test')
        body = json.loads(requests[-1].content)
        self.assertEqual(json.loads(body['input']), self.state)
        self.assertIsInstance(body['questions'], list)
        self.assertNotIn('state', body)
        self.assertEqual(result['answers']['best_reply']['choice'], 'reply_b')

    def test_http_error_is_redacted(self):
        factory = openai.OpenAI
        def handler(request):
            return httpx.Response(401, json={'error': {'message': 'official-test rejected'}})
        def client(**kwargs):
            return factory(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'official-test'}), \
                patch('openai.OpenAI', side_effect=client), self.assertRaises(JevError) as caught:
            ask(self.state, self.questions)
        self.assertEqual(caught.exception.status, 401)
        self.assertNotIn('official-test', str(caught.exception))

    def test_only_decisions_models_are_offered(self):
        factory = openai.OpenAI
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={'id': 'gpt-6-luna', 'object': 'model',
                                           'created': 0, 'owned_by': 'openai'})
        def client(**kwargs):
            return factory(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        with patch('openai.OpenAI', side_effect=client):
            self.assertEqual(list_models('openai', 'test-key'), ['gpt-6-luna'])
        self.assertEqual(requests[0].url.path, '/v1/models/gpt-6-luna')

    def test_engine_uses_converted_judgment_and_ranking(self):
        calls = []
        def fake_ask(state, questions, **kwargs):
            calls.append(questions)
            return normalize_response(response_for(questions), questions)
        with patch.object(engine, 'ask', side_effect=fake_ask), \
                patch.object(engine, 'draft_candidates', return_value=['甲', '乙', '丙']) as draft:
            result = engine.analyze([('her', '明天开会')], 'colleagues')
        self.assertEqual(len(calls), 2)
        self.assertEqual(list(calls[1]), ['best_reply'])
        self.assertEqual(result['best_index'], 1)
        self.assertEqual(result['scores'], [0.1, 0.8, 0.1])
        self.assertTrue(draft.call_args.kwargs['guidance'])


class KeySettingsTests(unittest.TestCase):
    def test_provider_key_isolation_and_no_draft_fallback(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'official', 'JEV_API_KEY': 'judge',
                                     'LLM_API_KEY': 'draft'}, clear=True), \
                patch.object(settings, '_read_env', side_effect=lambda n: os.environ.get(n, '')):
            self.assertEqual(settings.jev_key('openai'), 'official')
            self.assertEqual(settings.jev_key('openrouter'), 'judge')
            for provider in ('openai', 'deepseek', 'custom_openai'):
                self.assertEqual(settings.llm_key(provider), 'draft')
            self.assertEqual(redact_secrets('official judge draft'), '[REDACTED] [REDACTED] [REDACTED]')
            os.environ.pop('LLM_API_KEY')
            with self.assertRaises(JevError):
                _api_key(key_env('openai', 'draft'))
            self.assertEqual(settings.llm_key('openai'), '')

    def test_save_does_not_copy_official_key_to_draft(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(settings, '_CONFIG', str(Path(directory) / 'config.json')), \
                patch.object(settings, '_read_env', side_effect=lambda n: {'OPENAI_API_KEY': 'official'}.get(n, '')), \
                patch.object(settings, '_set_key') as write_key, patch.object(settings, '_notify_env'):
            settings.save(jev_provider_text='openai', draft_provider_text='openai')
            write_key.assert_not_called()
            self.assertNotIn('official', Path(settings._CONFIG).read_text(encoding='utf-8'))
            settings.save(jev_key_text='new-judge', llm_key_text='new-draft')
            self.assertEqual(write_key.call_args_list[0].args, ('OPENAI_API_KEY', 'new-judge'))
            self.assertEqual(write_key.call_args_list[1].args, ('LLM_API_KEY', 'new-draft'))


if __name__ == '__main__':
    unittest.main()
