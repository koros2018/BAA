#!/usr/bin/env python3
"""批量审查测试图纸 — 通过 FastAPI TestClient 直接调用（跳过 HTTP 瓶颈）。"""
import os
import sys
import signal

BAAROOT = "/mnt/d/OpenClawData3workspace/Projects/BAA"
sys.path.insert(0, BAAROOT)
os.environ["BAA_API_KEY"] = "test-api-key"
os.environ["BAA_AUTH_SECRET"] = "test-secret"

ROOT = "/mnt/d/BaiduNetdiskDownload/测试图纸"
OUT = "/tmp/baa_batch_results.txt"
TIMEOUT_SEC = 300

class _Timeout(Exception):
    pass
def _alarm(*a):
    raise _Timeout()
signal.signal(signal.SIGALRM, _alarm)

from fastapi.testclient import TestClient
from src.api.baa_api import app  # noqa: E402
client = TestClient(app)
_API_KEY = "test-api-key"
os.environ["BAA_API_KEY"] = _API_KEY

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
                signal.alarm(TIMEOUT_SEC)
                with open(fp, "rb") as f:
                    r = client.post(
                        "/review",
                        files={"file": (os.path.basename(fp), f)},
                        params={"building_type": "civil", "api_key": _API_KEY},
                    )
                signal.alarm(0)
                if r.status_code != 200:
                    err += 1
                    out.write(f"{rel}\tHTTP_{r.status_code}\t0\t0\t\n")
                    print(f"[{i}/{len(pending)}] {rel} -> HTTP {r.status_code}", flush=True)
                    continue
                data = r.json()
                items = data.get("results", data.get("violations", []))
                total = len(items)
                fails = [it.get("rule_id", it.get("code", "?")) for it in items
                         if str(it.get("status", "")).upper() in ("FAIL", "VIOLATION")]
                if fails:
                    fail += 1
                    out.write(f"{rel}\tFAIL\t{total}\t{len(fails)}\t{','.join(fails[:20])}\n")
                    print(f"[{i}/{len(pending)}] {rel} -> FAIL {len(fails)}/{total}", flush=True)
                else:
                    ok += 1
                    out.write(f"{rel}\tOK\t{total}\t0\t\n")
                    print(f"[{i}/{len(pending)}] {rel} -> OK {total}", flush=True)
                out.flush()
            except _Timeout:
                signal.alarm(0)
                err += 1
                out.write(f"{rel}\tEXC:TIMEOUT({TIMEOUT_SEC}s)\t0\t0\t\n")
                out.flush()
                print(f"[{i}/{len(pending)}] {rel} -> TIMEOUT", flush=True)
            except Exception as e:
                signal.alarm(0)
                err += 1
                out.write(f"{rel}\tEXC:{str(e)[:50]}\t0\t0\t\n")
                out.flush()
                print(f"[{i}/{len(pending)}] {rel} -> EXC {e}", flush=True)
    print(f"\n=== 本次: OK={ok} FAIL={fail} ERR={err} ===", flush=True)
    print(f"结果已追加到 {OUT}", flush=True)

if __name__ == "__main__":
    main()