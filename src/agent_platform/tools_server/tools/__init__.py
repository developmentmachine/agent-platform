"""单个工具的 SPEC 定义（每个模块导出一个 ``SPEC: ToolSpec``）。

handler 实现仍复用 ``infrastructure.tools.handlers.*``（W2 暂不物理迁移
handler 文件，W7 一次性收尾删除旧路径）；schema 与 handler 的绑定收敛在此。
"""
