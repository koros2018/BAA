#!/usr/bin/env python3
"""批量审查 — 跳过结构图（02结构/路径含"结构"），只审建筑/电气/给排水/暖通等图纸。"""
import os, sys, time, requests

BASE = "http://localhost:8000"
ROOT = "/mnt/d/BaiduNetdiskDownload/测试图纸"
OUT = "/tmp/baa_batch_results.txt"
REQ_TIMEOUT = 600
SLEEP = 0.3

# 跳过结构图路径
SKIP_PATTERNS = ["/02结构", "结构总说明", "梁平法", "桩基础", "墙柱", "梁配筋", "板配筋",
                  "墙身大样", "楼梯表", "楼梯结构", "结构平面图", "基础结构", "LT-", "G-"]

def skip(fp):
    rel = os.path.relpath(fp, ROOT)
    for pat in SKIP_PATTERNS:
        if pat in rel:
            return True
    return False

def collect_dxf(root):
    files = []
    for dirpath, _, fnames in os.walk(root):
        for fn in fnames:
            if fn.lower().endswith(".dxf"):
                fp = os.path.join(dirpath, fn)
                if not skip(fp):
                    files.append(fp)
    return sorted(files)

def load_done():
    done = {}
    if os.path.exists(OUT):
        for line in open(OUT):
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[1] == "OK":
                done[parts[0]] = True
    return done

def main():
    files = collect_dxf(ROOT)
    done = load_done()
    pending = [f for f in files if os.path.relpath(f, ROOT) not in done]
    print(f"共 {len(files)} 张（跳过结构图），已完成 OK {len(files)-len(pending)}，剩余 {len(pending)}", flush=True)
    ok = fail = err = 0
    with open(OUT, "a") as out:
        for i, fp in enumerate(pending, 1):
            rel = os.path.relpath(fp, ROOT)
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
                    print(f"[{i}/{len(pending)}] {rel} -> HTTP {r.status_code}", flush=True)
                    continue
                data = r.json()
                items = data.get("results", data.get("violations", []))
                total = len(items)
                fails = [it.get("rule_id", it.get("code", "?")) for it in items
                         if str(it.get("status", "")).upper() in ("FAIL", "VIOLATION")]
                if fails:
                    fail += 1
                    out.write(f"{rel}\tFAIL\t{total}\t{len(fails)}\t{','.join(fails[:20])}\n"); out.flush()
                    print(f"[{i}/{len(pending)}] {rel} -> FAIL {len(fails)}/{total}", flush=True)
                else:
                    ok += 1
                    out.write(f"{rel}\tOK\t{total}\t0\t\n"); out.flush()
                    print(f"[{i}/{len(pending)}] {rel} -> OK {total}", flush=True)
            except requests.exceptions.Timeout:
                err += 1
                out.write(f"{rel}\tTIMEOUT\t0\t0\t\n"); out.flush()
                print(f"[{i}/{len(pending)}] {rel} -> TIMEOUT", flush=True)
            except Exception as e:
                err += 1
                out.write(f"{rel}\tEXC:{str(e)[:40]}\t0\t0\t\n"); out.flush()
                print(f"[{i}/{len(pending)}] {rel} -> EXC {e}", flush=True)
            time.sleep(SLEEP)
    print(f"\n=== 完成: OK={ok} FAIL={fail} ERR={err} ===", flush=True)

if __name__ == "__main__":
    main()