# HSK 3.0 考纲数据

本目录包含 HSK 3.0（2026-07 实施版）考纲数据，供 `hsk30-tutor` Agent 进行字词约束验证和 prompt 注入。

## 数据来源

权威来源：《中文水平考试 HSK 考试大纲》——中外语言交流合作中心 2025-11 发布。

通过腾讯文档 MCP 导出 PDF（406 页），使用 PyMuPDF 提取文本，手工清洗后生成 JSON。

## 数据文件

- `syllabus_data.json` — 考纲原始数据（约 290KB），包含：
  - `tasks` — 任务大纲（9 级，每级描述该等级的语言运用场景和功能）
  - `grammar` — 语法大纲（9 级，含语素、词类、短语、句子成分、句型、复句）
  - `topics` — 话题大纲（9 级，一级话题→二级话题→三级话题层次结构）
  - `vocabulary` — 词汇表（9 级，总计 10,370 词，累积制）
  - `char_recognition` / `char_recognition_cumulative` — 认读字表（9 级，累积制，总计 3,086 字）
  - `char_writing` / `char_writing_cumulative` — 书写字表（6 组，累积制，总计 866 字）

## 累积制设计

HSK 3.0 采用三阶段九级体系，**Level N 的数据包含 Level 1 到 N 的全部内容**：

| 等级 | 阶段 | 认读字 | 词汇 |
|------|------|--------|------|
| Level 1 | 初等 | 245 | 296 |
| Level 2 | 初等 | 370 | 490 |
| Level 3 | 初等 | 654 | 980 |
| Level 4 | 中等 | 1,094 | 1,969 |
| Level 5 | 中等 | 1,525 | 3,548 |
| Level 6 | 中等 | 1,938 | 5,316 |
| Level 7-9 | 高等 | 3,086 | 10,370 |

## 在 Agent 中的使用

1. **System Prompt 注入** — `prompts.py` 将任务大纲、话题大纲、语法大纲、认读字表、词汇表注入 system prompt
2. **输出验证** — `validation.py` 对 LLM 回复进行汉字级和词汇级验证（豁免专有名词）
3. **重试修正** — `use_case.py` 在验证失败时自动生成修正指令重试 LLM（最多 2 次）

## 更新数据

如需更新考纲数据：
1. 从权威来源获取最新 PDF
2. 运行提取脚本（参考 git history 中的提取代码）
3. 更新 `syllabus_data.json`
4. 运行 `pytest tests/test_hsk30_tutor_units.py` 验证累积性
