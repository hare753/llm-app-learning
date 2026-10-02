# ============================================================
# Day17 结构化输出稳定率测试
# 目标：重复调用抽取器，统计 JSON 解析成功率、字段完整率、null 正确率
# 结构：环境初始化 → 工具函数 → 抽取函数 → 失败落盘 → 主逻辑
# ============================================================

import os
import json
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


# ========== 1. 路径与环境初始化 ==========

# BASE_DIR = 当前脚本所在目录，即 .../basic/3-week3/day17
BASE_DIR = Path(__file__).resolve().parent

# ENV_PATH = basic/.env
# parents[0] = 3-week3，parents[1] = basic，parents[2] = code（项目根）
ENV_PATH = BASE_DIR.parents[1] / ".env"
load_dotenv(ENV_PATH)

# 本次测试要抽取的四个字段（顺序由列表固定，不依赖字典）
FIELDS = ["name", "skills", "years", "education"]

# 每个字段的说明，给模型看，决定它怎么理解字段含义
FIELD_DESC = {
    "name": "姓名，字符串",
    "skills": "技能列表，数组格式",
    "years": "工作年限，整数",
    "education": "学历，字符串",
}


def _require_env():
    """
    检查必需的三个环境变量是否存在。
    缺任何一个都直接抛错，避免后面调用 API 时报一堆难懂的错。
    """
    missing = [
        key for key in ("DEEPSEEK_API_KEY", "BASE_URL", "MODEL_NAME")
        if not os.getenv(key)
    ]
    if missing:
        raise RuntimeError(
            f"缺少环境变量：{', '.join(missing)}，请检查 .env 文件：{ENV_PATH}"
        )


# 模块加载时就校验环境，比在 main() 里更早暴露配置问题
_require_env()

# 初始化 OpenAI 客户端（DeepSeek 兼容 OpenAI SDK，只需换 base_url）
# 这两个值只用一次，所以直接写在初始化里，不单独拎成全局变量
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("BASE_URL"),
)

# MODEL 后面每次调用都要用，拎出来只读一次环境变量，改名也方便
MODEL = os.getenv("MODEL_NAME")


# ========== 2. 工具函数 ==========

def clean_json(raw: str) -> str:
    """
    清洗模型返回的 markdown 包裹，返回纯 JSON 字符串。
    防御性保留：即使已用 response_format，换模型时仍可能需要。
    """
    return raw.strip().replace("```json", "").replace("```", "").strip()


def build_extract_prompt(fields: list[str]) -> str:
    """
    根据传入的字段列表拼出 system prompt。
    - fields：这次要抽哪些字段
    - FIELD_DESC：每个字段怎么描述
    拆成两个的好处：改字段只传列表，不用复制整个字典。
    """
    prompt = "你是专业信息抽取助手，只输出JSON，不要任何多余文字。\n请从文本中抽取以下字段：\n"

    for f in fields:
        # 查字段说明，查不到就走兜底描述
        desc = FIELD_DESC.get(f, "按原文内容抽取")
        prompt += f"- {f}: {desc}。未提及填 null，禁止编造。\n"

    return prompt


# ========== 3. 抽取函数：只负责调用与解析，不直接写文件 ==========

def extract_with_fields(text: str, fields: list[str]):
    """
    调用模型抽取字段。

    返回值：(result, raw, error_info)
    - 成功：result 为 dict，raw 为原始返回，error_info 为 None
    - 失败：result 为 None，raw 为原始返回，error_info 为错误详情 dict

    设计要点：函数不写文件、不打印日志，只返回结果。
    失败落盘交给主逻辑统一处理，降低耦合。
    """
    prompt = build_extract_prompt(fields)

    # 提前初始化 raw，防止 API 调用抛异常时后面引用 raw 报 NameError
    raw = ""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
            temperature=0,
            # 强制模型返回合法 JSON 字符串（注意 Prompt 里必须出现 "json" 字样）
            response_format={"type": "json_object"},
        )

        raw = resp.choices[0].message.content or ""
        cleaned = clean_json(raw)
        result = json.loads(cleaned)

        return result, raw, None

    except Exception as e:
        # 失败时打包错误信息，交给主逻辑决定怎么写日志
        error_info = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "text": text,
            "raw": raw,
            "error_type": type(e).__name__,
            "error_msg": str(e),
        }
        return None, raw, error_info


# ========== 4. 失败落盘 ==========

def write_failed(failed_items: list[dict]):
    """
    把本次所有失败记录追加写入 failed_raw.txt。
    统一在这里写，而不是在抽取函数里写，方便以后改成写数据库或上传日志系统。
    """
    if not failed_items:
        return

    failed_path = BASE_DIR / "failed_raw.txt"
    with open(failed_path, "a", encoding="utf-8") as f:
        for item in failed_items:
            f.write("\n" + "=" * 50 + "\n")
            f.write(f"时间：{item.get('time')}\n")
            f.write(f"用例：{item.get('case_id')} 第 {item.get('round')} 次\n")
            f.write(f"输入文本：{item.get('text')}\n")
            f.write(f"原始返回：{item.get('raw')}\n")
            f.write(f"错误类型：{item.get('error_type')}\n")
            f.write(f"错误信息：{item.get('error_msg')}\n")

    print(f"失败原始返回已追加写入：{failed_path}")


# ========== 5. 稳定率测试主逻辑 ==========

def main():
    # ---------- 5.1 测试用例（数据驱动，加用例不改主逻辑） ----------
    # expect_null：预期哪些字段应该为 null
    # expect_complete：预期四个字段是否都非空
    cases = [
        {
            "id": "完整信息",
            "text": "王五，28岁，本科，5年Python开发经验，熟悉FastAPI和SQLite，做过RAG项目。",
            "expect_null": [],
            "expect_complete": True,
        },
        {
            "id": "部分缺失",
            "text": "李四，熟悉Java和Spring开发，做过企业级后端项目。",
            "expect_null": ["years", "education"],
            "expect_complete": False,
        },
        {
            "id": "无有效信息",
            "text": "今天天气不错，适合出去散步放松。",
            "expect_null": ["name", "skills", "years", "education"],
            "expect_complete": False,
        },
        {
            "id": "空文本",
            "text": "",
            "expect_null": ["name", "skills", "years", "education"],
            "expect_complete": False,
        },
    ]

    repeat = 3  # 每个用例重复次数

    # ---------- 5.2 统计计数器 ----------
    total = 0           # 总调用次数（分母）
    parse_ok = 0        # JSON 解析成功次数

    complete_total = 0  # 需要检查字段完整率的分母
    complete_ok = 0     # 字段真的完整的次数

    null_total = 0      # 需要检查 null 正确率的分母（字段数 × 重复次数）
    null_ok = 0         # null 检查通过的次数

    failed_items = []   # 失败记录集合，最后统一落盘

    # ---------- 5.3 打印开头信息 ----------
    print("=" * 50)
    print("开始结构化输出稳定率测试")
    print(f"测试字段：{FIELDS}")
    print(f"每个用例重复 {repeat} 次，temperature=0")
    print("=" * 50)

    # ---------- 5.4 主循环：每个用例重复跑 ----------
    for case in cases:
        print(f"\n>>> 测试用例：{case['id']}")

        for i in range(repeat):
            total += 1
            print(f"  第 {i + 1} 次调用...", end=" ")

            # 调 API 抽取（失败时不抛异常，返回 error_info）
            result, raw, error_info = extract_with_fields(case["text"], FIELDS)
            time.sleep(1)  # 防限流

            # 失败分支：记录 + 跳过后续检查
            if result is None:
                print("[FAIL] 解析失败，已记录")
                failed_items.append({
                    "case_id": case["id"],
                    "round": i + 1,
                    "text": case["text"],
                    "raw": raw,
                    # 把 error_info 的键值对合并进来（若为 None 则合并空 dict）
                    **(error_info or {}),
                })
                continue

            # 成功分支：计入解析成功
            parse_ok += 1

            # 字段完整率：只对 expect_complete=True 的用例统计
            if case.get("expect_complete"):
                complete_total += 1
                all_has_value = all(result.get(f) is not None for f in FIELDS)
                if all_has_value:
                    complete_ok += 1
                    print("[OK] 解析成功，字段齐全")
                else:
                    print(f"[WARN] 解析成功，但字段缺失：{result}")

            # null 正确率：按 expect_null 列表逐字段检查
            for f in case.get("expect_null", []):
                null_total += 1
                if result.get(f) is None:
                    null_ok += 1
                else:
                    print(f"[WARN] null 规则不符：{f}={result.get(f)}")

            # 打印抽取结果（ensure_ascii=False 保证中文不乱码）
            print(f"[OK] 结果：{json.dumps(result, ensure_ascii=False)}")

    # ---------- 5.5 统一写失败日志 ----------
    write_failed(failed_items)

    # ---------- 5.6 打印统计结果 ----------
    print("\n" + "=" * 50)
    print("测试统计结果")
    print("=" * 50)
    print(f"总调用次数：{total}")
    print(f"JSON 解析成功率：{parse_ok}/{total} = {parse_ok / total * 100:.1f}%")

    # if 判断防止分母为 0 时除零报错
    if complete_total:
        print(f"完整文本字段完整率：{complete_ok}/{complete_total} = "
              f"{complete_ok / complete_total * 100:.1f}%")
    else:
        print("完整文本字段完整率：无完整文本用例")

    if null_total:
        print(f"null 正确率：{null_ok}/{null_total} = "
              f"{null_ok / null_total * 100:.1f}%")
    else:
        print("null 正确率：无预期 null 字段")


# ========== 6. 程序入口 ==========
# 只有直接运行本文件时才执行 main()，被 import 时不会跑
if __name__ == "__main__":
    main()