"""``python -m agent_platform.adapters.qq`` — 启动 QQ 机器人长连接。"""
from __future__ import annotations

import logging
import sys

from agent_platform.adapters.qq.connector import (
    QqBotConnector,
    load_qq_options_from_settings,
)
from agent_platform.config.settings import get_settings
from agent_platform.runtime.factory import create_runtime


def main() -> int:
    settings = get_settings()
    level = getattr(logging, str(settings.log_level).upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    opts = load_qq_options_from_settings(settings)
    if not opts.enabled:
        logging.getLogger(__name__).error("QQ_BOT_ENABLED=false，退出")
        return 1
    if not (opts.app_id and opts.app_secret):
        logging.getLogger(__name__).error(
            "缺少 QQ_BOT_APP_ID / QQ_BOT_CLIENT_SECRET（或 QQ_BOT_APP_SECRET）"
        )
        return 1

    runtime = create_runtime(settings=settings)
    try:
        QqBotConnector(options=opts, runtime=runtime).start()
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("qq bot stopped")
    finally:
        runtime.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
