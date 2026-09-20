# day8_api_params_demo.py
# 功能：演示 temperature 参数对比 + 流式输出
# 运行前：安装 openai 和 python-dotenv，并配置 .env 文件

import os
from dotenv import load_dotenv
from openai import OpenAI

# 1. 加载 .env 中的 API Key
load_dotenv()
api_key = os.getenv("DEEPSEEK_API_KEY")

if not api_key:
    # 主动报错，并打印括号里的提示
    raise ValueError("请在 .env 文件中设置 DEEPSEEK_API_KEY")

# 2. 初始化 DeepSeek 客户端（兼容 OpenAI 格式）
client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"
)

# ============================================================
# 实验一：temperature 对比（0 vs 1.5）
# ============================================================
print("=" * 50)
print("实验一：temperature 对比（0 和 1.5）")
print("=" * 50)

# 3. 提问
question = "写一句关于秋天的诗"

# 4. temperature 对比
for temp in [0, 1.5]:
    print(f"\n--- temperature = {temp} ---")
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": question}],
        temperature=temp,
        max_tokens=100
    )
    print(resp.choices[0].message.content)

# 说明：
# temperature=0 时，每次输出几乎一样，适合抽取信息、写代码。
# temperature=1.5 时，输出更随机、更有创意，但可能不稳定。

# ============================================================
# 实验二：流式输出（打字机效果）
# ============================================================
print("\n" + "=" * 50)
print("实验二：流式输出（打字机效果）")
print("=" * 50)
# flush=True 可以让 print 立即输出，而不是等到换行或缓冲区满才输出
print("\nAI 正在回答：", end="", flush=True)

# 5. 流式输出
# stream=True 告诉API不要一次性返回，而是生成一点就返回一点
stream = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": question}],
    stream=True,
    temperature=0.7
)

# 6. 逐步输出流式响应
# chunk 流式返回时，一次收到的一小包数据
for chunk in stream:
    # 有些 chunk 的 delta.content 是 None，要判断
    # delta 这一小包里新增的内容（增量）
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)

print("\n\n流式输出结束。")