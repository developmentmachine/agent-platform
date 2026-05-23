"""Shim → ``agent_platform.agents.stock_recap.render``（stock-recap 展示逻辑）。"""


def __getattr__(name: str):
    from agent_platform.agents import stock_recap

    return getattr(stock_recap.render, name)


def __dir__():
    from agent_platform.agents.stock_recap import render

    return sorted(dir(render))
