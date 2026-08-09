#!/usr/bin/env python3
"""重试失败的小文件 — 用 requests 打 gunicorn /review 端点。"""
import os, sys, time, requests

BASE = "http://localhost:8000"
ROOT = "/mnt/d/BaiduNetdiskDownload/测试图纸"
OUT = "/tmp/baa_batch_results.txt"
REQ_TIMEOUT = 600
SLEEP = 0.3

def load_failed():
    """读取结果文件中非 OK 的行（需重试）"""
    failed = []
    if os.path.exists(OUT):
        for line in open(OUT):
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2 or parts[1] == "OK":
                continue
            failed.append(parts[0])
    return failed

def main():
    retry = load_failed()
    print(f"需重试 {len(retry)} 张", flush=True)
    ok = fail = err = 0
    with open(OUT, "a") as out:
        for i, rel in enumerate(retry, 1):
            fp = os.path.join(ROOT, rel)
            try:
                with open(fp, "rb") as f:
                    r = requests.post(
                        f"{BASE}/review",
                        files={"file": (os.path.basename(fp), f)},
                        params={"building_type": "civil", "api_key": "test-api-key"},
                        timeout=REQ_TIMEOUT,
                    )
                if r.status_code != 200:
                    err += 1
                    out.write(f"{rel}\tRETRY_HTTP_{r.status_code}\t0\t0\t\n"); out.flush()
                    print(f"[{i}/{len(retry)}] {rel} -> HTTP {r.status_code}", flush=True)
                    continue
                data = r.json()
                items = data.get("results", data.get("violations", []))
                total = len(items)
                fails = [it.get("rule_id", it.get("code", "?")) for it in items
                         if str(it.get("status", "")).upper() in ("FAIL", "VIOLATION")]
                if fails:
                    fail += 1
                    out.write(f"{rel}\tFAIL\t{total}\t{len(fails)}\t{','.join(fails[:20])}\n"); out.flush()
                    print(f"[{i}/{len(retry)}] {rel} -> FAIL {len(fails)}/{total}", flush=True)
                else:
                    ok += 1
                    out.write(f"{rel}\tOK\t{total}\t0\t\n"); out.flush()
                    print(f"[{i}/{len(retry)}] {rel} -> OK {total}", flush=True)
            except requests.exceptions.Timeout:
                err += 1
                out.write(f"{rel}\tRETRY_TIMEOUT\t0\t0\t\n"); out.flush()
                print(f"[{i}/{len(retry)}] {rel} -> TIMEOUT", flush=True)
            except Exception as e:
                err += 1
                out.write(f"{rel}\tRETRY_EXC:{str(e)[:40]}\t0\t0\t\n"); out.flush()
                print(f"[{i}/{len(retry)}] {rel} -> EXC {e}", flush=True)
            time.sleep(SLEEP)
    print(f"\n=== 重试完成: OK={ok} FAIL={fail} ERR={err} ===", flush=True)

if __name__ == "__main__":
    main()