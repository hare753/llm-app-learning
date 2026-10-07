"""
Day19：Function Calling 参数校验与错误回传
--------------------------------
目标：工具收到非法参数或缺少参数时，本地校验后把错误作为 tool 消息回传，
      让模型组织自然语言解释，而不是直接抛异常给用户。

对比 Day18 的升级：
    - calculator 加三层校验：必填校验、类型校验、operator 枚举校验、除零校验
    - 错误统一作为 role:"tool" 的 content 回传，不抛出、不崩溃
    - 工具函数返回字符串（成功=结果，失败=错误信息），调用方不再 try/except
    - 新增 test_validation_directly()：不花 API 费用直接验证本地校验
    - 新增 _test_error_recovery()：模拟错误 tool_call，验证错误回传闭环

核心思想：
    模型只做决策（调哪个工具、传什么参数），
    真正校验和执行的是本地 Python 代码。
    "模型决策 → 本地校验 → 错误回传 → 模型总结" = Agent 容错的四步闭环。
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
# 综合效果：拿到 day19/ 这个文件夹的绝对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# "../../.env" 从 day19/ 往上跳两级：day19 → 3-week3 → basic
# os.path.join 会自动处理不同系统的斜杠（Windows \，Linux /）
ENV_PATH = os.path.join(BASE_DIR, "../../.env")


def _require_env():
    """
    加载 .env 文件，并检查关键环境变量是否存在。
    缺配置时立刻抛中文错误，不等到网络超时才报错。
    """
    # load_dotenv 读取 .env，把里面的 key=value 注入到 os.environ
    load_dotenv(ENV_PATH)

    # 【列表推导式】
    #   for k in (...)         → 遍历待检查的变量名
    #   os.getenv(k)           → 读环境变量，没配置时返回 None
    #   if not os.getenv(k)    → None 视为缺失
    # 最终 missing 是"缺失变量名"列表，比如 ["BASE_URL"]
    missing = [k for k in ("DEEPSEEK_API_KEY", "BASE_URL") if not os.getenv(k)]

    if missing:
        raise RuntimeError(
            f"缺少环境变量：{', '.join(missing)}\n"
            f"请检查 {ENV_PATH} 是否存在且包含对应配置。"
        )


# 模块加载时立刻执行一次校验：如果 .env 缺东西，从这里就抛错
_require_env()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("BASE_URL"),
)

# MODEL 有默认值兜底：.env 里没写 MODEL_NAME 时用 "deepseek-chat"
MODEL = os.getenv("MODEL_NAME", "deepseek-chat")


# ============================================================
# 二、工具函数（含严格参数校验）
# ============================================================
# 与 Day18 的关键差异：
#   Day18 工具抛异常（ValueError / ZeroDivisionError），由调用方 try/except 兜底
#   Day19 工具内部校验后 **返回错误字符串**，调用方不再需要 try/except
#   参数默认值设为 None，是为了能显式检测「缺参数」

VALID_OPERATORS = ("+", "-", "*", "/")


def calculator(a=None, b=None, operator=None) -> str:
    """
    四则运算。含三层校验 + 除零保护。
    返回值：
        成功 → 结果的字符串形式（如 "56088"、"25.0"）
        失败 → 错误信息字符串（如 "参数错误：..." / "计算错误：..."）

    注意参数默认值：
        写成 a=None, b=None, operator=None 而不是 a, b, operator
        是为了让"模型没传参数"这种情况能被显式检测出来。
        如果写成必填参数 def calculator(a, b, operator)，
        缺参数时 Python 直接抛 TypeError，来不及走到我们的校验。
    """
    # ---------- 第 1 层：必填校验 ----------
    # 参数默认值是 None，只要有一个是 None，就说明模型漏传了
    #
    # 【{a!r} 里的 !r 是什么】
    #   !r 是 f-string 的转换标志，表示用 repr() 格式输出这个值
    #       f"{a}"    → str(a)     给人看的字符串
    #       f"{a!r}"  → repr(a)    给程序员看的、能还原的表示
    #   关键差别：字符串会带引号
    #       a = "hello"
    #       f"{a}"    → hello      （看不出来是字符串还是变量名）
    #       f"{a!r}"  → 'hello'    （一眼看出是字符串）
    #   为什么错误信息要用 !r：
    #       如果 operator="+ "（多了个空格）
    #       {operator}  → 收到 +          ← 看不出多空格！
    #       {operator!r} → 收到 '+ '      ← 一眼看出多空格！
    if a is None or b is None or operator is None:
        return (
            f"参数错误：a、b、operator 均为必填，"
            f"收到 a={a!r}, b={b!r}, operator={operator!r}"
        )

    # ---------- 第 2 层：类型校验 ----------
    #
    # 【isinstance() 是什么】
    #   判断一个对象是不是某个（或某些）类型
    #       isinstance(对象, 类型)             单个类型
    #       isinstance(对象, (类型1, 类型2))   多个类型，命中任一即 True
    #   示例：
    #       isinstance(123, int)             # True
    #       isinstance("abc", (int, float))  # False
    #       isinstance(5, (int, float))      # True
    #
    # 【为什么不用 type(x) == int】
    #   isinstance 支持继承链，type 太严格：
    #       class MyInt(int): pass
    #       x = MyInt(5)
    #       isinstance(x, int)    # True   ✅
    #       type(x) == int        # False  ❌ 子类不认
    #
    # 【为什么 bool 要单独排除】
    #   bool 是 int 的子类！isinstance(True, int) 返回 True
    #   如果不排除，calculator(True, 2, "+") 会被算成 3，偷偷踩坑
    if isinstance(a, bool) or not isinstance(a, (int, float)):
        return f"参数错误：a 必须是数字，收到 {type(a).__name__}"
    if isinstance(b, bool) or not isinstance(b, (int, float)):
        return f"参数错误：b 必须是数字，收到 {type(b).__name__}"

    # ---------- 第 3 层：operator 枚举校验 ----------
    if operator not in VALID_OPERATORS:
        return (
            f"参数错误：operator 只能取 {VALID_OPERATORS} 之一，"
            f"收到 {operator!r}"        # ← 用 !r 让空格、大小写差异看得见
        )

    # ---------- 第 4 层：除零校验 ----------
    if operator == "/" and b == 0:
        return "计算错误：除数不能为 0"

    # ---------- 显式分支执行（绝不用 eval） ----------
    # eval 是安全红线：靠上游校验保下游安全是脆弱的，
    # 显式分支写 5 行，安全一辈子。
    if operator == "+":
        return str(a + b)
    if operator == "-":
        return str(a - b)
    if operator == "*":
        return str(a * b)
    # 走到这里 operator 一定是 "/"
    return str(a / b)


def count_text_length(text=None) -> str:
    """
    统计 text 的字符数。含参数校验，返回字符串。

    【这个方法有什么用】
        1. 它是 Day18 加进来的第二个工具，用来验证"模型能在多个工具间正确路由"。
           只有 1 个工具时，"选工具"能力根本没被测试；有 2 个工具，
           才能验证模型真的根据 description 做选择。
        2. 它处理的是字符串，和 calculator 处理数字形成互补，
           多一个类型的校验维度（text 必须是 str，而不是数字）。
        3. Day19 用它演示"类型校验"：传数字、传 None 都会返回错误字符串。

    【实际调用效果】
        count_text_length("今天天气很好")  → "6"
        count_text_length(123)             → "参数错误：text 必须是字符串，收到 int"
        count_text_length()                → "参数错误：text 为必填"
    """
    if text is None:
        return "参数错误：text 为必填"
    if not isinstance(text, str):
        return f"参数错误：text 必须是字符串，收到 {type(text).__name__}"
    return str(len(text))


# ============================================================
# 三、工具 JSON Schema（模型"看懂"的说明书）
# ============================================================
# 模型不读你的函数代码，只读这里的 description
# description 越具体（什么时候调、参数含义），模型路由越准

tools = [
    # ---------- 工具1：计算器 ----------
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": (
                "执行加减乘除四则运算。"
                "当用户需要计算两个数字的加减乘除结果时调用。"
                "a、b 必须是数字，operator 只能取 + - * / 之一，除数不能为 0。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "第一个操作数"},
                    "b": {"type": "number", "description": "第二个操作数"},
                    "operator": {
                        "type": "string",
                        "enum": ["+", "-", "*", "/"],   # 限定取值范围
                        "description": "运算符，只能取 + - * / 之一",
                    },
                },
                "required": ["a", "b", "operator"],
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
# 四、工具注册表
# ============================================================
# 值的位置是函数对象本身（calculator），不是计算结果（calculator()）
#   calculator    → 函数对象，可以后面 func(**args) 调用
#   calculator()  → 立刻调用并返回结果，存到字典里就没意义了
#
# 好处：加新工具 = 加函数 + 加 Schema + 加一行映射，主逻辑不动

TOOL_MAP = {
    "calculator": calculator,
    "count_text_length": count_text_length,
}


# ============================================================
# 五、核心流程
# ============================================================

# ---------- 系统提示：明确告诉模型"工具可能返回错误，你要解释" ----------
SYSTEM_PROMPT = (
    "你是一个乐于助人的助手，需要时调用工具。"
    "如果工具返回的内容以'参数错误'或'计算错误'开头，"
    "说明本次调用失败，请向用户解释出错原因，并给出修正建议。"
    "不要自己编造结果。"
)


def _execute_tool(tool_name: str, raw_args: str, tool_call_id: str, messages: list):
    """
    执行单个 tool_call，并把结果（或错误）作为 tool 消息追加到 messages。
    与 Day18 的差异：工具内部已返回字符串，不再需要外层 try/except。
    """
    print(f"[工具路由] 模型选择：{tool_name}，原始参数：{raw_args}")

    # ---------- 解析参数 ----------
    #
    # 【json.loads(raw_args) if raw_args else {} 是什么意思】
    #
    # 这句等价于：
    #     if raw_args:                      # raw_args 非空
    #         tool_args = json.loads(raw_args)   # JSON 字符串 → Python dict
    #     else:
    #         tool_args = {}                # 空字典兜底
    #
    # 是的，json.loads 就是把 JSON 字符串转换成 Python 字典：
    #     '{"a": 123, "b": 456}'  →  {"a": 123, "b": 456}
    #
    # 为什么加 "if raw_args else {}"：
    #   模型有时候会返回 arguments="" 或 None（尤其工具无参数时）
    #       json.loads("")     → JSONDecodeError
    #       json.loads(None)   → TypeError
    #   所以先判断非空，空就给个 {} 兜底。
    #
    # 数据流全景：
    #   raw_args（字符串） → json.loads → tool_args（dict）
    #   → func(**tool_args) 把 dict 拆成关键字参数
    #   等价于 calculator(a=123, b=456, operator="*")
    try:
        tool_args = json.loads(raw_args) if raw_args else {}
    except json.JSONDecodeError as e:
        result = f"参数解析失败：{e}，原始参数：{raw_args}"
        print(f"[工具执行] {result}")
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result,
        })
        return

    # ---------- 查注册表 ----------
    func = TOOL_MAP.get(tool_name)
    if func is None:
        result = f"未知工具：{tool_name}"
        print(f"[工具执行] {result}")
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result,
        })
        return

    # ---------- 执行 ----------
    # 工具内部已做完整校验并返回字符串，这里不再 try/except 判分支
    # 但仍保留一层兜底，防止未来加工具时忘了内部校验
    try:
        result = func(**tool_args)      # ** 是字典解包，见函数上方注释
    except Exception as e:
        result = f"工具执行异常：{type(e).__name__}: {e}"

    print(f"[工具执行] 返回：{result}")
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": result,
    })


def run_with_tools(user_query: str) -> str:
    """跑一次完整流程：模型决策 → 本地校验 → 错误回传 → 模型总结。"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_query},
    ]

    # ---------- 第一次调用：模型决策 ----------
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools,             # 带上工具说明书，模型才知道有哪些工具可调
        temperature=0,           # 工具选择要稳定，不要随机漂移
    )
    assistant_msg = resp.choices[0].message

    # 必须把 assistant_msg 追加进历史
    # 第二次调用时要让模型看到自己刚才的决策（含 tool_calls）
    messages.append(assistant_msg)

    # ---------- 模型没选工具，直接回答 ----------
    if not assistant_msg.tool_calls:
        print(f"[模型回答] 未选择工具，直接回答：{assistant_msg.content}")
        return assistant_msg.content

    # ---------- 循环执行所有 tool_calls ----------
    # 用 for 而不是 tool_calls[0]：模型可能一次请求多个工具
    for tool_call in assistant_msg.tool_calls:
        _execute_tool(
            tool_name=tool_call.function.name,
            raw_args=tool_call.function.arguments,
            tool_call_id=tool_call.id,
            messages=messages,
        )

    # ---------- 第二次调用：模型组织自然语言（含解释错误） ----------
    final_resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0,
    )
    answer = final_resp.choices[0].message.content
    print(f"[模型回答] {answer}")
    return answer


# ============================================================
# 六、本地单元测试（不花 API 费用）
# ============================================================

def test_validation_directly():
    """
    直接调用工具函数，验证校验逻辑。不经过 API，不花一分钱。
    覆盖：正常路径、除零、非法 operator、缺参数、类型错误。
    """
    print("\n" + "=" * 60)
    print("本地单元测试：工具参数校验逻辑（不花 API 费用）")
    print("=" * 60)

    # ---------- lambda 表达式是什么 ----------
    #
    # lambda 是"匿名函数"，用来写"只用一次、不值得起名"的小函数。
    # 语法：
    #     lambda 参数: 返回值
    # 等价于：
    #     def 匿名(参数):
    #         return 返回值
    #
    # 对比：
    #     def add(x, y):        # 普通函数
    #         return x + y
    #     add = lambda x, y: x + y   # 等价的 lambda
    #
    # 【为什么这里用 lambda】
    #   如果直接写 ("加法正常", calculator(1, 2, "+"))，
    #   calculator(1, 2, "+") 会在"定义列表时"立刻执行，
    #   把结果 "3" 存进列表，而不是"待执行的调用"。
    #
    #   套一层 lambda: calculator(...)，
    #   相当于把"调用动作"包起来，延迟到 fn() 时才执行。
    #
    # 【常见搭配】
    #   users.sort(key=lambda u: u["age"])              # sorted 的 key
    #   list(filter(lambda x: x > 0, [1, -2, 3]))       # [1, 3]
    #   list(map(lambda x: x * 2, [1, 2, 3]))           # [2, 4, 6]
    cases = [
        # (用例名, lambda 返回工具调用结果)
        ("加法正常",       lambda: calculator(1, 2, "+")),
        ("减法正常",       lambda: calculator(88, 12, "-")),
        ("除法正常",       lambda: calculator(100, 4, "/")),
        ("除零错误",       lambda: calculator(100, 0, "/")),
        ("非法 operator",  lambda: calculator(2, 3, "^")),
        ("缺 b",           lambda: calculator(a=1, operator="+")),
        ("缺 operator",    lambda: calculator(a=1, b=2)),
        ("a 是字符串",     lambda: calculator("abc", 2, "+")),
        ("a 是 True",      lambda: calculator(True, 2, "+")),
        ("text 缺参数",    lambda: count_text_length()),
        ("text 传数字",    lambda: count_text_length(123)),
        ("text 正常",      lambda: count_text_length("今天天气很好")),
    ]

    for name, fn in cases:
        # 工具内部已返回字符串，正常不会抛异常
        # 这一层 try/except 只是兜底，万一未来改动破坏了契约
        #
        # 【{name:<15} 是什么】
        #   :<15 是"左对齐、宽度 15"的格式说明，纯粹为了终端输出整齐。
        #   f"{name:<15}"   → "加法正常           "（补齐到 15 字符宽）
        #   f"{name:>15}"   → "           加法正常"（右对齐）
        #   f"{name:^15}"   → "     加法正常      "（居中）
        #   这样多行输出的箭头 → 会竖向对齐。去掉也不影响功能。
        try:
            result = fn()
            print(f"[直接校验] {name:<15} → {result}")
        except Exception as e:
            print(f"[直接校验] {name:<15} → 抛异常 {type(e).__name__}: {e}")


# ============================================================
# 七、模拟错误 tool_call，验证"错误回传 + 模型解释"闭环
# ============================================================

def _test_error_recovery(tool_name: str, args_json: str, user_question: str):
    """
    手动构造一个已发生错误的 tool_call，走完整闭环：
    本地校验 → 错误字符串 → tool 消息回传 → 模型组织自然语言解释。

    为什么需要这一步：
        模型不太可能主动传 '^' 或漏参数，靠 run_with_tools() 跑不出这些场景。
        手动构造 assistant 消息带错误 tool_call，才能稳定覆盖边界。
    """
    print("\n" + "-" * 60)
    print(f"模拟错误场景：{tool_name}({args_json})")
    print("-" * 60)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_question},
        # 手动构造一个"模型已经发出了错误调用"的 assistant 消息
        {
            "role": "assistant",
            "content": None,        # assistant 发工具调用时 content 通常是 None
            "tool_calls": [
                {
                    "id": "call_test_1",        # 手动编一个 id，和后面 tool 消息对应
                    "type": "function",
                    "function": {"name": tool_name, "arguments": args_json},
                }
            ],
        },
    ]

    # 走完整的工具执行 + 错误回传
    _execute_tool(
        tool_name=tool_name,
        raw_args=args_json,
        tool_call_id="call_test_1",
        messages=messages,
    )

    # 第二次调用：让模型解释错误
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0,
    )
    print(f"[模型回答] {resp.choices[0].message.content}")


# ============================================================
# 八、测试入口
# ============================================================
# if __name__ == "__main__" 保护：
#   - 直接运行本文件时，__name__ == "__main__" → 下面的测试会执行
#   - 被其他文件 import 时，__name__ == "day19_tool_validation" → 测试不执行
#     （避免 import 时就偷偷调 API 花钱）

if __name__ == "__main__":
    # ---------- 第 1 步：本地直接校验（不花 API 费用，先跑） ----------
    test_validation_directly()

    # ---------- 第 2 步：API 集成测试（含真实错误回传） ----------
    print("\n" + "=" * 60)
    print("API 集成测试：模型决策 + 本地校验 + 错误回传 + 模型总结")
    print("=" * 60)

    test_questions = [
        # 正常路径
        ("计算：123 乘以 456", "123 乘以 456 等于多少？"),
        ("文本长度",           "统计这段话有多少字：今天天气很好，适合出门散步。"),
        # 异常路径：除零（模型多半会直接传 0 作除数）
        ("除零",               "帮我算一下 100 除以 0 等于多少？"),
    ]

    for label, q in test_questions:
        print(f"\n" + "-" * 60)
        print(f"[用例] {label}：{q}")
        print("-" * 60)
        run_with_tools(q)

    # ---------- 第 3 步：模拟错误 tool_call，覆盖"非法 operator"和"缺参数" ----------
    _test_error_recovery(
        tool_name="calculator",
        args_json='{"a": 2, "b": 3, "operator": "^"}',
        user_question="请帮我算 2 的 3 次方。",
    )
    _test_error_recovery(
        tool_name="calculator",
        args_json='{"a": 1, "operator": "+"}',
        user_question="请帮我算 1 加几。",
    )