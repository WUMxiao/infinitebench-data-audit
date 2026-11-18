"""配置读取：yaml + 环境变量，禁止在业务代码里硬编码路径或模型。"""
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "configs" / "default.yaml"


def _load_dotenv() -> None:
    """极简 .env 加载器：KEY=VALUE，只补未设置的变量（不覆盖已有环境变量）。"""
    path = REPO_ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


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

    @property
    def data_dir(self) -> Path:
        """优先 IB_DATA：数据不入仓，本地可以直接指向已下载的目录。"""
        env = os.environ.get("IB_DATA")
        return Path(env).expanduser().resolve() if env else self.path_of("data")

    @property
    def out_dir(self) -> Path:
        env = os.environ.get("IB_OUT")
        return Path(env).expanduser().resolve() if env else self.path_of("out")

    def source_url(self, task: str) -> str:
        return self.raw["dataset"]["source"].format(task=task)

    # --- 密钥 ---------------------------------------------------------
    def api_key(self, provider: str) -> str:
        env_name = self.raw["env"][f"{provider}_key"]
        key = os.environ.get(env_name, "").strip()
        if not key or key.startswith("sk-在这里"):
            raise RuntimeError(
                f"缺少 {env_name}。请编辑仓库根的 .env 填入真实 key"
                f"（不要提交它）。离线基线不需要 key：python -m ib_lab baseline offline"
            )
        return key

    def base_url(self, provider: str) -> str:
        """中转地址，例如 https://xxx.com/v1；为空表示用官方默认地址。"""
        env_name = self.raw["env"][f"{provider}_base_url"]
        return os.environ.get(env_name, "").strip().rstrip("/")


def load(path: str | None = None) -> Config:
    p = Path(path).resolve() if path else DEFAULT_CONFIG
    if not p.exists():
        raise FileNotFoundError(f"配置文件不存在: {p}")
    with open(p, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Config(raw=raw, path=p)
