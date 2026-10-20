"""测试配置独立存放，避免读取或覆盖用户的配置和密钥。"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import settings


class SettingsTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        for name, value in (("_CONFIG", str(Path(directory.name) / "config.json")),
                            ("_CACHE", None), ("_CACHE_PATH", None)):
            patcher = patch.object(settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(settings, "_read_env", return_value="test-key")
        patcher.start()
        self.addCleanup(patcher.stop)
