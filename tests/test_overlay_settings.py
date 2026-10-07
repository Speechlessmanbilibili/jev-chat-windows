"""验证设置界面按当前来源选择密钥，测试期间隔离实际配置和用户环境。"""
import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from app import settings
from app.overlay import Overlay


class OverlaySettingsTests(unittest.TestCase):
    def test_score_panels_and_expansion_do_not_generate(self):
        generate = Mock()
        with patch.object(settings, '_read', side_effect=lambda name, default=None: default), \
                patch.object(settings, '_read_env', return_value=''):
            overlay = Overlay(on_fill=lambda text: None, on_generate=generate)
            try:
                overlay.set_chat('测试会话')
                overlay.show({'answers': {'intent_thanks': {'score': 3.5}}})
                self.assertTrue(overlay.draftContent.isHidden())
                self.assertTrue(overlay.draftSettings.isHidden())
                self.assertEqual(len(overlay.intentPanel.rows), 4)
                self.assertEqual(len(overlay.tonePanel.rows), 4)
                overlay.intentPanel.toggle.click()
                self.assertEqual(len(overlay.intentPanel.rows), 18)
                overlay.tonePanel.toggle.click()
                self.assertEqual(len(overlay.tonePanel.rows), 10)
                overlay.draftToggle.click()
                generate.assert_not_called()
                overlay.generateButton.click()
                generate.assert_called_once_with('测试会话')
                overlay.set_draft_busy(True)
                self.assertFalse(overlay.generateButton.isEnabled())
                self.assertFalse(overlay.intentPanel.isHidden())
                overlay.set_draft_busy(False, '测试起草失败')
                self.assertEqual(overlay.draftFeedback.text(), '测试起草失败')
                self.assertFalse(overlay.intentPanel.isHidden())
                overlay.invalidate_replies()
                overlay.generateButton.click()
                generate.assert_called_once()
                overlay.set_busy(True)
                overlay.show_cached(None)
                self.assertFalse(overlay._busy)
                self.assertIsNone(overlay._result)
                self.assertFalse(overlay.generateButton.isEnabled())
            finally:
                overlay.win.close()

    def test_only_judgment_key_is_needed_to_save(self):
        with patch.object(settings, '_read', side_effect=lambda name, default=None: default), \
                patch.object(settings, '_read_env', side_effect=lambda n: 'official' if n == 'OPENAI_API_KEY' else ''), \
                patch.object(settings, 'save') as save:
            overlay = Overlay(on_fill=lambda text: None)
            try:
                overlay._save()
                save.assert_called_once()
                self.assertIsNone(save.call_args.kwargs['llm_key_text'])
            finally:
                overlay.win.close()

    def test_provider_switch_and_draft_isolation(self):
        keys = {'OPENAI_API_KEY': 'official', 'JEV_API_KEY': 'judge', 'LLM_API_KEY': 'draft'}
        with patch.object(settings, '_read', side_effect=lambda name, default=None: default), \
                patch.object(settings, '_read_env', side_effect=lambda name: keys.get(name, '')):
            overlay = Overlay(on_fill=lambda text: None)
            try:
                self.assertEqual(overlay._provider_of(overlay.jev), 'openai')
                self.assertEqual(overlay.jev.modelBox.text(), 'gpt-6-luna')
                self.assertEqual(overlay.jev.stored_key(), 'official')
                overlay.jev.keyEdit.setText('unsaved-official')
                overlay.jev.providerBox.setCurrentIndex(overlay.jev.ids.index('openrouter'))
                self.assertEqual(overlay.jev.stored_key(), 'judge')
                self.assertEqual(overlay.jev.keyEdit.text(), '')
                self.assertEqual(overlay.jev.modelBox.text(), 'typesafe/jev-1.13')
                overlay.jev.providerBox.setCurrentIndex(overlay.jev.ids.index('openai'))
                self.assertEqual(overlay.jev.stored_key(), 'official')
                overlay.draft.providerBox.setCurrentIndex(overlay.draft.ids.index('openai'))
                self.assertEqual(overlay.draft.stored_key(), 'draft')
                keys.pop('LLM_API_KEY')
                self.assertEqual(overlay.draft.stored_key(), '')
            finally:
                overlay.win.close()

    def test_incomplete_optional_draft_does_not_block_judgment_settings(self):
        with patch.object(settings, '_read', side_effect=lambda name, default=None: default), \
                patch.object(settings, '_read_env', return_value='test-key'), \
                patch.object(settings, 'save') as save:
            overlay = Overlay(on_fill=lambda text: None)
            try:
                overlay.draft.providerBox.setCurrentIndex(overlay.draft.ids.index('custom_openai'))
                overlay.baseEdit.clear()
                overlay.draft.modelBox.clear()
                overlay._save()
                save.assert_called_once()
            finally:
                overlay.win.close()


if __name__ == '__main__':
    unittest.main()
