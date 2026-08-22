"""
==================== 使用教程 ====================
1. 基本逻辑：
   - 导入本模块后，会自动全局重定向 sys.stdout (普通 print) 为 [INFO] 级别日志。
   - 重定向 sys.stderr (如未捕获的报错/异常) 为 [ERROR] 级别日志。

2. 常用用法：
   - 普通打印 (INFO 级别)：
     print("这是一条普通消息")  
     --> 输出: 2026-08-22 10:00:00 - [INFO] - 这条是普通消息

   - 打印警告/其他级别 (推荐方式)：
     import logging
     logging.warning("这是一条警告消息")
     logging.debug("这是一条调试消息")

   - 方便的快捷函数 (像 print 一样输出警告)：
     logger_print("这是一条警告消息", level="warning")
     logger_print("发生重大错误！", level="critical")
==================================================
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler

# ==================== 配置区 ====================
from zConfig import get_config

# 配置区
LOG_DIR = get_config("logger.log_dir", default="logs")
LOG_FILE_NAME = get_config("logger.log_file_name", default="app.log")
MAX_BYTES = get_config("logger.max_bytes", default=512 * 1024)
BACKUP_COUNT = get_config("logger.backup_count", default=20)
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
            if line.strip():
                self.logger_func(line)

    def flush(self):
        if self._buffer.strip():
            self.logger_func(self._buffer)
            self._buffer = ''

# 防重复初始化检查
if not isinstance(sys.stdout, LoggerWriter):
    # 1. 自动创建指定的日志文件夹
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, LOG_FILE_NAME)

    # 2. 创建全局 Logger
    logger = logging.getLogger("GlobalPrintLogger")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # ========== 关键修复：判断控制台是否存在 ==========
    # pythonw 环境 sys.__stdout__ 为 None，跳过控制台handler
    if sys.__stdout__ is not None:
        console_handler = logging.StreamHandler(sys.__stdout__)
        console_handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
        logger.addHandler(console_handler)

    # 3. 文件日志 Handler（始终启用）
    file_handler = RotatingFileHandler(
        filename=log_path,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    # 分级日志输出格式
    file_handler.setFormatter(logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s'))
    logger.addHandler(file_handler)

    # 4. 接管全局 stdout 和 stderr
    sys.stdout = LoggerWriter(logger.info)
    sys.stderr = LoggerWriter(logger.error)

def logger_print(message, level="warning"):
    """
    可选的快捷打印函数：像 print 一样输出警告、调试或严重错误日志
    支持级别: 'debug', 'info', 'warning' (或 'warn'), 'error', 'critical'
    """
    lvl_map = {
        'debug': logger.debug,
        'info': logger.info,
        'warning': logger.warning,
        'warn': logger.warning,
        'error': logger.error,
        'critical': logger.critical
    }
    log_func = lvl_map.get(str(level).lower(), logger.warning)
    log_func(message)