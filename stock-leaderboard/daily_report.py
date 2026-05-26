#!/usr/bin/env uv run
# -*- coding: utf-8 -*-
# /// script
# dependencies = [
# ]
# ///
"""
日终复盘与龙虎榜汇总集成脚本
1. 执行 stock-recap 复盘命令
2. 执行 leaderboard_summary 龙虎榜命令
3. 输出复盘的 WeChat 文本
"""

import subprocess
import os
import sys
from datetime import datetime
import glob

def run_command(cmd):
    print(f"执行命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"命令执行失败!")
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        return False
    return True

def main():
    # 获取日期，默认今天
    today = datetime.now().strftime("%Y-%m-%d")
    
    print(f"开始生成 {today} 的日终报告...\n")

    # 1. 执行 stock-recap
    # uv run agent-platform stock-recap --mode daily --provider live --model gemini-cli
    recap_cmd = [
        "uv", "run", "agent-platform", "stock-recap", 
        "--mode", "daily", 
        "--provider", "live", 
        "--model", "gemini-cli"
    ]
    
    if not run_command(recap_cmd):
        sys.exit(1)

    # 查找生成的 wechat 文本文件
    # 默认在当前目录，文件名格式如 recap_2026-05-26_daily_wechat.txt
    wechat_files = glob.glob(f"recap_{today}_daily_wechat.txt")
    wechat_text = ""
    if wechat_files:
        wechat_file = wechat_files[0]
        with open(wechat_file, "r", encoding="utf-8") as f:
            wechat_text = f.read()
        print(f"找到复盘文本: {wechat_file}")
    else:
        print(f"未找到日期为 {today} 的复盘文本文件。")

    # 2. 执行龙虎榜汇总
    # uv run leaderboard_summary.py --footer-image assets/qrcode-wechat.jpg --footer-image assets/qrcode-mini.jpg
    leaderboard_cmd = [
        "uv", "run", "leaderboard_summary.py",
        "--footer-image", "assets/qrcode-wechat.jpg",
        "--footer-image", "assets/qrcode-mini.jpg"
    ]
    
    if not run_command(leaderboard_cmd):
        print("龙虎榜生成失败，继续输出复盘文本...\n")
    else:
        print("龙虎榜图片已生成。\n")

    # 3. 输出 WeChat 文本给用户
    if wechat_text:
        print("==================== WECHAT REPORT ====================")
        print(wechat_text)
        print("=======================================================")
    
    print("\n报告生成任务结束。")

if __name__ == "__main__":
    main()
