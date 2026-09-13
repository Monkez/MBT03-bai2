import unittest
from unittest.mock import patch

from OrangePiZero2W.deploy import _verify_service


class DeployHealthTests(unittest.TestCase):
    def test_stable_process_is_accepted(self):
        with patch('OrangePiZero2W.deploy._run', return_value=(
                'ActiveState=active\nMainPID=12\nNRestarts=2', 0)):
            _verify_service(None, duration=0)

    def test_inactive_or_missing_process_is_rejected(self):
        for state in ('ActiveState=active\nMainPID=0',
                      'ActiveState=activating\nMainPID=12'):
            with self.subTest(state=state), patch('OrangePiZero2W.deploy._run', return_value=(state, 0)):
                with self.assertRaises(RuntimeError):
                    _verify_service(None, duration=0)

    def test_restart_is_rejected_even_when_service_is_active(self):
        states = [(f'ActiveState=active\nMainPID={pid}\nNRestarts=0', 0) for pid in (12, 13)]
        with patch('OrangePiZero2W.deploy._run', side_effect=states), patch('OrangePiZero2W.deploy.time.sleep'):
            with self.assertRaisesRegex(RuntimeError, 'restarted'):
                _verify_service(None)
