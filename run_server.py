#!/usr/bin/env python3
"""Start the Remote Video Monitor server.

Run it directly -- no installation or PYTHONPATH needed::

    python run_server.py                      # use the webcam if one exists
    python run_server.py --no-camera          # generated scene instead
    python run_server.py --port 9000 --width 320 --height 240 --fps 10

Then open the printed address in a browser.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from rvm.server.app import main  # noqa: E402

if __name__ == "__main__":
    main()