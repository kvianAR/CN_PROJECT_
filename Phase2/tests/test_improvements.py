"""Regression checks for deployment guards and reliable evidence handling."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cn


class DeploymentGuards(unittest.TestCase):
    def test_configuration_shape_and_domain_limits(self):
        for invalid in ([], {}, dict(cn.defaults(), domain=123),
                        dict(cn.defaults(), domain='a.' * 123 + 'team.test')):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                cn.validate(invalid)

    def test_loopback_requires_explicit_rehearsal(self):
        config = dict(cn.defaults(), mac1='127.0.0.2')
        with self.assertRaisesRegex(ValueError, 'loopback'):
            cn.validate(config)
        self.assertEqual(cn.validate(config, rehearsal=True)['mac1'], '127.0.0.2')
