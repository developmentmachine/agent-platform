"""推送 provider 抽象层。

新增推送渠道只需：
1. 继承 PushProvider
2. 实现 push() 和 test() 方法
3. 在 get_push_provider() 中注册
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

from agent_platform.domain.models import Recap


class PushProvider(ABC):
    @abstractmethod
    def push(self, recap: Recap) -> bool:
        """推送复盘内容，返回 True 表示成功。"""
        ...

    @abstractmethod
    def test(self) -> bool:
        """发送测试消息，验证配置是否正确。"""
        ...


def get_push_provider(
    settings: object,
    *,
    render_markdown: Optional[Callable[[Recap], str]] = None,
    render_text: Optional[Callable[[Recap], str]] = None,
) -> "PushProvider | None":
    """根据 settings 返回合适的 push provider，未配置时返回 None。

    render_markdown / render_text 由调用方（agent）注入，
    平台层不依赖任何 agent 的 render 实现。
    """
    from agent_platform.config.settings import Settings
    s: Settings = settings  # type: ignore[assignment]

    if s.push_enabled and s.wxwork_webhook_url:
        from agent_platform.infra.push.wechat import WechatWorkProvider

        if render_markdown is None or render_text is None:
            raise ValueError(
                "render_markdown and render_text are required for WechatWork push; "
                "the calling agent must inject its own render functions."
            )
        return WechatWorkProvider(
            webhook_url=s.wxwork_webhook_url,
            render_markdown=render_markdown,
            render_text=render_text,
            fallback_text=s.push_fallback_text,
        )

    return None
