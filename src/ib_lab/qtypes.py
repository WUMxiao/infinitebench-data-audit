"""问题类型分类：给每条样本打两个标签。

    L1  任务类型（8 类，由 task 直接映射）
    L2  问题形态（任务内再切：否定式/肯定式、wh-类型、排名问法…）

产出：
    out/question_types.csv    逐条标签（3946 行）
    out/type_summary.csv      类型 × 任务 × n
    out/type_performance.csv  类型 × 模型 × 分数 × 主要失败方式（有 API 结果时）
"""
import re
from collections import Counter

import pandas as pd

from . import data

L1 = {
    "passkey": "Q1 定位检索", "number_string": "Q1 定位检索", "kv_retrieval": "Q1 定位检索",
    "math_calc": "Q2 数值计算",
    "math_find": "Q3 排名比较",
    "code_debug": "Q4 代码理解", "code_run": "Q4 代码理解",
    "longbook_choice_eng": "Q5 多选理解",
    "longbook_qa_eng": "Q6 开放问答", "longbook_qa_chn": "Q6 开放问答",
    "longbook_sum_eng": "Q7 摘要",
    "longdialogue_qa_eng": "Q8 对话指代",
}

_WH_EN = [("how many", "数量"), ("how much", "数量"),
          ("which people", "人物"), ("which person", "人物"),
          ("who", "人物"), ("where", "地点"), ("when", "时间"),
          ("why", "因果"), ("how", "方式"),
          ("which", "选择"), ("what", "事实")]
_WH_ZH = [("多少", "数量"), ("几个", "数量"), ("几人", "数量"), ("几次", "数量"),
          ("谁", "人物"), ("哪些人", "人物"), ("何人", "人物"),
          ("哪里", "地点"), ("哪儿", "地点"), ("什么地方", "地点"),
          ("什么时候", "时间"), ("哪年", "时间"), ("何时", "时间"),
          ("为什么", "因果"), ("为何", "因果"), ("原因", "因果"),
          ("怎么", "方式"), ("如何", "方式"),
          ("什么", "事实"), ("哪些", "事实"), ("哪", "事实")]
_NEG = re.compile(r"which of the following\b.*\b(not|except)\b|\bexcept\b", re.I)


def l2_of(task: str, question: str) -> str:
    q = (question or "").lower()
    raw = question or ""
    if task in ("passkey", "number_string", "kv_retrieval"):
        return "模板化检索"
    if task == "math_calc":
        return "算术求值"
    if task == "math_find":
        for k, name in [("second largest", "取第2大"), ("third largest", "取第3大"),
                        ("largest", "取最大"), ("second smallest", "取第2小"),
                        ("third smallest", "取第3小"), ("smallest", "取最小"),
                        ("median", "取中位")]:
            if k in q:
                return name
        return "其他"
    if task == "code_debug":
        return "定位错误函数"
    if task == "code_run":
        return "计算返回值"
    if task == "longbook_choice_eng":
        return "否定式(NOT/EXCEPT)" if _NEG.search(raw) else "肯定式"
    if task == "longbook_sum_eng":
        return "整书摘要"
    if task == "longdialogue_qa_eng":
        return "角色指代 MASK" if "$$mask$$" in q else "其他"
    # 开放问答：先看是否填空式，再按中英文疑问词分类
    if "___" in raw:
        return "填空式"
    for k, name in _WH_EN:
        if k in q:
            return name
    if re.search(r"[\u4e00-\u9fff]", raw):
        for k, name in _WH_ZH:
            if k in raw:
                return name
    return "其他"


def run(cfg) -> int:
    rows = []
    for task in cfg.tasks:
        if not (cfg.data_dir / f"{task}.jsonl").exists():
            continue
        n_task = 0
        for d in data.load_task(cfg, task):
            inp = d.get("input") or ""
            rows.append({"task": task, "sample_id": str(d.get("id")),
                         "q1": L1.get(task, "Q9 其他"), "q2": l2_of(task, inp),
                         "question": inp[:120]})
            n_task += 1
        print(f"[ok] {task}: {n_task}", flush=True)

    df = pd.DataFrame(rows)
    out = cfg.out_dir
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "question_types.csv", index=False, encoding="utf-8-sig")

    summary = (df.groupby(["q1", "q2", "task"]).size().reset_index(name="n")
                 .sort_values(["q1", "n"], ascending=[True, False]))
    summary.to_csv(out / "type_summary.csv", index=False, encoding="utf-8-sig")

    print("\n===== L1 分布 =====")
    print(df.groupby("q1").size().reset_index(name="n").to_string(index=False))
    print("\n===== L2 分布（前 15）=====")
    print(df.groupby(["q1", "q2"]).size().reset_index(name="n")
            .sort_values("n", ascending=False).head(15).to_string(index=False))
    print(f"\n总计 {len(df)} 条 | L1 {df['q1'].nunique()} 类 | L2 {df['q2'].nunique()} 类")

    write_performance(cfg, df)
    return 0


def write_performance(cfg, types: pd.DataFrame) -> None:
    """把类型标签接到 API 结果上：哪类问题分数低、主要怎么错。"""
    api_files = list((cfg.out_dir / "api").rglob("*.jsonl"))
    if not api_files:
        print("\n(还没有 API 结果，跳过 type_performance)")
        return
    import json
    rows = []
    for f in api_files:
        with open(f, encoding="utf-8") as fp:
            rows.extend(json.loads(line) for line in fp if line.strip())
    api = pd.DataFrame(rows)
    api["sample_id"] = api["sample_id"].astype(str)
    perf = api.merge(types[["task", "sample_id", "q1", "q2"]], on=["task", "sample_id"], how="left")
    perf["score"] = perf["score"] * 100

    g = (perf.groupby(["q1", "q2", "model"])
             .agg(n=("score", "size"), score=("score", "mean")).reset_index())
    g["score"] = g["score"].round(1)
    g.to_csv(cfg.out_dir / "type_performance.csv", index=False, encoding="utf-8-sig")
    print("\n===== 类型 × 模型 分数 =====")
    print(g.to_string(index=False))
    print(f"写出: {cfg.out_dir / 'type_performance.csv'}")
