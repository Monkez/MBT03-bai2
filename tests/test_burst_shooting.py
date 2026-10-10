import sys
import struct
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from test_connection_timeout import _make_client_harness, _make_server_harness
from PyQt5.QtCore import Qt

with patch.object(sys, "path", [str(Path(__file__).resolve().parents[1] / "assets" / "OrangePiZero2W"), *sys.path]):
    from OrangePiZero2W.r_client import MBT03HardwareClient


class BurstShootingTests(unittest.TestCase):
    def hardware_for_chunks(self, chunks):
        hardware = MBT03HardwareClient.__new__(MBT03HardwareClient)
        hardware.running = True
        hardware.core = MagicMock()
        hardware._last_battery_percent = None
        hardware.serial_port = MagicMock(is_open=True)
        pending = iter(chunks)

        def read(_size):
            try:
                return next(pending)
            except StopIteration:
                hardware.running = False
                return b""

        hardware.serial_port.read.side_effect = read
        hardware.shoot = MagicMock()
        return hardware

    def test_uart_preserves_every_trigger_in_one_read(self):
        hardware = self.hardware_for_chunks([b"0S000\n0S000\n0S000\n"])
        hardware._uart_listen_loop()
        self.assertEqual(hardware.shoot.call_count, 3)

    def test_uart_preserves_partial_trigger_after_another_shot(self):
        hardware = self.hardware_for_chunks([b"0S000\n0", b"S000\n0S", b"000\n"])
        hardware._uart_listen_loop()
        self.assertEqual(hardware.shoot.call_count, 3)

    def test_uart_preserves_shots_mixed_with_battery_and_errors(self):
        hardware = self.hardware_for_chunks([b"BAT-086\n0S000\n0E100\n0S000\n0E2", b"00\n"])
        hardware._uart_listen_loop()
        self.assertEqual(hardware.shoot.call_count, 2)
        hardware.core.set_battery_percent.assert_called_with(86)
        self.assertEqual([item.args[0] for item in hardware.core.send_data.call_args_list],
                         [{"UART_RX_DEBUG": "E1"}, {"UART_RX_DEBUG": "E2"}])

    def test_hardware_burst_queues_an_image_for_every_parsed_trigger(self):
        client = _make_client_harness()
        hardware = self.hardware_for_chunks([b"0S000\n0S000\n0S000\n"])
        hardware.core = client
        hardware._frame_lock = threading.Lock()
        hardware._frame_buffer = [client._shoot_frame]
        hardware.shoot = lambda: MBT03HardwareClient.shoot(hardware)
        with patch("server_client.client_core.time.time", return_value=100.0):
            hardware._uart_listen_loop()
        self.assertEqual(len(client._shoot_pool.jobs), 3)
        self.assertEqual(client._priority_control_send_queue.qsize(), 3)

    def test_interactive_shoot_still_debounces_duplicate_calls(self):
        client = _make_client_harness()
        with patch("server_client.client_core.time.time", return_value=100.0):
            self.assertTrue(client.shoot())
            self.assertFalse(client.shoot())
        self.assertEqual(len(client._shoot_pool.jobs), 1)

    def test_network_batching_does_not_discard_distinct_shoot_notifications(self):
        server = _make_server_harness()
        received = []
        server.shoot_notify_signal.connect(received.append, type=Qt.DirectConnection)
        timestamps = [100.0, 100.1, 100.2]
        with patch("server_client.server_core.time.time", return_value=102.0):
            for timestamp in timestamps:
                server._handle_shoot_notify(b'old-identity', struct.pack('!d', timestamp))
        self.assertEqual(received, timestamps)


if __name__ == "__main__":
    unittest.main()
