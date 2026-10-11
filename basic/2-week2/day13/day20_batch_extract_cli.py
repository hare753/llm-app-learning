"""
Day20: 批量抽取容错 + 重试 + 日志

运行（必须在 basic/2-week2/day13/ 下，与 day13_extractor.py 同目录）：
    python day20_batch_extract_cli.py               # 默认处理脚本所在目录
    python day20_batch_extract_cli.py ./mytexts     # 处理指定目录

设计要点：
- 文件路径全部基于 __file__ 锚定，不依赖当前工作目录（Day15/Day19 复用经验）
- 三层职责分离：main 管批量 / process_file 管单文件 / extract_with_retry 管重试
- process_file 保证"总返回、不抛异常"，主循环无需 try/except
- 重试仅针对"临时错误"（网络抖动、模型偶发解析失败），空文件等确定性失败不重试
"""
import os
import sys
import json
import time
import glob
from datetime import datetime

from day13_extractor import extract   # 复用 Day13 主线抽取函数，一行不改


# ─────────────────────────────────────────────────────────────
# 全局常量
# ─────────────────────────────────────────────────────────────

# 锚定脚本所在目录：__file__ 是脚本自身路径，abspath 转绝对，dirname 取目录
# 好处：无论从哪个目录启动脚本，路径都指向脚本所在地，不会落错位置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 日志文件路径：拼在脚本目录下，与 BASE_DIR 同源，永不漂移
LOG_PATH = os.path.join(BASE_DIR, "extract_log.jsonl")

# 重试策略：最多重试 1 次（即总共调 2 次），重试前等 1 秒防限流
MAX_RETRY = 1
RETRY_SLEEP = 1.0


# ─────────────────────────────────────────────────────────────
# 日志写入
# ─────────────────────────────────────────────────────────────

def write_log(entry: dict) -> None:
    """
    追加一行 JSONL 日志。

    JSONL = 每行一个独立 JSON 对象。相比一个大 JSON 数组：
    - 追加写不用读全文件，O(1) 落盘
    - 单行损坏不影响其他行
    - 命令行可逐行 json.loads 读取

    ensure_ascii=False：中文原样写入，不转成 Unicode 转义序列
    encoding="utf-8"：Windows 默认 GBK，不加会乱码
    """
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ─────────────────────────────────────────────────────────────
# 抽取 + 重试
# ─────────────────────────────────────────────────────────────

def extract_with_retry(text: str, max_retry: int = MAX_RETRY):
    """
    带重试的抽取。只负责"调 API + 失败重试"这一段。

    返回 (result, error) 二元组：
      - 成功：(dict, None)
      - 失败：(None, "错误描述字符串")

    为什么用双返回值而不是抛异常：
      调用方（process_file）不关心"第一次失败还是重试后失败"，
      只想要"最终成没成、错在哪"。元组比异常更直接。

    重试范围：
      - extract() 返回 None（模型解析失败）→ 重试
      - extract() 抛异常（网络抖动等）  → 重试
      - 空文本、文件不存在等 → 由上游预检拦下，不到这里
    """
    last_error = None

    # range(max_retry + 1)：max_retry=1 → 循环 2 次
    # attempt=0 是初试，attempt=1 是重试
    for attempt in range(max_retry + 1):
        try:
            result = extract(text)

            # 用 is not None 而非 if result：
            # 空字典 {} 在 Python 里是假值，if result 会误判为失败
            if result is not None:
                return result, None   # 成功立刻返回，不浪费后续时间

            last_error = "抽取失败，extract() 返回 None"

        except Exception as e:
            # 记录异常类型（如 ConnectTimeout、JSONDecodeError）
            # type(e).__name__ 比 str(e) 更稳定，便于分类统计
            last_error = f"抽取异常：{type(e).__name__}: {e}"

        # 不是最后一次迭代才 sleep
        # 最后一次失败直接返回，没必要再等 1 秒
        if attempt < max_retry:
            time.sleep(RETRY_SLEEP)

    # 循环走完仍失败，返回最后一次错误
    return None, last_error


# ─────────────────────────────────────────────────────────────
# 单文件处理流水线
# ─────────────────────────────────────────────────────────────

def process_file(filepath: str) -> dict:
    """
    处理单个文件的全流程，返回一条日志条目 dict。

    契约：**保证不抛异常**。任何失败点都自己 return 一个 failed 条目。
    因此主循环 for fp in files: process_file(fp) 不需要 try/except。

    5 步流水线：
      1. 读文件    → 读不出直接返回 failed
      2. 空文本预检 → 空文件不调 API，省两次调用
      3. 抽取（带重试）→ 失败返回 failed
      4. 写 JSON   → 写不进返回 failed
      5. 成功返回 success 条目
    """
    # 只取文件名（如 "resume.txt"），日志里不写全路径，更简洁
    filename = os.path.basename(filepath)

    # ISO 8601 格式时间戳，排序友好，带时区时可扩展
    # timespec="seconds" 去掉微秒，日志更易读
    now = datetime.now().isoformat(timespec="seconds")

    # ── 步骤 1：读文件 ──────────────────────
    # encoding="utf-8" 必加，Windows 默认 GBK 会乱码
    # with open(...) 保证无论是否异常，文件都被关闭
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        # 读不出来（权限、编码错误、文件消失）→ 直接失败
        return {
            "file": filename,
            "status": "failed",
            "error": f"读取失败：{type(e).__name__}: {e}",
            "timestamp": now,
        }

    # ── 步骤 2：空文本预检（省钱）──────────
    # 空文件 100% 会失败。提前判断可以省掉：
    #   - 1 次初试 API 调用
    #   - 1 次重试 API 调用
    #   - 2 秒重试 sleep
    # .strip() 把空格、换行、Tab 全剥掉，全是空白也算空
    if not text.strip():
        return {
            "file": filename,
            "status": "failed",
            "error": "文件为空",
            "timestamp": now,
        }

    # ── 步骤 3：抽取（带重试）────────────────
    # 真正的网络调用发生在这里
    result, error = extract_with_retry(text)
    if result is None:
        return {
            "file": filename,
            "status": "failed",
            "error": error or "未知错误",
            "timestamp": now,
        }

    # ── 步骤 4：写 JSON ─────────────────────
    # splitext 返回 (文件名, 扩展名) 二元组，_ 表示丢弃扩展名
    # "resume.txt" → base="resume", _=".txt"
    base, _ = os.path.splitext(filename)

    # 输出到源文件所在目录，而不是 BASE_DIR
    # 支持"指定其他目录"时输出跟随源目录
    out_path = os.path.join(os.path.dirname(filepath), f"{base}_extracted.json")

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            # ensure_ascii=False：中文原样输出
            # indent=2：可读缩进，便于人工检查
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return {
            "file": filename,
            "status": "failed",
            "error": f"输出失败：{type(e).__name__}: {e}",
            "timestamp": now,
        }

    # ── 步骤 5：成功返回 ────────────────────
    # 只记输出文件名，不记全路径，日志更简洁
    return {
        "file": filename,
        "status": "success",
        "output": os.path.basename(out_path),
        "timestamp": now,
    }


# ─────────────────────────────────────────────────────────────
# 主流程：批量调度
# ─────────────────────────────────────────────────────────────

def main():
    """
    程序总指挥：找文件 → 循环派活 → 记日志 → 打印统计。
    只管"批"，不管"单"——单文件逻辑全在 process_file 里。
    """
    # ── 1. 决定目标目录 ──────────────────────
    # 命令行给了参数就用参数，没给就用脚本自身所在目录
    # sys.argv[0] 是脚本名，sys.argv[1] 才是第一个参数
    target_dir = sys.argv[1] if len(sys.argv) > 1 else BASE_DIR

    # ── 2. 目录合法性检查 ────────────────────
    # sys.exit(1)：非零退出码 = 异常结束，方便 CI / shell 脚本捕获
    if not os.path.isdir(target_dir):
        print(f"错误：目录不存在 - {target_dir}")
        sys.exit(1)

    # ── 3. 找出所有目标文件 ──────────────────
    # glob.glob(".../resume*.txt") 一次匹配前缀 resume、后缀 .txt
    # sorted() 保证每次运行顺序一致，输出可预测
    files = sorted(glob.glob(os.path.join(target_dir, "resume*.txt")))

    # 没有匹配文件不是错误，只是没活干
    # sys.exit(0) = 正常退出，不报错
    if not files:
        print(f"在 {target_dir} 中未找到 resume*.txt 文件")
        sys.exit(0)

    print(f"找到 {len(files)} 个文件，开始处理...\n")

    # ── 4. 循环处理 + 记日志 + 计数 ──────────
    success_count = 0
    failed_count = 0

    for fp in files:
        # process_file 保证不抛异常，所以这里不包 try/except
        # 单条失败也不会跳出循环，天然实现"失败不中断"
        entry = process_file(fp)

        # 先落盘日志，再打印：
        # 即使进程随后被 Ctrl+C 打断，日志也已保存
        write_log(entry)

        # 按状态分别计数 + 打印（人可读反馈）
        if entry["status"] == "success":
            success_count += 1
            print(f"[成功] {entry['file']} → {entry['output']}")
        else:
            failed_count += 1
            print(f"[失败] {entry['file']} | {entry['error']}")

    # ── 5. 收尾统计 ──────────────────────────
    print(f"\n处理完成：成功 {success_count} 个，失败 {failed_count} 个")
    print(f"日志已写入: {LOG_PATH}")


# 脚本入口保护：只有直接运行才执行 main
# 被 import 时不执行，避免测试或复用函数时触发副作用
if __name__ == "__main__":
    main()