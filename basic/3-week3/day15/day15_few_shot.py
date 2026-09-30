import os
import json
from dotenv import load_dotenv
from openai import OpenAI

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".env"))

load_dotenv(dotenv_path=ENV_PATH)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(
            f"[配置错误] 环境变量 {name} 未配置或为空。\n"
            f"请检查文件：{ENV_PATH}\n"
            f"参考格式：\n"
            f"  DEEPSEEK_API_KEY=sk-xxxxxxxx\n"
            f"  BASE_URL=https://api.deepseek.com\n"
            f"  MODEL_NAME=deepseek-chat"
        )
    return value.strip()


API_KEY = _require_env("DEEPSEEK_API_KEY")
BASE_URL = _require_env("BASE_URL")
MODEL = os.getenv("MODEL_NAME", "deepseek-chat").strip() or "deepseek-chat"

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
    timeout=30.0,
)

def clean_json(raw: str) -> str:
    return raw.strip().replace("```json", "").replace("```", "").strip()

SYSTEM_PROMPT = "你是一个信息抽取助手。只输出 JSON，不要解释，不要多余文字。"

TEXT = "王五，28岁，本科，5年Python开发经验，熟悉FastAPI和SQLite，做过RAG项目。"

def run_0shot(text: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "从下面文本中抽取 name、skills、years、education 四个字段。"
                "未提及的字段填 null。只输出 JSON。\n\n"
                f"文本：{text}"
            ),
        },
    ]

    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or ""
    return raw

def run_fewshot(text: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "张三，本科，3年Python经验，会FastAPI。请抽取 name、skills、years、education。",
        },
        {
            "role": "assistant",
            "content": '{"name":"张三","skills":["Python","FastAPI"],"years":3,"education":"本科"}',
        },
        {
            "role": "user",
            "content": "李四，硕士，5年经验，熟悉LangChain和RAG。请抽取 name、skills、years、education。",
        },
        {
            "role": "assistant",
            "content": '{"name":"李四","skills":["LangChain","RAG"],"years":5,"education":"硕士"}',
        },
        {
            "role": "user",
            "content": (
                "从下面文本中抽取 name、skills、years、education 四个字段。"
                "未提及的字段填 null。只输出 JSON。\n\n"
                f"文本：{text}"
            ),
        },
    ]

    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or ""
    return raw

def parse_or_none(raw: str):
    try:
        return json.loads(clean_json(raw))
    except json.JSONDecodeError:
        return None


if __name__ == "__main__":
    raw_0 = run_0shot(TEXT)
    raw_few = run_fewshot(TEXT)

    data_0 = parse_or_none(raw_0)
    data_few = parse_or_none(raw_few)

    print("===== 0-shot raw =====")
    print(raw_0)
    print("===== 0-shot parsed =====")
    print(data_0)

    print("\n===== few-shot raw =====")
    print(raw_few)
    print("===== few-shot parsed =====")
    print(data_few)

    out_path_0 = os.path.join(BASE_DIR, "day15_0shot_raw.txt")
    out_path_few = os.path.join(BASE_DIR, "day15_fewshot_raw.txt")

    with open(out_path_0, "w", encoding="utf-8") as f:
        f.write(raw_0)

    with open(out_path_few, "w", encoding="utf-8") as f:
        f.write(raw_few)

    print("\n解析成功率：")
    print("0-shot:", data_0 is not None)
    print("few-shot:", data_few is not None)