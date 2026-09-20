import os
from dotenv import load_dotenv
from openai import OpenAI

# 加载环境变量
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

# 创建OpenAI客户端，填base_url
client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"
)

# 对话历史
messages = [
    {"role": "system", "content": "你是一个毒舌但温柔且有记忆的人生导师，言辞犀利直戳重点，善于比喻。"}
]

# UI界面
def ui():
    print("="*50)
    print("AI 对话机器人已启动！")
    print("直接输入你的问题，按回车发送")
    print("输入 '退出' 或 'exit' 结束对话")
    print("="*50)

# 运行UI
ui()

# 主循环
while True:
    # 读用户输入
    user_input=input("\n你:").strip()

    # 如果退出就 break
    if user_input.lower() in ["退出","exit","quit"]:
        print("GoodBye!")
        break

    # 空输入跳过
    if not user_input:
        continue

    # 清空
    if user_input.lower() in ["清空","clear"]:
        messages=messages[:1]
        print("已清空记忆")
        continue

    # 查看历史
    if user_input.lower() in ["回顾历史","history"]:
        print("历史消息:")
        for msg in messages:
            print(f"{msg['role']}: {msg['content']}")
        continue

    # 把用户这句话加进历史
    messages.append({"role":"user","content":user_input})

    # 调API
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.7
        )
    except Exception as e:
        print("调用出错了:",e)
        # 出错后把刚加的那条用户消息去掉，避免历史污染
        messages.pop()
        continue

    # 取reply
    assistant_reply = response.choices[0].message.content
    print("AI:",assistant_reply)
    
    # messages.append(assistant)
    messages.append({"role":"assistant","content":assistant_reply})