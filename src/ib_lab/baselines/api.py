"""API 基线：OpenAI 兼容中转，gpt-6-sol / claude 系。

约定：
    * 截断预算统一 100k，每条记录实际保留比例
    * 缓存键 = sha1(sample_id | model | prompt_ver | budget)，重跑不重复花钱
    * 每条落盘一行 jsonl：raw / score / tokens / latency / error
    * 失败重试 3 次，指数退避；解析失败单独统计，不算 0 分混进去
"""
import hashlib
import json
import random
import threading
import time
import urllib.error
import urllib.request

import pandas as pd

from .. import data, metrics

PROMPT_VER = "v1"
SYSTEM = ("You are a careful reader. Answer the question using only the answer itself, "
          "with no explanation and no extra words.")

# 长输出任务给更大的预算；检索类只需几个 token
MAX_TOKENS = {"longbook_sum_eng": 512, "math_calc": 2048, "default": 128}


def max_tokens_for(task: str) -> int:
    return MAX_TOKENS.get(task, MAX_TOKENS["default"])


def sample_ids(cfg, task: str, n: int) -> list:
    """从体检表取该任务的 id，按固定 seed 抽样；没有体检表就扫一遍文件。"""
    samples = cfg.out_dir / "samples.csv"
    if samples.exists():
        df = pd.read_csv(samples, encoding="utf-8-sig")
        ids = [str(x) for x in df.loc[df["task"] == task, "id"].tolist()]
    else:
        ids = [str(d.get("id")) for d in data.load_task(cfg, task)]
    rng = random.Random(f"{cfg.seed}:{task}")
    k = min(n, len(ids))
    return sorted(rng.sample(ids, k)) if k else []


def build_messages(cfg, item: dict) -> tuple:
    ctx = item.get("context") or ""
    question = item.get("input") or ""
    ctx_cut, ratio = data.truncate_middle(ctx, cfg.truncate_tokens)
    user = f"{ctx_cut}\n\nQuestion: {question}\nAnswer:"
    return ([{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}], ratio)


def call(cfg, model: str, messages: list, max_tokens: int, retry: dict) -> dict:
    body = json.dumps({"model": model, "messages": messages,
                       "max_tokens": max_tokens, "temperature": 0}).encode()
    url = cfg.base_url("openai") + "/chat/completions"
    headers = {"Authorization": "Bearer " + cfg.api_key("openai"),
               "Content-Type": "application/json"}
    last = ""
    for attempt in range(retry["max"]):
        t0 = time.time()
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=300) as r:
                payload = json.load(r)
            choice = payload["choices"][0]
            return {"raw": choice["message"].get("content") or "",
                    "finish": choice.get("finish_reason"),
                    "usage": payload.get("usage", {}),
                    "latency": round(time.time() - t0, 2), "error": ""}
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}"
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {str(e)[:200]}"
        if attempt < retry["max"] - 1:
            time.sleep(retry["backoff_ms"] / 1000 * (2 ** attempt))
    return {"raw": "", "finish": "", "usage": {}, "latency": 0.0, "error": last}


def run(cfg, models=None, n=None, tasks=None) -> int:
    n = n or cfg.sample_per_task
    retry = cfg.raw["baseline"]["retry"]
    workers = int(cfg.raw["baseline"]["max_workers"])
    wanted = models or [m["id"] for m in cfg.models]
    targets = tasks or cfg.tasks

    lock = threading.Lock()
    all_rows = []
    for model in wanted:
        model_dir = cfg.out_dir / "api" / model.replace("/", "_") / PROMPT_VER
        model_dir.mkdir(parents=True, exist_ok=True)
        for task in targets:
            path = cfg.data_dir / f"{task}.jsonl"
            if not path.exists():
                print(f"[skip] {task}")
                continue
            out_file = model_dir / f"{task}.jsonl"
            done = set()
            if out_file.exists():
                with open(out_file, encoding="utf-8") as f:
                    done = {json.loads(line)["sample_id"] for line in f if line.strip()}

            ids = [i for i in sample_ids(cfg, task, n) if i not in done]
            if not ids:
                print(f"[cache] {model} {task}: 已有 {len(done)} 条，跳过")
                continue
            wanted_ids = set(ids)
            items = [d for d in data.load_task(cfg, task) if str(d.get("id")) in wanted_ids]
            print(f"[run] {model} {task}: {len(items)} 条", flush=True)

            def work(item):
                mid = str(item.get("id"))
                golds = metrics.make_ground_truth(task, data.normalize_answers(item.get("answer")),
                                                  item.get("options") or [])
                messages, ratio = build_messages(cfg, item)
                res = call(cfg, model, messages, max_tokens_for(task), retry)
                sc = metrics.score(task, res["raw"], golds) if res["raw"] else 0.0
                u = res["usage"] or {}
                row = {"task": task, "sample_id": mid, "model": model,
                       "prompt_ver": PROMPT_VER, "keep_ratio": round(ratio, 4),
                       "gold": golds, "raw": res["raw"][:2000], "score": sc,
                       "finish": res["finish"], "latency_s": res["latency"],
                       "prompt_tokens": u.get("prompt_tokens", 0),
                       "cached_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
                       "completion_tokens": u.get("completion_tokens", 0),
                       "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0),
                       "error": res["error"]}
                with lock:
                    with open(out_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                return row

            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(work, it) for it in items]
                for fut in as_completed(futures):
                    row = fut.result()
                    all_rows.append(row)
                    flag = "" if row["score"] >= 1.0 else "  <-- fail"
                    print(f"  {task:20s} {row['sample_id']:>10s} score={row['score']:.2f} "
                          f"{row['latency_s']:5.1f}s{flag}", flush=True)

    return summarize(cfg, models=wanted, n=n)


def summarize(cfg, models=None, n=None) -> int:
    api_dir = cfg.out_dir / "api"
    rows = []
    for f in api_dir.rglob("*.jsonl"):
        with open(f, encoding="utf-8") as fp:
            for line in fp:
                if line.strip():
                    rows.append(json.loads(line))
    if not rows:
        print("没有 API 结果")
        return 0
    df = pd.DataFrame(rows)
    # 解析失败：没报错、分数为 0、但 gold 的字面值出现在原始输出里
    def parse_fail(r) -> int:
        if not r["raw"] or r["error"]:
            return 0
        g = r["gold"][0] if r["gold"] else ""
        return int(r["score"] == 0 and bool(g) and str(g).lower() in r["raw"].lower())
    df["parse_fail"] = df.apply(parse_fail, axis=1)
    df["total_tokens"] = df["prompt_tokens"] + df["completion_tokens"]

    agg = (df.groupby(["model", "task"])
             .agg(n=("score", "size"), score=("score", "mean"),
                  err=("error", lambda s: int((s != "").sum())),
                  parse_fail=("parse_fail", "sum"),
                  latency_s=("latency_s", "mean"),
                  prompt_tokens=("prompt_tokens", "sum"),
                  completion_tokens=("completion_tokens", "sum"),
                  cached_tokens=("cached_tokens", "sum"))
             .reset_index())
    agg["score"] = (agg["score"] * 100).round(2)
    out = cfg.out_dir / "api_summary.csv"
    agg.to_csv(out, index=False, encoding="utf-8-sig")
    print("\n===== API 汇总 =====")
    print(agg.to_string(index=False))
    print(f"\n写出: {out}")
    print(f"总调用 {len(df)} 条 | 错误 {int((df['error'] != '').sum())} 条 | "
          f"解析失败 {int(df['parse_fail'].sum())} 条 | "
          f"tokens {int(df['total_tokens'].sum()):,}")
    return 0
