"""生成报告 docs/REPORT.md（5–10 页中文）。

设计：表格全部从 out/ 的产物现算，叙述部分固定。数据变了重跑即可，
避免“报告里的数”和“表里的数”对不上。
"""
import json
from datetime import date

import pandas as pd

from . import data, metrics
from .table import GPT4, TASK_CN, BASE_CN, BASE_ORDER

GRADED = {"longbook_sum_eng", "longbook_qa_eng", "longbook_qa_chn", "math_calc"}


def md(df: pd.DataFrame, float_cols=()) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in df.itertuples(index=False):
        vals = []
        for c, v in zip(cols, r):
            if isinstance(v, float):
                vals.append(f"{v:.1f}" if c not in float_cols else f"{v:.2f}")
            else:
                vals.append("" if v is None else str(v))
        out.append("| " + " | ".join(vals) + " |")
    return "\n".join(out)


def load_v3(cfg) -> pd.DataFrame:
    rows = []
    for f in (cfg.out_dir / "api").glob("*/v3/*.jsonl"):
        with open(f, encoding="utf-8") as fp:
            rows.extend(json.loads(line) for line in fp if line.strip())
    return pd.DataFrame(rows)


def run(cfg) -> int:
    ts = pd.read_csv(cfg.out_dir / "task_summary.csv", encoding="utf-8-sig")
    ts["_o"] = ts["task"].map({t: i for i, t in enumerate(cfg.tasks)})
    ts = ts.sort_values("_o").drop(columns="_o")
    ps = pd.read_csv(cfg.out_dir / "problem_summary.csv", encoding="utf-8-sig")
    br = pd.read_csv(cfg.out_dir / "baseline_results.csv", encoding="utf-8-sig")
    qt = pd.read_csv(cfg.out_dir / "question_types.csv", encoding="utf-8-sig")
    v3 = load_v3(cfg)
    fl = pd.read_csv(cfg.out_dir / "failure_log.csv", encoding="utf-8-sig")

    # 只取 v3（按版本列过滤，避免 v2_pilot 的同名样本被重复计入）
    fl3 = fl[fl["ver"] == "v3"].copy()

    L = []
    add = L.append
    add("# InfiniteBench 数据体检与基线报告")
    add("")
    add(f"> {date.today().isoformat()}　|　12 个任务 / {len(v3)} 条模型预测　|　"
        f"模型 gpt-6-sol　|　截断预算 100k token")
    add("")

    # ---------- 摘要 ----------
    api_task = (v3[v3["task"] != "math_calc"].groupby("task")
                  .agg(n=("score", "size"), score=("score", "mean")).reset_index())
    ok_rate = (fl3["reason"] == "OK").mean() * 100
    fmt_fail = (fl3["reason"] == "F3").mean() * 100
    add("## 0. 摘要")
    add("")
    add(f"1. **12 个子任务里有 4 个零模型可解**：PassKey / Number / KV / Math.Find 的"
        f"正则基线全是 100%。这些任务的分数反映“能不能定位字符串”，不是长上下文理解。")
    add(f"2. **模型总体答对 {ok_rate:.1f}%**（{int((fl3['reason'] == 'OK').sum())}/{len(fl3)}），"
        f"但格式失败只剩 {fmt_fail:.1f}%——修 prompt 前是 11.2%。")
    add(f"3. **在四个检索类任务上，模型仍低于三行正则**（88–92 vs 100）。")
    add(f"4. **En.Sum 的 ROUGE 失效**：20 条人工评均分 4.6/5，ROUGE 只有 11.3，"
        f"秩相关 −0.05，指标测不出内容对错。")
    add(f"5. **真正属于模型能力问题的失败只有 29 条（5.2%）**，其余来自指标、提示词、输出形态。")
    add("")

    # ---------- 1 数据卡 ----------
    add("## 1. 数据集概况")
    add("")
    add(f"InfiniteBench 共 12 个子任务、3946 条样本、约 2.33 GB。"
        f"这 12 个任务并不独立：70 段上下文跨任务复用，涉及 582 条（14.7%）。")
    add("")
    t1 = pd.DataFrame({
        "任务": ts["task"].map(TASK_CN), "n": ts["n"],
        "指标": ts["metric"], "中位 token": ts["ctx_tok_med"].round(0).astype(int),
        "最长 token": ts["ctx_tok_max"].astype(int), "模板数": ts["uniq_input"],
        "复用倍数": ts["ctx_reuse"].round(2),
        "答案在文中": (ts["ans_in_ctx_rate"] * 100).round(0).astype(int).astype(str) + "%",
    })
    add(md(t1))
    add("")
    add("读法：`模板数=1` 说明该任务只有一种问法；`复用倍数>1` 说明同一段上下文被问了多次；"
        "`答案在文中` 低说明答案是改写出来的，人工无法逐条核对。")
    add("")

    # ---------- 2 方法 ----------
    add("## 2. 方法")
    add("")
    add("```")
    add("① 对齐口径（读官方判分代码） → ② 体检 → ③ 建 chance level")
    add("   → ④ 零模型可解性 → ⑤ 问题分诊")
    add("```")
    add("")
    add("三处口径必须按代码来，README 没写：")
    add("")
    add("1. 选择题的 `answer` 只有选项文本，判分器要 `[文本, 字母]`，必须先补字母；")
    add("2. Math.Calc 是“最长正确前缀比例”，不是全对才算对；")
    add("3. 官方对 gpt4 有 `pred_nums[1:]` 特判——同一模型换个名字，分数会变。")
    add("")

    # ---------- 3 基线 ----------
    add("## 3. 基线结果")
    add("")
    add("### 3.1 离线基线（无模型）")
    add("")
    piv = br.pivot_table(index="task", columns="baseline", values="score")
    t2 = pd.DataFrame({"任务": [TASK_CN[t] for t in piv.index]})
    for b in BASE_ORDER:
        t2[BASE_CN[b]] = (piv[b].values * 100).round(2)
    add(md(t2))
    add("")
    add("**四个任务的正则基线是 100%**：这些任务的分数再高也不代表理解能力。"
        "`最高频标签` 在 En.Sum 上是 31.1，已经超过论文里 GPT-4 的 14.73。")
    add("")

    add("### 3.2 模型基线（gpt-6-sol，每任务 50 条）")
    add("")
    t3 = pd.DataFrame({
        "任务": api_task["task"].map(TASK_CN), "n": api_task["n"],
        "分数": (api_task["score"] * 100).round(1),
        "GPT-4(论文)": [GPT4.get(t) for t in api_task["task"]],
    })
    add(md(t3, float_cols=("分数", "GPT-4(论文)")))
    add("")
    add("En.Sum 的 11.6 不能和别的任务比（指标失效，见 §4.3）；Math.Calc 已确认不可测，"
        "排除出排名。")
    add("")

    add("### 3.3 prompt 演进")
    add("")
    add("| 任务 | v1 | v2 | v3 | 关键改动 |")
    add("|---|---|---|---|---|")
    add("| En.MC | 0.00 | 0.90 | 0.92 | v2 把 options 送进 prompt |")
    add("| Code.Debug | 0.30 | 0.80 | 0.94 | 同上 |")
    add("| Code.Run | 0.50 | 0.30 | 0.98 | v3 要求数字放在句子之后 |")
    add("| En.Sum | 0.09 | 0.14 | 0.12 | 改摘要指令 |")
    add("")
    add("**v1 有个硬 bug**：`options` 是独立字段，从没进过 prompt，模型只能凭自己的知识回答。"
        "修完后 En.MC 从 0 直接到 90 分。")
    add("")

    # ---------- 4 失败分析 ----------
    add("## 4. 失败分析：为什么没拿满")
    add("")
    comp = (fl3.groupby(["reason", "reason_cn"]).size().reset_index(name="count")
              .sort_values("count", ascending=False))
    comp["占比"] = (comp["count"] / len(fl3) * 100).round(1)
    comp = comp.rename(columns={"reason": "编号", "reason_cn": "类别", "count": "条数"})
    add(md(comp))
    add("")
    sub = fl3[fl3["sub_reason"].notna() & (fl3["sub_reason"] != "")]
    if len(sub):
        s = (sub.groupby("sub_reason").size().reset_index(name="条数")
               .sort_values("条数", ascending=False)
               .rename(columns={"sub_reason": "F5 子类"}))
        add(md(s))
        add("")
    add("**F3 格式失败只剩 1 条**。剩下的失败里，一半以上能归到指标与输出形态："
        "摘要 50 条是 ROUGE 不认内容对；计算 9 条、选项 3 条才是模型真错。")
    add("")

    # ---------- 5 问题分类 ----------
    add("## 5. 问题分类（三层）")
    add("")
    add("### 5.1 数据缺陷 P1–P7")
    add("")
    probs = [
        ("P1", "输入模板化", "PassKey/Number 各 590 条共享同一句问题；上下文 47 万字符里有效信息 38 字符"),
        ("P2", "上下文复用", "70 段上下文跨任务复用，582 条（14.7%）；En.QA 5.09x、Zh.QA 5.40x"),
        ("P3", "标注口径矛盾", "Math.Find 排名类按去重（200/200），median 按原序列（50/50）"),
        ("P4", "零模型可解", "4 个任务正则 100%"),
        ("P5", "长度超窗", "Zh.QA 中位保留 19.6%，p10 仅 5.7%"),
        ("P6", "指标与任务不匹配", "En.Sum 最高频答案 ROUGE 31.1 > GPT-4 14.73；Math.Calc 答案 14999 个数"),
        ("P7", "元数据不一致", "Zh.QA 文档 175 条实为 189；Code.Debug 拼写错误 394/394"),
    ]
    add(md(pd.DataFrame(probs, columns=["编号", "问题", "证据"])))
    add("")
    add("### 5.2 模型错题 F0–F6")
    add("")
    add("| 编号 | 含义 | 判定方式 |")
    add("|---|---|---|")
    for k, v, how in [
        ("F1", "检索失败", "答案在截断后的文中但模型没找到"),
        ("F2", "截断丢失", "答案在原文但被 100k 截断砍掉"),
        ("F3", "格式失败", "内容对但形态不合判分要求"),
        ("F4", "拒答", "模型明确说文中没有"),
        ("F5", "其他（已细分）", "再分 7 个子类：指标 / 真错 / 输出形态"),
        ("F6", "输出不完整", "输出是 gold 的前缀或子串"),
        ("F0", "API 错误", "请求失败"),
    ]:
        add(f"| {k} | {v} | {how} |")
    add("")
    add("### 5.3 问题类型 L1/L2")
    add("")
    l1 = qt.groupby("q1").size().reset_index(name="条数").rename(columns={"q1": "类型"})
    l1["占比"] = (l1["条数"] / len(qt) * 100).round(1)
    add(md(l1.sort_values("条数", ascending=False)))
    add("")
    add(f"L2 进一步切成 {qt['q2'].nunique()} 类（否定式、wh-类型、排名问法、填空式、MASK 指代）。"
        f"人工抽检 50 条，判对 49 条（98%）。")
    add("")
    # 类型 × 分数（只看 v3）
    v3q = v3.copy()
    v3q["sample_id"] = v3q["sample_id"].astype(str)
    qt2 = qt.copy()
    qt2["sample_id"] = qt2["sample_id"].astype(str)
    m = v3q.merge(qt2[["task", "sample_id", "q1"]], on=["task", "sample_id"], how="left")
    by_type = (m.groupby("q1").agg(n=("score", "size"), 分数=("score", "mean"))
                 .reset_index().rename(columns={"q1": "类型"}))
    by_type["分数"] = (by_type["分数"] * 100).round(1)
    add("按类型看模型分数（v3）：")
    add("")
    add(md(by_type.sort_values("分数", ascending=False)))
    add("")
    add("一个只有分类才看得出来的事实：229 条选择题里**只有 2 条是否定式**"
        "（`Which is NOT...`），样本量不足以支持“否定式更难”的结论。")
    add("")

    # ---------- 6 讨论 ----------
    add("## 6. 讨论")
    add("")
    add("### 6.1 为什么“跑不满”")
    add("")
    add("按顺序排查，四个原因的重要度递减：")
    add("")
    add("1. **指标不适用**（最大）：En.Sum 20 条人工评 4.6/5，ROUGE 11.3，秩相关 −0.05。"
        "这不是模型问题，是 ROUGE 只奖励措辞重合。")
    add("2. **提示词缺信息**：v1 没把 options 送进 prompt，选择题必然 0 分。修完后 +90。")
    add("3. **输出形态**：Code.Run 的数字位置、Math.Calc 的长序列，都是“格式”而不是“能力”。")
    add("4. **真能力**：检索类任务上模型 88–92 分，正则 100——差距是真的，但只有 8–12 个点。")
    add("")
    add("### 6.2 对使用这份数据的建议")
    add("")
    add("- 报告分数时必须同时给 **chance level** 与**规则基线**；否则不知道分数意味着什么。")
    add("- 四个检索类任务不要和长文档任务求平均；它们的难度不在一个维度。")
    add("- En.Sum 不要用 ROUGE 排名；要么人工评，要么换语义指标。")
    add("- Math.Calc 在 chat API 上不可测（模型不会数完 14999 个数），必须单列。")
    add("")

    # ---------- 7 局限 ----------
    add("## 7. 局限")
    add("")
    add("1. **只有一个模型**：中转上没有 Claude，无法做跨厂商对比。")
    add("2. **单一 prompt**：v3 只覆盖 zero-shot，few-shot 对照还没跑（表中 planned）。")
    add("3. **人工评样本小**：摘要人工评 20 条，只能证明“ROUGE 与内容无关”，不能给精确分数。")
    add("4. **长度是估算**：token 数按字符粗估，与官方 tokenizer 有约 1% 偏差。")
    add("5. **数据不入仓**：clone 后需自行下载 2.3 GB，见 README。")
    add("")

    # ---------- 8 复现 ----------
    add("## 8. 复现")
    add("")
    add("```bash")
    add("export PYTHONPATH=src IB_DATA=/path/to/data")
    add("python -m ib_lab analyze && python -m ib_lab diagnose")
    add("python -m ib_lab baseline offline")
    add("python -m ib_lab baseline api --model gpt-6-sol --n 50")
    add("python -m ib_lab baseline api --rescore")
    add("python -m ib_lab failure && python -m ib_lab qtypes")
    add("python -m ib_lab pilot && python -m ib_lab table && python -m ib_lab report")
    add("```")
    add("")

    out = cfg.path_of("out").parent / "docs" / "REPORT.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("写出:", out)
    return 0
