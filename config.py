import os
import sys


APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "")
CUSTOM_WIDGETS_DIR = os.path.join(DATA_DIR, "MonkezCustomWidgets")
ASSETS_CUSTOM_WIDGETS_DIR = os.path.join(DATA_DIR, "assets", "MonkezCustomWidgets")

for path in (CUSTOM_WIDGETS_DIR, ASSETS_CUSTOM_WIDGETS_DIR):
    if path not in sys.path:
        sys.path.append(path)
