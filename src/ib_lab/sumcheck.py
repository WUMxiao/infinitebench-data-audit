"""En.Sum 人工评（20 条）：验证 ROUGE 是否还能用来排序摘要。

评分口径（1–5，只看“是否覆盖原著主线”）：
    5 主要人物/情节正确且完整
    4 主线正确，个别细节错（性别、人名、支线）
    3 只覆盖部分主线或重心偏移
    2 大量错误
    1 与原著无关/拒答

用法: python -m ib_lab sumcheck
产出: docs/SUM_HUMAN_EVAL.md
"""
import json
import random

import pandas as pd

# 2026-11-18 人工评分（seed=4 抽的 20 条，顺序与打印一致）
HUMAN = [4, 4, 4, 5, 5, 5, 5, 4, 4, 5, 5, 5, 5, 4, 5, 5, 5, 5, 3, 5]


def run(cfg) -> int:
    path = cfg.out_dir / "api" / "gpt-6-sol" / "v3" / "longbook_sum_eng.jsonl"
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    random.Random(4).shuffle(rows)
    rows = rows[:20]
    assert len(rows) == len(HUMAN), "评分条数与样本数不一致"

    df = pd.DataFrame({
        "i": range(1, len(rows) + 1),
        "rouge": [r["score"] * 100 for r in rows],
        "human": HUMAN,
        "ref": [r["gold"][0][:80].replace("\n", " ") for r in rows],
        "model": [r["raw"][:80].replace("\n", " ") for r in rows],
    })
    # Spearman = 秩的 Pearson（不依赖 scipy）
    rho = df["rouge"].rank().corr(df["human"].rank())
    pear = df["rouge"].corr(df["human"])

    docs = cfg.path_of("out").parent / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    lines = ["# En.Sum 人工评（20 条）：ROUGE 还能不能用", "",
             f"- 人工均分 **{df['human'].mean():.2f}/5**，最低 {df['human'].min()}，最高 {df['human'].max()}",
             f"- ROUGE-Lsum 均分 **{df['rouge'].mean():.1f}**",
             f"- Spearman 相关 **{rho:.2f}**，Pearson **{pear:.2f}**", "",
             "## 逐条", "", "| # | ROUGE | 人工 | 参考摘要（前 80 字） |", "|---|---|---|---|"]
    for r in df.itertuples(index=False):
        lines.append(f"| {r.i} | {r.rouge:.1f} | {r.human} | {r.ref} |")
    lines += ["", "## 结论", "",
              f"20 条摘要人工均分 {df['human'].mean():.1f}/5（多数 4–5 分，主线正确），"
              f"但 ROUGE 只有 {df['rouge'].mean():.1f}，两者秩相关仅 {rho:.2f}。",
              "",
              "说明 **ROUGE 无法区分“内容对”和“用词不同”**；本任务上的 ROUGE 只能当"
              "“与参考答案的措辞重合度”，不能当摘要质量。",
              "", "报告口径：En.Sum 单列，标注“指标失效”，不参与跨任务平均。", ""]
    out = docs / "SUM_HUMAN_EVAL.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"人工均分 {df['human'].mean():.2f} | ROUGE 均分 {df['rouge'].mean():.1f} | "
          f"Spearman {rho:.2f}")
    print("写出:", out)
    return 0
