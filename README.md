# LLM 应用开发学习项目

## Week2 Day14 FastAPI 最小封装

启动目录：`basic/2-week2/day13`

```bash
cd basic/2-week2/day13
python -m uvicorn day13_api:app --reload --port 8000
```

打开 http://127.0.0.1:8000/docs 测试 `POST /extract`。

请求体示例：

```json
{"text": "张三，28岁，本科，5年Python开发经验，熟悉LangChain、RAG、FastAPI。"}
```

预期返回：

```json
{
  "result": {
    "name": "张三",
    "skills": ["Python", "LangChain", "RAG", "FastAPI"],
    "years": 5,
    "education": "本科"
  }
}
```

---

## Week3 并行：FastAPI + SQLite 完整后端

把 Week2 的 `day13_api.py` 升级为带持久化、历史查询、批量抽取的完整服务，主线抽取逻辑一行不改。

### 启动

```bash
cd basic/2-week2/day13
python -m uvicorn day13_api_sqlite:app --reload --port 8000
```

> 必须在 `basic/2-week2/day13/` 目录下启动，因为 `2-week2` 带连字符不能作为 Python 包名。

启动后浏览器打开：http://127.0.0.1:8000/docs

### 接口清单

| 方法 | 路径             | 请求体 / 参数               | 说明                                        |
| :--- | :--------------- | :-------------------------- | :------------------------------------------ |
| GET  | `/health`        | —                           | 健康检查，返回 `{"status": "ok"}`           |
| POST | `/extract`       | `{"text": "..."}`           | 抽取单条文本，结果写入 SQLite               |
| GET  | `/records`       | `?limit=10`                 | 查询历史记录，limit 范围 0~100              |
| POST | `/batch-extract` | `{"texts": ["...", "..."]}` | 批量抽取，单条失败不中断，返回成功/失败统计 |

### 统一错误码

| 状态码 | 含义         | 触发场景                           |
| :----- | :----------- | :--------------------------------- |
| 200    | 成功         | 正常请求                           |
| 400    | 参数错误     | 空文本、缺少必填字段               |
| 422    | 参数校验失败 | FastAPI 自动校验（如 `limit=200`） |
| 500    | 服务内部错误 | 抽取失败、数据库异常               |

### SQLite 表结构

```sql
CREATE TABLE IF NOT EXISTS extractions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    result_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 测试

```bash
cd basic/2-week2/day13
python -m pytest tests/ -v
```

预期：`7 passed`

---

## Week3 Day20：批量抽取 CLI

批量处理指定目录下的 `resume*.txt`，单条失败自动重试 1 次，全流程写 JSONL 日志。

### 运行

```bash
cd basic/2-week2/day13
python day20_batch_extract_cli.py               # 处理脚本所在目录
python day20_batch_extract_cli.py ./mytexts     # 处理指定目录
```

### 产出

- 每个成功文件生成 `{原名}_extracted.json`
- `extract_log.jsonl`：每行一条 `{"file", "status", "output"/"error", "timestamp"}`

### 特性

- **三层职责分离**：`main` 管批 / `process_file` 管单 / `extract_with_retry` 管重试
- **`process_file` 契约：总返回、不抛异常**。主循环不写 `try/except`，单条失败天然不中断
- **空文本预检**：`.strip()` 一判，直接返回 failed，不浪费 API 调用
- **重试只留给临时错误**：网络抖动、模型偶发解析失败重试 1 次；空文件等确定性错误不重试
- **日志先落盘再打印**：进程被 Ctrl+C 也不丢

---

## Week3 产出概览（2026-09-30 ~ 2026-10-12）

### 主线（Prompt 工程深化）

| Day   | 主题                     | 关键文件                                      |
| :---- | :----------------------- | :-------------------------------------------- |
| Day15 | Few-shot 示例控制输出    | `3-week3/day15/day15_few_shot.py`             |
| Day16 | Prompt 模板化            | `3-week3/day16/day16_prompt_template.py`      |
| Day17 | 稳定率测试               | `3-week3/day17/day17_stability_test.py`       |
| Day18 | FC 多工具                | `3-week3/day18/day18_multi_tools.py`          |
| Day19 | 工具参数校验与错误回传   | `3-week3/day19/day19_tool_validation.py`      |
| Day20 | 批量抽取 CLI             | `2-week2/day13/day20_batch_extract_cli.py`    |

### 并行后端 A（FastAPI + SQLite）

- 4 个接口：`GET /health`、`POST /extract`、`GET /records`、`POST /batch-extract`
- SQLite 持久化（`extractions` 表）
- pytest 7 个用例全过
- 统一错误码：400 / 422 / 500
- `DB_PATH` 用 `os.path.join(BASE_DIR, ...)` 锚定脚本目录

### 关键理解沉淀

1. Few-shot 是给模型看例子，不是讲道理——控制输出风格。
2. Prompt 模板化的核心是「改字段不改流程」。
3. 稳定率测试 = 重复调用 + 统一统计 + 失败可回溯。
4. FC 四步闭环：模型决策 → 本地校验 → 错误回传 → 模型总结。
5. 批量处理四件套：`try/except + continue + 重试 + 日志`。
6. `BASE_DIR` 锚定 `__file__`，Day15/19/20 三次复用救命。

### 踩坑合集

- `response_format={"type":"json_object"}` 要求 Prompt 含 "json" 字样
- `2-week2` 带连字符不能作包名，必须在该目录下启动 uvicorn
- `isinstance(True, int)` 返回 True，bool 必须显式排除
- `if result:` 会误判空字典 `{}` 为失败，用 `if result is not None`
- docstring 里 `\uXXXX` 触发 `SyntaxError`，改中文描述或加 `r` 前缀
- 相对路径会让文件落错目录，一律 `os.path.join(BASE_DIR, ...)`