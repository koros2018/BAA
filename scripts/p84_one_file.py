"""
P84 A 管线 — 单文件处理，轻量版
"""
import sys, os, gc
from pathlib import Path
from collections import Counter
ROOT = '/mnt/d/OpenClawData3workspace/Projects/BAA'
sys.path.insert(0, ROOT)
import ezdxf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

from src.baa_engine.drawing_parser import DrawingParser
from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer

DPI = 100
MAX_SIZE = 768
MIN_PX = 8
GAP = 2000

ENTITY_TO_YOLO = {
    'wall':0,'door':1,'window':2,'stair':3,'staircase':3,'corridor':4,
    'fire_door':5,'exit':6,'fire_zone':8,'fire_window':9,'shaft':10,
    'room':11,'exit_sign':12,'sprinkler_system':13,'sprinkler':13,
    'fire_alarm':14,'smoke_detector':14,'heat_detector':14,
    'insulation':15,'evacuation_lighting':16,'refuge_floor':17,
    'vertical_shaft':10,'cable_shaft':10,'pipe_shaft':10,'duct_shaft':10,
    'fire_compartment':8,'sprinkler_head':13,'heat_detector':14,
}
YOLO_NAME = {0:'wall',1:'door',2:'window',3:'staircase',4:'corridor',
    5:'fire_door',6:'exit',7:'fire_lane',8:'fire_zone',9:'fire_window',
    10:'shaft',11:'room',12:'exit_sign',13:'sprinkler_system',
    14:'fire_alarm',15:'insulation',16:'evacuation_lighting',17:'refuge_floor'}

def split_floors(prims):
    bands = [(p.bbox['y'], p.bbox['y']+p.bbox.get('height',0))
             for p in prims if p.bbox
             and 10 < p.bbox.get('width',0) < 200000
             and 10 < p.bbox.get('height',0) < 200000]
    bands.sort()
    floors, cur = [], None
    for y0,y1 in bands:
        if cur is None: cur=(y0,y1)
        elif y0 > cur[1]+GAP: floors.append(cur); cur=(y0,y1)
        else: cur=(min(cur[0],y0),max(cur[1],y1))
    if cur: floors.append(cur)
    return floors

def render(dxf, x0,x1,y0,y1, out):
    doc = ezdxf.readfile(dxf); msp = doc.modelspace()
    x0-=200;x1+=200;y0-=200;y1+=200
    ww,wh=x1-x0,y1-y0
    fw, fh = ww/25.4, wh/25.4
    r = min(MAX_SIZE/(fw*DPI), MAX_SIZE/(fh*DPI), 1.0)
    fw*=r; fh*=r
    fig,ax=plt.subplots(figsize=(fw,fh),dpi=DPI)
    ax.set_xlim(x0,x1); ax.set_ylim(y0,y1); ax.set_aspect('equal'); ax.axis('off')
    for e in msp:
        try:
            if hasattr(e.dxf,'layer') and e.dxf.layer.upper()=='META': continue
            t=e.dxftype()
            if t=='LINE':
                s,e2=e.dxf.start,e.dxf.end; ax.plot([s[0],e2[0]],[s[1],e2[1]],'k-',lw=0.3)
            elif t=='LWPOLYLINE':
                pts=[(v[0],v[1]) for v in e.get_points()]; xs,ys=zip(*pts)
                ax.plot(xs,ys,'k-',lw=0.3)
            elif t=='CIRCLE':
                cx,cy=e.dxf.center[:2]; r=e.dxf.radius
                ax.add_patch(plt.Circle((cx,cy),r,fill=False,color='k',lw=0.3))
        except: pass
    plt.savefig(out,dpi=DPI,bbox_inches='tight',pad_inches=0.05,facecolor='white')
    plt.close(fig)
    return Image.open(out).size

def process_file(dxf, img_dir, label_dir):
    print(f'\n=== {os.path.basename(dxf)} ===')
    parser=DrawingParser()
    result=parser.parse(dxf, file_id=os.path.basename(dxf))
    if not result.success:
        print(f'  SKIP: {result.error}'); return
    prims=result.primitives
    floors=split_floors(prims)
    print(f'  Prims={len(prims)}, Floors={len(floors)}')
    
    analyzer=SemanticAnalyzer()
    ents=analyzer.analyze(prims).get('entities',[])
    
    type_ct=Counter(); total=0
    img_idx=len(os.listdir(img_dir))
    
    for i,(y0,y1) in enumerate(floors):
        xs=[p.bbox['x'] for p in prims if p.bbox]
        x_min,x_max=min(xs),max(p.bbox['x']+p.bbox.get('width',0) for p in prims if p.bbox)
        img=f'{img_dir}/img_{img_idx:05d}.jpg'
        w,h=render(dxf,x_min,x_max,y0,y1,img)
        s_x=w/(x_max-x_min); s_y=h/(y1-y0)
        lines=[]; ct=Counter()
        for e in ents:
            cid=ENTITY_TO_YOLO.get(e.get('type',''))
            if cid is None: continue
            b=e.get('bbox',{})
            bw,bh=b.get('width',0),b.get('height',0)
            if bw<=0 or bh<=0:
                # 墙/门等线型实体的 bbox 可能一个维度为 0
                # 取非零维度作为有效尺寸
                bw = bw if bw > 0 else bh
                bh = bh if bh > 0 else bw
            if max(bw, bh) < 10: continue  # too small
            by=b['y']
            if not(y0-2000<by+bh/2<y1+2000): continue
            px_x=(b['x']-x_min)*s_x; px_y=(by-y0)*s_y
            px_w=bw*s_x; px_h=bh*s_y
            if px_w<MIN_PX or px_h<MIN_PX: continue
            if px_w>w*0.95 or px_h>h*0.95: continue
            cx=(px_x+px_w/2)/w; cy=(px_y+px_h/2)/h
            ww2,hh2=px_w/w,px_h/h
            if not(0<=cx<=1 and 0<=cy<=1): continue
            lines.append(f'{cid} {cx:.6f} {cy:.6f} {ww2:.6f} {hh2:.6f}')
            ct[YOLO_NAME[cid]]+=1
        if lines:
            with open(f'{label_dir}/img_{img_idx:05d}.txt','w') as f:
                f.write('\n'.join(lines)+'\n')
            total+=len(lines); type_ct.update(ct)
            print(f'  floor {i}: {w}x{h} yolo={len(lines)} {dict(ct.most_common(5))}')
        img_idx+=1
    del prims, ents
    gc.collect()
    return dict(type_ct), total

if __name__=='__main__':
    img_dir='/mnt/d/OpenClawData3workspace/Projects/BAA/output/p84_train_data/images'
    label_dir='/mnt/d/OpenClawData3workspace/Projects/BAA/output/p84_train_data/labels'
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(label_dir, exist_ok=True)
    
    dxf_path=sys.argv[1]
    ct, total=process_file(dxf_path, img_dir, label_dir)
    print(f'  Total: {total}')
