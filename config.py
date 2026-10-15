"""集中配置常量，避免散落在 app / services 中。"""

from pathlib import Path

EXPECTED_RULE_COUNT = 49
DB_PATH = Path("audit.db")
RUNS_DIR = Path("runs")

DEFAULT_MAX_WORKERS = 5

DOWNLOAD_RETRY_COUNT = 3
DOWNLOAD_RETRY_DELAY = 3
DOWNLOAD_TIMEOUT = 60

API_HOST = "0.0.0.0"
API_PORT = 8000
API_VERSION = "2.0.0"
