"""失败分析：一条预测为什么没拿满。

分类（先规则判定，F5 留人工）：
    OK      得分 1
    F1      检索失败    答案在（截断后的）文中，模型没找到
    F2      截断丢失    答案在原文，但被 100k 截断砍掉
    F3      格式失败    答案内容对/接近，但不符合判分要求的形态（如用选项原文而非字母）
    F4      拒答        模型明确说“文中没有/未提供”
    F5      其他        需人工看（推理错、聚合错、答案在文中但输出跑偏）
    F0      API 错误    请求失败

产出：
    out/failure_log.csv      逐条失败记录
    out/failure_ratio.csv    模型 × 任务 × 类别 的比例（带分子分母）
    docs/FAILURE_ANALYSIS.md 每类 3 个真实例子
"""
import json
import re
from collections import defaultdict

import pandas as pd

from . import data

REJECT = re.compile(
    r"(not provided|no digits|does not say|not mentioned|cannot find|no information|"
    r"not specified|not stated|there is no|n/?a\b|none of the)", re.I)

REASON_CN = {
    "OK": "答对", "F1": "检索失败", "F2": "截断丢失", "F3": "格式失败",
    "F4": "拒答", "F5": "其他(需人工)", "F6": "输出不完整", "F0": "API 错误",
}

# 生成式任务：答案不在原文里，不存在“检索失败/截断丢失”
GENERATIVE = {"longbook_sum_eng", "math_calc"}
# 连续指标（ROUGE / token-F1 / 前缀准确率）永远到不了 1.0，失败阈值要单独定
GRADED = {"longbook_sum_eng", "longbook_qa_eng", "longbook_qa_chn", "math_calc"}
GRADED_FAIL = 0.5
# 拒答只对短输出有意义：长摘要里出现 "there is no" 是正常行文
REJECT_MAX_LEN = 40


def is_fail(task: str, score: float) -> bool:
    return score < (GRADED_FAIL if task in GRADED else 1.0)


def load_rows(cfg) -> pd.DataFrame:
    rows = []
    for f in (cfg.out_dir / "api").rglob("*.jsonl"):
        with open(f, encoding="utf-8") as fp:
            rows.extend(json.loads(line) for line in fp if line.strip())
    return pd.DataFrame(rows)


def context_flags(cfg, tasks) -> dict:
    """对每个被抽中的样本，判断 gold 是否在原文、是否在截断后的文本里。

    结果缓存到 out/context_flags.json：同一批样本只扫一次 2.3 GB。
    """
    want = defaultdict(set)
    for f in (cfg.out_dir / "api").rglob("*.jsonl"):
        with open(f, encoding="utf-8") as fp:
            for line in fp:
                r = json.loads(line)
                want[r["task"]].add(str(r["sample_id"]))

    cache_path = cfg.out_dir / "context_flags.json"
    flags = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    for task in tasks:
        need = {i for i in want.get(task, set()) if f"{task}|{i}" not in flags}
        if not need:
            continue
        for d in data.load_task(cfg, task):
            mid = str(d.get("id"))
            if mid not in need:
                continue
            gold = data.normalize_answers(d.get("answer"))
            g = (gold[0] if gold else "").strip().lower()
            ctx = (d.get("context") or "")
            cut, _ = data.truncate_middle(ctx, cfg.truncate_tokens)
            flags[f"{task}|{mid}"] = {
                "in_ctx": bool(g) and g in ctx.lower(),
                "in_trunc": bool(g) and g in cut.lower(),
            }
    cache_path.write_text(json.dumps(flags, ensure_ascii=False), encoding="utf-8")
    return flags


def classify(row: dict, flag: dict) -> str:
    if row.get("error"):
        return "F0"
    raw = (row.get("raw") or "").strip()
    if not raw:
        return "F0"
    if not is_fail(row["task"], row["score"]):
        return "OK"
    golds = row["gold"]
    gold = (golds[0] if golds else "").strip().lower()
    low = raw.lower()

    # 输出不完整：原文是 gold 的前缀/子串（典型：UUID 少一位、函数名少一节）
    if gold and (low in gold) and len(low) >= 6:
        return "F6"
    # 选择题：用选项原文回答（内容对、形态错）
    if row["task"] in ("code_debug", "longbook_choice_eng") and gold and gold in low:
        return "F3"
    # 普通题：gold 出现在输出里但没判对。
    # math_calc 的 gold 是 14999 个数字的列表，随便命中一个不算“格式对”，排除。
    if row["task"] != "math_calc" and len(golds) == 1 and gold and gold in low:
        return "F3"
    # 拒答：只在短输出时判，长文本里的 "there is no" 是正常行文
    if len(raw) <= REJECT_MAX_LEN and REJECT.search(raw):
        return "F4"
    # 生成式任务没有“检索/截断”这一说
    if row["task"] in GENERATIVE:
        return "F5"
    if flag.get("in_trunc"):
        return "F1"
    if flag.get("in_ctx") and not flag.get("in_trunc"):
        return "F2"
    return "F5"


def run(cfg) -> int:
    df = load_rows(cfg)
    if df.empty:
        print("没有 API 结果，先跑 baseline api")
        return 1

    flags = context_flags(cfg, set(df["task"]))
    df["reason"] = [classify(r._asdict(), flags.get(f"{r.task}|{r.sample_id}", {}))
                    for r in df.itertuples(index=False)]
    df["reason_cn"] = df["reason"].map(REASON_CN)

    out = cfg.out_dir
    log_cols = ["model", "task", "sample_id", "score", "reason", "reason_cn",
                "gold", "raw", "keep_ratio", "latency_s", "error"]
    df[log_cols].to_csv(out / "failure_log.csv", index=False, encoding="utf-8-sig")

    ratio = (df.groupby(["model", "task", "reason", "reason_cn"])
               .size().reset_index(name="count"))
    tot = df.groupby(["model", "task"]).size().reset_index(name="n")
    ratio = ratio.merge(tot, on=["model", "task"])
    ratio["pct"] = (ratio["count"] / ratio["n"] * 100).round(1)
    ratio.to_csv(out / "failure_ratio.csv", index=False, encoding="utf-8-sig")

    print("\n===== 失败构成（全部任务）=====")
    overall = df.groupby(["reason", "reason_cn"]).size().reset_index(name="count")
    overall["pct"] = (overall["count"] / len(df) * 100).round(1)
    print(overall.to_string(index=False))
    print(f"\n总计 {len(df)} 条 | 答对 {int((df['reason'] == 'OK').sum())} "
          f"| 失败 {int((df['reason'] != 'OK').sum())}")

    print("\n===== 按任务 =====")
    print(df.pivot_table(index="task", columns="reason", values="sample_id",
                         aggfunc="count", fill_value=0).to_string())

    write_md(cfg, df)
    print(f"\n写出: {out / 'failure_log.csv'}\n      {out / 'failure_ratio.csv'}\n"
          f"      {cfg.path_of('out').parent / 'docs' / 'FAILURE_ANALYSIS.md'}")
    return 0


def write_md(cfg, df: pd.DataFrame) -> None:
    docs = cfg.path_of("out").parent / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    lines = ["# 失败分析：为什么没拿满", "",
             f"样本：{len(df)} 条 API 预测（{df['model'].iloc[0]}，每任务 "
             f"{df.groupby('task').size().iloc[0]} 条）", ""]
    overall = df.groupby(["reason", "reason_cn"]).size().reset_index(name="count")
    overall["pct"] = (overall["count"] / len(df) * 100).round(1)
    lines += ["## 失败构成", "", "| 类别 | 含义 | 条数 | 占比 |", "|---|---|---|---|"]
    for r in overall.itertuples(index=False):
        lines.append(f"| {r.reason} | {r.reason_cn} | {r.count} | {r.pct}% |")
    lines.append("")

    for code in ["F3", "F4", "F2", "F1", "F5", "F0"]:
        sub = df[df["reason"] == code]
        if sub.empty:
            continue
        lines += [f"## {code} {REASON_CN[code]}（{len(sub)} 条）", ""]
        for r in sub.head(3).itertuples(index=False):
            lines += [f"- `{r.task}` / `{r.sample_id}`　gold=`{r.gold}`",
                      f"  - 模型输出：`{(r.raw or '')[:160]}`"]
        lines.append("")

    lines += ["## 复现", "", "```bash",
              "python -m ib_lab baseline api --model gpt-6-sol --n 10",
              "python -m ib_lab failure", "```", ""]
    (docs / "FAILURE_ANALYSIS.md").write_text("\n".join(lines), encoding="utf-8")
