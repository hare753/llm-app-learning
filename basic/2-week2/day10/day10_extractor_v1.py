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

# 4. system_prompt：这是你发给模型的“系统指令”
#    它是一段普通字符串，不是 JSON，也不是 Python 字典。
#    模型会按照这个指令来抽取信息。
system_prompt = """你是一个信息抽取助手。
从用户给的文本中抽取以下字段，严格输出JSON：
{
  "name": "姓名，不知道填null",
  "skills": ["技能1", "技能2"],
  "years": 工作年限（数字，不知道填null）,
  "education": "最高学历，不知道填null"
}
只输出JSON，不要解释，不要markdown代码块。
未提及的信息必须填null，绝对不能编造。
"""

# 5. 测试用的文本，也是普通字符串
text_full = """
我叫李四，今年30岁，有5年Python开发经验。
本科毕业于某某大学计算机专业。
熟练掌握Python、FastAPI、Docker，了解LangChain。
"""

text_missing = """
我叫王五，喜欢研究AI，会写一点Python。
"""

def extract(text):
    # 6. 发送请求：messages 列表里有两个角色
    #    - system：系统指令，告诉模型角色和规则
    #    - user：用户输入，即要处理的文本
    #    注意：这里并没有 assistant 消息，assistant 是模型返回的。
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},   # 你发出去的：系统指令
            {"role": "user", "content": text}                # 你发出去的：用户文本
        ],
        temperature=0,
        max_tokens=300,
        response_format={"type": "json_object"}
    )

    # 7. 获取模型返回的内容
    #    resp.choices[0].message 是 assistant 角色
    #    .content 是一个 JSON 字符串（符合 JSON 标准，键和字符串值都用双引号）
    raw = resp.choices[0].message.content
    print("原始返回（JSON 字符串）：", raw)

    # 8. 清洗：去掉可能存在的 markdown 代码块包裹
    #    虽然使用了 response_format，但保留这一步作为防御性编程
    raw = raw.strip().replace("```json", "").replace("```", "").strip()

    # 9. 把 JSON 字符串解析成 Python 字典
    #    - JSON 里的 null 会自动变成 Python 的 None
    #    - JSON 里的双引号字符串会变成 Python 的 str
    try:
        data = json.loads(raw)      # data 现在是 Python 字典
    except json.JSONDecodeError:
        print("解析失败，原始返回：", raw)
        return None

    # 10. 返回的是 Python 字典（打印时内部字符串用单引号显示）
    return data

print("=" * 40)
print("完整简历：")
result1 = extract(text_full)
# 这里 result1 是 Python 字典，打印时内部字符串用单引号
print("Python 字典结果：", result1)

print("=" * 40)
print("缺失信息：")
result2 = extract(text_missing)
print("Python 字典结果：", result2)