# InfiniteBench Data Audit

对 [InfiniteBench](https://github.com/OpenBMB/InfiniteBench) 做一次可复现的审读：
**它到底在测什么、分数为什么上不去、哪些问题出在数据而不是模型。**

- 12 个子任务 · 3,946 条样本 · 2.33 GB
- 5 个无模型基线 + 1 个 API 模型（gpt-6-sol）× 11 任务 × 50 条
- 三层问题分类：数据缺陷 P1–P7 / 模型错题 F0–F6 / 问题类型 8×25
- 完整分析见 **[docs/REPORT.md](docs/REPORT.md)**

## 结果摘要

| 任务 | 分数 | GPT-4(论文) | 说明 |
|---|---|---|---|
| Code.Run | **98.0** | 23.25 | 修 prompt 后从 30 → 98 |
| En.Dia | 96.0 | 8.50 | |
| Code.Debug | 94.0 | 37.06 | 修 options 后从 30 → 94 |
| En.MC | 92.0 | 67.25 | 修 options 后从 0 → 92 |
| Retrieve.KV | 92.0 | 89.00 | 正则基线 100，模型仍低 8 点 |
| Retrieve.Number | 90.0 | 100.00 | 正则 100 |
| Retrieve.PassKey | 88.0 | 100.00 | 正则 100 |
| Math.Find | 88.0 | 60.00 | 正则 100 |
| En.QA | 59.6 | 22.44 | token-F1 |
| Zh.QA | 48.0 | 25.96 | token-F1，中位只保留原文 19.6% |
| En.Sum | 11.6 | 14.73 | **ROUGE 失效**，人工评 4.6/5 |
| Math.Calc | — | 0.04 | 排除：模型不肯输出 14999 个数 |

合计 560 条调用，答对 426 条（76.1%）。

## 四个关键发现

1. **4 个任务零模型可解**：PassKey / Number / KV / Math.Find 的正则基线全是 100%——
   它们测的是"能不能在长文里定位一个字符串"，不是长上下文理解。
2. **在检索类任务上，模型打不过三行正则**：88–92 vs 100（同样本对比）。
3. **"分低"一半不是模型的问题**：失败里 50 条是 ROUGE 不认内容对，17 条真推理错，
   9 条计算错位；格式失败在修 prompt 后从 11.2% 降到 0.2%。
4. **En.Sum 的 ROUGE 测不出摘要质量**：20 条人工评均分 4.6/5，ROUGE 11.3，秩相关 −0.05。

## 快速开始

```bash
git clone https://github.com/<you>/infinitebench-data-audit.git
cd infinitebench-data-audit
pip install -r requirements.txt

export PYTHONPATH=src                 # Windows: $env:PYTHONPATH="src"
python download_data.py               # 拉 2.3 GB 数据到 data/（数据不进仓库）

python -m ib_lab analyze              # 体检 → out/task_summary.csv 等
python -m ib_lab diagnose             # 数据缺陷 P1–P7
python -m ib_lab baseline offline     # 5 个无模型基线
python -m ib_lab baseline api --model gpt-6-sol --n 50   # 需要 .env 里的 key
python -m ib_lab baseline api --rescore                  # 改口径后重算，不调 API
python -m ib_lab failure              # 失败分类 F0–F6
python -m ib_lab qtypes               # 问题类型
python -m ib_lab table                # 实验表
python -m ib_lab report               # 报告
```

API 配置：复制 `.env.example` 为 `.env`，填入中转地址与 key（`.env` 不会进 git）。

## 仓库结构

```
src/ib_lab/
  config.py      yaml + .env + IB_DATA/IB_OUT 覆盖
  data.py        流式读取 / 答案规范化 / 截断 / 指纹
  metrics.py     与官方 scorer 对齐（含多答案拆分）
  analyze.py     体检
  diagnose.py    数据缺陷 P1–P7
  baselines/     offline（5 基线）/ api（缓存 + 并发 + rescore）
  failure.py     模型错题 F0–F6 + F5 子类
  qtypes.py      问题类型 L1/L2
  pilot_analysis.py, sumcheck.py, table.py, report.py
tests/           口径回归测试
docs/            REPORT / STATUS / TASKS / FAILURE_ANALYSIS / PILOT_ANALYSIS / SUM_HUMAN_EVAL
```

## 方法要点

**先读评测代码，再读 README。** 本项目踩到三处只有代码里才写得清的口径：

1. 选择题的 `answer` 只有选项文本，判分器要 `[文本, 字母]`——不补字母会 IndexError；
2. Math.Calc 是"最长正确前缀比例"，不是全对才算对；
3. 官方对 `model_name == "gpt4"` 有 `pred_nums[1:]` 特判。

**每个分数都要有参照系**：随机基线、规则基线、GPT-4 锚点。没有参照的分数不可解释。

## 数据说明

数据**不入仓**（2.3 GB，GitHub 单文件上限 100 MB）。`download_data.py` 会从
[hf-mirror](https://hf-mirror.com/datasets/xinrongzhang2022/InfiniteBench) 拉取并写 `data/SHA256SUMS`。
`data/` 只读，所有派生结果写 `out/`（均被 gitignore）。

## 已知限制

- 只有一个模型（gpt-6-sol），无法做跨厂商对比
- 只有 zero-shot，few-shot 对照未跑（实验中表里标记为 planned）
- 摘要人工评只有 20 条，能证明"ROUGE 与内容无关"，不能给精确分数
- token 数按字符粗估，与官方 tokenizer 约 1% 偏差

## License

MIT，见 [LICENSE](LICENSE)。
