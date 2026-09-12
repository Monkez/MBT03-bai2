import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from gui.main_window import MainWindow
from gui.option_window import OptionWindow
from gui.client_widget import ClientWidget
from gui.setting_window import SettingWindow


class FakeButton:
    def __init__(self):
        self.text = ""

    def setText(self, text):
        self.text = text


class ShootingScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_start_command_is_sent_to_every_server(self):
        servers = [MagicMock(), MagicMock()]
        window = type("WindowState", (), {})()
        window.servers = servers
        window.START_UART_COMMAND = MainWindow.START_UART_COMMAND

        MainWindow._send_start_uart_command(window)

        self.assertEqual(MainWindow.START_UART_COMMAND, "0Q000\n")
        for server in servers:
            server.send_uart_command.assert_called_once_with("0Q000\n")

    def test_q0_display_keeps_live_stream_and_overlays_previous_shot(self):
        live_frame = np.full((120, 160, 3), 10, dtype=np.uint8)
        frozen_shot = np.full((120, 160, 3), 200, dtype=np.uint8)
        image_sink = MagicMock()
        window = SimpleNamespace(
            _current_stream_frame=live_frame,
            _q0_capture_frame=frozen_shot,
            _adjusting_camera=False,
            Q0=True,
            Q0_values=[(0.5, 0.5)],
            monkezusbcamera=image_sink,
        )

        SettingWindow._update_frame(window)

        displayed = image_sink.set_image.call_args.args[0]
        self.assertTrue(np.array_equal(displayed[0, 0], live_frame[0, 0]))
        self.assertFalse(np.array_equal(displayed, frozen_shot))
        self.assertFalse(np.array_equal(displayed, live_frame))

    def test_q0_display_matches_wireless_shot_progress(self):
        live_frame = np.zeros((120, 200, 3), dtype=np.uint8)
        image_sink = MagicMock()
        window = SimpleNamespace(
            _current_stream_frame=live_frame,
            _adjusting_camera=False,
            Q0=True,
            Q0_SAMPLE_COUNT=3,
            Q0_values=[(0.5, 0.5)],
            monkezusbcamera=image_sink,
        )

        SettingWindow._update_frame(window)

        displayed = image_sink.set_image.call_args.args[0]
        # Hai chấm xanh còn lại giống chỉ báo tiến độ của MBT03-wireless.
        self.assertTrue(np.array_equal(displayed[30, 30], [255, 0, 0]))
        self.assertTrue(np.array_equal(displayed[30, 90], [255, 0, 0]))
        self.assertTrue(np.array_equal(displayed[60, 100], [0, 255, 255]))

    def test_q0_confirm_waits_for_all_required_shots(self):
        accept = MagicMock()
        window = SimpleNamespace(
            Q0=True,
            Q0_SAMPLE_COUNT=3,
            Q0_values=[(0.4, 0.5), (0.5, 0.5)],
            accept=accept,
        )

        SettingWindow._confirm_settings(window)

        accept.assert_not_called()

    def test_auto_close_commands_match_model_classes(self):
        self.assertEqual(
            MainWindow.AUTO_CLOSE_TARGET_COMMANDS,
            {
                1: ("@112#", "gap bia so 6"),
                0: ("@222#", "gap bia so 10"),
                2: ("@332#", "gap bia so 7b"),
                3: ("@442#", "an bia so 8"),
            },
        )

    def test_hit_closes_supported_target_only_once(self):
        window = type("WindowState", (), {})()
        window.testing = True
        window.automatic_close_target_enabled = True
        window.AUTO_CLOSE_TARGET_COMMANDS = MainWindow.AUTO_CLOSE_TARGET_COMMANDS
        window._auto_closed_target_classes = set()
        window.lora = MagicMock()

        self.assertTrue(MainWindow._maybe_close_hit_target(window, 1, True))
        self.assertFalse(MainWindow._maybe_close_hit_target(window, 1, True))
        self.assertFalse(MainWindow._maybe_close_hit_target(window, 0, False))

        window.lora.send_command.assert_called_once_with("@112#")

    def test_hit_hides_target_8_only_once(self):
        window = type("WindowState", (), {})()
        window.testing = True
        window.automatic_close_target_enabled = True
        window.AUTO_CLOSE_TARGET_COMMANDS = MainWindow.AUTO_CLOSE_TARGET_COMMANDS
        window._auto_closed_target_classes = set()
        window.lora = MagicMock()

        self.assertTrue(MainWindow._maybe_close_hit_target(window, 3, True))
        self.assertFalse(MainWindow._maybe_close_hit_target(window, 3, True))
        window.lora.send_command.assert_called_once_with("@442#")

    def test_lora_commands_match_the_required_timeline(self):
        self.assertEqual(
            [(seconds, command) for seconds, command, _ in MainWindow.LORA_SCRIPT],
            [(15, "@111#"), (32, "@221#"), (42, "@331#"), (64, "@444#")],
        )

    def test_single_pedestal_defaults_auto_close_on_and_allows_toggle(self):
        window = OptionWindow()

        self.assertEqual(window.p_num, 1)
        self.assertTrue(window.automatic_close_target_enabled)
        self.assertEqual(window.automatic_close_target.text(), "Gập bia: BẬT")

        window.automatic_close_target.click()
        self.app.processEvents()

        self.assertFalse(window.automatic_close_target_enabled)
        self.assertEqual(window.automatic_close_target.text(), "Gập bia: TẮT")
        window.close()

    def test_multiple_pedestals_default_auto_close_off(self):
        window = OptionWindow()

        window.p_num_btn_clicked(2)

        self.assertFalse(window.automatic_close_target_enabled)
        self.assertEqual(window.automatic_close_target.text(), "Gập bia: TẮT")
        window.close()

    def test_hub_does_not_advertise_recovering_reserved_pedestal(self):
        reserved = type(
            "Server",
            (),
            {"port_id": 1, "port": 1711, "is_session_reserved": True},
        )()
        free = type(
            "Server",
            (),
            {"port_id": 2, "port": 1995, "is_session_reserved": False},
        )()
        window = type("WindowState", (), {})()
        window.servers = [reserved, free]
        window.hub_registrar = MagicMock()

        MainWindow._update_hub_availability(window)

        window.hub_registrar.update_available.assert_called_once_with({2: 1995})

    def test_client_widget_shows_degraded_and_offline_states(self):
        widget = ClientWidget(1)

        widget.set_connection_quality_state("degraded", 620, 72)
        self.assertTrue(widget.connected)
        self.assertIn("CHẬP CHỜN", widget.pedestal_name_label.text())

        widget.set_connection_quality_state("offline", 900, 70)
        self.assertFalse(widget.connected)
        self.assertIn("MẤT TÍN HIỆU", widget.pedestal_name_label.text())
        widget.close()

    def test_healthy_heartbeat_restores_green_style_after_degraded(self):
        widget = ClientWidget(1)
        widget.set_connection_quality_state("degraded", 620, 72)
        self.assertIn("217, 119, 6", widget.pedestal_name_label.styleSheet())

        widget.set_connection_quality_state("healthy", 48, 71)

        self.assertTrue(widget.connected)
        self.assertIn("ĐÃ KẾT NỐI", widget.pedestal_name_label.text())
        self.assertIn("Ping 48ms", widget.pedestal_name_label.text())
        self.assertIn("0, 153, 0", widget.pedestal_name_label.styleSheet())
        self.assertNotIn("217, 119, 6", widget.pedestal_name_label.styleSheet())
        widget.close()

    def test_button_counts_up_and_does_not_stop_the_test(self):
        window = type("WindowState", (), {})()
        window.testing = True
        window._test_start_time = 100.0
        window.start_btn = FakeButton()

        with patch("gui.main_window.time.monotonic", return_value=142.9):
            MainWindow.update_app(window)

        self.assertEqual(window.start_btn.text, "KẾT THÚC (42s)")
        self.assertTrue(window.testing)


if __name__ == "__main__":
    unittest.main()
