#!/usr/bin/env python3
"""AI API Tester — 直接运行入口（兼容 python cli.py 方式）"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.cli import main

if __name__ == "__main__":
    main()
