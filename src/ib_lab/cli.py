"""命令行入口：python -m ib_lab <command> [options]"""
import argparse

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ib_lab",
        description="InfiniteBench 数据体检：分析数据、跑基线、汇总实验表",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--config", default=None, help="配置文件路径（默认 configs/default.yaml）")
    sub = p.add_subparsers(dest="command", required=True, metavar="<command>")

    a = sub.add_parser("analyze", help="体检：扫描数据集 -> out/samples.csv 等")
    a.set_defaults(func=_analyze)

    d = sub.add_parser("diagnose", help="数据缺陷分诊 P1-P7")
    d.set_defaults(func=_diagnose)

    b = sub.add_parser("baseline", help="跑基线")
    b.add_argument("kind", choices=["offline", "api"], help="offline=无模型基线; api=模型基线")
    b.add_argument("--model", action="append", default=None, help="仅 api：模型 id，可重复")
    b.add_argument("--n", type=int, default=None, help="仅 api：每任务抽样条数")
    b.add_argument("--tasks", nargs="*", default=None, help="只跑指定任务")
    b.set_defaults(func=_baseline)

    t = sub.add_parser("table", help="汇总成实验表")
    t.set_defaults(func=_table)

    f = sub.add_parser("failure", help="失败分析：为什么没拿满")
    f.set_defaults(func=_failure)

    q = sub.add_parser("qtypes", help="问题类型分类：哪类问题更难")
    q.set_defaults(func=_qtypes)

    r = sub.add_parser("report", help="生成报告")
    r.set_defaults(func=_report)
    return p


def _analyze(args, cfg):
    from . import analyze
    return analyze.run(cfg)


def _diagnose(args, cfg):
    from . import diagnose
    return diagnose.run(cfg)


def _baseline(args, cfg):
    if args.kind == "offline":
        from .baselines import offline
        return offline.run(cfg, tasks=args.tasks)
    from .baselines import api
    return api.run(cfg, models=args.model, n=args.n, tasks=args.tasks)


def _table(args, cfg):
    from . import table
    return table.run(cfg)


def _failure(args, cfg):
    from . import failure
    return failure.run(cfg)


def _qtypes(args, cfg):
    from . import qtypes
    return qtypes.run(cfg)


def _report(args, cfg):
    from . import report
    return report.run(cfg)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    from .config import load
    cfg = load(args.config)
    return args.func(args, cfg) or 0
