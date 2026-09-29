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