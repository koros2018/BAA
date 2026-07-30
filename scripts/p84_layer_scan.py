"""Scan all DXF files for layers matching shaft/exit_sign/evacuation_lighting keywords.
Output: JSON report by keyword."""
import json, os, sys, ezdxf

# Build keyword→class reverse map
TARGET_KEYWORDS = {
    "shaft": ["井", "shaft", "竖井", "风井", "管井", "垃圾", "水井", "电梯井", "通风", "smoke_shaft", "water_shaft"],
    "exit_sign": ["出口", "exit", "出口标志", "安全出口", "出口指示"],
    "evacuation_lighting": ["应急", "evacuation", "疏散", "emergency", "e_light", "安全照明", "照明"],
}

def find_dxfs():
    dxfs = []
    root = os.path.join("data", "图纸")
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if f.lower().endswith(".dxf"):
                dxfs.append(os.path.join(dirpath, f))
    return sorted(dxfs)

def safe_layer_name(l):
    try:
        return l.dxf.name or ""
    except Exception:
        return ""

def safe_text_value(t):
    try:
        return str(t.dxf.text) or str(t.dxf.value) or ""
    except Exception:
        return ""

def scan():
    dxfs = find_dxfs()
    results = {k: [] for k in TARGET_KEYWORDS}

    for i, dxf_path in enumerate(dxfs, 1):
        fname = os.path.relpath(dxf_path)
        try:
            doc = ezdxf.readfile(dxf_path)
        except Exception as e:
            print(f"[{i}/{len(dxfs)}] FAIL read {fname}: {e}", flush=True)
            continue
        print(f"[{i}/{len(dxfs)}] {fname}", flush=True)

        models = [doc.modelspace()]
        block_count = 0
        try:
            block_count = len(doc.blocks)
        except Exception:
            pass
        if block_count > 5:
            for block in doc.blocks:
                try:
                    if block.is_anonymous:
                        continue
                    if block.name in ("*Model_Space", "*Paper_Space", "*Paper_Space0",
                                      "*Paper_Space1", "*Paper_Space2", "*Layout1"):
                        continue
                    models.append(block)
                except Exception:
                    continue

        for m in models:
            for target_class, keywords in TARGET_KEYWORDS.items():
                matched_layers = set()
                matched_texts = set()
                matched_blocks = set()

                for e in m:
                    try:
                        layer_name = safe_layer_name(e)
                    except Exception:
                        continue
                    for kw in keywords:
                        if kw in layer_name:
                            matched_layers.add(layer_name)

                    if hasattr(e, 'dxf') and hasattr(e.dxf, 'text'):
                        try:
                            text = safe_text_value(e)
                            for kw in keywords:
                                if kw in text:
                                    matched_texts.add(text[:50])
                        except Exception:
                            pass

                    if isinstance(e, ezdxf.entities.Insert):
                        try:
                            for kw in keywords:
                                if kw in e.dxf.name:
                                    matched_blocks.add(e.dxf.name)
                        except Exception:
                            pass

                if matched_layers or matched_texts or matched_blocks:
                    results[target_class].append({
                        "file": fname,
                        "layers": sorted(matched_layers)[:20],
                        "texts": sorted(matched_texts)[:10],
                        "blocks": sorted(matched_blocks)[:10],
                    })

    return results

if __name__ == "__main__":
    results = scan()
    out = "/tmp/p84_layer_scan.json"
    with open(out, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nDone. Report: {out}")
    for k, v in results.items():
        print(f"  {k}: {len(v)} files matched")
