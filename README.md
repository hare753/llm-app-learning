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

预期：`4 passed`