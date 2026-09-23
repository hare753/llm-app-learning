import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# 1. 加载 .env 文件中的环境变量
#    .env 文件里写了 DEEPSEEK_API_KEY=sk-xxxx，避免 Key 硬编码在代码里
load_dotenv()

# 2. 读取 API Key
#    注意：.env 里的变量名必须和这里完全一致（大小写敏感）
api_key = os.getenv("DEEPSEEK_API_KEY")

# 如果没读到 Key，主动报错，并提示用户去 .env 里设置
if not api_key:
    raise ValueError("请在 .env 文件中设置 DEEPSEEK_API_KEY")

# 3. 初始化 DeepSeek 客户端
#    DeepSeek 完全兼容 OpenAI 的接口格式，所以直接用 openai 库
#    base_url 必须改成 DeepSeek 的地址
client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"
)

# 4. 构造提示词
#    这里明确要求“只返回 JSON，不要多余文字”，并且给出了字段格式
#    注意：格式里 age 要求是数字，不是字符串，避免模型返回 "28" 带引号
requirement = """
从下面这句话里抽取信息，只返回 JSON，不要多余文字。
格式：{"name":"姓名","age":年龄数字}
这句话："我叫张三，今年28岁，是一名程序员。"
"""

# 5. 调用大模型
resp = client.chat.completions.create(
    model="deepseek-chat",                 # 使用 DeepSeek 的对话模型
    messages=[{"role": "user", "content": requirement}],
    temperature=0,                        # 0 表示输出最稳定，适合信息抽取
    max_tokens=100,                       # 限制输出长度，防止 JSON 被截断
    response_format={"type": "json_object"}  # 强制模型输出合法 JSON 字符串
)

# 6. 拿到原始返回文本
#    用了 response_format 后，raw 理论上就是合法 JSON，但为了保险还是先打印看看
raw = resp.choices[0].message.content
print("原始返回：", raw)

# 7. 清洗 + 解析
#    虽然 response_format 保证了 JSON 语法合法，但模型有时仍会包一层 ```json ... ```
#    这里用 strip 去掉首尾空白，再去掉常见的 markdown 包裹，最后转成 Python 字典
raw = raw.strip().replace("```json", "").replace("```", "").strip()
data = json.loads(raw)

# 8. 提取字段
print(data["name"], data["age"])