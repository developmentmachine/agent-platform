"""HTTP adapter — FastAPI 入口（按 AgentRegistry 自动装配路由）。"""
from agent_platform.adapters.http.api.app import create_app
from agent_platform.adapters.http.api.routes import app

__all__ = ["app", "create_app"]
