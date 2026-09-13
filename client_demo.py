"""Launch the MBT03 demo client from the project root.

The GUI implementation stays in ``assets/server_client/demo_client.py`` so it
shares the same ``MBT03ClientCore`` and protocol as the deployed client.
"""

from __future__ import annotations

import os
import sys


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")


def _load_demo_main():
    if ASSETS_DIR not in sys.path:
        sys.path.insert(0, ASSETS_DIR)
    from server_client.demo_client import main as demo_main

    return demo_main


def main():
    return _load_demo_main()()


if __name__ == "__main__":
    main()
