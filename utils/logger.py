"""
日志模块
=====
基于标准库 logging，提供控制台和文件日志。
各模块通过 get_logger(__name__) 获取 logger 实例。
"""

import loggingimport sysfrom pathlib import Path# 日志格式
_CONSOLE_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_FILE_FORMAT = "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s"
_DATE_FORMAT = "%H:%M:%S"

# 日志级别 (可通过环境变量覆盖，默认 INFO)
_LOG_LEVEL = logging.INFO


class _ColoredFormatter(logging.Formatter):
    """控制台彩色输出（Windows/Linux 通用）。"""

    _COLORS = {
        logging.DEBUG: "\033[36m",      # 青色
        logging.INFO: "\033[32m",       # 绿色
        logging.WARNING: "\033[33m",    # 黄色
        logging.ERROR: "\033[31m",      # 红色
        logging.CRITICAL: "\033[41;37m",  # 白字红底
    }
    _RESET = "\033[0m"

    def format(self, record):
        color = self._COLORS.get(record.levelno, self._RESET)
        original = super().format(record)
        if sys.stdout.isatty() and sys.platform != "win32":
            # 非 Windows 终端支持 ANSI
            return f"{color}{original}{self._RESET}"
        return original


def _setup_root_logger():
    """配置根 logger（首次调用时执行一次）。"""
    logger = logging.getLogger()
    if logger.handlers:
        return  # 避免重复配置

    logger.setLevel(_LOG_LEVEL)

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(_ColoredFormatter(_CONSOLE_FORMAT, datefmt=_DATE_FORMAT))
    logger.addHandler(console_handler)

    # 文件处理器（可选，默认不开启）
    # _setup_file_handler(logger)


def _setup_file_handler(root_logger, log_dir: str = "logs"):
    """添加文件日志处理器（可按需启用）。"""
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(
        log_path / "agent.log",
        encoding="utf-8",
        mode="a",
    )
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt=_DATE_FORMAT))
    root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger 实例。

    用法:
        logger = get_logger(__name__)
        logger.info("消息")
        logger.error("出错了", exc_info=True)
    """
    _setup_root_logger()
    return logging.getLogger(name)
