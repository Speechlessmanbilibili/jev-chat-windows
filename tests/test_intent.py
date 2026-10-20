"""程度展示、分析/起草隔离和部分拒答的回归测试。"""
import json
import unittest
from unittest.mock import patch

from core import engine
from core import draft
from core.intent import INTENT_QUESTIONS, percentage, ratings
from core.jev_client import JevError
from core.openai_decisions import normalize_response


class IntentTests(unittest.TestCase):
    def test_fractional_scores_and_invalid_values(self):
        for score, expected in ((0, 0), (1, 25), (2, 50), (3, 75), (4, 100),
                                (3.42, 86), (0.02, 1), (1.98, 50)):
            self.assertEqual(percentage(score), expected)
        for value in (None, True, '3', -0.1, 4.01, float('nan'), float('inf')):
            self.assertIsNone(percentage(value))

    def test_multiple_labels_stay_independent_and_missing_is_unknown(self):
        answers = {'intent_reminder': {'score': 3.8}, 'intent_thanks': {'score': 3.4},
                   'intent_refusal': {'score': 0}}
        values = ratings(answers, 'intent')
        self.assertEqual(values[:3], [('提醒', 95), ('感谢', 85), ('拒绝', 0)])
        self.assertGreater(sum(v for _, v in values if v is not None), 100)
        self.assertIsNone(values[-1][1])



    def test_partial_refusal_is_visible_as_unknown(self):
        questions = {name: INTENT_QUESTIONS[name] for name in ('intent_thanks', 'tone_calm')}
        response = {'answers': [{'name': 'intent_thanks', 'type': 'score', 'score': 3.5,
                                 'confidence': 0.8, 'probabilities': []},
                                {'name': 'tone_calm', 'type': 'refusal'}]}
        result = normalize_response(response, questions)
        self.assertEqual(ratings(result['answers'], 'intent')[0], ('感谢', 88))
        self.assertTrue(all(value is None for _, value in ratings(result['answers'], 'tone')))



    def test_target_outside_context_fails_before_request(self):
        with patch.object(engine, 'ask') as ask, self.assertRaises(JevError):
            engine.analyze([('her', '请明天提交', '小李'), ('her', '你好', '小王')],
                           'colleagues', reply_to='小李', context=1)
        ask.assert_not_called()

    def test_reply_target_is_shared_by_analysis_drafting_and_ranking(self):
        messages = [('her', '晚饭去哪里吃', '小林'), ('her', '明天几点集合', '小林'),
                    ('her', '我去买水', '小周')]
        for reply_to, expected in ((None, '我去买水'), ('小林', '明天几点集合')):
            with self.subTest(reply_to=reply_to), \
                    patch.object(engine, 'ask', return_value={'answers': {}}) as ask, \
                    patch.object(draft, '_api_key', return_value='synthetic-key'), \
                    patch.object(draft, 'chat', return_value='["我先核对一下时间", "明天下午两点可以吗", "到地铁站后联系你"]') as generate:
                analysis = engine.analyze(messages, 'friends', reply_to=reply_to)
                engine.generate_replies(analysis)
                target = analysis['reply_target']
                self.assertEqual(target['text'], expected)
                self.assertEqual(ask.call_args_list[0].args[0]['chat']['reply_target'], target)
                self.assertEqual(ask.call_args_list[1].args[0]['chat']['reply_target'], target)
                prompt = generate.call_args.args[5][0]
                embedded = json.loads(prompt.split('聊天记录和本次回复目标：\n')[1])
                self.assertEqual(embedded, analysis['state'])
                self.assertIn('chat.reply_target', ask.call_args_list[1].args[1]['best_reply']['instructions'])
