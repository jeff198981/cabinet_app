from __future__ import annotations

import configparser
import os
import sys
from dataclasses import dataclass


def _installed_odbc_drivers() -> list[str]:
    """Return ODBC driver names visible to pyodbc on this machine."""
    try:
        import pyodbc  # type: ignore

        return list(pyodbc.drivers())
    except Exception:
        return []


def installed_odbc_drivers() -> list[str]:
    """Public helper for UI/error reporting."""
    return _installed_odbc_drivers()


def choose_sqlserver_driver(preferred: str) -> str:
    """Pick a SQL Server ODBC driver.

    - If `preferred` exists locally, use it.
    - If `preferred` is empty or 'auto', pick the best available.
    - If `preferred` doesn't exist, fallback to the best available.

    Raises RuntimeError if no SQL Server ODBC driver is available.
    """
    preferred = (preferred or '').strip()
    drivers = _installed_odbc_drivers()

    # Fast path: exact match
    if preferred and preferred.lower() != 'auto':
        for d in drivers:
            if d.lower() == preferred.lower():
                return d

    # Best-effort fallbacks (most modern first)
    fallbacks = [
        'ODBC Driver 18 for SQL Server',
        'ODBC Driver 17 for SQL Server',
        'ODBC Driver 13 for SQL Server',
        'ODBC Driver 11 for SQL Server',
        'SQL Server',
    ]
    for want in fallbacks:
        for d in drivers:
            if d.lower() == want.lower():
                return d

    # As a last resort, use any driver containing "SQL Server"
    for d in drivers:
        if 'sql server' in d.lower():
            return d

    raise RuntimeError(
        '未检测到可用的 SQL Server ODBC 驱动。请安装 Microsoft ODBC Driver 17/18 for SQL Server，'
        '或在 db_config.ini 的 driver= 指定已安装的驱动名称。'
    )


def base_dir() -> str:
    # PyInstaller onefile puts resources under sys._MEIPASS
    return getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))


@dataclass
class SqlServerConfig:
    server: str
    port: int
    database: str
    username: str
    password: str
    driver: str = 'ODBC Driver 17 for SQL Server'
    trust_server_certificate: str = 'yes'

    def to_odbc_conn_str(self) -> str:
        # SQL Server ODBC: SERVER=host,port
        server_part = f"{self.server},{self.port}" if self.port else self.server
        driver_name = choose_sqlserver_driver(self.driver)
        return (
            f"DRIVER={{{driver_name}}};"
            f"SERVER={server_part};"
            f"DATABASE={self.database};"
            f"UID={self.username};PWD={self.password};"
            f"TrustServerCertificate={self.trust_server_certificate};"
        )


def config_path() -> str:
    # For editable config, prefer executable folder (onefile) or script folder.
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else base_dir()
    return os.path.join(exe_dir, 'db_config.ini')


def load_sqlserver_config() -> SqlServerConfig:
    path = config_path()
    if not os.path.exists(path):
        raise FileNotFoundError(f'Cannot find db_config.ini at: {path}')

    cp = configparser.ConfigParser()
    # tolerate non-utf8 ini written by external tools
    read_ok = False
    for enc in ('utf-8', 'utf-8-sig', 'gbk'):
        try:
            with open(path, 'r', encoding=enc) as f:
                cp.read_file(f)
            read_ok = True
            break
        except UnicodeDecodeError:
            continue
    if not read_ok:
        # fallback to binary read with replacement
        with open(path, 'rb') as f:
            data = f.read().decode('utf-8', errors='replace')
        cp.read_string(data)
    sec = cp['sqlserver']

    return SqlServerConfig(
        server=sec.get('server', '127.0.0.1').strip(),
        port=sec.getint('port', 1433),
        database=sec.get('database', 'OperRoom').strip(),
        username=sec.get('username', 'sa').strip(),
        password=sec.get('password', '').strip(),
        driver=sec.get('driver', 'ODBC Driver 17 for SQL Server').strip(),
        trust_server_certificate=sec.get('trust_server_certificate', 'yes').strip(),
    )
