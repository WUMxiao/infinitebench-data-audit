"""实验表：把离线基线与 API 结果拼成一张可交付的表。

每行必须回答三件事：
    我在验证什么       -> hypothesis / setting
    数字在什么协议下测  -> dataset / n / metric / prompt_ver
    这个数算什么水平    -> ref_id / ref_score / delta / gpt4_published

产出：out/experiments.csv / .xlsx / .md
"""
import json
from datetime import date

import pandas as pd

TASK_CN = {
    "passkey": "Retrieve.PassKey", "number_string": "Retrieve.Number",
    "kv_retrieval": "Retrieve.KV", "math_find": "Math.Find",
    "math_calc": "Math.Calc", "code_debug": "Code.Debug", "code_run": "Code.Run",
    "longbook_qa_eng": "En.QA", "longbook_qa_chn": "Zh.QA",
    "longbook_choice_eng": "En.MC", "longbook_sum_eng": "En.Sum",
    "longdialogue_qa_eng": "En.Dia",
}
# 论文里 GPT-4 的公开成绩（外部锚点）
GPT4 = {
    "passkey": 100.0, "number_string": 100.0, "kv_retrieval": 89.0, "math_find": 60.0,
    "math_calc": 0.04, "code_debug": 37.06, "code_run": 23.25, "longbook_qa_eng": 22.44,
    "longbook_qa_chn": 25.96, "longbook_choice_eng": 67.25, "longbook_sum_eng": 14.73,
    "longdialogue_qa_eng": 8.50,
}
BASE_CN = {"random": "随机猜", "first_option": "恒选A", "majority": "最高频标签",
           "question_echo": "只回显问题词", "regex_read": "规则抽取"}
BASE_ORDER = ["random", "first_option", "majority", "question_echo", "regex_read"]
HYP = {
    "random": "建立 chance level：模型必须显著高于此值才算有信息",
    "first_option": "选项位置是否存在系统偏置",
    "majority": "标签先验是否可被利用",
    "question_echo": "答案是否被问题文本重复泄露",
    "regex_read": "任务是否仅靠表层模式即可解（高 = 不测长上下文理解）",
}
METRIC_CN = {"rouge_f1": "token-F1", "rougeLsum": "ROUGE-Lsum", "prefix_acc": "prefix-acc"}


def load_offline(cfg) -> pd.DataFrame:
    return pd.read_csv(cfg.out_dir / "baseline_results.csv", encoding="utf-8-sig")


def load_api(cfg, ver: str = "v3") -> pd.DataFrame:
    rows = []
    for f in (cfg.out_dir / "api").glob(f"*/{ver}/*.jsonl"):
        with open(f, encoding="utf-8") as fp:
            rows.extend(json.loads(line) for line in fp if line.strip())
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df[df["task"] != "math_calc"]          # 已确认不可测，排除出排名
    return (df.groupby("task")
              .agg(n=("score", "size"), score=("score", "mean"))
              .reset_index())


def run(cfg) -> int:
    off = load_offline(cfg)
    api = load_api(cfg)

    rows, k = [], 0
    # 1) 离线基线：先排好 id，方便引用
    off_ids = {}
    for task in cfg.tasks:
        for b in BASE_ORDER:
            k += 1
            off_ids[(task, b)] = f"E{k:03d}"

    for task in cfg.tasks:
        sub = off[off["task"] == task]
        if sub.empty:
            continue
        base = float(sub.loc[sub["baseline"] == "random", "score"].iloc[0])
        for b in BASE_ORDER:
            r = sub[sub["baseline"] == b]
            if r.empty:
                continue
            score = float(r["score"].iloc[0])
            rows.append({
                "exp_id": off_ids[(task, b)], "date": date.today().isoformat(),
                "hypothesis": HYP[b], "dataset": "InfiniteBench",
                "task": TASK_CN.get(task, task), "n": int(r["n"].iloc[0]),
                "setting": BASE_CN[b], "prompt_ver": "-",
                "metric": METRIC_CN.get(r["metric"].iloc[0], r["metric"].iloc[0]),
                "score": round(score * 100, 2),
                "ref_id": off_ids[(task, "random")],
                "ref_score": round(base * 100, 2),
                "delta": round((score - base) * 100, 2),
                "gpt4_published": GPT4.get(task), "status": "done",
                "notes": "无模型基线",
            })

    # 2) API 行：检索类比规则基线，其余比随机基线
    for r in api.itertuples(index=False):
        k += 1
        rid = off_ids.get((r.task, "regex_read"))
        rsub = off[(off["task"] == r.task) & (off["baseline"] == "regex_read")]
        r_score = float(rsub["score"].iloc[0]) * 100 if not rsub.empty else 0.0
        if r_score >= 50:                     # 规则基线真的能解，才有比较意义
            ref_id, ref_score = rid, r_score
            ref_kind = "规则抽取"
        else:
            ref_id = off_ids.get((r.task, "random"))
            ref_score = float(off[(off["task"] == r.task) &
                                  (off["baseline"] == "random")]["score"].iloc[0]) * 100
            ref_kind = "随机猜"
        metric = off[off["task"] == r.task]["metric"].iloc[0]
        rows.append({
            "exp_id": f"E{k:03d}", "date": date.today().isoformat(),
            "hypothesis": "gpt-6-sol 在 v3 prompt 下的真实表现",
            "dataset": "InfiniteBench", "task": TASK_CN.get(r.task, r.task),
            "n": int(r.n), "setting": "gpt-6-sol / zero-shot",
            "prompt_ver": "v3", "metric": METRIC_CN.get(metric, metric),
            "score": round(float(r.score) * 100, 2),
            "ref_id": ref_id, "ref_score": round(ref_score, 2),
            "delta": round(float(r.score) * 100 - ref_score, 2),
            "gpt4_published": GPT4.get(r.task), "status": "done",
            "notes": (f"参照={ref_kind}；截断 100k；Math.Calc 已排除"
                      if r.task != "longbook_sum_eng"
                      else "参照=随机；ROUGE 失效，人工评 4.6/5，见 docs/SUM_HUMAN_EVAL.md"),
        })

    # 3) planned：还没做的对照
    for name, note in [
        ("BM25 检索 top-k + 短窗口", "分离检索失败与长上下文理解失败"),
        ("128k 中部截断 vs 完整输入", "量化截断损失"),
        ("few-shot 提示（3 任务）", "排除格式依从性干扰"),
    ]:
        k += 1
        rows.append({
            "exp_id": f"E{k:03d}", "date": "", "hypothesis": note,
            "dataset": "InfiniteBench", "task": "全部", "n": 0, "setting": name,
            "prompt_ver": "-", "metric": "-", "score": None, "ref_id": "",
            "ref_score": None, "delta": None, "gpt4_published": None,
            "status": "planned", "notes": "待跑",
        })

    df = pd.DataFrame(rows)
    out = cfg.out_dir
    df.to_csv(out / "experiments.csv", index=False, encoding="utf-8-sig")
    write_xlsx(df, out / "experiments.xlsx")
    write_md(df, out / "experiments.md")
    print(df[["exp_id", "task", "setting", "metric", "score", "ref_score", "delta", "status"]]
          .tail(15).to_string(index=False))
    print(f"\n共 {len(df)} 行（{(df['status'] == 'done').sum()} done / "
          f"{(df['status'] == 'planned').sum()} planned）")
    print(f"写出: {out / 'experiments.csv'} / .xlsx / .md")
    return 0


def write_xlsx(df: pd.DataFrame, path) -> None:
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        df.to_excel(xw, index=False, sheet_name="实验表")
        ws = xw.sheets["实验表"]
        head = PatternFill("solid", fgColor="1F3864")
        thin = Side(style="thin", color="D9D9D9")
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF", size=10)
            c.fill = head
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.freeze_panes = "C2"
        ws.row_dimensions[1].height = 40
        widths = {"A": 8, "B": 11, "C": 44, "D": 14, "E": 16, "F": 6, "G": 24,
                  "H": 11, "I": 13, "J": 8, "K": 8, "L": 9, "M": 7, "N": 14,
                  "O": 10, "P": 9, "Q": 30}
        for col, w in widths.items():
            ws.column_dimensions[col].width = w
        for r_i in range(2, ws.max_row + 1):
            ws.row_dimensions[r_i].height = 18
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
                c.alignment = Alignment(vertical="top", wrap_text=True)
        ws.auto_filter.ref = ws.dimensions


def write_md(df: pd.DataFrame, path) -> None:
    cols = ["exp_id", "task", "setting", "n", "metric", "score", "ref_score", "delta", "status"]
    lines = ["# 实验表（InfiniteBench）", "",
             f"生成于 {date.today().isoformat()}　|　{len(df)} 行　|　"
             f"分数统一 0–100；delta 相对同任务参照", "",
             "| " + " | ".join(cols) + " |",
             "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in df[cols].itertuples(index=False):
        vals = [f"{v:.2f}" if isinstance(v, float) else str(v) for v in r]
        lines.append("| " + " | ".join(vals) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
