"""``python -m agent_platform.adapters.wecom`` — 启动企微智能机器人 WebSocket 长连接。"""
from __future__ import annotations

import logging
import sys

from agent_platform.adapters.wecom.connector import (
    WecomAiBotConnector,
    load_wecom_options_from_env,
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
    opts = load_wecom_options_from_env()
    if not opts.enabled:
        logging.getLogger(__name__).error("WECOM_AIBOT_ENABLED=false，退出")
        return 1
    if not (opts.bot_id and opts.secret):
        logging.getLogger(__name__).error("缺少 WECOM_AIBOT_BOT_ID / WECOM_SECRET")
        return 1

    runtime = create_runtime(settings=settings)
    try:
        WecomAiBotConnector(options=opts, runtime=runtime).start()
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("wecom bot stopped")
    finally:
        runtime.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
