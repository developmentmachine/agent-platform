#!/usr/bin/env python3
"""
每日自动流程：stock-recap 复盘 + 龙虎榜 → 微信公众号草稿箱
每交易日 17:00 由 cron 调用。
"""
import subprocess
import urllib.request
import json
import os
import sys
import glob
import random
from datetime import datetime
from pathlib import Path

# MIMO LLM structured output retries can be slow; give 10 min budget
os.environ.setdefault("RECAP_AGENT_MAX_WALL_MS", "600000")

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
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=600)
    if result.returncode != 0:
        log(f"失败: {result.stderr[:500]}")
        return False, result.stderr
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
    """从素材库获取 leaderboard 开头的图片 media_id"""
    data = json.dumps({"type": "image", "offset": 0, "count": 50}).encode()
    req = urllib.request.Request(
        f"https://api.weixin.qq.com/cgi-bin/material/batchget_material?access_token={token}",
        data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as r:
        result = json.loads(r.read())

    ids = []
    for item in result.get("item", []):
        if item.get("name", "").startswith("leaderboard"):
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

# ─── 主流程 ──────────────────────────────────────────────────────────────────────

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    log(f"开始 {today} 日终流程")

    # Step 1: 运行 stock-recap
    log("Step 1: 生成复盘...")
    ok, output = run_cmd(
        ["uv", "run", "agent-platform", "stock-recap",
         "--mode", "daily", "--provider", "live",
         "--no-write-files", "--skip-trading-check"],
        cwd=str(PROJECT_DIR)
    )
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

    # Step 2: 生成龙虎榜
    log("Step 2: 生成龙虎榜...")
    leaderboard_img = LEADERBOARD_DIR / f"leaderboard_{today}.png"
    ok, _ = run_cmd(
        ["uv", "run", "leaderboard_summary.py",
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

    # 封面：用刚上传的龙虎榜图片
    thumb_id = media_id

    # Step 4: 创建草稿
    log("Step 4: 创建草稿...")
    title = f"{today} A股行情复盘"
    content = format_recap_html(recap_text, img_url)
    draft_id = create_draft(token, title, thumb_id, content)
    log(f"草稿已创建: {draft_id}")
    log("请登录微信公众号后台 → 草稿箱 → 发表")

if __name__ == "__main__":
    main()
