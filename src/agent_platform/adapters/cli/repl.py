"""终端交互 REPL 小工具（供各 Agent CLI 共用）。"""
from __future__ import annotations

import sys
from typing import Callable, Optional


def read_interactive_line(prompt: str = "> ") -> Optional[str]:
    """读一行用户输入；EOF/Ctrl-D 返回 None。"""
    try:
        line = input(prompt)
    except EOFError:
        return None
    except KeyboardInterrupt:
        print(file=sys.stderr)
        return None
    return line.strip()


def run_repl(
    *,
    banner: str,
    prompt: str = "> ",
    on_line: Callable[[str], bool],
) -> int:
    """循环读入直到 ``on_line`` 返回 False（退出）或 EOF。"""
    print(banner, flush=True)
    print("输入 help 查看命令；quit / exit 退出。\n", flush=True)
    while True:
        line = read_interactive_line(prompt)
        if line is None:
            print("\n再见。", flush=True)
            return 0
        if not line:
            continue
        try:
            if not on_line(line):
                print("再见。", flush=True)
                return 0
        except KeyboardInterrupt:
            print("\n(已中断本轮，继续输入或 quit 退出)", flush=True)
        except Exception as e:
            print(f"错误: {e}", file=sys.stderr)
