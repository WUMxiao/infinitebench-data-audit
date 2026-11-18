"""Canary：用一条真实样本探测 API 的行为，不批量。

看四件事：
    1. 100k 上下文能不能吃下（400 = 窗口不够）
    2. 是否遵守“只答答案”
    3. reasoning_tokens 实际多少（估算整批成本）
    4. 单条延迟

用法:
    python scripts/canary.py --task passkey --model gpt-6-sol
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ib_lab import data  # noqa: E402
from ib_lab.config import load  # noqa: E402

SYSTEM = ("You are a careful reader. Answer the question using only the answer itself, "
          "with no explanation and no extra words.")


def build_prompt(cfg, task: str) -> tuple:
    item = next(data.load_task(cfg, task))
    ctx = item.get("context") or ""
    question = item.get("input") or ""
    keep = cfg.truncate_tokens
    ctx_cut, ratio = data.truncate_middle(ctx, keep)
    user = f"{ctx_cut}\n\nQuestion: {question}\nAnswer:"
    return user, item, ratio, data.est_tokens(ctx_cut)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="passkey")
    ap.add_argument("--model", default="gpt-6-sol")
    ap.add_argument("--max-tokens", type=int, default=512)
    args = ap.parse_args()

    cfg = load()
    user, item, ratio, est = build_prompt(cfg, args.task)
    body = json.dumps({
        "model": args.model,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": user}],
        "max_tokens": args.max_tokens,
        "temperature": 0,
    }).encode()

    req = urllib.request.Request(
        cfg.base_url("openai") + "/chat/completions", data=body,
        headers={"Authorization": "Bearer " + cfg.api_key("openai"),
                 "Content-Type": "application/json"})
    print(f"task={args.task} model={args.model} est_tokens={est} keep_ratio={ratio:.3f} "
          f"prompt_chars={len(user)}", flush=True)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            data_json = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} in {time.time() - t0:.1f}s")
        print(e.read().decode("utf-8", "ignore")[:500])
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"ERR {type(e).__name__} {e} in {time.time() - t0:.1f}s")
        return 1

    choice = data_json["choices"][0]
    print(f"latency={time.time() - t0:.1f}s finish={choice.get('finish_reason')}")
    print("usage:", json.dumps(data_json.get("usage", {}), ensure_ascii=False))
    print("content:", repr((choice["message"].get("content") or "")[:300]))
    print("gold    :", repr(item.get("answer")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
