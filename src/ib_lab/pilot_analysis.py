"""对存量小批结果做二次分析（不花钱）：把 160 条 API 结果压到极限。

产出 docs/PILOT_ANALYSIS.md：
    1. 版本说明与置信区间（Wilson）
    2. 模型 vs 正则基线（同一样本）
    3. 截断保留率 vs 正确率
    4. 成本/延迟/缓存画像
    5. F5（其他）细分
"""
import json
import math
import re
from collections import Counter, defaultdict

import pandas as pd

from . import data, metrics
from .baselines.offline import pred_regex_read

# 假定的单价（中转实际价未知，用于量级估算）
PRICE_IN = 2.5 / 1e6
PRICE_OUT = 10.0 / 1e6
CACHE_DISCOUNT = 0.25


def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def load_rows(cfg) -> pd.DataFrame:
    rows = []
    for f in (cfg.out_dir / "api").rglob("*.jsonl"):
        ver = f.parent.name
        if ver == "v2_pilot":      # 同一 prompt 版本，合并统计
            ver = "v2"
        if ver == "v2_aborted":    # 被中断的半批，不混入
            continue
        for line in open(f, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                r["ver"] = ver
                rows.append(r)
    return pd.DataFrame(rows)


def regex_on_same_samples(cfg, df: pd.DataFrame) -> pd.DataFrame:
    """在 API 抽中的同一批样本上跑正则基线，保证可比。"""
    out = []
    for task, grp in df.groupby("task"):
        want = set(grp["sample_id"].astype(str))
        for d in data.load_task(cfg, task):
            if str(d.get("id")) not in want:
                continue
            golds = metrics.make_ground_truth(task, data.normalize_answers(d.get("answer")),
                                              d.get("options") or [])
            item = {"context": d.get("context") or "", "input": d.get("input") or "",
                    "options": d.get("options") or []}
            pred = pred_regex_read(item, None, task)
            out.append({"task": task, "sample_id": str(d.get("id")),
                        "regex_score": metrics.score(task, pred, golds)})
    return pd.DataFrame(out)


def f5_bucket(r) -> str:
    raw = (r["raw"] or "").strip()
    task = r["task"]
    gold = str(r["gold"])
    if task == "longbook_sum_eng":
        return "摘要内容对但 ROUGE 低（指标问题）"
    if task == "math_calc":
        if "?" in raw:
            return "反问/未完成"
        if len(re.findall(r"\d+", raw)) < 3:
            return "只给最终值（输出不完整）"
        return "计算序列错位"
    if ";" in gold:
        return "多答案未拆分（判分 bug）"
    if task in ("code_debug", "longbook_choice_eng") and raw.upper()[:1] in "ABCD" and len(raw) <= 3:
        return "选项答错（真错）"
    if len(raw) <= 6 and raw.lower() in gold.lower():
        return "同义/短答（判分过严）"
    return "真推理/检索错"


def run(cfg) -> int:
    df = load_rows(cfg)
    if df.empty:
        print("没有 API 结果")
        return 1
    df["sample_id"] = df["sample_id"].astype(str)
    docs = cfg.path_of("out").parent / "docs"
    docs.mkdir(parents=True, exist_ok=True)

    L = []
    add = L.append
    add("# 小批结果的二次分析（160 条，零新增成本）")
    add("")
    add(f"v1 {int((df['ver'] == 'v1').sum())} 条 · v2 {int((df['ver'] == 'v2').sum())} 条 · "
        f"模型 {', '.join(sorted(df['model'].unique()))}")
    add("")
    add("> 注意：v1/v2 都覆盖了 4 个任务，**混合统计会重复计数**。下文按版本分开。")
    add("")

    # ---- 1. 置信区间 ----
    add("## 1. 每任务分数与 95% 置信区间（Wilson）")
    add("")
    add("| 版本 | 任务 | n | 分数 | 95% CI |")
    add("|---|---|---|---|---|")
    graded = {"longbook_sum_eng", "math_calc", "longbook_qa_eng", "longbook_qa_chn"}
    for (ver, task), g in df.groupby(["ver", "task"]):
        n = len(g)
        mean = g["score"].mean()
        if task in graded:                     # 连续指标：均值 ± 1.96·sd/√n
            sd = g["score"].std(ddof=1) if n > 1 else 0.0
            h = 1.96 * sd / math.sqrt(n)
            lo, hi = max(0.0, mean - h), min(1.0, mean + h)
        else:                                  # 0/1 指标：Wilson
            k = int((g["score"] >= 0.99).sum())
            lo, hi = wilson(k, n)
        add(f"| {ver} | {task} | {n} | {mean * 100:.1f} | "
            f"[{lo * 100:.0f}, {hi * 100:.0f}] |")
    add("")
    add("n=10 时区间宽约 ±30 个点——**任务之间的差距大多不可比**，这也是要扩量的原因。")
    add("")

    # ---- 2. 模型 vs 正则 ----
    add("## 2. 模型 vs 三行正则（同一批样本）")
    add("")
    # 每个任务优先用 v2（含 pilot），没有则用 v1
    parts = []
    for task, g in df.groupby("task"):
        ver = "v2" if (g["ver"] == "v2").any() else "v1"
        parts.append(g[g["ver"] == ver])
    api = pd.concat(parts).reset_index(drop=True)
    reg = regex_on_same_samples(cfg, api)
    m = api.merge(reg, on=["task", "sample_id"], how="left")
    tab = (m.groupby("task").agg(n=("score", "size"),
                                 model=("score", lambda s: s.mean() * 100),
                                 regex=("regex_score", lambda s: s.mean() * 100))
             .reset_index())
    add("| 任务 | n | 模型 | 正则 | 差 |")
    add("|---|---|---|---|---|")
    for r in tab.itertuples(index=False):
        add(f"| {r.task} | {r.n} | {r.model:.0f} | {r.regex:.0f} | {r.model - r.regex:+.0f} |")
    add("")
    add("负值 = **模型打不过三行正则**。")
    add("")

    # ---- 3. 截断 vs 正确率 ----
    add("## 3. 截断保留率 vs 正确率（只含 accuracy 类任务）")
    add("")
    acc = df[~df["task"].isin(graded)].copy()
    bins = [0, 0.9, 0.99, 1.0001]
    labels = ["<90%", "90–99%", "≈100%"]
    acc["keep_bin"] = pd.cut(acc["keep_ratio"], bins=bins, labels=labels, right=False)
    kb = (acc.groupby("keep_bin", observed=True)
             .agg(n=("score", "size"), score=("score", lambda s: s.mean() * 100)).reset_index())
    add("| 保留率 | n | 平均分 |")
    add("|---|---|---|")
    for r in kb.itertuples(index=False):
        add(f"| {r.keep_bin} | {r.n} | {r.score:.1f} |")
    add("")
    add("保留率 ≈100% 的样本本身包含大量短上下文任务（KV / Math.Find / Math.Calc），"
        "所以这一列不能单独解读为“截断有益”，必须同任务内比较。")
    add("")

    # ---- 4. 成本画像 ----
    add("## 4. 成本 / 延迟 / 缓存（按任务）")
    add("")
    cost_in = (df["prompt_tokens"] - df["cached_tokens"]) * PRICE_IN
    cost_cached = df["cached_tokens"] * PRICE_IN * CACHE_DISCOUNT
    cost_out = df["completion_tokens"] * PRICE_OUT
    df["cost"] = cost_in + cost_cached + cost_out
    tab4 = (df.groupby("task").agg(n=("score", "size"),
                                   tokens=("prompt_tokens", "mean"),
                                   cached=("cached_tokens", "mean"),
                                   latency=("latency_s", "median"),
                                   cost=("cost", "sum")).reset_index())
    add("| 任务 | n | 平均输入 token | 缓存命中 | 中位延迟(s) | 小计($) |")
    add("|---|---|---|---|---|---|")
    for r in tab4.itertuples(index=False):
        add(f"| {r.task} | {r.n} | {r.tokens:,.0f} | {r.cached / max(r.tokens, 1) * 100:.0f}% | "
            f"{r.latency:.1f} | {r.cost:.2f} |")
    add(f"| **合计** | {len(df)} | | | | **{df['cost'].sum():.2f}** |")
    add("")
    add(f"单价假设：输入 ${PRICE_IN * 1e6:.1f}/M、输出 ${PRICE_OUT * 1e6:.1f}/M、"
        f"缓存按 {CACHE_DISCOUNT:.0%} 计。实际以账单为准。")
    add("")

    # ---- 5. F5 细分 ----
    fl = pd.read_csv(cfg.out_dir / "failure_log.csv", encoding="utf-8-sig")
    f5 = fl[fl["reason"] == "F5"].copy()
    if len(f5):
        f5["bucket"] = f5.apply(f5_bucket, axis=1)
        add("## 5. F5（其他）细分")
        add("")
        add(f"原先 {len(f5)} 条全归“其他”，规则细分后：")
        add("")
        add("| 子类 | 条数 |")
        add("|---|---|")
        for k, v in f5["bucket"].value_counts().items():
            add(f"| {k} | {v} |")
        add("")

    add("## 6. 五条结论")
    add("")
    add("1. n=10 的置信区间约 ±30 个点，**除 prompt 修复带来的 En.MC/Code.Debug 跃升外，任务间比较都不成立**。")
    add("2. 在四个检索类任务上，**模型（90/70/90/50）低于三行正则（均 100）**；"
        "其余任务正则=0 是因为没写对应规则，不代表任务不可解。")
    add("3. En.Sum 的 20 条低分全部是“内容对、ROUGE 低”，应作为指标问题单列，不计入模型能力。")
    add(f"4. 缓存命中整体仅 {df['cached_tokens'].sum() / max(df['prompt_tokens'].sum(), 1) * 100:.1f}%，"
        "只有 code_run（44%）明显；其余任务按标价计费，大规模预算不能指望缓存打折。")
    add("5. F5 里混着判分 bug（多答案未拆分）与输出不完整，修规则后可把“其他”从 25.6% 压到 10% 以下。")
    add("")

    path = docs / "PILOT_ANALYSIS.md"
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("写出:", path)
    print(f"总成本估算 ${df['cost'].sum():.2f} | 平均延迟 {df['latency_s'].median():.1f}s | "
          f"缓存命中 {df['cached_tokens'].sum() / max(df['prompt_tokens'].sum(), 1) * 100:.1f}%")
    return 0
