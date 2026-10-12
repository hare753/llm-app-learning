# Week3 小结（2026-09-30 ~ 2026-10-12）

## 主线产出

| Day   | 主题                   | 关键文件                                   |
| :---- | :--------------------- | :----------------------------------------- |
| Day15 | Few-shot 示例控制输出  | `3-week3/day15/day15_few_shot.py`          |
| Day16 | Prompt 模板化          | `3-week3/day16/day16_prompt_template.py`   |
| Day17 | 稳定率测试             | `3-week3/day17/day17_stability_test.py`    |
| Day18 | FC 多工具              | `3-week3/day18/day18_multi_tools.py`       |
| Day19 | 工具参数校验与错误回传 | `3-week3/day19/day19_tool_validation.py`   |
| Day20 | 批量抽取 CLI           | `2-week2/day13/day20_batch_extract_cli.py` |

## 并行后端 A（FastAPI + SQLite）

- 4 个接口：`GET /health`、`POST /extract`、`GET /records`、`POST /batch-extract`
- SQLite 持久化（`extractions` 表）
- pytest 7 个用例全过
- `DB_PATH` 用 `os.path.join(BASE_DIR, ...)` 锚定脚本目录
- 真实 uvicorn 启动验证通过（`/health` 返回 `{"status": "ok"}`）

## 关键理解

1. Few-shot 是给模型看例子，不是讲道理——控制输出风格。
2. Prompt 模板化的核心是「改字段不改流程」。
3. 稳定率测试 = 重复调用 + 统一统计 + 失败可回溯。
4. FC 四步闭环：模型决策 → 本地校验 → 错误回传 → 模型总结。
5. 批量处理四件套：`try/except + continue + 重试 + 日志`。
6. `BASE_DIR` 锚定 `__file__`，Day15/19/20 三次复用救命。

## 踩坑合集

- `response_format={"type":"json_object"}` 要求 Prompt 含 "json" 字样
- `2-week2` 带连字符不能作包名，必须在该目录下启动 uvicorn
- `isinstance(True, int)` 返回 True，bool 必须显式排除
- `if result:` 会误判空字典 `{}` 为失败，用 `if result is not None`
- docstring 里 `\uXXXX` 触发 `SyntaxError`，改中文描述或加 `r` 前缀
- 相对路径会让文件落错目录，一律 `os.path.join(BASE_DIR, ...)`

## 下一步

阶段一（Prompt 工程深化）内容已全部覆盖：API 参数、结构化输出、Prompt 模板化、Few-shot、批量处理、Function Calling。

Week4 具体安排待定。