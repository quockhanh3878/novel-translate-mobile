#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""API-only entrypoint.

The project no longer ships or loads local ONNX translation models.  This
compatibility launcher keeps ``python app.py`` working and starts the
DeepSeek API web interface.
"""

import http.server
import os

from web_gui import Handler


def main() -> None:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print("GUI web API-only: http://localhost:8000")
    http.server.ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()


if __name__ == "__main__":
    main()
