# -*- coding: utf-8 -*-
"""让测试可以直接 import pipeline 目录下的模块。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "pipeline"))
