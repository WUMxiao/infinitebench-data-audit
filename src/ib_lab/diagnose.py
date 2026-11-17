"""数据缺陷分诊：P1–P7，每类问题一个可量化证据。

    P1 输入模板化      多个子任务只有 1 种问题模板
    P2 上下文复用      同一段上下文跨任务/跨问题复用
    P3 标注口径矛盾    排名类按去重排序、median 按原序列
    P4 零模型可解      正则基线 100%
    P5 长度超窗        127k 中部截断，保留比例
    P6 指标与任务不匹配 ROUGE / 前缀准确率
    P7 元数据不一致    文档 n 与实际 n

产出：
    out/problem_summary.csv   每任务 27 列诊断指标
    out/math_find_check.csv   P3 复核（排名类 vs median 的两种口径）
"""
import re
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

from . import data

# 官方文档声称的样本数，用来对账（P7）
DOC_N = {
    "longbook_sum_eng": 103, "longbook_qa_eng": 351, "longbook_choice_eng": 229,
    "longdialogue_qa_eng": 200, "longbook_qa_chn": 175, "code_debug": 394,
    "code_run": 400, "math_calc": 50, "math_find": 350, "passkey": 590,
    "number_string": 590, "kv_retrieval": 500,
}
RETRIEVAL = {"passkey", "number_string", "kv_retrieval"}

_MATH_KINDS = ["third largest", "second largest", "largest",
               "third smallest", "second smallest", "smallest"]
_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def scan_task(cfg, task: str) -> dict:
    n = 0
    inputs, ctxs = Counter(), Counter()
    in_ctx = occ1 = 0
    tok = []
    over128k = over200k = over1m = 0
    ans_lens = []
    head_pos = tail_pos = mid_pos = 0
    keep_rates = []
    gold_visible = gold_judged = 0
    multi_ans = alias_ans = 0
    calc_list_lens = []
    float_gold = 0

    for d in data.load_task(cfg, task):
        ctx = d.get("context") or ""
        inp = d.get("input") or ""
        ans = data.normalize_answers(d.get("answer"))
        gold = ans[0] if ans else ""
        t = data.est_tokens(ctx)
        tok.append(t)
        inputs[inp] += 1
        # 必须用全文哈希：用前 N 字符会把“填充文本相同、针不同”的样本误判成复用
        ctxs[data.sha1_16(ctx)] += 1
        n += 1

        ans_lens.append(len(gold))
        if len(ans) > 1:
            multi_ans += 1
            if any(a != b and (a.lower() in b.lower() or b.lower() in a.lower())
                   for a in ans for b in ans):
                alias_ans += 1
        if task == "math_calc":
            calc_list_lens.append(len(ans))
        if task == "math_find":
            float_gold += int(isinstance(d["answer"][0], float))

        gl = gold.strip().lower()
        if gl and gl in ctx.lower():
            in_ctx += 1
            if ctx.lower().count(gl) == 1:
                occ1 += 1
                if task in RETRIEVAL:
                    cpos = ctx.lower().find(gl)
                    pos = cpos / max(len(ctx), 1)
                    if pos < 0.1:
                        head_pos += 1
                    elif pos > 0.9:
                        tail_pos += 1
                    else:
                        mid_pos += 1
                    # 官方按 127k token 中部截断（保头尾），判断唯一答案是否还活着
                    if t > 127_000:
                        kr = 127_000 / t
                        head_chars = len(ctx) * 0.5 * kr
                        tail_chars = len(ctx) * 0.5 * kr
                        gold_visible += int(cpos < head_chars or cpos > len(ctx) - tail_chars)
                        gold_judged += 1
        over128k += int(t > 128_000)
        over200k += int(t > 200_000)
        over1m += int(t > 1_000_000)
        keep_rates.append(min(1.0, 127_000 / t) if t else 1.0)

    tok_arr = np.array(tok)
    print(f"[ok] {task}: n={n} uniq_input={len(inputs)} in_ctx={in_ctx / n:.2f} "
          f"occ1={occ1 / n:.2f} >128k={over128k / n:.2f}", flush=True)
    return {
        "task": task,
        "n": n,
        "doc_n": DOC_N.get(task),
        "n_diff": n - DOC_N.get(task, n),
        "uniq_input": len(inputs),
        "input_diversity": len(inputs) / n,
        "uniq_ctx": len(ctxs),
        "ctx_reuse": n / max(len(ctxs), 1),
        "ans_in_ctx_rate": in_ctx / n,
        "ans_unique_occ_rate": occ1 / n,
        "tok_p50": np.percentile(tok_arr, 50),
        "tok_p90": np.percentile(tok_arr, 90),
        "tok_max": tok_arr.max(),
        "over_128k": over128k / n,
        "over_200k": over200k / n,
        "over_1m": over1m / n,
        "ans_chars_p50": np.percentile(ans_lens, 50),
        "multi_answer_rate": multi_ans / n,
        "alias_answer_rate": alias_ans / n,
        "math_calc_list_len_p50": (np.percentile(calc_list_lens, 50) if calc_list_lens else np.nan),
        "math_find_float_rate": (float_gold / n if task == "math_find" else np.nan),
        "gold_occ1_head": head_pos,
        "gold_occ1_mid": mid_pos,
        "gold_occ1_tail": tail_pos,
        "trunc_keep_rate_p50": np.percentile(keep_rates, 50),
        "trunc_keep_rate_p10": np.percentile(keep_rates, 10),
        "gold_visible_after_trunc": (gold_visible / gold_judged if gold_judged else np.nan),
    }


def math_kind(q: str) -> str:
    for k in _MATH_KINDS:
        if k in q:
            return k
    return "median" if "median" in q else "?"


def math_pick(seq, k: str) -> float:
    if k == "third largest":
        return seq[-3]
    if k == "second largest":
        return seq[-2]
    if k == "largest":
        return seq[-1]
    if k == "third smallest":
        return seq[2]
    if k == "second smallest":
        return seq[1]
    if k == "smallest":
        return seq[0]
    m = len(seq)
    return seq[m // 2] if m % 2 else (seq[m // 2 - 1] + seq[m // 2]) / 2


def check_math_find(cfg) -> pd.DataFrame:
    """P3：同一任务内混用两种排序口径——排名类按去重，median 按原序列。"""
    res = defaultdict(lambda: [0, 0, 0])
    for d in data.load_task(cfg, "math_find"):
        k = math_kind((d.get("input") or "").lower())
        nums = [float(x) for x in _NUM.findall(d.get("context") or "")]
        raw, ded = sorted(nums), sorted(set(nums))
        a = d["answer"]
        a = float(a[0]) if isinstance(a, list) else float(a)
        row = res[k]
        row[0] += 1
        row[1] += math_pick(ded, k) == a
        row[2] += math_pick(raw, k) == a
    return pd.DataFrame(
        [{"question_type": k, "n": n, "dedup_match": dd, "raw_match": rr}
         for k, (n, dd, rr) in res.items()])


def run(cfg) -> int:
    out = cfg.out_dir
    out.mkdir(parents=True, exist_ok=True)

    rows = [scan_task(cfg, t) for t in cfg.tasks
            if (cfg.data_dir / f"{t}.jsonl").exists()]
    df = pd.DataFrame(rows)
    df.to_csv(out / "problem_summary.csv", index=False, encoding="utf-8-sig")

    print("\n===== 诊断指标 =====")
    cols = ["task", "n", "doc_n", "uniq_input", "ctx_reuse", "ans_unique_occ_rate",
            "tok_p50", "tok_max", "over_128k", "multi_answer_rate"]
    print(df[cols].to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    mf = check_math_find(cfg)
    mf.to_csv(out / "math_find_check.csv", index=False, encoding="utf-8-sig")
    print("\n===== P3 排序口径复核（Math.Find）=====")
    print(mf.to_string(index=False))
    print(f"\n合计: 去重 {mf.dedup_match.sum()}/{mf.n.sum()}  "
          f"原序列 {mf.raw_match.sum()}/{mf.n.sum()}")
    return 0
