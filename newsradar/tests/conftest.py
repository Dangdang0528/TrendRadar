# coding=utf-8
"""pytest 公共夹具:为整个测试会话准备隔离环境(临时工作目录 + SQLite)

注意:环境变量必须在导入 app.* 之前设置,因为 app.config / app.db 在导入期
读取配置并创建引擎。
"""

import os
import shutil
import tempfile
from pathlib import Path

# ---- 1. 隔离工作目录:复制 trendradar 的 config/(供抓取阶段读取)----
_TEST_ROOT = tempfile.mkdtemp(prefix="newsradar_test_")
shutil.copytree("/workspace/config", os.path.join(_TEST_ROOT, "config"))

# ---- 2. 环境变量 ----
os.environ["APP_ENV"] = "dev"
os.environ["DEBUG"] = "true"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_ROOT}/test.db"
os.environ["TRENDRADAR_WORK_DIR"] = _TEST_ROOT
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "test-cred-key")
os.environ.pop("AI_API_KEY", None)  # 默认让 AI 步骤处于关闭态,由用例按需开启

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def work_dir() -> str:
    return _TEST_ROOT


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def pytest_configure(config: pytest.Config) -> None:
    Path(_TEST_ROOT).mkdir(parents=True, exist_ok=True)