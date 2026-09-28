import os
import sys
import json
from dotenv import load_dotenv
from openai import OpenAI

# 加载当前目录的 .env 文件，把里面的变量读取到环境变量中
load_dotenv()

# 从环境变量中读取 API Key
api_key = os.getenv("DEEPSEEK_API_KEY")
# 如果没读到，说明 .env 配置有问题，直接报错并终止程序
if not api_key:
    raise ValueError("未找到 DEEPSEEK_API_KEY，请检查 .env 文件")

# 创建 OpenAI 客户端，base_url 指向 DeepSeek 的兼容接口
client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"
)

# 系统提示词：告诉模型要抽取哪些字段、缺失时填 null、只输出 JSON
SYSTEM_PROMPT = """你是一个信息抽取器。
请从用户提供的文本中抽取以下字段：
- name：姓名，字符串，未提及填 null
- skills：技能列表，数组，未提及填 null
- years：工作年限，数字，未提及填 null
- education：学历，字符串，未提及填 null

只返回一个 JSON 对象，不要输出任何解释、Markdown 或多余文字。
"""

def clean_json(raw: str) -> str:
    """
    清洗模型返回的字符串。
    参数 raw: 模型返回的原始文本
    返回: 去掉 Markdown 代码块标记后的纯 JSON 字符串
    """
    return raw.strip().replace("```json", "").replace("```", "").strip()

def extract(text: str):
    """
    调用大模型从文本中抽取结构化信息。
    参数 text: 待抽取的原始文本
    返回: 解析成功的字典，失败则返回 None
    """
    # 调用 DeepSeek 的聊天接口
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},  # 系统指令
            {"role": "user", "content": text},             # 用户提供的文本
        ],
        temperature=0,                                     # 温度为 0，保证输出稳定
        response_format={"type": "json_object"},           # 强制返回合法 JSON
    )
    # 获取模型返回的内容，如果为 None 则用空字符串兜底
    raw = resp.choices[0].message.content or ""

    try:
        # 清洗掉可能的 Markdown 包裹
        cleaned = clean_json(raw)
        # 解析 JSON 字符串为 Python 字典
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # 如果解析失败，打印原始返回内容，方便排查
        print("解析失败，原始返回：")
        print(raw)
        return None

def main():
    # 1. 接收命令行参数：脚本名之后必须跟一个文件路径
    if len(sys.argv) < 2:
        print("用法：python day13_extractor.py <文件路径>")
        print("示例：python day13_extractor.py resume.txt")
        sys.exit(1)  # 退出码 1 表示异常退出

    # 获取用户传入的文件路径
    input_path = sys.argv[1]

    # 2. 判断文件是否存在
    if not os.path.exists(input_path):
        print(f"找不到文件：{input_path}")
        sys.exit(1)

    # 3. 读取文本内容，指定 utf-8 编码防止中文乱码
    with open(input_path, "r", encoding="utf-8") as f:
        text = f.read()

    # 4. 调用抽取函数
    print(f"正在抽取：{input_path} ...")
    result = extract(text)
    if result is None:
        print("抽取失败，未生成 JSON 文件。")
        sys.exit(1)

    # 5. 构造输出文件名：resume.txt -> resume_extracted.json
    #    os.path.splitext 返回 (文件名, 扩展名)，_ 表示忽略扩展名
    base, _ = os.path.splitext(input_path)
    output_path = base + "_extracted.json"

    # 6. 保存 JSON 文件
    with open(output_path, "w", encoding="utf-8") as f:
        # ensure_ascii=False 保证中文正常显示，indent=2 让 JSON 有缩进便于阅读
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 打印结果
    print(f"抽取成功：{output_path}")
    print(json.dumps(result, ensure_ascii=False, indent=2))

# 当脚本被直接运行时，执行 main 函数
if __name__ == "__main__":
    main()