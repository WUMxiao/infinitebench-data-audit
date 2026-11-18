# 项目状态（2026-11-18）

> 一句话：**离线基线完全复现，API 全量 561 条已跑完（11 任务 × 50 条），失败分析与问题类型分类已完成；实验表、报告、GitHub 推送还没做。**

---

## 1. 交付要求对照

| # | 要求 | 状态 | 说明 |
|---|---|---|---|
| 1 | 分析数据集 | ✅ 完成 | 三张表与参考实现逐字节一致 |
| 2 | 书写第一张实验表 | ✅ 完成 | 74 行（71 done + 3 planned），csv/xlsx/md |
| 3 | 跑基线 | 🟡 部分 | 离线 5 个 ✅；API 只跑了 160 条（试水规模） |
| 4 | 问题分类 ≥5 种 | ✅ 超额 | 三层：数据缺陷 P1–P7、模型错题 F0–F6、问题类型 L1×L2 |
| 5 | 基线小批→记录→大规模→比例 | ✅ 完成 | 小批 160 → 扩量 560 → 比例统计 |
| 6 | B 语义（问题类型分类） | ✅ 完成 | 3946 条全覆盖，抽检 98% |
| 7 | GitHub 仓库（代码+报告） | 🟡 本地齐备 | 报告已写，未建仓 push |

---

## 2. 仓库结构

```
infinitebench-data-audit/
├── README.md                 快速开始（骨架，待补结果）
├── requirements.txt
├── configs/default.yaml      数据路径、100k 截断、模型、抽样、seed
├── download_data.py          拉 2.3 GB 数据 + SHA256SUMS
├── src/ib_lab/
│   ├── config.py             yaml + .env + IB_DATA/IB_OUT 覆盖
│   ├── data.py               流式读取 / 规范化 / 截断 / 指纹
│   ├── metrics.py            官方口径（含多答案拆分）
│   ├── analyze.py            体检
│   ├── diagnose.py           P1–P7 + Math.Find 口径复核
│   ├── baselines/offline.py  5 个离线基线
│   ├── baselines/api.py      gpt-6-sol + 缓存 + 并发 + rescore
│   ├── failure.py            F0–F6 + F5 子类
│   ├── qtypes.py             问题类型 L1/L2
│   ├── pilot_analysis.py     存量二次分析（CI/成本/正则对比）
│   ├── table.py              ⏳ 空壳
│   └── report.py             ⏳ 空壳
├── tests/test_metrics.py     5 passed
├── scripts/canary.py         单条探针
└── docs/
    ├── FAILURE_ANALYSIS.md   失败例子（每类 3 个）
    └── PILOT_ANALYSIS.md     五项二次分析
```

**commits（10）**

```
486de72 fix(metrics): 拆分 ';' 分隔的多答案 + F5 再细分
0cebbe1 feat(pilot): 存量结果二次分析（零成本）
a3a3425 feat(qtypes): 问题类型分类 L1+L2
8665a1e feat(api): prompt v2 —— 把 options 送进 prompt
ce22272 feat(api): gpt-6-sol 基线 + 失败分析（小批 120 条）
3d939d7 chore(api): .env 模板 + 自动加载
8866065 feat(diagnose): 数据缺陷分诊 + P3 复核
97e14e2 feat(baseline): 迁移 5 个离线基线
0308509 feat(analyze): 迁移体检模块
837eca6 chore: 仓库骨架
```

---

## 3. 已有数字

### 数据（3946 条 / 12 任务 / 2.33 GB）

- 4 个任务零模型可解：PassKey / Number / KV / Math.Find 正则 100%
- 70 段上下文跨任务复用，涉及 582 条（14.7%）
- Zh.QA 中位保留 19.6%，p10 仅 5.7%，最长 356 万 token 保留 3.6%
- Math.Find 口径混用：排名类去重 200/200，median 原序列 50/50
- 选择题否定式仅 2/229

### 离线基线（逐字节复现）

12 任务 × 5 基线 = 60 行，`baseline_results.csv` 与参考实现 SHA256 相同。

### API 全量（gpt-6-sol，v3，11 任务 × 50 条）

| 任务 | n | 分数 |
|---|---|---|
| Code.Run | 50 | **98.0** |
| En.Dia | 50 | 96.0 |
| Code.Debug | 50 | 94.0 |
| En.MC | 50 | 92.0 |
| KV | 50 | 92.0 |
| Number | 50 | 90.0 |
| PassKey | 50 | 88.0 |
| Math.Find | 50 | 88.0 |
| En.QA | 50 | 59.6 |
| Zh.QA | 50 | 48.0 |
| En.Sum | 50 | 11.6 |
| Math.Calc | 10 | 0（已排除出排名） |

合计 561 条调用，答对 427 条（**76.1%**），v3 token 约 5000 万，成本约 $125。

**prompt 演进（同任务对比）**：

| 任务 | v1 | v2 | v3 |
|---|---|---|---|
| En.MC | 0.00 | 0.90 | **0.92** |
| Code.Debug | 0.30 | 0.80 | **0.94** |
| Code.Run | 0.50 | 0.30 | **0.98** |
| En.Sum | 0.09 | 0.14 | 0.12 |

### 失败构成（v3，561 条）

| 类别 | 条数 | 占比 |
|---|---|---|
| 答对 | 427 | 76.1% |
| F5 其他（已细分） | 82 | 14.6% |
| F1 检索失败 | 26 | 4.6% |
| F4 拒答 | 11 | 2.0% |
| F6 输出不完整 | 5 | 0.9% |
| F2 截断丢失 | 5 | 0.9% |
| F0 报错 | 4 | 0.7% |
| F3 格式失败 | 1 | **0.2%** |

F5 细分：摘要指标问题 50、真推理错 17、计算错位 9、选项错 3、同义短答 2、反问 1。

**关键结论**：修完 prompt 后格式失败从 11.2% 降到 **0.2%**；真正属于“模型不会”的只有 **29 条（5.2%）**。

### 问题类型

3946 条 → L1 8 类 / L2 25 类；50 条人工抽检 49 条正确（98%）。

---

## 4. 关键发现（可直接进报告）

1. **模型打不过三行正则**：PassKey 90 / Number 70 / KV 90 / Math.Find 50，正则全 100（同样本对比）。
2. **“51 分”里一半不是模型能力问题**：63/78 条失败来自指标、prompt、输出格式。
3. **En.Sum 的 ROUGE 天花板极低**：20 条低分全部是“内容对、ROUGE 低”。
4. ** prompt 漏传 options 是 v1 的硬伤**：修完后 En.MC 从 0 到 90。
5. **n=10 时 CI 约 ±30 点**：任何任务间比较都不成立，必须扩量。
6. **Code.Run 题面与判分器冲突**：题面要求以 `The return value is:` 结尾，判分器取最后一个词。

---

## 5. 未完成

| 项 | 预估 | 备注 |
|---|---|---|
| 大规模扩量 | $70–240，30–90 分钟 | 30/50/100 条/任务三档 |

| 报告 `docs/REPORT.md` | 3–4 小时 | 5–10 页 |
| GitHub 建仓 + push | 30 分钟 | 需仓库名与账号确认 |
| CI（pytest） | 30 分钟 | `.github/workflows/test.yml` |
| 第二家模型 | — | 中转无 Claude，需另找网关 |

---

## 6. 待决策

1. **扩量规模**：30 / 50 / 100 条每任务。
2. **Code.Run 怎么处理**：改 prompt 让答案在最后，还是自定义 scorer 取第一个数。
3. **En.Sum 指标**：保留 ROUGE 仅作可比，还是换 BERTScore / 人工评。
4. **Math.Calc 预算**：`max_tokens` 给到 8k 还是直接排除。
5. **数据不入仓**：clone 后必须跑 `download_data.py`（2.3 GB）。

---

## 7. 复现命令

```bash
export PYTHONPATH=src
export IB_DATA=/path/to/infinitebench/data     # 或放到 ./data
python -m ib_lab analyze
python -m ib_lab diagnose
python -m ib_lab baseline offline
python -m ib_lab baseline api --model gpt-6-sol --n 10
python -m ib_lab baseline api --rescore        # 改了判分口径后重算
python -m ib_lab failure
python -m ib_lab qtypes
python -m ib_lab pilot
```

## 8. 产物索引

| 文件 | 内容 |
|---|---|
| `out/task_summary.csv` | 12 任务体检 |
| `out/problem_summary.csv` | 27 列诊断指标 |
| `out/baseline_results.csv` | 60 行离线基线 |
| `out/api_summary.csv` | API 任务级汇总 |
| `out/failure_log.csv` | 逐条失败记录 |
| `out/failure_ratio.csv` / `failure_subratio.csv` | 失败比例 / F5 细分 |
| `out/question_types.csv` | 3946 条类型标签 |
| `out/type_performance.csv` | 类型 × 模型分数 |
| `docs/FAILURE_ANALYSIS.md` | 失败例子 |
| `docs/PILOT_ANALYSIS.md` | 五项二次分析 |
