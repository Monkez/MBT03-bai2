import unittest
from unittest.mock import MagicMock

from OrangePiZero2W.connection_led import ConnectionLED


class ConnectionLEDTests(unittest.TestCase):
    def test_boot_wifi_server_and_disconnect_transitions(self):
        send = MagicMock(return_value=True)
        led = ConnectionLED(send)
        led.update(wifi_connected=False)
        led.update(wifi_connected=True)
        led.update(server_connected=True)
        led.update(server_connected=False)
        led.update(wifi_connected=False)
        self.assertEqual([call.args[0] for call in send.call_args_list],
                         ['0LR01', '0LG01', '0LG00', '0LG01', '0LR01'])

    def test_wifi_loss_overrides_stale_connected_socket(self):
        send = MagicMock(return_value=True)
        led = ConnectionLED(send)
        led.update(wifi_connected=True, server_connected=True)
        led.update(wifi_connected=False)
        send.assert_called_with('0LR01')

    def test_stable_state_does_not_spam_uart_or_override_locate(self):
        send = MagicMock(return_value=True)
        led = ConnectionLED(send)
        for _ in range(5):
            led.update(wifi_connected=True, server_connected=True)
        send.assert_called_once_with('0LG00')

    def test_failed_write_is_retried(self):
        send = MagicMock(side_effect=[False, True])
        led = ConnectionLED(send)
        led.update()
        led.update()
        led.update()
        self.assertEqual(send.call_count, 2)
