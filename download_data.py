"""下载 InfiniteBench 12 个子任务到 data/（走 hf-mirror）。

数据不入仓（2.3 GB，超出 GitHub 单文件限制）。clone 之后先跑这一条。

用法:
    python download_data.py                # 全部下载（已存在则跳过）
    python download_data.py passkey        # 只下某个任务
    python download_data.py --verify       # 只校验 SHA256SUMS
"""
import hashlib
import os
import sys
import time

import requests

BASE = "https://hf-mirror.com/datasets/xinrongzhang2022/InfiniteBench/resolve/main/{}.jsonl"
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
SUMS = os.path.join(DATA_DIR, "SHA256SUMS")

TASKS = [
    "passkey", "number_string", "kv_retrieval",
    "math_find", "math_calc",
    "code_debug", "code_run",
    "longbook_qa_eng", "longbook_qa_chn", "longbook_choice_eng",
    "longbook_sum_eng", "longdialogue_qa_eng",
]


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(task: str, session: requests.Session) -> None:
    path = os.path.join(DATA_DIR, f"{task}.jsonl")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        print(f"[skip] {task} 已有 {os.path.getsize(path) / 1e6:.1f} MB", flush=True)
        return
    tmp = path + ".part"
    t0 = time.time()
    with session.get(BASE.format(task), stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total and done % (50 << 20) < (1 << 20):
                    print(f"  {task} {done / 1e6:7.1f}/{total / 1e6:.1f} MB "
                          f"({done / total * 100:4.1f}%)", flush=True)
    os.replace(tmp, path)
    print(f"[ok] {task} {os.path.getsize(path) / 1e6:.1f} MB in {time.time() - t0:.0f}s", flush=True)


def write_sums() -> None:
    lines = [f"{sha256(os.path.join(DATA_DIR, t + '.jsonl'))}  {t}.jsonl" for t in TASKS]
    with open(SUMS, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[ok] {SUMS}")


def verify() -> int:
    bad = 0
    with open(SUMS, encoding="utf-8") as f:
        for line in f:
            digest, name = line.split()
            path = os.path.join(DATA_DIR, name)
            if not os.path.exists(path):
                print(f"[missing] {name}")
                bad += 1
            elif sha256(path) != digest:
                print(f"[mismatch] {name}")
                bad += 1
    print("校验通过" if not bad else f"{bad} 个文件有问题")
    return 0 if not bad else 1


def main() -> int:
    if "--verify" in sys.argv:
        return verify()
    os.makedirs(DATA_DIR, exist_ok=True)
    targets = [a for a in sys.argv[1:] if not a.startswith("-")] or TASKS
    s = requests.Session()
    s.trust_env = False
    for t in targets:
        for attempt in range(3):
            try:
                download(t, s)
                break
            except Exception as e:  # noqa: BLE001
                print(f"[retry {attempt + 1}] {t}: {type(e).__name__} {e}", flush=True)
                time.sleep(3)
        else:
            print(f"[FAIL] {t}", flush=True)
    write_sums()
    print("ALL DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
