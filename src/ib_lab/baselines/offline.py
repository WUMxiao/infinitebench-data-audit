"""离线基线：不需要模型、不需要 key，用来建立 chance level。

五个基线：
    random         随机猜 / 随机抽 3 个词   —— 绝对下界
    first_option   永远选 A                —— 选项位置偏置
    majority       永远猜最高频标签          —— 标签先验（用了测试集分布，仅作诊断）
    question_echo  把问题里最长的实词当答案   —— 答案是否被问题泄露
    regex_read     正则直接从上下文抽        —— 任务是否只是表层匹配

产出：out/baseline_results.csv + out/preds/<task>.csv
设计要点：每个任务的文件只读一遍，同一遍里同时算 5 个基线（2.3 GB 不重复 IO）。
"""
import json
import re
from collections import Counter

import numpy as np
import pandas as pd

from .. import data, metrics

# 种子固定：与 run_baseline.py 一致。改了它，所有 random/dropout 类分数都会变。
SEED = 20261116

BASELINES = ["random", "first_option", "majority", "question_echo", "regex_read"]
_NUM = re.compile(r"-?\d+(?:\.\d+)?")

# 评分口径（math_calc 是“最长正确前缀比例”，不是 accuracy）
METRIC = {
    "passkey": "accuracy", "number_string": "accuracy", "kv_retrieval": "accuracy",
    "math_find": "accuracy", "math_calc": "prefix_acc", "code_debug": "accuracy",
    "code_run": "accuracy", "longbook_choice_eng": "accuracy",
    "longdialogue_qa_eng": "accuracy",
    "longbook_qa_eng": "rouge_f1", "longbook_qa_chn": "rouge_f1",
    "longbook_sum_eng": "rougeLsum",
}


# ---------------- 预测器 ----------------

def pred_random(item, rng, task):
    opts = item["options"]
    if opts:
        return chr(ord("A") + int(rng.integers(len(opts))))
    words = (item["context"] or " ").split()
    if not words:
        return ""
    return " ".join(str(x) for x in rng.choice(words, size=3))


def pred_first_option(item, rng, task):
    return "A" if item["options"] else ""


def pred_question_echo(item, rng, task):
    """把问题里最长的那个实词当答案 —— 测答案是否被问题本身泄露。"""
    words = re.findall(r"[A-Za-z\u4e00-\u9fff]{3,}", item["input"] or "")
    return max(words, key=len) if words else ""


def pred_regex_read(item, rng, task):
    ctx = item["context"] or ""
    inp = item["input"] or ""
    if task == "passkey":
        m = re.search(r"The pass key is (\w+)", ctx)
        return m.group(1) if m else ""
    if task == "number_string":
        m = re.search(r"The sequence of digits is (\d+)", ctx)
        return m.group(1) if m else ""
    if task == "kv_retrieval":
        keys = re.findall(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", inp)
        for k in keys:
            m = re.search(r'"%s":\s*"([^"]+)"' % re.escape(k), ctx)
            if m:
                return m.group(1)
        return ""
    if task == "math_find":
        # 坑：官方答案对排名类问题用的是“去重后”的顺序（见问题 P3）
        nums = [float(x) for x in _NUM.findall(ctx)]
        if not nums:
            return ""
        q = inp.lower()
        asc, uniq = sorted(nums), sorted(set(nums))
        if "third largest" in q:
            v = uniq[-3]
        elif "second largest" in q:
            v = uniq[-2]
        elif "largest" in q:
            v = uniq[-1]
        elif "third smallest" in q:
            v = uniq[2]
        elif "second smallest" in q:
            v = uniq[1]
        elif "smallest" in q:
            v = uniq[0]
        elif "median" in q:
            n = len(asc)
            v = asc[n // 2] if n % 2 else (asc[n // 2 - 1] + asc[n // 2]) / 2
        else:
            return ""
        return str(int(v)) if float(v).is_integer() else str(v)
    return ""


PREDICTORS = {
    "random": pred_random,
    "first_option": pred_first_option,
    "question_echo": pred_question_echo,
    "regex_read": pred_regex_read,
}


def run_task(cfg, task: str) -> tuple:
    metric = METRIC.get(task, "accuracy")
    rng = np.random.default_rng(SEED)
    recs = []
    for d in data.load_task(cfg, task):
        opts = d.get("options") or []
        golds = metrics.make_ground_truth(task, data.normalize_answers(d.get("answer")), opts)
        item = {"id": d.get("id"), "context": d.get("context") or "",
                "input": d.get("input") or "", "options": opts, "answer": golds}
        rec = {"id": item["id"], "gold": json.dumps(golds, ensure_ascii=False),
               "n_options": len(opts), "metric": metric, "task": task}
        for b, fn in PREDICTORS.items():
            try:
                rec[b] = fn(item, rng, task)
            except Exception:  # noqa: BLE001 —— 单个样本失败不该中断整个基线
                rec[b] = ""
        recs.append(rec)

    df = pd.DataFrame(recs)
    df["gold_list"] = df["gold"].map(json.loads)

    # majority：选择题 → 最高频字母；其它 → 最高频 gold
    if df["n_options"].gt(0).all() and len(df):
        letters = df["gold_list"].map(lambda g: g[1] if len(g) > 1 else "")
        df["majority"] = Counter(letters).most_common(1)[0][0]
    else:
        firsts = df["gold_list"].map(lambda g: g[0] if g else "")
        df["majority"] = Counter(firsts).most_common(1)[0][0]

    rows = []
    for b in BASELINES:
        scores = [metrics.score(task, getattr(r, b) or "", r.gold_list)
                  for r in df.itertuples(index=False)]
        df[f"score_{b}"] = scores
        rows.append({"task": task, "baseline": b, "metric": metric, "n": len(df),
                     "score": float(np.mean(scores)) if scores else float("nan")})
        print(f"  {task:20s} {b:14s} n={len(df):4d}  {metric:10s} "
              f"{np.mean(scores) * 100:6.2f}", flush=True)

    preds_dir = cfg.out_dir / "preds"
    preds_dir.mkdir(parents=True, exist_ok=True)
    df.drop(columns=["gold_list"]).to_csv(
        preds_dir / f"{task}.csv", index=False, encoding="utf-8-sig")
    return rows, len(df)


def run(cfg, tasks=None) -> int:
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    targets = tasks or cfg.tasks
    rows = []
    for task in targets:
        if not (cfg.data_dir / f"{task}.jsonl").exists():
            print(f"[skip] {task}")
            continue
        r, _ = run_task(cfg, task)
        rows.extend(r)

    res = pd.DataFrame(rows)
    res.to_csv(cfg.out_dir / "baseline_results.csv", index=False, encoding="utf-8-sig")
    print("\n===== 基线结果矩阵 =====")
    print((res.pivot_table(index="task", columns="baseline", values="score") * 100)
          .round(2).to_string())
    return 0
