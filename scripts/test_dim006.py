#!/usr/bin/env python3
"""Quick DIM-006 test on key files."""
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from src.baa_engine.drawing_parser import DrawingParser
from src.baa_engine.semantic_analyzer import SemanticAnalyzer
from src.baa_engine.atomic_functions import FuncRegistry
from collections import Counter
import os

files = [
    'data/drawings/real/东莞通-建筑-外部参照（不打印）.dxf',
    'data/files/baa-file-1957929b036e.dwg',
    'data/files/baa-file-0951e6c2f743.dwg',
    'data/files/baa-file-c157664de336.dwg',
]
for fpath in files:
    if not os.path.exists(fpath):
        print(f'{fpath}: NOT FOUND')
        continue
    parser = DrawingParser()
    result = parser.parse(fpath, 'test')
    if not result.success:
        fname = os.path.basename(fpath)
        print(f'{fname}: FAIL - {str(result.error)[:60]}')
        continue
    semantic = SemanticAnalyzer().analyze(result.primitives, result.dimensions)
    entities = [e if isinstance(e, dict) else getattr(e, '__dict__', {}) for e in semantic['entities']]
    registry = FuncRegistry()
    dim006_count = 0
    dim006_types = Counter()
    for e in entities:
        r = registry.execute_chained(['DIM-006'], e)
        for fid, res in r.items():
            if res and res.result == 'FAIL':
                dim006_count += 1
                dim006_types[e.get('type', '')] += 1
    fname = os.path.basename(fpath)
    print(f'{fname}: DIM-006={dim006_count} types={dict(dim006_types)}')
