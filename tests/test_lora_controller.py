import unittest
from unittest.mock import patch

from gui.lora_controller import LoraController


class FakeSerialPort:
    def __init__(self, echo_on_attempt=None):
        self.is_open = True
        self.echo_on_attempt = echo_on_attempt
        self.write_count = 0
        self._response = b""

    @property
    def in_waiting(self):
        return len(self._response)

    def reset_input_buffer(self):
        self._response = b""

    def write(self, payload):
        self.write_count += 1
        if self.write_count == self.echo_on_attempt:
            self._response = b"\r\n" + payload + b"\r\n"
        return len(payload)

    def flush(self):
        pass

    def read(self, size):
        result = self._response[:size]
        self._response = self._response[size:]
        return result

    def close(self):
        self.is_open = False


class LoraControllerTests(unittest.TestCase):
    def test_finds_usb_serial_port_by_description(self):
        ports = [
            {"device": "COM2", "description": "Bluetooth Link"},
            {"device": "COM7", "description": "USB Serial Port (COM7)"},
        ]
        with patch.object(LoraController, "available_ports", return_value=ports):
            self.assertEqual(LoraController.default_port_name(), "COM7")

    def test_retries_until_the_command_is_echoed(self):
        controller = LoraController()
        device = FakeSerialPort(echo_on_attempt=2)
        controller._serial = device
        controller._port_name = "COM7"
        results = []
        sent = []
        controller.command_sent.connect(lambda *args: sent.append(args))
        controller.command_finished.connect(
            lambda command, success, attempts: results.append((command, success, attempts))
        )

        controller._send_with_retry("@111#")

        self.assertEqual(device.write_count, 2)
        self.assertEqual(results, [("@111#", True, 2)])
        self.assertEqual(len(sent), 1, "Retries must not restart the target window")
        self.assertEqual(sent[0][0], "@111#")
        self.assertLessEqual(sent[0][1], sent[0][2])
        controller.close()

    def test_stops_after_three_attempts_without_an_echo(self):
        controller = LoraController()
        controller.ACK_TIMEOUT_SECONDS = 0.001
        device = FakeSerialPort()
        controller._serial = device
        controller._port_name = "COM7"
        results = []
        controller.command_finished.connect(
            lambda command, success, attempts: results.append((command, success, attempts))
        )

        controller._send_with_retry("@444#")

        self.assertEqual(device.write_count, 3)
        self.assertEqual(results, [("@444#", False, 3)])
        controller.close()

    def test_fold_all_sends_once_without_reading_a_response(self):
        controller = LoraController()
        self.addCleanup(controller.close)
        device = FakeSerialPort()
        controller._serial = device
        results = []
        sent = []
        controller.command_sent.connect(lambda *args: sent.append(args))
        controller.command_finished.connect(lambda *args: results.append(args))

        with patch.object(device, "read", side_effect=AssertionError("Must not wait for echo")):
            controller._send_with_retry("@661#")

        self.assertEqual(device.write_count, 1)
        self.assertEqual(results, [("@661#", True, 1)])
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], "@661#")

    def test_fold_all_reports_write_failure_without_retry(self):
        controller = LoraController()
        self.addCleanup(controller.close)
        device = FakeSerialPort()
        controller._serial = device
        results = []
        sent = []
        controller.command_sent.connect(lambda *args: sent.append(args))
        controller.command_finished.connect(lambda *args: results.append(args))

        with patch.object(device, "write", side_effect=OSError("Disconnected")) as write:
            controller._send_with_retry("@661#")

        write.assert_called_once_with(b"@661#")
        self.assertEqual(results, [("@661#", False, 1)])
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
