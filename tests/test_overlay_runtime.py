"""通过真实 Qt 控件验证消息调度、会话切换和候选操作。"""
import os
import queue
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import main
from app import settings
from app.overlay import Overlay


def analysis(text):
    return {'answers': {'intent_thanks': {'score': 3.8}}, 'analyzed_text': text,
            '_messages': [('her', text)], '_options': {'relationship': 'friends', 'context': 10,
            'jev_provider': 'openai', 'jev_model': 'gpt-6-luna'}, '_rev': 0}


class OverlayRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(settings, '_read', side_effect=lambda name, default=None: default))
        self.stack.enter_context(patch.object(settings, '_read_env', return_value='test-key'))
        self.thread = self.stack.enter_context(patch.object(main.threading, 'Thread'))
        main.chats.clear()
        main.state.update(chat='甲', hwnd=None, area=None)
        for name in ('q', 'results', 'draft_results', 'update_result'):
            self.stack.enter_context(patch.object(main, name, queue.Queue(), create=True))
        self.fill = Mock()
        self.overlay = Overlay(on_fill=self.fill, result_of=main.result_for,
                               on_generate=main.on_generate)
        self.addCleanup(self.overlay.win.close)
        self.stack.enter_context(patch.object(main, 'ov', self.overlay, create=True))
        self.stack.enter_context(patch.object(self.overlay, 'after'))
        self.overlay.set_chat('甲')

    def test_new_message_during_drafting_keeps_only_fresh_analysis(self):
        main.chat_of('甲')['result'] = analysis('旧消息')
        self.overlay.show_cached(main.result_for('甲'))
        self.overlay.draftToggle.click()
        self.overlay.generateButton.click()
        self.assertTrue(self.overlay._draft_busy)
        main.q.put(('new', '甲', [('her', None, '谢谢提醒')], (0, 0, 10, 10)))
        main.tick()
        self.assertTrue(self.overlay._busy)
        self.assertFalse(self.overlay.generateButton.isEnabled())
        fresh = analysis('谢谢提醒')
        main.results.put(('ok', fresh, '甲', 1))
        main.draft_results.put(('ok', {**analysis('旧消息'), 'candidates': ['旧候选']}, '甲', 0))
        main.tick()
        self.assertFalse(self.overlay._busy)
        self.assertEqual(self.overlay.latest.text(), '谢谢提醒')
        self.assertEqual(self.overlay.cands, [])
        self.assertTrue(self.overlay.generateButton.isEnabled())
        self.assertEqual(self.overlay.intentPanel.values[0], ('感谢', 95))

    def test_cached_candidates_cannot_fill_another_chat_and_keep_original_index(self):
        main.chat_of('乙')['result'] = {**analysis('乙的消息'), 'candidates': ['A', 'B', 'C'],
                                      'best_index': 1, 'scores': [0.1, 0.8, 0.1]}
        self.overlay._switch_to('乙')
        self.assertTrue(self.overlay.draftContent.isHidden())
        self.assertFalse(self.overlay.generateButton.isEnabled())
        self.overlay.cards[0].fillButton.click()
        self.fill.assert_not_called()
        main.q.put(('chat', '乙'))
        main.tick()
        self.overlay.draftToggle.click()
        self.assertTrue(self.overlay.cards[0].fillButton.isEnabled())
        self.overlay.cards[0].fillButton.click()
        self.fill.assert_called_once_with('B')
