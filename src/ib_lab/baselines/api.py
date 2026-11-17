"""API 基线：OpenAI / Anthropic。

约定（第 5 步实现）：
    * 截断预算统一 100k，每条记录实际保留比例
    * 缓存键 = sha1(sample_id | model | prompt_ver | budget)，重跑不重复花钱
    * 每条落盘一行 jsonl：raw / parsed / score / tokens / latency / cost
    * 失败重试 3 次，指数退避；解析失败单独统计，不算 0 分混进去
    * 20 条/任务是试水；差距 >25 点的任务再扩到 100 条
"""


def run(cfg, models=None, n=None, tasks=None) -> int:
    raise NotImplementedError("第 5 步实现")
