"""Test: verify bbox world→pixel mapping for one DXF."""
import sys, os, shutil
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, ROOT)
from src.baa_engine.yolo_integrator import YOLODetectionIntegrator
from src.baa_engine.drawing_parser import DrawingParser
from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
from PIL import Image

dxf = 'data/图纸/中原人工智能计算中心/20210409-3#泵房_t3.dxf'

# Render
integrator = YOLODetectionIntegrator()
tmp = integrator._render_dxf(dxf, dpi=100)
img = Image.open(tmp)
w, h = img.size
print(f'Rendered image: {w}x{h}')

# Parse + analyze
parser = DrawingParser()
result = parser.parse(dxf, file_id='pump')
analyzer = SemanticAnalyzer()
analysis = analyzer.analyze(result.primitives, dxf_path=dxf)

# Compute world bbox
all_x, all_y = [], []
for p in result.primitives:
    b = p.bbox
    if b:
        all_x.extend([b.get('x', 0), b.get('x', 0) + b.get('width', 0)])
        all_y.extend([b.get('y', 0), b.get('y', 0) + b.get('height', 0)])
wmn_x, wmx_x = min(all_x), max(all_x)
wmn_y, wmx_y = min(all_y), max(all_y)
print(f'World range: x=[{wmn_x:.0f},{wmx_x:.0f}] y=[{wmn_y:.0f},{wmx_y:.0f}]')

# Check entities with valid bbox
entities = analysis.get('entities', [])
print()
for e in entities:
    b = e.get('bbox', {})
    t = e.get('type', '')
    bw = b.get('width', 0)
    bh = b.get('height', 0)
    if bw > 100 and bh > 100:
        px = (b['x'] - wmn_x) * w / (wmx_x - wmn_x)
        py = (b['y'] - wmn_y) * h / (wmx_y - wmn_y)
        pw = bw * w / (wmx_x - wmn_x)
        ph = bh * h / (wmx_y - wmn_y)
        line = f'{t}: px=({px:.0f},{py:.0f}) size=({pw:.0f}x{ph:.0f}) world=({b["x"]:.0f},{b["y"]:.0f},{bw:.0f}x{bh:.0f})'
        print(line)
