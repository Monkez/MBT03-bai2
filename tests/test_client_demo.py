import contextlib
import io
import sys
import unittest
from unittest import mock

import client_demo


class ClientDemoEntryPointTests(unittest.TestCase):
    def test_entry_point_loads_current_shared_demo(self):
        demo_main = client_demo._load_demo_main()

        self.assertEqual(demo_main.__module__, "server_client.demo_client")

    def test_help_uses_root_entry_point_name_without_starting_gui(self):
        output = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["client_demo.py", "--help"]),
            contextlib.redirect_stdout(output),
        ):
            result = client_demo.main()

        self.assertIsNone(result)
        self.assertIn("python client_demo.py", output.getvalue())


if __name__ == "__main__":
    unittest.main()
