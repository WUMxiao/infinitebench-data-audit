"""体检：逐条流式扫描 2.3 GB，产出三张表。

    out/samples.csv       每条样本的元数据（id/长度/答案形态/是否在文中...）
    out/task_summary.csv  每任务聚合
    out/ctx_index.csv     上下文指纹，用于查复用

设计要点：一次扫描同时吐三张表，后续所有分析都从这三张表 join，不重复 IO。
"""
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

from . import data

# 官方指标口径：哪些算 accuracy，哪些算 token-F1 / ROUGE
METRIC = {
    "passkey": "accuracy", "number_string": "accuracy", "kv_retrieval": "accuracy",
    "math_find": "accuracy", "math_calc": "accuracy", "code_debug": "accuracy",
    "code_run": "accuracy", "longbook_choice_eng": "accuracy",
    "longdialogue_qa_eng": "accuracy",
    "longbook_qa_eng": "rouge_f1", "longbook_qa_chn": "rouge_f1",
    "longbook_sum_eng": "rougeLsum",
}
# 是否为选择题：不看文档，看数据里到底有没有 options（实测只有 2 个任务有）
CHOICE = {"longbook_choice_eng", "code_debug"}


def scan(cfg) -> tuple:
    rows = []
    task_extra = defaultdict(lambda: {"answers": Counter(), "letters": Counter(),
                                      "n_options": Counter()})
    for task in cfg.tasks:
        path = cfg.data_dir / f"{task}.jsonl"
        if not path.exists():
            print(f"[skip] {task} 未下载")
            continue
        n = 0
        for d in data.load_task(cfg, task):
            ctx = d.get("context") or ""
            inp = d.get("input") or ""
            opts = d.get("options") or []
            ans = data.normalize_answers(d.get("answer"))
            gold = ans[0] if ans else ""
            ctx_l, gold_l = ctx.lower(), gold.strip().lower()
            n_occ = ctx_l.count(gold_l) if gold_l else 0
            letter = data.gold_letter(gold, opts) if task in CHOICE else ""

            rows.append({
                "task": task,
                "id": d.get("id"),
                "metric": METRIC.get(task, "?"),
                "is_choice": task in CHOICE,
                "ctx_chars": len(ctx),
                "ctx_words": len(ctx.split()),
                "ctx_est_tokens": data.est_tokens(ctx),
                "input_chars": len(inp),
                "n_options": len(opts),
                "n_answers": len(ans),
                "answer_chars": len(gold),
                "answer_words": len(gold.split()),
                "gold_is_empty": int(not gold.strip()),
                "ans_in_ctx": int(bool(gold_l) and gold_l in ctx_l),
                "ans_occ_in_ctx": n_occ,
                "ans_in_input": int(bool(gold_l) and gold_l in inp.lower()),
                "opt_dup": int(len(set(o.strip().lower() for o in opts)) != len(opts)),
                "gold_letter": letter,
                "ctx_sha1": data.sha1_16(ctx),
                "input_sha1": data.sha1_16(inp),
            })
            task_extra[task]["answers"][gold.strip()] += 1
            if letter:
                task_extra[task]["letters"][letter] += 1
            if opts:
                task_extra[task]["n_options"][len(opts)] += 1
            n += 1
        print(f"[ok] {task}: {n} samples", flush=True)
    return pd.DataFrame(rows), task_extra


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    agg = df.groupby("task").agg(
        n=("id", "size"),
        metric=("metric", "first"),
        ctx_tok_med=("ctx_est_tokens", "median"),
        ctx_tok_p90=("ctx_est_tokens", lambda s: np.percentile(s, 90)),
        ctx_tok_max=("ctx_est_tokens", "max"),
        input_chars_med=("input_chars", "median"),
        ans_chars_med=("answer_chars", "median"),
        n_ans_gt1=("n_answers", lambda s: int((s > 1).sum())),
        gold_empty=("gold_is_empty", "sum"),
        ans_in_ctx_rate=("ans_in_ctx", "mean"),
        ans_in_input_rate=("ans_in_input", "mean"),
        uniq_ctx=("ctx_sha1", "nunique"),
        uniq_input=("input_sha1", "nunique"),
    ).reset_index()
    agg["ctx_reuse"] = agg["n"] / agg["uniq_ctx"]
    return agg


def context_index(df: pd.DataFrame) -> pd.DataFrame:
    return (df.groupby("ctx_sha1")
              .agg(tasks=("task", lambda s: "|".join(sorted(set(s)))),
                   n_rows=("id", "size"),
                   n_tasks=("task", "nunique"))
              .reset_index()
              .sort_values("n_rows", ascending=False))


def run(cfg) -> int:
    out = cfg.out_dir
    out.mkdir(parents=True, exist_ok=True)

    df, task_extra = scan(cfg)
    df.to_csv(out / "samples.csv", index=False, encoding="utf-8-sig")

    agg = summarize(df)
    agg.to_csv(out / "task_summary.csv", index=False, encoding="utf-8-sig")

    idx = context_index(df)
    idx.to_csv(out / "ctx_index.csv", index=False, encoding="utf-8-sig")

    print("\n===== 任务汇总 =====")
    print(agg.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print("\n===== 上下文复用 Top10 =====")
    print(idx.head(10).to_string(index=False))

    print("\n===== 选择题 gold 字母分布 =====")
    for t in CHOICE:
        if t in task_extra:
            c = task_extra[t]["letters"]
            tot = sum(c.values()) or 1
            print(f"{t:24s} " + "  ".join(f"{k}:{v / tot * 100:.1f}%" for k, v in sorted(c.items())))
            print(f"{'':24s} 选项数分布: {dict(task_extra[t]['n_options'])}")
    return 0
