#!/usr/bin/env python3
"""
每日自动流程：stock-recap 复盘 + 龙虎榜 → 微信公众号草稿箱
每交易日 17:00 由 cron 调用。

特性：
- 失败自动重试（最多 3 次，间隔递增）
- 全部失败时通过 webhook 通知用户
"""
import subprocess
import urllib.request
import json
import os
import sys
import glob
import random
import time
import traceback
from datetime import datetime
from pathlib import Path

# ─── 加载 .env（不依赖 python-dotenv）────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent  # stock-leaderboard/
_PROJECT_DIR = _SCRIPT_DIR.parent              # agent-platform/

def _load_env():
    """从 .env 文件加载环境变量（不覆盖已有的）"""
    for env_path in [
        Path("/opt/data/.env"),
        Path.home() / ".env",
        _PROJECT_DIR / ".env",
    ]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
            break

_load_env()

# MIMO LLM structured output retries can be slow; give 10 min budget
os.environ.setdefault("RECAP_AGENT_MAX_WALL_MS", "600000")

# ─── 重试 & 通知配置 ──────────────────────────────────────────────────────────
MAX_RETRIES = 3
RETRY_DELAYS = [60, 180, 300]  # 秒：1min, 3min, 5min

# Slack webhook（用于失败通知），从环境变量读取
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
# 备用：企业微信 webhook
WECHAT_WEBHOOK_URL = os.environ.get("WECHAT_WEBHOOK_URL", "")

# ─── 配置 ─────────────────────────────────────────────────────────────────────
WECHAT_APPID = "wx2fa955fe856dd1c9"
WECHAT_SECRET = "4ef2765ac8ee7e0ea0ee5f724179c052"
PROJECT_DIR = Path(__file__).resolve().parent.parent  # agent-platform/
LEADERBOARD_DIR = Path(__file__).resolve().parent      # stock-leaderboard/
AUTHOR = "Agent Platform"

# ─── 工具函数 ───────────────────────────────────────────────────────────────────

def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def run_cmd(cmd: list[str], cwd: str = None) -> tuple[bool, str]:
    """执行命令，返回 (成功, 输出)"""
    log(f"执行: {' '.join(cmd[:6])}...")
    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        cwd=cwd, timeout=1800, stdin=subprocess.DEVNULL,  # 30min, no TTY
    )
    if result.returncode != 0:
        log(f"失败 (rc={result.returncode}): {result.stdout[:500]}")
        return False, result.stdout
    return True, result.stdout

def get_access_token() -> str:
    """获取微信 access_token"""
    url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={WECHAT_APPID}&secret={WECHAT_SECRET}"
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())["access_token"]

def upload_image(token: str, image_path: str) -> tuple[str, str]:
    """上传图片到微信素材库，返回 (media_id, url)"""
    import http.client
    import mimetypes

    boundary = "----WebKitFormBoundary" + str(random.randint(100000, 999999))
    filename = os.path.basename(image_path)

    with open(image_path, "rb") as f:
        file_data = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="media"; filename="{filename}"\r\n'
        f"Content-Type: {mimetypes.guess_type(image_path)[0] or 'image/png'}\r\n"
        f"\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

    conn = http.client.HTTPSConnection("api.weixin.qq.com")
    conn.request("POST", f"/cgi-bin/material/add_material?access_token={token}&type=image",
                 body=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    resp = conn.getresponse()
    result = json.loads(resp.read())
    conn.close()

    if "media_id" not in result:
        raise Exception(f"上传失败: {result}")
    return result["media_id"], result.get("url", "")

def list_leaderboard_images(token: str) -> list[str]:
    """从素材库获取 leaderboard-title 开头的图片 media_id（用作封面）"""
    data = json.dumps({"type": "image", "offset": 0, "count": 50}).encode()
    req = urllib.request.Request(
        f"https://api.weixin.qq.com/cgi-bin/material/batchget_material?access_token={token}",
        data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as r:
        result = json.loads(r.read())

    ids = []
    for item in result.get("item", []):
        if item.get("name", "").startswith("leaderboard-title"):
            ids.append(item["media_id"])
    return ids

def create_draft(token: str, title: str, thumb_id: str, content: str) -> str:
    """创建微信草稿，返回 media_id"""
    draft = {
        "articles": [{
            "title": title,
            "author": AUTHOR,
            "thumb_media_id": thumb_id,
            "need_open_comment": 1,
            "only_fans_can_comment": 0,
            "content": content,
        }]
    }
    data = json.dumps(draft, ensure_ascii=False).encode()
    req = urllib.request.Request(
        f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}",
        data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as r:
        result = json.loads(r.read())

    if "media_id" not in result:
        raise Exception(f"创建草稿失败: {result}")
    return result["media_id"]

# ─── 复盘内容格式化 ──────────────────────────────────────────────────────────────

def format_recap_html(recap_text: str, leaderboard_url: str) -> str:
    """将复盘文本转为微信公众号 HTML"""
    # 简单转换：保留原有结构，加样式
    section_style = 'background:#1a1a2e;color:#fff;padding:12px 20px;border-radius:6px;font-size:22px;font-weight:bold;margin:30px 0 20px 0;'

    html = f'<p style="{section_style}">#1 行情复盘</p>\n'
    html += '<h2>【复盘基准日：' + datetime.now().strftime('%Y年%m月%d日') + '】</h2>\n'

    # 解析复盘文本
    lines = recap_text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('### '):
            html += f'<h3>{line[4:]}</h3>\n'
        elif line.startswith('## '):
            html += f'<h2>{line[3:]}</h2>\n'
        elif line.startswith('* **观点：**'):
            html += f'<p><strong>观点：</strong>{line[8:]}</p>\n'
        elif line.startswith('* **分析：**'):
            html += '<p><strong>分析：</strong></p>\n<ul>\n'
        elif line.startswith('    * '):
            html += f'<li>{line[6:]}</li>\n'
        elif line.startswith('- '):
            html += f'<li>{line[2:]}</li>\n'
        elif line.startswith('---'):
            html += '<hr/>\n'
        elif '仅供参考' in line:
            html += f'<p style="color:#999;font-size:12px;">{line}</p>\n'
        else:
            html += f'<p>{line}</p>\n'

    # 关闭可能未闭合的 ul
    if '<ul>' in html and '</ul>' not in html.split('<ul>')[-1]:
        html += '</ul>\n'

    html += f'\n<p style="{section_style}">#2 龙虎榜</p>\n'
    html += f'<p><img src="{leaderboard_url}" alt="龙虎榜" style="max-width:100%;" /></p>\n'

    return html

# ─── 失败通知 ───────────────────────────────────────────────────────────────────

def send_failure_notification(error_msg: str, attempt: int):
    """全部重试失败后，发送通知给用户"""
    today = datetime.now().strftime("%Y-%m-%d")
    text = (
        f"🚨 *微信公众号发布失败*\n"
        f"日期: {today}\n"
        f"重试次数: {attempt}/{MAX_RETRIES}\n"
        f"错误: {error_msg[:500]}\n"
        f"请手动检查或重跑。"
    )

    # 方式1: Slack webhook
    if SLACK_WEBHOOK_URL:
        try:
            data = json.dumps({"text": text}).encode()
            req = urllib.request.Request(
                SLACK_WEBHOOK_URL,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=10)
            log("✅ 失败通知已发送到 Slack")
        except Exception as e:
            log(f"⚠️ Slack 通知发送失败: {e}")

    # 方式2: 企业微信 webhook
    if WECHAT_WEBHOOK_URL:
        try:
            data = json.dumps({"msgtype": "text", "text": {"content": text}}).encode()
            req = urllib.request.Request(
                WECHAT_WEBHOOK_URL,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=10)
            log("✅ 失败通知已发送到企业微信")
        except Exception as e:
            log(f"⚠️ 企业微信通知发送失败: {e}")

    # 方式3: 无 webhook 时，打印到 stdout（cron 会自动投递）
    if not SLACK_WEBHOOK_URL and not WECHAT_WEBHOOK_URL:
        log("⚠️ 未配置 webhook，失败信息仅输出到日志")
        print(f"\n{'='*60}")
        print(text)
        print(f"{'='*60}\n")

# ─── 主流程 ──────────────────────────────────────────────────────────────────────

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    log(f"开始 {today} 日终流程")

    # Step 1: 运行 stock-recap
    # 降级策略：uv run → .venv/bin/python → 自动创建 venv
    log("Step 1: 生成复盘...")
    venv_python = str(PROJECT_DIR / ".venv" / "bin" / "python")
    venv_exists = Path(venv_python).exists()

    # 尝试 uv run
    uv_ok, _ = run_cmd(["uv", "run", "--help"], cwd=str(PROJECT_DIR))
    if uv_ok:
        stock_recap_cmd = ["uv", "run", "agent-platform", "stock-recap",
                           "--mode", "daily", "--provider", "live",
                           "--no-write-files", "--skip-trading-check"]
    elif venv_exists:
        stock_recap_cmd = [venv_python, "-m", "agent_platform", "stock-recap",
                           "--mode", "daily", "--provider", "live",
                           "--no-write-files", "--skip-trading-check"]
        log(f"uv 不可用，降级到: {venv_python}")
    else:
        # 两者都没有，尝试自动创建 venv
        log("uv 和 .venv 都不存在，尝试自动创建环境...")
        run_cmd(["uv", "venv", ".venv"], cwd=str(PROJECT_DIR))
        run_cmd([venv_python, "-m", "pip", "install", "-e", "."], cwd=str(PROJECT_DIR))
        if not Path(venv_python).exists():
            log("❌ 无法创建 .venv 环境，请手动安装 uv 或创建 venv")
            sys.exit(1)
        stock_recap_cmd = [venv_python, "-m", "agent_platform", "stock-recap",
                           "--mode", "daily", "--provider", "live",
                           "--no-write-files", "--skip-trading-check"]
        log(f"已自动创建环境: {venv_python}")

    ok, output = run_cmd(stock_recap_cmd, cwd=str(PROJECT_DIR))
    if not ok and stock_recap_cmd[0] == "uv":
        # uv run 失败（tcsetattr 等），降级到 .venv
        if not venv_exists:
            log("uv run 失败且 .venv 不存在，无法降级")
            sys.exit(1)
        log(f"uv run 失败，降级到: {venv_python}")
        stock_recap_cmd = [venv_python, "-m", "agent_platform", "stock-recap",
                           "--mode", "daily", "--provider", "live",
                           "--no-write-files", "--skip-trading-check"]
        ok, output = run_cmd(stock_recap_cmd, cwd=str(PROJECT_DIR))
    if not ok:
        log("复盘生成失败，中止")
        sys.exit(1)

    # 提取复盘内容（stdout 中 LLM 输出后的纯文本部分）
    recap_text = ""
    # 策略：先尝试精确匹配，如果内容太短则 fallback 到全文提取
    capture = False
    for line in output.split('\n'):
        if line.startswith('## 【复盘基准日') or line.startswith('### ') or line.startswith('# '):
            capture = True
        if capture:
            # 跳过 JSON 日志行（以 { 开头且包含 event/ts 字段）
            if line.startswith('{') and '"event"' in line:
                continue
            recap_text += line + '\n'
    recap_text = recap_text.strip()
    
    # Fallback: 如果提取内容太短（<500字），尝试跳过命令日志行，提取所有文本
    if len(recap_text) < 500:
        log("精确提取内容过短，使用 fallback 提取...")
        recap_text = ""
        for line in output.split('\n'):
            line_s = line.strip()
            # 跳过 JSON 日志行和空行
            if line_s.startswith('{') and '"event"' in line_s:
                continue
            if line_s.startswith('warning:') or line_s.startswith('['):
                continue
            recap_text += line + '\n'
        recap_text = recap_text.strip()

    if not recap_text:
        log("未能提取复盘内容，中止")
        sys.exit(1)
    log(f"复盘内容: {len(recap_text)} 字")

    # Step 2: 生成龙虎榜（复用 Step 1 的 venv_python）
    log("Step 2: 生成龙虎榜...")
    leaderboard_img = LEADERBOARD_DIR / f"leaderboard_{today}.png"
    ok, _ = run_cmd(
        [venv_python, "leaderboard_summary.py",
         "-d", today, "--image-only",
         "--footer-image", "assets/qrcode-wechat.jpg",
         "--footer-image", "assets/qrcode-mini.jpg"],
        cwd=str(LEADERBOARD_DIR)
    )
    if not ok or not leaderboard_img.exists():
        log("龙虎榜生成失败，使用素材库已有图片")
        leaderboard_img = None

    # Step 3: 上传龙虎榜图片
    log("Step 3: 上传图片...")
    token = get_access_token()

    if leaderboard_img and leaderboard_img.exists():
        # 上传今天的龙虎榜
        media_id, img_url = upload_image(token, str(leaderboard_img))
        log(f"已上传: media_id={media_id}, url={img_url[:80]}...")
    else:
        # 从素材库随机选一张
        img_url = "http://mmbiz.qpic.cn/mmbiz_png/gib5zl5ldEAvtXk6I0uToq8DZlWuJ6MQiaauMPXYic4UvibShrLCibknZkbqe2mIdO7GiceiaMhGK9k5n8OdqnMEhPuUDFJBOke03ootoxdmuaeNEw/0?wx_fmt=png"
        media_id = ""

    # 封面：从素材库随机选一张 leaderboard-title 图片
    title_imgs = list_leaderboard_images(token)
    if title_imgs:
        thumb_id = random.choice(title_imgs)
        log(f"封面: 随机选取 leaderboard-title 图片 ({len(title_imgs)} 张可选)")
    else:
        thumb_id = media_id
        log("封面: 未找到 leaderboard-title 图片，使用龙虎榜图片")

    # Step 4: 创建草稿
    log("Step 4: 创建草稿...")
    title = f"{today} A股行情复盘"
    content = format_recap_html(recap_text, img_url)
    draft_id = create_draft(token, title, thumb_id, content)
    log(f"草稿已创建: {draft_id}")
    log("请登录微信公众号后台 → 草稿箱 → 发表")

if __name__ == "__main__":
    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log(f"=== 第 {attempt}/{MAX_RETRIES} 次尝试 ===")
            main()
            log("✅ 流程完成，退出")
            sys.exit(0)
        except SystemExit as e:
            if e.code == 0:
                sys.exit(0)
            last_error = f"脚本退出码: {e.code}"
            log(f"❌ 第 {attempt} 次失败: {last_error}")
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            log(f"❌ 第 {attempt} 次异常: {last_error}")
            log(traceback.format_exc())

        if attempt < MAX_RETRIES:
            delay = RETRY_DELAYS[attempt - 1]
            log(f"⏳ {delay} 秒后重试...")
            time.sleep(delay)

    # 全部重试失败
    send_failure_notification(last_error, MAX_RETRIES)
    sys.exit(1)
