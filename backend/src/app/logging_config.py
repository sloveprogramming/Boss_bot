# ═══════════════════════════════════════════════════════════════
# 【小白导读】统一日志配置。
#   · Python logging 概念：任何模块里 logging.getLogger(__name__) 拿一个"记录器"往里写日志；
#     本文件的 setup_logging() 在应用启动时执行一次，决定日志"写到哪、什么格式、什么级别"。
#   · 双输出：控制台（开发时实时看）+ backend/logs/app.log（事后排查看）。
#   · 级别从低到高：DEBUG < INFO < WARNING < ERROR，由 .env 的 LOG_LEVEL 控制。
# ═══════════════════════════════════════════════════════════════
"""统一日志配置 — 控制台 + 文件双输出，格式统一

所有模块用 `logging.getLogger(__name__)` 获取 logger 即可，
本模块在应用启动时调用一次 setup_logging() 完成根 logger 配置。
"""
import logging
import sys
from pathlib import Path

from app.config import settings

_LOGGING_CONFIGURED = False

# 配置日志
def setup_logging() -> None:
    """配置根 logger：控制台 + 文件双输出，级别由 LOG_LEVEL 控制"""
    global _LOGGING_CONFIGURED # 确保只配置一次
    if _LOGGING_CONFIGURED: # 已配置，直接返回
        return
    # 配置日志级别
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台输出
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    # 文件输出（backend/logs/app.log）
    log_dir = Path(__file__).resolve().parents[2] / "logs"
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "app.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    _LOGGING_CONFIGURED = True
