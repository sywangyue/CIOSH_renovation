"""
CIOSH 情报雷达 · 配置模块
从 .env 读取所有运行时配置，对外暴露单一 Config 对象。
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# .env 与本文件同目录
_BASE_DIR = Path(__file__).parent.resolve()
load_dotenv(dotenv_path=_BASE_DIR / ".env")


class Config:
    # ── 项目路径 ──────────────────────────────────────────────
    BASE_DIR: Path = _BASE_DIR
    DB_PATH: Path = Path(os.getenv("DB_PATH", str(_BASE_DIR / "data" / "ciosh_intel.db")))
    KEYWORD_DB_PATH: Path = Path(os.getenv("KEYWORD_DB_PATH", str(_BASE_DIR / "keyword_db.json")))
    LOG_DIR: Path = Path(os.getenv("LOG_DIR", str(_BASE_DIR / "logs")))

    # ── DeepSeek ──────────────────────────────────────────────
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")

    # ── Tavily ────────────────────────────────────────────────
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

    # ── 163 邮件 ──────────────────────────────────────────────
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.163.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "465"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    MAIL_TO: str = os.getenv("MAIL_TO", "")
    MAIL_CC: str = os.getenv("MAIL_CC", "")   # 抄送，多个地址用逗号分隔，可为空

    # ── 采集参数 ──────────────────────────────────────────────
    MAX_RESULTS_PER_KEYWORD: int = int(os.getenv("MAX_RESULTS_PER_KEYWORD", "5"))
    LAYER2_MIN_SCORE: int = int(os.getenv("LAYER2_MIN_SCORE", "1"))
    DEDUP_THRESHOLD: int = int(os.getenv("DEDUP_THRESHOLD", "85"))

    # ── Layer3 分桶限额（Bucket Cap）────────────────────────────
    # Tavily 桶：国际内容，默认 15 条
    # 国内桶：百度/知乎/B站合并竞争，默认 25 条
    # 每日 Layer3 总量上限 = CAP_TAVILY + CAP_DOMESTIC ≤ 40 条
    LAYER3_CAP_TAVILY:   int = int(os.getenv("LAYER3_CAP_TAVILY", "15"))
    LAYER3_CAP_DOMESTIC: int = int(os.getenv("LAYER3_CAP_DOMESTIC", "25"))
    SEED_LAYER3_CAP:     int = int(os.getenv("SEED_LAYER3_CAP", "50"))

    def validate(self) -> list[str]:
        """返回缺失的必填配置项列表，空列表表示配置完整。"""
        missing = []
        if not self.DEEPSEEK_API_KEY:
            missing.append("DEEPSEEK_API_KEY")
        if not self.TAVILY_API_KEY:
            missing.append("TAVILY_API_KEY")
        if not self.SMTP_USER:
            missing.append("SMTP_USER")
        if not self.SMTP_PASSWORD:
            missing.append("SMTP_PASSWORD")
        if not self.MAIL_TO:
            missing.append("MAIL_TO")
        return missing


_config: "Config | None" = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config
