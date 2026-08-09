#!/usr/bin/env python3
"""批量审查 — 只审 <20MB 且非结构的图纸（快速完成），大文件标记为 SKIP_BIG。"""
import os, sys, time, requests

BASE = "http://localhost:8000"
ROOT = "/mnt/d/BaiduNetdiskDownload/测试图纸"
OUT = "/tmp/baa_batch_results.txt"
REQ_TIMEOUT = 300
SLEEP = 0.3
MAX_MB = 20

SKIP_PATTERNS = ["/02结构", "结构总说明", "梁平法", "桩基础", "墙柱", "梁配筋", "板配筋",
                  "墙身大样", "楼梯表", "楼梯结构", "结构平面图", "基础结构", "LT-", "G-"]

def skip(fp):
    rel = os.path.relpath(fp, ROOT)
    if os.path.getsize(fp) / 1024 / 1024 >= MAX_MB:
        return "BIG"
    for pat in SKIP_PATTERNS:
        if pat in rel:
            return "STRUCT"
    return None

def collect_dxf(root):
    files = []
    for dirpath, _, fnames in os.walk(root):
        for fn in fnames:
            if fn.lower().endswith(".dxf"):
                files.append(os.path.join(dirpath, fn))
    return sorted(files)

def load_done():
    done = {}
    if os.path.exists(OUT):
        for line in open(OUT):
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[1] in ("OK", "SKIP_BIG", "SKIP_STRUCT"):
                done[parts[0]] = True
    return done

def main():
    files = collect_dxf(ROOT)
    done = load_done()
    ok = fail = err = skip_big = skip_struct = 0
    with open(OUT, "a") as out:
        for i, fp in enumerate(files, 1):
            rel = os.path.relpath(fp, ROOT)
            if rel in done:
                continue
            reason = skip(fp)
            if reason == "BIG":
                skip_big += 1
                out.write(f"{rel}\tSKIP_BIG\t0\t0\t\n"); out.flush()
                continue
            if reason == "STRUCT":
                skip_struct += 1
                out.write(f"{rel}\tSKIP_STRUCT\t0\t0\t\n"); out.flush()
                continue
            try:
                with open(fp, "rb") as f:
                    r = requests.post(
                        f"{BASE}/review",
                        files={"file": (os.path.basename(fp), f)},
                        params={"building_type": "civil", "api_key": "***"},
                        timeout=REQ_TIMEOUT,
                    )
                if r.status_code != 200:
                    err += 1
                    out.write(f"{rel}\tHTTP_{r.status_code}\t0\t0\t\n"); out.flush()
                    print(f"[{i}/{len(files)}] {rel} -> HTTP {r.status_code}", flush=True)
                    continue
                data = r.json()
                items = data.get("results", data.get("violations", []))
                total = len(items)
                fails = [it.get("rule_id", it.get("code", "?")) for it in items
                         if str(it.get("status", "")).upper() in ("FAIL", "VIOLATION")]
                if fails:
                    fail += 1
                    out.write(f"{rel}\tFAIL\t{total}\t{len(fails)}\t{','.join(fails[:20])}\n"); out.flush()
                    print(f"[{i}/{len(files)}] {rel} -> FAIL {len(fails)}/{total}", flush=True)
                else:
                    ok += 1
                    out.write(f"{rel}\tOK\t{total}\t0\t\n"); out.flush()
                    print(f"[{i}/{len(files)}] {rel} -> OK {total}", flush=True)
            except requests.exceptions.Timeout:
                err += 1
                out.write(f"{rel}\tTIMEOUT\t0\t0\t\n"); out.flush()
                print(f"[{i}/{len(files)}] {rel} -> TIMEOUT", flush=True)
            except Exception as e:
                err += 1
                out.write(f"{rel}\tEXC:{str(e)[:40]}\t0\t0\t\n"); out.flush()
                print(f"[{i}/{len(files)}] {rel} -> EXC {e}", flush=True)
            time.sleep(SLEEP)
    print(f"\n=== 完成: OK={ok} FAIL={fail} ERR={err} SKIP_BIG={skip_big} SKIP_STRUCT={skip_struct} ===", flush=True)

if __name__ == "__main__":
    main()