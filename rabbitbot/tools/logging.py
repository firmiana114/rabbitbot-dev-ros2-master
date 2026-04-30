# -*- coding: utf-8 -*-
import os
import sys
import logging
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler


class FileLogger:
    """
    极简单例日志器
    用法：
        from my_logger import MyLogger
        logger = MyLogger().get_logger()
        logger.info("hello")
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self,
                 log_dir: str = None,
                 log_name: str = None,
                 file_level: int = logging.DEBUG,
                 backup_days: int = 15):
        if self._initialized:          # 保证只初始化一次
            return
        self._initialized = True

        # 1. 日志目录（默认: 当前文件所在目录/logs）
        if log_dir is None:
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)

        # 2. 日志文件名（默认: 脚本名_日期.log）
        if log_name is None:
            script = os.path.splitext(os.path.basename(sys.argv[0]))[0] or "console"
            log_name = f"{script}_{datetime.now():%Y-%m-%d}.log"
        self.log_path = os.path.join(log_dir, log_name)

        # 3. 日志格式
        fmt = "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(threadName)s | %(filename)s:%(lineno)d | %(funcName)s() | %(message)s"
        date_fmt = "%Y-%m-%d %H:%M:%S"
        formatter = logging.Formatter(fmt, date_fmt)

        # 5. 文件处理器（按天切割）
        file_handler = TimedRotatingFileHandler(
            filename=self.log_path,
            when="midnight",
            interval=1,
            backupCount=backup_days,
            encoding="utf-8",
            delay=False,
            utc=False
        )
        file_handler.setLevel(file_level)
        file_handler.setFormatter(formatter)
        file_handler.suffix = "%Y-%m-%d.log"

        # 6. 创建 logger
        self._logger = logging.getLogger("FileLogger")
        self._logger.setLevel(logging.DEBUG)  # 全局最低
        self._logger.addHandler(file_handler)
        self._logger.propagate = False        # 防止重复打印

    def get_logger(self) -> logging.Logger:
        return self._logger


# 懒人用法：直接导出单例 logger
logger = FileLogger(log_dir="logs").get_logger()
