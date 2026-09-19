# Day 6: 把 Day 5 的代码改成可对话的机器人
# 学习目标：
#   1. 学会用 while 循环实现多轮对话
#   2. 理解 messages 列表就是"对话历史"，每次都要带过去
#   3. 体验怎么维护上下文（模型记得你之前说过什么）

import os
from dotenv import load_dotenv
from openai import OpenAI

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

client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"
)

# ---------- 关键：维护一个对话历史列表 ----------
# 把 system 设定放在第一条，相当于给整个对话定基调
messages = [
    {"role": "system", "content": "你是一个友好的编程学习助手，用简洁通俗的中文回答问题。"}
]

print("=" * 50)
print("AI 对话机器人已启动！")
print("直接输入你的问题，按回车发送")
print("输入 '退出' 或 'exit' 结束对话")
print("=" * 50)

# ---------- 死循环：一直对话直到输入"退出" ----------
while True:
    # 1. 读取用户输入
    user_input = input("\n你：").strip()

    # 2. 如果输入退出，就跳出循环
    if user_input.lower() in ["退出", "exit", "quit"]:
        print("再见！")
        break

    # 3. 如果什么都没输入，跳过
    if not user_input:
        continue

    # 4. 把用户这句话加到对话历史里
    messages.append({"role": "user", "content": user_input})

    # 5. 把整个对话历史发给模型
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages
        )
    except Exception as e:
        print("调用出错了：", e)
        # 出错后把刚加的那条用户消息去掉，避免历史污染
        messages.pop()
        continue

    # 6. 取出模型回复
    assistant_reply = response.choices[0].message.content
    print("AI：", assistant_reply)

    # 7. 关键！把模型的回复也加到历史里，下一轮它才"记得"自己说过什么
    messages.append({"role": "assistant", "content": assistant_reply})

# ---------- 课后思考（以后会学到）----------
# 问题：对话越长，messages 列表越大，发给模型的 token 就越多，钱也花得越快
# 怎么解决？以后学 RAG 和上下文压缩时会讲
