# ============================================================
# day15_few_shot.py
# ------------------------------------------------------------
# Week3 Day15 主线：Few-shot 示例控制输出
#
# 目标：
#   同一段输入文本，分别用 0-shot 和 few-shot 两种 Prompt 写法调用模型，
#   对比两次输出在「格式稳定性」和「字段一致性」上的差异。
#
# 核心结论：
#   Few-shot 是给模型看例子，不是讲道理。
#   示例要短、字段名要和目标一致、assistant 的 content 必须是纯 JSON。
#
# 运行方式：
#   cd basic/3-week3/day15
#   python day15_few_shot.py
#
# 依赖：
#   basic/.env 中必须有 DEEPSEEK_API_KEY、BASE_URL；
#   MODEL_NAME 可选，缺省为 deepseek-chat。
#
# 输出：
#   终端打印两次 raw 与 parsed；
#   同目录下生成 day15_0shot_raw.txt、day15_fewshot_raw.txt。
# ============================================================

import os
import json
from dotenv import load_dotenv
from openai import OpenAI


# ------------------------------------------------------------
# 一、定位 .env 文件路径
# ------------------------------------------------------------
# 当前脚本位于 basic/3-week3/day15/，而 .env 在 basic/ 下。
# 用 __file__ 反推脚本所在目录，再往上走两级找到 .env。
# 这样不管从哪个工作目录运行脚本，都能读到同一个 .env。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))            # .../basic/3-week3/day15
ENV_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".env"))  # .../basic/.env

# 显式指定 .env 路径，避免 load_dotenv() 去当前工作目录里乱找
load_dotenv(dotenv_path=ENV_PATH)


# ------------------------------------------------------------
# 二、环境变量校验
# ------------------------------------------------------------
# 必填项缺失或为空时，立刻抛中文错误并终止程序。
# 好处：启动瞬间就知道是 .env 没配好，不用等到调 API 报 401 才排查。
def _require_env(name: str) -> str:
    value = os.getenv(name)
    # value 为 None（变量不存在）或 strip 后为空（全是空格），都视为未配置
    if value is None or not value.strip():
        raise RuntimeError(
            f"[配置错误] 环境变量 {name} 未配置或为空。\n"
            f"请检查文件：{ENV_PATH}\n"
            f"参考格式：\n"
            f"  DEEPSEEK_API_KEY=sk-xxxxxxxx\n"
            f"  BASE_URL=https://api.deepseek.com\n"
            f"  MODEL_NAME=deepseek-chat"
        )
    # 去掉首尾空格，防止手滑多敲空格导致鉴权失败
    return value.strip()


# API_KEY 与 BASE_URL 为必填项，缺一个直接报错
API_KEY = _require_env("DEEPSEEK_API_KEY")
BASE_URL = _require_env("BASE_URL")

# MODEL_NAME 为可选项：
#   - 没写 → 默认 "deepseek-chat"
#   - 写了但为空 → 用 or 兜底成 "deepseek-chat"
MODEL = os.getenv("MODEL_NAME", "deepseek-chat").strip() or "deepseek-chat"


# ------------------------------------------------------------
# 三、创建 OpenAI 客户端
# ------------------------------------------------------------
# DeepSeek 兼容 OpenAI 1.x 接口，所以直接用 openai 库。
# timeout=30.0：连接超时 30 秒，避免网络异常时长时间挂起。
client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
    timeout=30.0,
)


# ------------------------------------------------------------
# 四、通用工具函数
# ------------------------------------------------------------
def clean_json(raw: str) -> str:
    """
    清洗模型返回的字符串：
      1. 去掉首尾空白
      2. 去掉可能的 ```json 前缀
      3. 去掉可能的 ``` 后缀
      4. 再 strip 一次
    即使启用了 response_format，保留这一步作为兜底，
    方便以后换模型或关掉该参数时仍能正常解析。
    """
    return raw.strip().replace("```json", "").replace("```", "").strip()


# 系统提示词：约束模型只输出 JSON，不解释、不加多余文字
SYSTEM_PROMPT = "你是一个信息抽取助手。只输出 JSON，不要解释，不要多余文字。"

# 本次对比实验使用的测试文本
TEXT = "王五，28岁，本科，5年Python开发经验，熟悉FastAPI和SQLite，做过RAG项目。"


# ------------------------------------------------------------
# 五、0-shot 版本
# ------------------------------------------------------------
# 特点：只给 system 指令 + user 文本，不给任何示例。
# 缺点：模型可能字段名漂移、格式不稳、解释性文字混入。
def run_0shot(text: str) -> str:
    messages = [
        # 系统角色：约束输出风格
        {"role": "system", "content": SYSTEM_PROMPT},

        # 用户角色：给出任务和待抽取文本
        {
            "role": "user",
            "content": (
                "从下面文本中抽取 name、skills、years、education 四个字段。"
                "未提及的字段填 null。只输出 JSON。\n\n"
                f"文本：{text}"
            ),
        },
    ]

    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        # temperature=0：让输出尽可能确定，适合信息抽取这类结构化任务
        temperature=0,
        # 强制模型返回合法 JSON 字符串；
        # 注意：启用该参数时 Prompt 里必须出现 "json" 字样，否则 API 返回 400
        response_format={"type": "json_object"},
    )

    # content 可能为 None（极少情况），用 or "" 兜底，避免后续 .strip() 报错
    raw = resp.choices[0].message.content or ""
    return raw


# ------------------------------------------------------------
# 六、few-shot 版本
# ------------------------------------------------------------
# 特点：在 messages 里插入 2 组「user 提问 + assistant 回答 JSON」示例。
# 要求：示例短、字段名与目标一致、assistant 的 content 必须是纯 JSON 字符串。
# 效果：模型有样学样，字段名和格式会严格对齐示例风格。
def run_fewshot(text: str) -> str:
    messages = [
        # 系统角色
        {"role": "system", "content": SYSTEM_PROMPT},

        # ---------- 示例 1 ----------
        {
            "role": "user",
            "content": "张三，本科，3年Python经验，会FastAPI。请抽取 name、skills、years、education。",
        },
        {
            "role": "assistant",
            # 注意：这里必须是 JSON 字符串，不能是 Python dict
            "content": '{"name":"张三","skills":["Python","FastAPI"],"years":3,"education":"本科"}',
        },

        # ---------- 示例 2 ----------
        {
            "role": "user",
            "content": "李四，硕士，5年经验，熟悉LangChain和RAG。请抽取 name、skills、years、education。",
        },
        {
            "role": "assistant",
            "content": '{"name":"李四","skills":["LangChain","RAG"],"years":5,"education":"硕士"}',
        },

        # ---------- 真正要抽取的输入 ----------
        {
            "role": "user",
            "content": (
                "从下面文本中抽取 name、skills、years、education 四个字段。"
                "未提及的字段填 null。只输出 JSON。\n\n"
                f"文本：{text}"
            ),
        },
    ]

    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0,
        response_format={"type": "json_object"},
    )

    raw = resp.choices[0].message.content or ""
    return raw


# ------------------------------------------------------------
# 七、解析函数
# ------------------------------------------------------------
# 先 clean_json 再去 json.loads；
# 解析失败返回 None，不抛异常，让上层决定怎么处理。
def parse_or_none(raw: str):
    try:
        return json.loads(clean_json(raw))
    except json.JSONDecodeError:
        # 只捕获 JSON 解析错误；其它异常照常抛出，方便定位真正的 bug
        return None


# ------------------------------------------------------------
# 八、主流程
# ------------------------------------------------------------
if __name__ == "__main__":
    # 1. 分别跑 0-shot 和 few-shot
    raw_0 = run_0shot(TEXT)
    raw_few = run_fewshot(TEXT)

    # 2. 解析成 Python 字典（失败为 None）
    data_0 = parse_or_none(raw_0)
    data_few = parse_or_none(raw_few)

    # 3. 打印 0-shot 结果
    print("===== 0-shot raw =====")
    print(raw_0)
    print("===== 0-shot parsed =====")
    print(data_0)

    # 4. 打印 few-shot 结果
    print("\n===== few-shot raw =====")
    print(raw_few)
    print("===== few-shot parsed =====")
    print(data_few)

    # 5. 把两次 raw 保存到脚本所在目录
    #    用 os.path.join(BASE_DIR, ...) 确保不管从哪运行，都落到 day15/ 下
    out_path_0 = os.path.join(BASE_DIR, "day15_0shot_raw.txt")
    out_path_few = os.path.join(BASE_DIR, "day15_fewshot_raw.txt")

    with open(out_path_0, "w", encoding="utf-8") as f:
        f.write(raw_0)

    with open(out_path_few, "w", encoding="utf-8") as f:
        f.write(raw_few)

    # 6. 打印解析成功率
    #    只要 data_x 不是 None，就说明清洗 + 解析成功
    print("\n解析成功率：")
    print("0-shot:", data_0 is not None)
    print("few-shot:", data_few is not None)