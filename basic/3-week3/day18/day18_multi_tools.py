"""
Day18：Function Calling 多工具
--------------------------------
目标：在 Day12 计算器基础上增加第二个工具 count_text_length，
      让模型根据用户问题自己选择调用哪个工具。

核心流程（Function Calling 五步）：
    1 第一次调用带 tools  → 模型决策：调不调？调哪个？传什么参？
    2 你的代码真正执行函数（模型不执行任何东西）
    3 把结果作为 role:"tool" 消息回传
    4 第二次调用         → 模型把结果组织成自然语言
    5 返回最终回答

对比 Day12 的升级：
    - 从 1 个工具扩展到 2 个工具
    - 用 TOOL_MAP 注册表替代 if/elif，加工具只改一处
    - 循环处理所有 tool_calls，不只取第一个
    - 工具执行加 try/except，失败不崩溃
    - 日志加 [工具路由] / [工具执行] 前缀，便于定位
"""

import os
import json
from dotenv import load_dotenv
from openai import OpenAI


# ============================================================
# 一、路径与环境变量
# ============================================================

# __file__              → 当前脚本的路径（可能是相对的）
# os.path.abspath(...)  → 转成绝对路径
# os.path.dirname(...)  → 取所在目录（去掉文件名）
# 综合效果：拿到 day18/ 这个文件夹的绝对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# "../../.env" 从 day18/ 往上跳两级：day18 → 3-week3 → basic
# os.path.join 会自动处理不同系统的斜杠（Windows \，Linux /）
ENV_PATH = os.path.join(BASE_DIR, "../../.env")


def _require_env():
    """
    加载 .env 文件，并检查关键环境变量是否存在。
    缺配置时立刻抛中文错误，不等到网络超时才报错。
    """
    # load_dotenv 读取 .env 文件，把里面的 key=value 注入到 os.environ
    # 显式传路径，避免依赖当前工作目录
    load_dotenv(ENV_PATH)

    # 列表推导式：找出「还没配置」的变量名
    #   for k in (...)            → 遍历待检查的变量名
    #   os.getenv(k)              → 读环境变量，没配置时返回 None
    #   if not os.getenv(k)       → None 视为缺失，True 就加入结果
    # 最终 missing 是「缺失变量名」的列表，比如 ["BASE_URL"]
    missing = [k for k in ("DEEPSEEK_API_KEY", "BASE_URL") if not os.getenv(k)]

    if missing:
        # ', '.join(...) 把列表拼成字符串："DEEPSEEK_API_KEY, BASE_URL"
        # RuntimeError 比 ValueError 更贴切：这是运行环境配置问题
        raise RuntimeError(
            f"缺少环境变量：{', '.join(missing)}\n"
            f"请检查 {ENV_PATH} 是否存在且包含对应配置。"
        )


# 模块加载时立刻执行一次校验
# 如果 .env 缺东西，从这里就抛错，不用等到调 API 才发现
_require_env()


# 创建 OpenAI 客户端（DeepSeek 兼容 OpenAI SDK）
# api_key 和 base_url 都从环境变量读，绝不硬编码
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("BASE_URL"),
)

# MODEL 有默认值兜底：.env 里没写 MODEL_NAME 时用 "deepseek-chat"
# 这和 DEEPSEEK_API_KEY / BASE_URL 不同——那两个没配就直接报错
MODEL = os.getenv("MODEL_NAME", "deepseek-chat")


# ============================================================
# 二、工具函数（模型"想调"的本地函数）
# ============================================================

def calculator(a: float, b: float, operator: str) -> float:
    """四则运算。operator 只能取 + - * / 之一。"""
    # 早返回：先统一校验 operator，非法值立刻抛错
    # 注意：这里绝对不用 eval()，哪怕已经校验过 operator 也不安全
    #       eval 会执行任意 Python 表达式，是安全红线
    if operator not in ("+", "-", "*", "/"):
        raise ValueError(f"不支持的运算符：{operator}，仅支持 + - * /")

    # 除零单独检查，抛 ZeroDivisionError（比 ValueError 语义更准）
    if operator == "/" and b == 0:
        raise ZeroDivisionError("除数不能为 0")

    # 显式分支：写 5 行，安全一辈子
    if operator == "+":
        return a + b
    if operator == "-":
        return a - b
    if operator == "*":
        return a * b
    # 走到这里 operator 一定是 "/"（前面已经排除了其他可能）
    return a / b


def count_text_length(text: str) -> int:
    """返回 text 的字符数（中文按 1 个字符计）。"""
    # 不在代码里 strip()，避免"篡改输入"
    # 边界交给 description 说清楚："text 只包含待统计的正文"
    return len(text)


# ============================================================
# 三、工具 JSON Schema（模型"看懂"的说明书）
# ============================================================
# 模型不读你的函数代码，只读这里的 description
# description 越具体（什么时候调、参数含义），模型路由越准

tools = [
    # ---------- 工具1：计算器 ----------
    {
        "type": "function",                # 固定写法：声明这是函数类工具
        "function": {
            "name": "calculator",          # 必须和 TOOL_MAP 的键一致
            "description": "执行加减乘除四则运算。当用户需要计算两个数字的加减乘除结果时调用。",
            "parameters": {
                "type": "object",
                "properties": {            # 逐个字段描述
                    "a": {"type": "number", "description": "第一个操作数"},
                    "b": {"type": "number", "description": "第二个操作数"},
                    "operator": {
                        "type": "string",
                        "enum": ["+", "-", "*", "/"],   # 限定取值范围
                        "description": "运算符，只能取 + - * / 之一",
                    },
                },
                "required": ["a", "b", "operator"],     # 这三个必填
            },
        },
    },
    # ---------- 工具2：统计文本长度 ----------
    {
        "type": "function",
        "function": {
            "name": "count_text_length",
            "description": (
                "统计一段文本的字符总数。当用户询问文本长度、字数、字符数时调用。"
                "参数 text 只包含待统计的正文，不要把用户指令本身算进去。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要统计长度的正文内容"},
                },
                "required": ["text"],
            },
        },
    },
]


# ============================================================
# 四、工具注册表：工具名 → 本地函数
# ============================================================
# 关键点：值的位置是 `calculator`（函数对象本身），不是 `calculator()`
#   calculator   → 函数对象，可以后面 func(**args) 调用
#   calculator() → 立刻调用并返回结果，存到字典里就没意义了
#
# 好处：加新工具 = 加函数 + 加 Schema + 加一行映射，主逻辑不动
TOOL_MAP = {
    "calculator": calculator,
    "count_text_length": count_text_length,
}


# ============================================================
# 五、核心流程：模型决策 → 本地执行 → 回传 → 模型总结
# ============================================================

def run_with_tools(user_query: str) -> str:
    """
    执行一轮完整的 Function Calling 流程。
    返回最终的自然语言回答字符串（不打印，交给调用方决定怎么用）。
    """
    # ---------- 初始化消息历史 ----------
    # 从用户问题开始，后面每做一步就 append 一条
    messages = [{"role": "user", "content": user_query}]

    # ---------- 第一次调用：让模型决策 ----------
    # 带上 tools，模型会读两个工具的 description，决定调不调、调哪个
    # temperature=0 让工具选择稳定，不要随机漂移
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools,
        temperature=0,
    )
    assistant_msg = resp.choices[0].message

    # 必须把 assistant_msg 追加进历史
    # 第二次调用时要让模型看到自己刚才的决策（含 tool_calls）
    messages.append(assistant_msg)

    # ---------- 模型没选工具，直接回答 ----------
    # 比如问"你好"，模型不会调 calculator，直接给自然语言回答
    if not assistant_msg.tool_calls:
        print(f"[模型回答] 未选择工具，直接回答：{assistant_msg.content}")
        return assistant_msg.content

    # ---------- 循环执行每个工具调用 ----------
    # 用 for 而不是 tool_calls[0]：模型可能一次请求多个工具，丢掉会出错
    for tool_call in assistant_msg.tool_calls:
        # 取出工具名（字符串，和 TOOL_MAP 的键、Schema 的 name 都一致）
        tool_name = tool_call.function.name

        # arguments 是 JSON 字符串（不是字典！），必须先 json.loads
        # 例如 '{"a":123,"b":456,"operator":"*"}' → {"a":123, ...}
        tool_args = json.loads(tool_call.function.arguments)

        print(f"[工具路由] 模型选择：{tool_name}，参数：{tool_args}")

        # ---------- 从注册表查函数并执行 ----------
        func = TOOL_MAP.get(tool_name)

        if func is None:
            # 兜底：模型幻觉出了一个不存在的工具名
            result = f"未知工具：{tool_name}"
        else:
            try:
                # ** 是字典解包：
                #   {"a":123,"b":456,"operator":"*"} → calculator(a=123, b=456, operator="*")
                result = func(**tool_args)
            except Exception as e:
                # 工具执行失败（除零、非法参数等）不能让整个程序崩
                # 把错误信息变成字符串，回传给模型，让模型解释给用户
                result = f"工具执行失败：{e}"

        print(f"[工具执行] 结果：{result}")

        # ---------- 回传工具结果 ----------
        # role="tool" 必须带 tool_call_id，和模型请求的 id 对上
        # content 必须是字符串（不能传 int / float / dict）
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": str(result),
        })

    # ---------- 第二次调用：模型组织自然语言 ----------
    # 这时 messages = [user, assistant(含tool_calls), tool(结果)]
    # 模型看到"用户问题 + 自己的决策 + 工具结果"，生成自然语言回答
    final_resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0,
    )
    return final_resp.choices[0].message.content


# ============================================================
# 六、测试入口
# ============================================================
# if __name__ == "__main__" 保护：
#   - 直接运行本文件时，__name__ == "__main__" → 下面的测试会执行
#   - 被其他文件 import 时，__name__ == "day18_multi_tools" → 测试不执行
#     （避免 import 时就偷偷调 API 花钱）
if __name__ == "__main__":
    print("=== 测试1：计算类问题 ===")
    print(run_with_tools("123 乘以 456 等于多少"))

    print("\n=== 测试2：文本长度问题 ===")
    print(run_with_tools("统计这段话有多少字：今天天气很好，适合出门散步。"))

    print("\n=== 测试3：计算器再验证 ===")
    print(run_with_tools("100 除以 4"))