"""Logging utilities.

目标：
  - 将关键操作和错误都记录到一个日志文件，便于现场分析。
  - 兼容源码运行与 PyInstaller（one-folder / one-file）。

实现：
  - Root logger + RotatingFileHandler（避免日志无限增大）
  - 记录未捕获异常（sys.excepthook）
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import tempfile
from datetime import datetime
from typing import Optional


_CONFIGURED = False
_LOG_PATH: Optional[str] = None


def _safe_mkdir(p: str) -> bool:
    try:
        os.makedirs(p, exist_ok=True)
        return True
    except Exception:
        return False


def _try_open_for_append(path: str) -> bool:
    try:
        with open(path, 'a', encoding='utf-8'):
            pass
        return True
    except Exception:
        return False


def _default_log_path() -> str:
    """Choose a writable log file path.

    Priority:
      1) logs/ next to executable (portable use)
      2) %LOCALAPPDATA%\PersonnelRegister\logs (recommended on Windows)
      3) temp directory
    """
    # 1) Next to executable
    exe_dir = None
    try:
        exe_dir = os.path.dirname(sys.executable)
    except Exception:
        exe_dir = None
    if exe_dir:
        p1_dir = os.path.join(exe_dir, 'logs')
        if _safe_mkdir(p1_dir):
            p1 = os.path.join(p1_dir, 'personnel_register.log')
            if _try_open_for_append(p1):
                return p1

    # 2) LocalAppData
    lad = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA')
    if lad:
        p2_dir = os.path.join(lad, 'PersonnelRegister', 'logs')
        if _safe_mkdir(p2_dir):
            p2 = os.path.join(p2_dir, 'personnel_register.log')
            if _try_open_for_append(p2):
                return p2

    # 3) Temp
    p3_dir = os.path.join(tempfile.gettempdir(), 'PersonnelRegister', 'logs')
    _safe_mkdir(p3_dir)
    return os.path.join(p3_dir, 'personnel_register.log')


def get_log_path() -> str:
    global _LOG_PATH
    if _LOG_PATH:
        return _LOG_PATH
    _LOG_PATH = _default_log_path()
    return _LOG_PATH


def setup_logging(level: int = logging.INFO) -> str:
    """Configure application logging once.

    Returns:
        log_file_path
    """
    global _CONFIGURED
    if _CONFIGURED:
        return get_log_path()

    log_path = get_log_path()
    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter(
        fmt='%(asctime)s.%(msecs)03d | %(levelname)s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    # Rotate at 5MB, keep 5 backups.
    handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8',
    )
    handler.setFormatter(fmt)
    handler.setLevel(level)
    root.addHandler(handler)

    # Also log to stderr when running from source (useful for developers)
    if getattr(sys, 'frozen', False) is False:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        sh.setLevel(level)
        root.addHandler(sh)

    # Hook unhandled exceptions
    def _excepthook(exc_type, exc, tb):
        logging.getLogger('unhandled').exception('Unhandled exception', exc_info=(exc_type, exc, tb))
        # Keep default behavior
        try:
            sys.__excepthook__(exc_type, exc, tb)
        except Exception:
            pass

    sys.excepthook = _excepthook

    logging.getLogger(__name__).info('Logging initialized. log_file=%s', log_path)
    _CONFIGURED = True
    return log_path


def get_logger(name: str) -> logging.Logger:
    """Get a logger and ensure logging is configured."""
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(name)
