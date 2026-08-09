#!/usr/bin/env python3
"""只审 <10MB 的剩余小文件（串行，避免大文件阻塞）。"""
import os, sys, time, requests

BASE = "http://localhost:8000"
ROOT = "/mnt/d/BaiduNetdiskDownload/测试图纸"
OUT = "/tmp/baa_batch_results.txt"
REQ_TIMEOUT = 180
SLEEP = 0.2
MAX_MB = 10

def load_done():
    done = {}
    if os.path.exists(OUT):
        for line in open(OUT):
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[1] in ("OK", "SKIP_BIG", "SKIP_STRUCT"):
                done[parts[0]] = True
    return done

def main():
    done = load_done()
    files = []
    for dirpath, _, fnames in os.walk(ROOT):
        for fn in fnames:
            if fn.lower().endswith(".dxf"):
                fp = os.path.join(dirpath, fn)
                rel = os.path.relpath(fp, ROOT)
                size = os.path.getsize(fp) / 1024 / 1024
                if rel not in done and size < MAX_MB:
                    files.append((fp, size))
    files.sort(key=lambda x: x[1])
    print(f"剩余小文件 (<{MAX_MB}MB) {len(files)} 张", flush=True)
    ok = fail = err = 0
    with open(OUT, "a") as out:
        for i, (fp, size) in enumerate(files, 1):
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
                    print(f"[{i}/{len(files)}] {rel} ({size:.1f}MB) -> HTTP {r.status_code}", flush=True)
                    continue
                data = r.json()
                items = data.get("results", data.get("violations", []))
                total = len(items)
                fails = [it.get("rule_id", it.get("code", "?")) for it in items
                         if str(it.get("status", "")).upper() in ("FAIL", "VIOLATION")]
                if fails:
                    fail += 1
                    out.write(f"{rel}\tFAIL\t{total}\t{len(fails)}\t{','.join(fails[:20])}\n"); out.flush()
                    print(f"[{i}/{len(files)}] {rel} ({size:.1f}MB) -> FAIL {len(fails)}/{total}", flush=True)
                else:
                    ok += 1
                    out.write(f"{rel}\tOK\t{total}\t0\t\n"); out.flush()
                    print(f"[{i}/{len(files)}] {rel} ({size:.1f}MB) -> OK {total}", flush=True)
            except requests.exceptions.Timeout:
                err += 1
                out.write(f"{rel}\tTIMEOUT\t0\t0\t\n"); out.flush()
                print(f"[{i}/{len(files)}] {rel} ({size:.1f}MB) -> TIMEOUT", flush=True)
            except Exception as e:
                err += 1
                out.write(f"{rel}\tEXC:{str(e)[:40]}\t0\t0\t\n"); out.flush()
                print(f"[{i}/{len(files)}] {rel} ({size:.1f}MB) -> EXC {e}", flush=True)
            time.sleep(SLEEP)
    print(f"\n=== 小文件完成: OK={ok} FAIL={fail} ERR={err} ===", flush=True)

if __name__ == "__main__":
    main()