# Day 5: 用 Python 发第一条消息给大模型
# 学习目标：
#   1. 学会用 .env 文件管理 API Key（不写死在代码里）
#   2. 学会用 openai 库连接 DeepSeek
#   3. 亲眼感受 prompt（提示词）对输出的影响

# ---------- 第 0 步：先安装工具包（只需要装一次）----------
# 在 VSCode 终端里运行：pip install openai
# 这个库本来是给 ChatGPT 用的，但 DeepSeek 兼容它，所以直接用

# ---------- 第 1 步：导入工具包 ----------
import os
from dotenv import load_dotenv
from openai import OpenAI

# ---------- 第 2 步：读取 API Key ----------
load_dotenv()
api_key = os.getenv("DEEPSEEK_API_KEY")

# Key 缺失时给出明确提示，而不是等到调 API 才报错
if not api_key:
    print("=" * 50)
    print("未找到 DEEPSEEK_API_KEY")
    print("请确认 basic/ 目录下有 .env 文件，内容为：")
    print("DEEPSEEK_API_KEY=sk-你的真实key")
    print("=" * 50)
    exit()

# ---------- 第 3 步：创建客户端，连接 DeepSeek ----------
# api_key: 你的钥匙
# base_url: DeepSeek 的服务器地址（注意：DeepSeek 兼容 OpenAI 格式，所以用 openai 库）
client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"
)

# ---------- 第 4 步：第一次调用——最简单的问候 ----------
print("=" * 50)
print("【第 1 次调用】普通问候")
print("=" * 50)

response1 = client.chat.completions.create(
    model="deepseek-chat",   # 用的模型名；如果报错说模型不存在，改成 deepseek-v4-flash
    messages=[
        # messages 是一个列表，里面装你和模型的对话历史
        # role 表示谁说的：system=系统设定，user=你，assistant=模型
        {"role": "user", "content": "你好"}
    ]
)

# 从返回结果里取出模型说的话
reply1 = response1.choices[0].message.content
print("模型回复：", reply1)
print()

# ---------- 第 5 步：第二次调用——换个 prompt，看效果有什么不同 ----------
print("=" * 50)
print("【第 2 次调用】给它一个角色设定（这就是 prompt 的威力）")
print("=" * 50)

response2 = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        # 多加一条 system 消息，相当于给模型"定人设"
        {"role": "system", "content": "你是一个毒舌但靠谱的编程老师，说话简短犀利，喜欢用比喻。"},
        {"role": "user", "content": "你好"}
    ]
)

reply2 = response2.choices[0].message.content
print("模型回复：", reply2)
print()

# ---------- 第 6 步：对比一下 ----------
print("=" * 50)
print("【对比】")
print("同样是一句'你好'，加了角色设定后，回答风格完全变了：")
print("-" * 50)
print("没设定：", reply1)
print("-" * 50)
print("有设定：", reply2)
print("=" * 50)
print()
print("恭喜！你已经完成了 Day 5 的任务——用 Python 调通了大模型 API！")
print("接下来运行 day6_chat_bot.py 就能开始多轮对话了。")
