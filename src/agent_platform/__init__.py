"""agent_platform — 企业级 A 股日终复盘智能体"""
__version__ = "1.0.0"

# Monolith 启动时自动注册 core 接口的实现
try:
    from agent_platform.bootstrap import bootstrap
    bootstrap()
except Exception:
    pass  # 独立 core 包环境下 bootstrap 不可用，正常
