# =============================================================================
# Week3 Day16：Prompt 模板化与代码化
# -----------------------------------------------------------------------------
# 这个文件要干什么？
#   把「怎么写 prompt」这件事，从「写死一段文字」升级成「一个可以传参数的函数」。
#
# 举例：
#   想抽取姓名和技能 → 传 ["name", "skills"]
#   想抽取姓名、年限、学历 → 传 ["name", "years", "education"]
#   调用 API 的代码完全不用改，只改传进去的参数。
#
# 这就叫「改字段不改流程」——Day16 的核心目标。
# =============================================================================


# -----------------------------------------------------------------------------
# 0. import 部分：导入需要用到的工具
# -----------------------------------------------------------------------------
# import os         → 用来读环境变量，例如 os.getenv("DEEPSEEK_API_KEY")
# import json       → 用来处理 JSON：
#                       json.dumps() 把 Python 字典转成 JSON 字符串
#                       json.loads() 把 JSON 字符串转回 Python 字典
# from pathlib import Path → Path 是 Python 处理文件路径的现代方式，
#                             比直接用字符串拼路径更安全、更清晰
# from dotenv import load_dotenv → 从 .env 文件里把变量读进 os.environ
# from openai import OpenAI → DeepSeek 兼容 OpenAI 的 SDK，所以用同一个包
import os
import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


# -----------------------------------------------------------------------------
# 1. 找到 .env 文件的位置
# -----------------------------------------------------------------------------
# 问题背景：
#   我们写过 .env，里面存着 API Key。程序怎么找到它？
#   如果直接写 load_dotenv()，它会从「你运行命令的那个目录」往上找，
#   容易找不到、或者找到别的目录的 .env。
#
# 解决办法：
#   用 __file__ 拿到「当前这个 .py 文件自己的路径」，
#   再一级一级往上推到 basic/ 目录，那里存放着 .env。
#
# 相关语法：
#   __file__     是 Python 自动提供的一个变量，值 = 当前脚本的文件路径
#   Path(...)    把路径字符串包装成一个 Path 对象，方便调用各种方法
#   .resolve()   把路径转成「绝对路径」，去掉 . 和 .. 之类的相对符号
#   .parents     是 Path 对象的一个属性，是一个「上级目录列表」
#   .parents[0]  当前文件的直接上级目录
#   .parents[1]  再上一级
#   .parents[2]  再再上一级
#
# 当前目录结构：
#   basic/3-week3/day16/day16_prompt_template.py
#   parents[0] = day16
#   parents[1] = 3-week3
#   parents[2] = basic           ← .env 就在这一层
#
# 运算符 / ：
#   Path 对象支持用 / 拼路径，比 "a" + "/" + "b" 更清晰。
#   BASE_DIR / ".env" 等价于「在 BASE_DIR 目录下找 .env 文件」。
BASE_DIR = Path(__file__).resolve().parents[2]     # 得到 basic/ 的绝对路径
ENV_PATH = BASE_DIR / ".env"                        # 得到 basic/.env 的绝对路径

# load_dotenv() 的作用：
#   打开指定的 .env 文件，把里面的 KEY=VALUE 逐行读进「环境变量」。
#   读进去之后，就能用 os.getenv("KEY") 拿到对应的 VALUE。
#
# 为什么这里要显式传 ENV_PATH？
#   load_dotenv() 不传参数时，会从当前工作目录往上找 .env，
#   找到了就用，找不到就静默跳过。这种行为在某些场景下会「找到错的文件」。
#   显式传路径，等于告诉它：「只读这个文件，别乱找」。
load_dotenv(ENV_PATH)


# -----------------------------------------------------------------------------
# 2. 校验环境变量（_require_env 函数）
# -----------------------------------------------------------------------------
# 为什么需要提前校验？
#   如果 .env 里漏了 DEEPSEEK_API_KEY，程序不会在启动时告诉你，
#   而是等到你调 API 时，才报一个「网络超时」或「401 未授权」的错，
#   这种错误看不出真正原因，排查浪费时间。
#
#   所以这里在程序启动阶段就检查：缺少就立刻抛错，而且报错信息里写明
#   「去哪个 .env 文件补」，一目了然。
#
# 函数定义语法：
#   def 函数名(参数):
#       函数体
#       return 返回值
#
#   def _require_env():     ← 定义函数，函数名以下划线开头，约定表示「内部使用」
#   return a, b, c          ← 用逗号分隔返回多个值，调用方可以一次性接收
def _require_env():
    # os.getenv("XXX") 从环境变量里读 XXX 的值；
    # 如果不存在，返回 None。
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("BASE_URL")

    # os.getenv 的第二个参数是「默认值」：
    # 如果 MODEL_NAME 没设置，就返回 "deepseek-chat"。
    model_name = os.getenv("MODEL_NAME", "deepseek-chat")

    # if not xxx: 等价于 if xxx 是 空字符串 / None / 0 等「假值」。
    # raise RuntimeError("...") 抛出异常，直接终止程序，并把信息打印出来。
    # f"..." 是「格式化字符串」，里面的 {变量名} 会被替换成变量的实际值。
    if not api_key:
        raise RuntimeError(f"缺少 DEEPSEEK_API_KEY，请检查：{ENV_PATH}")
    if not base_url:
        raise RuntimeError(f"缺少 BASE_URL，请检查：{ENV_PATH}")

    # 一次性返回三个值，调用方用 a, b, c = 接收。
    return api_key, base_url, model_name


# 下面这行 = 调用上面的函数，并把三个返回值分别赋给三个变量。
# 这叫「解包赋值」。等号左边有三个变量，右边返回三个值，一一对应。
API_KEY, BASE_URL, MODEL_NAME = _require_env()

# 创建 OpenAI 客户端：
#   - 第一个参数 api_key：你的 DeepSeek Key
#   - 第二个参数 base_url：告诉 SDK 别打 OpenAI 官方地址，改打 DeepSeek 的地址
#     如果不写 base_url，SDK 默认访问 https://api.openai.com，国内会超时。
client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


# -----------------------------------------------------------------------------
# 3. 字段描述字典 FIELD_DESCRIPTIONS
# -----------------------------------------------------------------------------
# 这是什么？
#   一个 Python 字典（dict），用「键: 值」的形式存数据。
#   键 = 字段名（要抽取什么）
#   值 = 这个字段的说明（告诉模型这个字段是什么意思）
#
# 为什么要有它？
#   build_extract_prompt 会根据传入的字段名，到这里查描述；
#   描述写得越清楚，模型越知道该怎么填。
#
# 语法：
#   { "键1": "值1", "键2": "值2", ... }
#   键和值之间用冒号，多个键值对之间用逗号分隔。
#
# Day16 踩坑记录：
#   曾经把字段写成 "year"（单数），但字典键是 "years"（复数），
#   结果 .get() 找不到键，走了兜底描述，模型没能把「5年」映射进来。
#   教训：字段名和字典键必须完全一致。
FIELD_DESCRIPTIONS = {
    "name": "姓名，字符串。未提及填 null。",
    "skills": "技能列表，字符串数组。未提及填 null。",
    "years": "工作年限，整数。未提及填 null。",
    "education": "学历，字符串。未提及填 null。",
}


# -----------------------------------------------------------------------------
# 4. JSON 清洗函数 clean_json
# -----------------------------------------------------------------------------
# 背景：
#   模型有时会输出 markdown 代码块，比如：
#     ```json
#     {"name": "王五"}
#     ```
#   这样直接 json.loads 会报错，因为开头的 ```json 不是合法 JSON。
#   这个函数负责把「外壳」剥掉，只留下真正的 JSON 文本。
#
# 函数签名语法：
#   def clean_json(raw: str) -> str:
#     - "raw: str" 是「类型提示」，表示参数 raw 期望是字符串；
#     - "-> str" 是「返回值类型提示」，表示函数返回字符串。
#     - 类型提示只是给人看的，不写也能跑，但写了更清晰。
#
# 三引号 """...""" 是「文档字符串」（docstring），
#   写在函数第一行，用来描述这个函数是干什么的。
#   运行程序时不会被执行，只是给人（和工具）看的文档。
def clean_json(raw: str) -> str:
    """清洗模型可能带出的 markdown 代码块包裹。"""

    # .strip() 是字符串方法，去掉首尾的空白（空格、换行、制表符）。
    # 这里 raw = raw.strip() 表示「把处理结果再赋给 raw 自己」。
    # 相当于 raw 被更新成了「去空格后的版本」。
    raw = raw.strip()

    # .replace("旧", "新") 把字符串里的「旧」全部替换成「新」。
    # 链式调用：raw.replace(...).replace(...) 意思是对替换后的结果再做一次替换。
    # 第一步：把 "```json" 替换成空字符串 → 相当于删掉它
    # 第二步：把 "```" 也替换成空字符串 → 删掉剩余的反引号
    raw = raw.replace("```json", "").replace("```", "")

    # 再清一次首尾空白：因为剥掉 ``` 后，可能留下空行。
    return raw.strip()


# -----------------------------------------------------------------------------
# 5. Prompt 模板函数 build_extract_prompt —— Day16 的主角
# -----------------------------------------------------------------------------
# 核心思想：
#   把「构造 prompt」变成「用一个函数生成」。
#   输入：字段名列表，比如 ["name", "skills"]
#   输出：完整的 system prompt 字符串
#
# 这样做的好处：
#   - 想换字段 → 只改传进去的列表；
#   - prompt 的格式（要求、示例结构）保持统一；
#   - 改动集中在一处，不会到处找 prompt 文本。
def build_extract_prompt(fields: list[str]) -> str:
    """
    根据传入字段动态生成抽取 Prompt。
    目标：改字段只改参数，不改调用流程。
    """

    # 如果传入的是空列表 []，直接抛错。
    # 因为「抽取 0 个字段」这个要求本身就不合理，早点拦住。
    if not fields:
        raise ValueError("fields 不能为空")

    # 准备两个空容器，稍后往里面塞东西。
    # field_lines = [] 空列表，用来一行一行地攒「- 字段名: 描述」
    # example_obj = {} 空字典，用来攒「示例 JSON 结构」
    field_lines = []
    example_obj = {}

    # for 循环：把 fields 里的每个元素依次取出来，赋给变量 field。
    # 假设 fields = ["name", "skills"]，那么循环体执行两次：
    #   第 1 次：field = "name"
    #   第 2 次：field = "skills"
    for field in fields:
        # 字典的 .get(键, 默认值) 方法：
        #   如果键存在，返回对应的值；
        #   如果键不存在，返回第二个参数（默认值）。
        #
        # 这里：优先从 FIELD_DESCRIPTIONS 找描述；
        #       找不到就返回 "按原文抽取；未提及填 null。" 作为兜底。
        # 用 .get 而不是 [field]，是为了防止 KeyError（找不到键时崩溃）。
        desc = FIELD_DESCRIPTIONS.get(field, "按原文抽取；未提及填 null。")

        # .append(元素) 是列表方法：往列表末尾添加一个元素。
        # f"- {field}: {desc}" 生成类似 "- name: 姓名，字符串。未提及填 null。"
        field_lines.append(f"- {field}: {desc}")

        # 往 example_obj 字典里加一个键值对：
        #   键 = field（比如 "name"）
        #   值 = None（Python 里的 None 相当于 JSON 里的 null）
        # 示例里字段值都给 null，是为了告诉模型：「这是结构模板，不是答案」，
        # 避免模型把示例里的 null 直接抄下来。
        example_obj[field] = None

    # json.dumps() 把 Python 对象转成 JSON 格式的字符串。
    #   example_obj 是个字典，转成字符串后长这样：
    #     {
    #       "name": null,
    #       "skills": null
    #     }
    # 参数解释：
    #   ensure_ascii=False：允许中文原样输出，不转成 \uXXXX 转义序列；
    #   indent=2：每层缩进 2 个空格，输出更易读。
    example_json = json.dumps(example_obj, ensure_ascii=False, indent=2)

    # 下面用 f-string（三引号）拼出最终的 prompt 文本。
    # f"""...""" 表示「这是一个可以插入变量的多行字符串」。
    #
    # 关键点 1：{chr(10).join(field_lines)}
    #   chr(10) 返回换行符 "\n"。
    #   为什么不用直接写 "\n"？
    #     在 f-string 表达式内部（{}里）写反斜杠，老版本 Python 会报语法错误。
    #     用 chr(10) 拿到同样的换行符，绕过这个限制。
    #   "分隔符".join(列表) 把列表里的每个元素用分隔符连接成一个字符串。
    #     比如 ["a", "b"] 用 "\n" 连接 → "a\nb"
    #     这里是把多行字段描述用换行拼起来。
    #
    # 关键点 2：{fields}
    #   直接把列表插进 prompt，会显示成 "['name', 'skills']"。
    #   模型能看懂，但如果你追求更工整，可以改成 ", ".join(fields)。
    #
    # 关键点 3：Prompts 里必须出现小写 "json" 字样。
    #   因为我们调用 API 时用了 response_format={"type": "json_object"}，
    #   这个参数强制要求 prompt 里出现 "json" 单词，否则 API 直接返回 400。
    #   我们结尾那两行「必须是合法 json」「json 示例结构」就是这个作用。
    prompt = f"""你是一个结构化信息抽取器。请从用户文本中抽取以下字段：
{chr(10).join(field_lines)}

要求：
1. 只输出一个合法 json 对象，不要输出 markdown 代码块，不要输出任何解释。
2. 必须包含以下字段，字段名必须完全一致：{fields}
3. 未提及的字段填 null，不要编造。
4. 输出必须是合法 json。

json 示例结构：
{example_json}
"""

    # 把拼好的 prompt 返回给调用方。
    return prompt


# -----------------------------------------------------------------------------
# 6. 抽取函数 extract_with_fields
# -----------------------------------------------------------------------------
# 这个函数做三件事：
#   ① 用 build_extract_prompt 生成 system prompt
#   ② 调用 DeepSeek API
#   ③ 清洗 + 解析模型返回的 JSON
#
# 和 Day15 的 extract() 区别：
#   Day15 的字段写死在 prompt 里；
#   这里字段是通过参数传进来的，可以随时换。
def extract_with_fields(text: str, fields: list[str]) -> dict | None:
    """
    使用动态模板 Prompt 调用模型，并解析 JSON。

    返回类型说明：dict | None
      表示「要么返回一个字典，要么返回 None」。
      这是 Python 3.10+ 的新写法，等价于旧写法的 Optional[dict]。
    """

    # 用模板函数生成 system prompt。
    system_prompt = build_extract_prompt(fields)

    # 调用 API。
    # 参数逐个说明：
    #   model        → 用哪个模型（从 .env 读的，默认 deepseek-chat）
    #   messages     → 对话消息列表，每条是 {"role": "...", "content": "..."}
    #                  role 有三种：system（规则）、user（用户输入）、assistant（模型输出）
    #   temperature  → 采样温度，0 表示输出最稳定；写代码、抽信息一般都用 0
    #   response_format → 强制模型输出合法 JSON 对象
    #                     （前提：prompt 里必须出现 "json" 字样）
    resp = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )

    # 从返回值里一路取到模型返回的文本内容。
    #   resp                        → API 返回的完整对象
    #   resp.choices                → 返回的候选项列表（通常只取第 0 个）
    #   resp.choices[0]             → 第 0 个候选项
    #   .message                    → 那个候选项里的消息对象
    #   .message.content            → 消息里的文本内容（可能是 None）
    #   ... or ""                   → 如果取到的是 None，就用空字符串兜底，
    #                                  防止下面 .strip() 报 NoneType 错误。
    raw = resp.choices[0].message.content or ""

    # 打印原始返回，方便调试。print("\n--- raw ---") 里 \n 是换行。
    print("\n--- raw ---")
    print(raw)

    # try/except 是「异常处理」：
    #   try 里的代码如果出错，会跳到 except 里处理，程序不崩溃。
    # 这里的出错是 json.JSONDecodeError：
    #   当 json.loads 的输入不是合法 JSON 时，会抛出这个异常。
    #
    # 处理策略：
    #   打印错误 → 返回 None。让调用方（上层代码）自己决定怎么办
    #   （重试、跳过、上报），不要在这里直接崩。
    try:
        # 先 clean_json 剥掉 markdown 包裹，再 json.loads 转成字典。
        return json.loads(clean_json(raw))
    except json.JSONDecodeError as e:
        # f 前缀或逗号都可以，这里用逗号分隔，会自动拼在一起打印。
        print("JSON 解析失败：", e)
        return None


# -----------------------------------------------------------------------------
# 7. 命令行入口
# -----------------------------------------------------------------------------
# if __name__ == "__main__": 是什么意思？
#   Python 里每个文件都有个特殊变量 __name__：
#     - 当文件「直接运行」时，__name__ 的值是 "__main__"；
#     - 当文件被「别的文件 import」时，__name__ 的值是「文件名」。
#
#   所以这行的作用：
#     - 直接运行 → 下面的代码会执行；
#     - 被 import（比如未来被 FastAPI 导入）→ 下面不执行。
#
#   为什么要这么写？
#     否则 FastAPI import 这个模块时，会顺便把下面这些「测试代码」也跑了，
#     触发不必要的 API 调用。
if __name__ == "__main__":
    # 待抽取的测试文本。
    # 里面包含：姓名（王五）、年龄（28岁）、学历（本科）、
    #           年限（5年）、技能（Python/FastAPI/SQLite）、项目（RAG）
    text = "王五，28岁，本科，5年Python开发经验，熟悉FastAPI和SQLite，做过RAG项目"

    # 定义一个「字段组」列表。
    # 这个列表有 2 个元素，每个元素本身也是一个列表（字段名）。
    # 两个内层列表代表我们想要测试的两种字段组合。
    text_field_groups = [
        ["name", "skills"],
        ["name", "years", "education"],
    ]

    # 遍历每一组字段，分别跑一次抽取流程。
    for fields in text_field_groups:
        # "=" * 60 → 生成 60 个等号组成的字符串，用来做分隔线。
        print("=" * 60)

        # print 可以一次打印多个值，用逗号分隔，会自动加空格。
        print("传入字段：", fields)

        # 先打印生成的 prompt，肉眼确认「字段变了，prompt 也跟着变」。
        print("--- 生成的 Prompt ---")
        print(build_extract_prompt(fields))

        # 调用抽取函数，拿回结果。
        result = extract_with_fields(text, fields)

        print("--- 解析结果 ---")
        print(result)

        # 如果结果为 None（解析失败），打印失败提示并跳过后面的检查。
        # continue 表示「跳过后面的代码，直接进入下一轮循环」。
        if result is None:
            print("字段完整：False")
            continue

        # 「列表推导式」的语法：
        #   [要收集的元素 for 变量 in 可迭代对象 if 条件]
        # 读作：
        #   对于 fields 中的每个 f，如果 f 不在 result 里，就把 f 放进列表。
        #
        # 第一句 = 找出「要求抽但没抽到」的字段；
        # 第二句 = 找出「没要求抽却抽到了」的字段。
        # 只有两者都为空，说明模型乖乖按字段列表输出。
        missing = [f for f in fields if f not in result]
        extra = [f for f in result if f not in fields]

        print("缺失字段：", missing)
        print("多余字段：", extra)

        # not missing → 如果 missing 是空列表，则 not [] 为 True。
        # 所以「字段完整：True」表示所有要求的字段都在。
        print("字段完整：", not missing)