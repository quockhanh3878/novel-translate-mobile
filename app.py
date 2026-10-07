#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""API-only entrypoint.

The project no longer ships or loads local ONNX translation models.  This
compatibility launcher keeps ``python app.py`` working and starts the
DeepSeek API web interface.
"""

import os

from web_gui import make_server


def main() -> None:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print("GUI web API-only: http://localhost:8000")
    make_server().serve_forever()


if __name__ == "__main__":
    main()
