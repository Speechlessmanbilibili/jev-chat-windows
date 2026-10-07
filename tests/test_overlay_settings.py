"""验证设置界面按当前来源选择密钥，测试期间隔离实际配置和用户环境。"""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from app import settings
from app.overlay import Overlay


class OverlaySettingsTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
