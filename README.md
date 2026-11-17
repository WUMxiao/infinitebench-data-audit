# InfiniteBench Data Audit

对 [InfiniteBench](https://github.com/OpenBMB/InfiniteBench) 做一次可复现的数据体检：
**它到底在测什么、哪些分数不可信、模型在哪儿失败**。

> 状态：骨架阶段（Day 1）。下方的结果表在跑完基线后填入。

## 这份仓库回答四个问题

| # | 问题 | 产出 |
|---|---|---|
| 1 | 数据长什么样、有没有结构性问题 | `out/task_summary.csv` + 数据卡 |
| 2 | 什么都不学能拿多少分 | `out/baseline_results.csv`（5 个离线基线） |
| 3 | 模型真实表现如何（含失败方式） | `out/api/*.csv`（gpt-4o / claude-sonnet-4-5） |
| 4 | 数据与模型各有哪些问题 | 数据缺陷 P1–P7 + 模型错题分类 |

## 快速开始

```bash
git clone https://github.com/<you>/infinitebench-data-audit.git
cd infinitebench-data-audit
pip install -r requirements.txt

python download_data.py          # 拉 2.3 GB 原始数据到 data/（不入仓）
export PYTHONPATH=src            # Windows: $env:PYTHONPATH="src"
python -m ib_lab analyze         # 体检
python -m ib_lab baseline offline  # 离线基线
python -m ib_lab table           # 汇总成实验表
```

API 基线需要 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`：

```bash
python -m ib_lab baseline api --model gpt-4o --n 20
```

## 目录

```
configs/default.yaml     数据路径、截断预算、模型、抽样
src/ib_lab/              包：data / metrics / analyze / diagnose / baselines / errors / table
tests/                   口径回归测试（防“42% 假分”重演）
docs/REPORT.md           5–10 页分析报告
```

## 复现约定

- `data/` 只读，永不修改；派生结果全部写 `out/`
- 每条预测落盘（id / gold / pred / score），只打印到终端的数字等于没跑
- 所有分数必须带分母与 chance level
- 数据不入仓：`download_data.py` + `SHA256SUMS`

## License

TBD
