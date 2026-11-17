"""配置读取：yaml + 环境变量，禁止在业务代码里硬编码路径或模型。"""
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "configs" / "default.yaml"


@dataclass
class Config:
    raw: dict
    path: Path

    # --- 常用快捷访问 -------------------------------------------------
    @property
    def tasks(self) -> list:
        return list(self.raw["dataset"]["tasks"])

    @property
    def truncate_tokens(self) -> int:
        return int(self.raw["dataset"]["truncate_tokens"])

    @property
    def truncate_manner(self) -> str:
        return self.raw["dataset"]["truncate_manner"]

    @property
    def models(self) -> list:
        return list(self.raw["baseline"]["models"])

    @property
    def sample_per_task(self) -> int:
        return int(self.raw["baseline"]["sample_per_task"])

    @property
    def seed(self) -> int:
        return int(self.raw["baseline"]["seed"])

    # --- 路径 ---------------------------------------------------------
    def path_of(self, key: str) -> Path:
        """paths.data / paths.out，相对仓库根目录。"""
        return (REPO_ROOT / self.raw["paths"][key]).resolve()

    def source_url(self, task: str) -> str:
        return self.raw["dataset"]["source"].format(task=task)

    # --- 密钥 ---------------------------------------------------------
    def api_key(self, provider: str) -> str:
        env_name = self.raw["env"][f"{provider}_key"]
        key = os.environ.get(env_name, "")
        if not key:
            raise RuntimeError(
                f"缺少环境变量 {env_name}（provider={provider}）。"
                f"离线基线不需要 key：python -m ib_lab baseline offline"
            )
        return key


def load(path: str | None = None) -> Config:
    p = Path(path).resolve() if path else DEFAULT_CONFIG
    if not p.exists():
        raise FileNotFoundError(f"配置文件不存在: {p}")
    with open(p, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Config(raw=raw, path=p)
