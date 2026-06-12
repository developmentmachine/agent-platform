FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RECAP_DB_PATH=/data/recap_system.db \
    RECAP_OUTPUT_DIR=/data/reports \
    RECAP_LOG_LEVEL=INFO \
    UV_BIN=/usr/local/bin/uv \
    TZ=Asia/Shanghai

# 安装 uv。业务依赖由 pyproject.toml 管理。
RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY stock-leaderboard/ ./stock-leaderboard/

# 采用 editable install，确保内置 prompts/skills 等源码资源可直接随镜像读取。
# python-dotenv / pillow / requests：微信公众号日终草稿与龙虎榜图片生成。
RUN uv pip install --system --no-cache -e . \
    && uv pip install --system --no-cache python-dotenv pillow requests \
    && apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /data/reports \
    && chown -R app:app /app /data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

CMD ["agent-platform", "stock-recap", "--serve", "--host", "0.0.0.0", "--port", "8000"]
