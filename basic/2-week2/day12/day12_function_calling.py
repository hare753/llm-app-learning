# ============================================================
# Day12 Function Calling 入门：计算器
# ------------------------------------------------------------
# 【核心目标】
# 跑通 Function Calling 五步：
#   1. 发问：用户提问 + tools 一起发给模型
#   2. 决策：模型返回 tool_calls（要调哪个函数、传什么参）
#   3. 执行：你的 Python 代码真正执行 calculator()
#   4. 回传：把执行结果作为 tool 消息追加进对话历史
#   5. 总结：第二次调用，模型把结果组织成自然语言
#
# 【一句话理解】
# 模型自己不会算数，它只做决策；真正算数的是你的 Python 函数。
# ============================================================


# ============================================================
# 【第 0 部分】导入需要的库
# ============================================================

# os：用来读取环境变量（.env 里的 API Key）
#     也可以用来拼接文件路径（Day13 会用到）
import os

# json：用来把「JSON 格式的字符串」转成「Python 字典」
#       例如 '{"a": 123}' → {'a': 123}
#       注意：JSON 字符串和 Python 字典长得像，但不是一回事
import json

# OpenAI：DeepSeek 完全兼容 OpenAI 的接口格式
#         所以我们不装 deepseek 专用库，直接用 openai 库
#         只需要把 base_url 改成 DeepSeek 的地址即可
from openai import OpenAI

# load_dotenv：把 .env 文件里的键值对加载到环境变量 os.environ
#              这样 API Key 不写死在代码里，不会被提交到 GitHub
from dotenv import load_dotenv


# ============================================================
# 【第 1 部分】加载配置、初始化客户端
# ============================================================

# 读取 .env 文件，把里面的变量加载进内存
# .env 文件内容形如：DEEPSEEK_API_KEY=sk-xxxxxxxx
# 这一步必须在 os.getenv 之前调用，否则读不到变量
load_dotenv()

# 从环境变量里取出 API Key
# 【坑点】变量名必须和 .env 文件里写的完全一致，大小写敏感
#         写成 "deepseek_api_key" 或 "DEEPSEEK_KEY" 都会返回 None
api_key = os.getenv("DEEPSEEK_API_KEY")

# 主动检查 Key 是否读到
# 【为什么要这步】如果不检查，后面调用 API 时会报一个很难懂的错误
#                不如在这里直接给出明确提示
if not api_key:
    raise ValueError("请在 .env 文件中设置 DEEPSEEK_API_KEY")

# 初始化 DeepSeek 客户端
# api_key：刚才读到的 Key
# base_url：DeepSeek 的接口地址
# 【为什么要改 base_url】
#   openai 库默认请求 https://api.openai.com
#   DeepSeek 的地址是 https://api.deepseek.com
#   不改的话，请求会发到 OpenAI 官方，报 401 未授权
client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"
)


# ============================================================
# 【第 2 部分】本地工具函数：calculator
# ============================================================
# 【关键认知】
# 模型自己不会算数！它只负责「决定调哪个函数、传什么参数」，
# 真正执行计算的，是这个 Python 函数。
#
# 你可能会问：那模型怎么知道要调这个函数？
# 答：靠下面 tools 里的 description 告诉它。

def calculator(a, b, operator):
    """
    执行两个数字的四则运算。

    参数：
        a, b: 数字（模型会从用户提问里抽取）
        operator: 字符串，取值 '+' '-' '*' '/'

    返回：
        运算结果（数字），或错误提示字符串
    """
    if operator == '+':
        return a + b
    if operator == '-':
        return a - b
    if operator == '*':
        return a * b
    if operator == '/':
        # 【除零保护】直接 a / b 且 b=0 会触发 ZeroDivisionError 崩栈
        # 所以提前判断，返回一个友好提示
        if b == 0:
            return "错误：除数不能为 0"
        return a / b
    # 【兜底】如果模型传了 enum 之外的运算符（正常不会发生）
    # 返回错误提示，而不是静默失败
    return f"错误：不支持的运算符 {operator}"


# ============================================================
# 【第 3 部分】tools：告诉模型「有哪些工具可用」
# ============================================================
# 【它是什么】
# 一个 JSON Schema 结构。模型看这个结构，决定：
#   - 要不要调工具？
#   - 调哪个工具？
#   - 参数怎么传？
#
# 【关键技巧】
# description 写得越清楚，模型判断越准。
# 写得太模糊，模型可能不调用，或传错参数。

tools = [
    {
        # 工具类型，目前只支持 "function"，固定写法
        "type": "function",
        "function": {
            # 函数名，必须和本地 Python 函数名一致
            # 模型返回 tool_calls 时会带这个名字，你靠它匹配本地函数
            "name": "calculator",

            # 描述：告诉模型这个函数是干什么的、什么时候用它
            # 模型会根据用户提问和这段描述，判断要不要调用
            "description": "执行两个数字的加、减、乘、除计算。当用户需要精确数学计算时调用。",

            # parameters：参数的 JSON Schema
            # 告诉模型这个函数需要哪些参数、什么类型、是否必填
            "parameters": {
                # 参数整体是一个 object（对象/字典）
                "type": "object",

                # properties：列出每个参数的名称、类型、说明
                "properties": {
                    "a": {
                        "type": "number",            # 类型：数字（整数或小数都行）
                        "description": "第一个数字"   # 说明，帮助模型正确抽取
                    },
                    "b": {
                        "type": "number",
                        "description": "第二个数字"
                    },
                    "operator": {
                        "type": "string",
                        # enum：枚举，限制取值范围
                        # 模型只能从这四个里选一个，防止它乱传（比如传 "乘"）
                        "enum": ["+", "-", "*", "/"],
                        "description": "运算符：+ 加，- 减，* 乘，/ 除"
                    }
                },

                # required：必填字段列表
                # 模型必须提供这三个参数，一个都不能少
                # 如果某个参数是可选的，就不用写在这里
                "required": ["a", "b", "operator"]
            }
        }
    }
]


# ============================================================
# 【第 4 部分】主流程：一次完整的 Function Calling
# ============================================================
# 这个函数把五步走完：
#   1. 发问 → 2. 决策 → 3. 执行 → 4. 回传 → 5. 总结

def run_query(user_input: str):
    """
    处理一次用户提问的完整流程。

    参数：
        user_input: 用户的提问文本，例如 "请计算 123 乘以 456"
    """
    print("=" * 60)
    print("用户：", user_input)

    # --------------------------------------------------------
    # messages：对话历史，按时间顺序排列
    # 一开始只有用户提问。后面会陆续 append 更多消息。
    # --------------------------------------------------------
    # 每条消息都是字典，至少包含 role 和 content 两个键。
    # role 的四种取值：
    #   "system"    → 你给模型的角色指令（Day13 会用到）
    #   "user"      → 用户说的话
    #   "assistant" → 模型说的话（包括 tool_calls 决策）
    #   "tool"      → 工具执行结果，回传给模型
    messages = [
        {"role": "user", "content": user_input}
    ]

    # --------------------------------------------------------
    # 【第 1 步】第一次调用：让模型做决策
    # --------------------------------------------------------
    # 把「用户提问 + tools」一起发过去，模型会判断：
    #   - 需要调工具 → 返回 tool_calls
    #   - 不需要     → 直接返回文本 content
    first_resp = client.chat.completions.create(
        model="deepseek-chat",   # 指定模型
        messages=messages,       # 对话历史
        tools=tools,             # 【关键】把工具清单发给模型
        temperature=0,           # 计算类任务要稳定，温度调 0
    )

    # 从返回结果里取出 assistant 消息对象
    # 返回结构是 first_resp.choices[0].message
    #   choices 是列表，通常只有一个元素
    #   [0] 取第一个
    #   .message 取消息体
    assistant_msg = first_resp.choices[0].message

    # 打印模型返回的 tool_calls，方便观察
    # 如果模型决定调用，这里会显示函数名和参数
    # 如果不调用，这里是 None
    print("第一次返回 tool_calls：", assistant_msg.tool_calls)

    # --------------------------------------------------------
    # 【分支】模型没调工具，直接返回文本
    # --------------------------------------------------------
    # 比如用户问「今天星期几」，模型不需要计算，直接回答
    # 这时直接打印 content 并结束，不走后面的流程
    if not assistant_msg.tool_calls:
        print("模型没有调用工具，直接回答：", assistant_msg.content)
        return

    # --------------------------------------------------------
    # 【第 4 步的一部分】把 assistant 消息追加进历史
    # --------------------------------------------------------
    # 【关键一步，最容易漏】
    # 必须把模型返回的 assistant_msg 追加进 messages。
    # 为什么？因为第二次调用时，模型需要看到自己之前的决策，
    # 才能把 tool 结果和 tool_call_id 对应起来。
    #
    # 如果不追加，第二次调用会报错：
    #   "tool_call_id ... does not have a corresponding tool_call"
    messages.append(assistant_msg)

    # --------------------------------------------------------
    # 【第 3 步】本地执行：遍历模型要求的每个工具调用
    # --------------------------------------------------------
    # 模型可能一次返回多个 tool_calls（比如让算 1+2 和 3+4）
    # 本例只有一个，但用 for 遍历更通用
    for tool_call in assistant_msg.tool_calls:

        # 判断函数名，决定调用本地哪个函数
        # 如果以后有多个工具，这里会写成 if/elif/else 分支
        # 本例只有一个 calculator，所以只写一个 if
        if tool_call.function.name == "calculator":

            # --------------------------------------------------------
            # 取出参数
            # --------------------------------------------------------
            # 【重要】arguments 是 JSON 格式的字符串，不是字典！
            # 例如：'{"a": 123, "b": 456, "operator": "*"}'
            # 所以不能直接当字典用，必须先 json.loads 解析
            raw_args = tool_call.function.arguments
            print("arguments 原始字符串：", raw_args)

            # JSON 字符串 → Python 字典
            # 解析后：{'a': 123, 'b': 456, 'operator': '*'}
            args = json.loads(raw_args)
            print("解析后参数：", args)

            # --------------------------------------------------------
            # 执行本地函数
            # --------------------------------------------------------
            # **args 是字典解包：把字典的键值对作为关键字参数传入
            # 等价于 calculator(a=123, b=456, operator="*")
            # 结果就是 56088
            result = calculator(**args)
            print("本地执行结果：", result)

            # --------------------------------------------------------
            # 【第 4 步】把工具执行结果回传给模型
            # --------------------------------------------------------
            # 这是一条 role="tool" 的消息，三个关键字段：
            #   role         → "tool"，表示工具返回
            #   tool_call_id → 必须和模型返回的 tool_call.id 一致
            #                  模型靠这个 id 对应「哪个请求得到了哪个结果」
            #   content      → 执行结果，必须是字符串
            #                  所以用 str(result)，不能直接塞数字
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(result),
            })

    # --------------------------------------------------------
    # 【第 5 步】第二次调用：让模型组织自然语言回答
    # --------------------------------------------------------
    # 此时 messages 里已经有三条：
    #   1. user：用户提问
    #   2. assistant：模型的 tool_calls 决策
    #   3. tool：工具执行结果
    #
    # 把这三条一起发给模型，它就能：
    #   - 看到用户问了什么
    #   - 看到自己决定调什么工具、传什么参
    #   - 看到工具返回了什么结果
    # 然后组织出一句自然语言回答
    #
    # 【为什么这次不传 tools】
    # 因为决策已经做完了，这次只是让模型总结，不需要再决策。
    # 如果要让模型连续调多个工具，才需要继续传 tools。
    second_resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=0,
    )

    # 取出最终回答文本
    # 这次返回的 assistant 消息里没有 tool_calls，只有 content
    final_answer = second_resp.choices[0].message.content
    print("最终回答：", final_answer)


# ============================================================
# 【第 5 部分】入口：用三个不同运算符验证
# ============================================================
# __name__ == "__main__" 的意思是：
#   只有直接运行这个脚本时才执行下面的代码
#   如果这个文件被其他文件 import，则不执行
#
# 三个测试用例覆盖三种运算符，验证模型能正确选择：
#   "123 乘以 456"  → operator="*"
#   "100 除以 4"    → operator="/"
#   "88 减 12"      → operator="-"
if __name__ == "__main__":
    run_query("请计算 123 乘以 456")
    run_query("请计算 100 除以 4")
    run_query("请计算 88 减 12")