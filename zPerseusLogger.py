import os
import sys
import logging
from logging.handlers import RotatingFileHandler

# ==================== 配置区 ====================
LOG_DIR = "logs"             # 指定日志文件夹名称（也可以用绝对路径，如 "D:/my_logs"）
LOG_FILE_NAME = "app.log"    # 主日志文件名
MAX_BYTES = 5 * 1024 * 1024  # 单个文件最大 5MB
BACKUP_COUNT = 20             # 最多保留 5 个分卷备份
# ================================================

class LoggerWriter:
    """把 print 的输出转发给 logging 处理器"""
    def __init__(self, logger_func):
        self.logger_func = logger_func
        self._buffer = ''

    def write(self, message):
        self._buffer += message
        while '\n' in self._buffer:
            line, self._buffer = self._buffer.split('\n', 1)
            if line:
                self.logger_func(line)

    def flush(self):
        if self._buffer:
            self.logger_func(self._buffer)
            self._buffer = ''

# 防重复初始化检查
if not isinstance(sys.stdout, LoggerWriter):
    # 1. 自动创建指定的日志文件夹（如果不存在）
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, LOG_FILE_NAME)  # 拼接完整的日志文件路径

    # 2. 创建全局 Logger
    logger = logging.getLogger("GlobalPrintLogger")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # 3. 控制台 Handler（屏幕继续显示 print 内容）
    console_handler = logging.StreamHandler(sys.__stdout__)
    console_handler.setFormatter(logging.Formatter('%(message)s'))

    # 4. 指定文件夹的分卷文件 Handler
    file_handler = RotatingFileHandler(
        filename=log_path,    # <--- 这里传入了带文件夹的路径
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))

    # 5. 挂载 Handler
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # 6. 接管全局 stdout 和 stderr
    sys.stdout = LoggerWriter(logger.info)
    sys.stderr = LoggerWriter(logger.error)
