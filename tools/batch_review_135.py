#!/usr/bin/env python3
"""批量审查测试图纸 — 通过 gunicorn /review 端点。

- 每张请求带严格 timeout（默认 90s），超时记为 EXC:TIMEOUT 并继续
- 断点续跑：读取已有 /tmp/baa_batch_results.txt，跳过已完成文件
- 输出: /tmp/baa_batch_results.txt
"""
import os
import time
import requests

BASE = "http://localhost:8000"
ROOT = "/mnt/d/BaiduNetdiskDownload/测试图纸"
OUT = "/tmp/baa_batch_results.txt"
REQ_TIMEOUT = 90  # 每张请求超时（秒）
SLEEP = 0.4

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
            rel = line.split("\t", 1)[0]
            done[rel] = True
    return done

def write_row(f, rel, st, total, nfail, flist):
    f.write(f"{rel}\t{st}\t{total}\t{nfail}\t{flist}\n")
    f.flush()

def main():
    files = collect_dxf(ROOT)
    done = load_done()
    pending = [f for f in files if os.path.relpath(f, ROOT) not in done]
    print(f"共 {len(files)} 张，已完成 {len(files)-len(pending)}，剩余 {len(pending)}", flush=True)
    ok = fail = err = 0
    with open(OUT, "a") as out:
        for i, fp in enumerate(pending, 1):
            rel = os.path.relpath(fp, ROOT)
            try:
                with open(fp, "rb") as f:
                    r = requests.post(
                        f"{BASE}/review",
                        files={"file": (os.path.basename(fp), f)},
                        params={"building_type": "civil"},
                        timeout=REQ_TIMEOUT,
                    )
                if r.status_code != 200:
                    err += 1
                    write_row(out, rel, "HTTP_" + str(r.status_code), 0, 0, "")
                    print(f"[{i}/{len(pending)}] {rel} -> HTTP {r.status_code}", flush=True)
                    continue
                data = r.json()
                items = data.get("results", data.get("violations", []))
                total = len(items)
                fails = [it.get("rule_id", it.get("code", "?")) for it in items
                         if str(it.get("status", "")).upper() in ("FAIL", "VIOLATION")]
                if fails:
                    fail += 1
                    write_row(out, rel, "FAIL", total, len(fails), ",".join(fails[:20]))
                    print(f"[{i}/{len(pending)}] {rel} -> FAIL {len(fails)}/{total}", flush=True)
                else:
                    ok += 1
                    write_row(out, rel, "OK", total, 0, "")
                    print(f"[{i}/{len(pending)}] {rel} -> OK {total}", flush=True)
            except requests.exceptions.Timeout:
                err += 1
                write_row(out, rel, "EXC:TIMEOUT", 0, 0, "")
                print(f"[{i}/{len(pending)}] {rel} -> TIMEOUT", flush=True)
            except Exception as e:
                err += 1
                write_row(out, rel, "EXC:" + str(e)[:50], 0, 0, "")
                print(f"[{i}/{len(pending)}] {rel} -> EXC {e}", flush=True)
            time.sleep(SLEEP)

    print(f"\n=== 本次: OK={ok} FAIL={fail} ERR={err} ===", flush=True)
    print(f"结果已追加到 {OUT}", flush=True)

if __name__ == "__main__":
    main()