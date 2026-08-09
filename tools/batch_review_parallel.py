#!/usr/bin/env python3
"""批量审查剩余图纸 — 4 并发 requests 打 gunicorn，断点续跑。"""
import os, sys, time, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "http://localhost:8000"
ROOT = "/mnt/d/BaiduNetdiskDownload/测试图纸"
OUT = "/tmp/baa_batch_results.txt"
REQ_TIMEOUT = 300
WORKERS = 4

def load_done():
    done = {}
    if os.path.exists(OUT):
        for line in open(OUT):
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[1] in ("OK", "SKIP_BIG", "SKIP_STRUCT"):
                done[parts[0]] = True
    return done

def collect_pending():
    done = load_done()
    files = []
    for dirpath, _, fnames in os.walk(ROOT):
        for fn in fnames:
            if fn.lower().endswith(".dxf"):
                fp = os.path.join(dirpath, fn)
                rel = os.path.relpath(fp, ROOT)
                if rel not in done:
                    files.append(fp)
    return sorted(files)

def review_one(fp):
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
            return (rel, f"HTTP_{r.status_code}", 0, 0, "")
        data = r.json()
        items = data.get("results", data.get("violations", []))
        total = len(items)
        fails = [it.get("rule_id", it.get("code", "?")) for it in items
                 if str(it.get("status", "")).upper() in ("FAIL", "VIOLATION")]
        if fails:
            return (rel, "FAIL", total, len(fails), ",".join(fails[:20]))
        return (rel, "OK", total, 0, "")
    except requests.exceptions.Timeout:
        return (rel, "TIMEOUT", 0, 0, "")
    except Exception as e:
        return (rel, f"EXC:{str(e)[:40]}", 0, 0, "")

def main():
    pending = collect_pending()
    print(f"剩余 {len(pending)} 张，{WORKERS} 并发", flush=True)
    ok = fail = err = 0
    with open(OUT, "a") as out:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(review_one, fp): fp for fp in pending}
            for i, fut in enumerate(as_completed(futs), 1):
                rel, st, total, nfail, flist = fut.result()
                out.write(f"{rel}\t{st}\t{total}\t{nfail}\t{flist}\n"); out.flush()
                if st == "OK":
                    ok += 1
                elif st == "FAIL":
                    fail += 1
                else:
                    err += 1
                print(f"[{i}/{len(pending)}] {rel} -> {st} {nfail}/{total}", flush=True)
    print(f"\n=== 完成: OK={ok} FAIL={fail} ERR={err} ===", flush=True)

if __name__ == "__main__":
    main()