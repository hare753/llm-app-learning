# ============================================================
# day13_api_sqlite.py
# ------------------------------------------------------------
# 作用：
#   在 day13_api.py 的基础上加 SQLite 持久化，把每次抽取结果存进数据库，
#   为后续 Day16 的 GET /records 历史查询、Day18 的批量接口做准备。
#
# 与 day13_api.py 的区别：
#   1. 多了 os、sqlite3、json 三个 import
#   2. 多了 BASE_DIR / DB_PATH 常量和 init_db() 函数
#   3. POST /extract 成功后，多了一步「写库」操作
#   4. 接口逻辑、错误码、请求体模型完全不变
#
# 启动目录：必须在 basic/2-week2/day13/ 下启动
#           因为 2-week2 带连字符不能作为 Python 包名，
#           且要保证能 import 到同目录的 day13_extractor.py。
# 启动命令：python -m uvicorn day13_api_sqlite:app --reload --port 8000
#
# 数据库文件：extractions.db（由 .gitignore 忽略，不提交 GitHub）
# ============================================================


# ------------------------------------------------------------
# 一、导入依赖
# ------------------------------------------------------------

# FastAPI：应用类，用来创建整个 Web 应用实例
# HTTPException：用来主动抛出 HTTP 错误码（如 400、500）
# ★ 新增 Query：用来给查询参数加约束（比如 limit 的范围），
#   不写 Query 也能跑，但加上它能自动校验并在 /docs 里显示范围。
from fastapi import FastAPI, HTTPException, Query

# BaseModel：Pydantic 的基类，用于定义请求体结构，自动做类型校验
from pydantic import BaseModel

# os 用于定位脚本所在目录，拼出数据库文件的绝对路径。
# 加它的原因：DB_PATH 要从「相对路径」改成「基于 __file__ 的绝对路径」，
# 否则在哪个目录启动 uvicorn，数据库就落在哪个目录（会出现多份）。
import os

# sqlite3 是 Python 标准库自带，无需 pip 安装。
# 它提供 PEP 249 规范的接口：connect / cursor / execute / commit / close，
# 和 Java 的 JDBC 属于同一套设计模式。
import sqlite3

# json 用于把抽取结果 dict 序列化成 JSON 字符串存库；
# 读库时再 json.loads 还原成 dict。
import json

# 从 Python 标准库 typing 导入 List，
# 用于在 Pydantic 模型里声明「字符串列表」这种类型。
# 不加也能用 list[str]，但 List[str] 兼容性更好，写法也更常见。
from typing import List

# 导入 day13 主线脚本里的抽取函数。
# 注意：这里能 import 成功，是因为 day13_extractor.py 里
#      用 if __name__ == "__main__": 包住了命令行逻辑，
#      否则导入时会直接执行 sys.argv 判断并退出。
from day13_extractor import extract


# ------------------------------------------------------------
# 二、创建 FastAPI 应用实例
# ------------------------------------------------------------
# title 会显示在 /docs 页面顶部，方便一眼看出服务做什么。
app = FastAPI(title="LLM 信息抽取 API + SQLite")


# ------------------------------------------------------------
# 三、SQLite 数据库路径（绝对路径，与启动目录解耦）
# ------------------------------------------------------------
# 【为什么不用相对路径 "extractions.db"】
#   相对路径相对的是「启动 uvicorn 时所在目录」。
#   在 day13/ 下启动   → 库落在 day13/；
#   在 code/ 根目录误启动一次 → 库就落在了根目录，出现两份。
#   这和 Day15 踩过的坑是同一类问题（当时是 day15_*_raw.txt 落错目录）。
#
# 【正确做法：基于 __file__ 锚定】
#   os.path.abspath(__file__) → 当前脚本的绝对路径
#   os.path.dirname(...)      → 取所在目录（即 day13/）
#   os.path.join(BASE_DIR, "extractions.db")
#                             → 数据库永远落在 day13/，不受启动目录影响
#
# 该文件已在 .gitignore 中忽略，不会上传 GitHub。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "extractions.db")


# ------------------------------------------------------------
# 四、建表函数
# ------------------------------------------------------------
# SQLite 是一个「文件型数据库」：不需要单独开服务进程，
# 整个数据库就是一个 .db 文件。第一次 connect 时文件不存在会自动创建。
#
# 表结构：
#   id          自增主键，每条记录唯一编号
#   filename    来源文件名（当前接口先写死 "api_request"，以后可扩展）
#   result_json 抽取结果的 JSON 字符串
#   created_at  创建时间，由 SQLite 用 CURRENT_TIMESTAMP 自动填
#
# 为什么 result_json 用 TEXT 而不是 JSON 类型：
#   SQLite 没有原生 JSON 类型，存结构化数据的标准做法是
#   写入时 json.dumps 成字符串，读取时 json.loads 还原。
def init_db():
    """启动时自动建表，表已存在则跳过（IF NOT EXISTS）。"""
    # 1. 打开数据库连接。文件不存在会自动创建。
    conn = sqlite3.connect(DB_PATH)

    # 2. 从连接获取游标，用来执行 SQL 并接收结果。
    cur = conn.cursor()

    # 3. 执行建表 SQL。
    #    IF NOT EXISTS：如果表已存在就跳过，不报错，保证幂等。
    #    没有这句的话，第二次启动服务会报 "table already exists"。
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS extractions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            result_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # 4. 提交事务。
    #    SQLite 默认是事务模式：execute 的写操作不会立刻落盘，
    #    必须 commit() 后才真正写入 .db 文件。
    conn.commit()

    # 5. 关闭连接，释放文件句柄。
    conn.close()


# 模块加载时执行一次建表。
# 放在模块级而不是放在某个路由里，是为了确保「服务一启动，表就已经存在」，
# 后续所有写库操作都不会因表不存在而报错。
init_db()


# ------------------------------------------------------------
# 五、请求体模型
# ------------------------------------------------------------
# 客户端 POST 过来的 JSON 必须包含一个 text 字段。
# Pydantic 会自动做类型校验：
#   - 缺 text 字段 → 422
#   - text 不是字符串 → 422
# 校验通过后，FastAPI 会把请求体自动转成 ExtractRequest 实例传入函数。
class ExtractRequest(BaseModel):
    text: str

# ------------------------------------------------------------
# 五之二、批量请求体模型
# ------------------------------------------------------------
# 客户端 POST 过来的 JSON 必须包含一个 texts 字段，且必须是字符串列表。
# Pydantic 会自动校验：
#   - 缺 texts 字段       → 422
#   - texts 不是列表      → 422
#   - 列表里元素不是字符串 → 422
class BatchExtractRequest(BaseModel):
    texts: List[str]

# ------------------------------------------------------------
# 六、健康检查接口
# ------------------------------------------------------------
# 路径：GET /health
# 作用：给运维/部署用，确认服务是否存活。
#      很多平台（Docker、K8s、云服务）会定时请求这个接口判断服务状态。
@app.get("/health")
def health():
    return {"status": "ok"}


# ------------------------------------------------------------
# 七、核心抽取接口
# ------------------------------------------------------------
# 路径：POST /extract
# 请求体：{"text": "待抽取的文本"}
# 返回：{"result": {抽取出的四字段字典}}
#
# 与 day13_api.py 相比，这个函数多了一步「写库」。
@app.post("/extract")
def extract_api(req: ExtractRequest):

    # ---------- 第 1 步：空文本校验 ----------
    # 用 strip() 后判断，可以拦住 "   " 这种「看着有内容其实没意义」的输入。
    # 这是业务层校验，返回 400（参数错误），而不是 Pydantic 的 422（格式错误）。
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="text 不能为空")

    # ---------- 第 2 步：调用主线抽取函数 ----------
    # extract() 内部会：调用 DeepSeek API → 清洗返回 → 解析 JSON。
    # 解析失败时返回 None，成功时返回 dict。
    result = extract(req.text)

    # ---------- 第 3 步：处理抽取失败 ----------
    # 用 is None 精确判断，而不是 if not result。
    # 因为空字典 {} 也算「抽取成功但字段全空」，不应该走这条分支。
    # 返回 500 服务内部错误，提示去看服务端日志。
    if result is None:
        raise HTTPException(status_code=500, detail="抽取失败，请查看服务端日志")

    # ---------- 第 4 步：写库 ----------

    # 4.1 打开数据库连接。
    #     文件不存在会自动创建，但表已经由 init_db() 建好了。
    #     每次请求都新开一个连接，用完就关，是最简单可靠的做法。
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 4.2 执行 INSERT。
    #
    # 参数化 SQL：
    #   "?" 是占位符，真实值通过 execute 的第二个参数（元组）传入。
    #   这样能防止 SQL 注入，也让 SQLite 正确处理特殊字符（单引号、换行等）。
    #
    # 字段说明：
    #   id 自增，不用写；created_at 有默认值，不用写。
    #   只填 filename 和 result_json 两个字段。
    #
    # json.dumps(result, ensure_ascii=False)：
    #   把 dict 序列化成 JSON 字符串存进 TEXT 字段。
    #   ensure_ascii=False 保证中文存进去是「张三」而不是 "\u5f20\u4e09"。
    #   不加这个参数，读出来虽然能还原，但查库时看到一堆转义很难受。
    cur.execute(
        "INSERT INTO extractions (filename, result_json) VALUES (?, ?)",
        ("api_request", json.dumps(result, ensure_ascii=False)),
    )

    # 4.3 提交事务，让写入真正落盘。
    #     SQLite 默认事务模式，不 commit 的话改动可能丢失。
    conn.commit()

    # 4.4 关闭连接，释放资源。
    conn.close()

    # ---------- 第 5 步：返回成功响应 ----------
    # 把抽取结果包一层 {"result": ...} 返回。
    # 好处：
    #   - 响应结构统一，以后可以加 record_id、created_at
    #   - 不直接把内部 dict 裸暴露给客户端
    #   - FastAPI 会自动把 dict 序列化为 JSON 响应
    return {"result": result}


# ------------------------------------------------------------
# 八、★ 新增：查询历史记录接口
# ------------------------------------------------------------
# 路径：GET /records?limit=10
# 作用：把 extractions 表里的记录按 id 倒序取出，返回 JSON 数组。
#
# 参数 limit：
#   默认 10，最少 0，最多 100。
#   FastAPI 会根据 Query(...) 的约束自动做校验：
#     - limit 传 200 → 返回 422（超过 le=100）
#     - limit 传 -1  → 返回 422（小于 ge=0）
#     - limit 不传   → 使用默认值 10
#
# 为什么用 conn.row_factory = sqlite3.Row：
#   默认查询结果每行是一个 tuple，只能按位置取（row[0]、row[1]）。
#   设置 row_factory 后，每行变成类似字典的对象，可以按列名取（row["id"]）。
#   代码可读性更好，也不怕以后列顺序变化。
#
# 为什么返回 result 时还要 json.loads：
#   库里存的是 JSON 字符串，直接返回会让客户端拿到 "{\"name\":\"张三\"}"
#   这样的字符串。json.loads 还原成 dict 后，FastAPI 会自动序列化成
#   嵌套对象返回，客户端用起来更自然。
@app.get("/records")
def get_records(limit: int = Query(10, ge=0, le=100)):
    """
    查询历史抽取记录，默认返回最近 10 条。
    limit=0 时返回空数组。
    """
    # 1. 打开数据库连接，并设置行工厂，让 row 支持按列名访问。
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 2. try/finally 保证无论查询是否出错，连接最终都会被关闭。
    #    （不写 finally 也能跑通，但某天查询报错时连接会泄漏。）
    try:
        # 3. 执行查询。
        #    ORDER BY id DESC：最新的记录排最前。
        #    LIMIT ?：参数化占位符，防注入。
        rows = conn.execute(
            """
            SELECT id, filename, result_json, created_at
            FROM extractions
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    # 4. 把每行转成 dict，并解析 result_json。
    records = []
    for row in rows:
        # 反序列化：库里存的是字符串，转回 Python 对象。
        # 万一存的时候出过问题（比如手动往库里塞了非法 JSON），
        # 用 try/except 兜底，避免整个接口 500。
        try:
            result_obj = json.loads(row["result_json"]) if row["result_json"] else None
        except json.JSONDecodeError:
            result_obj = {"_raw": row["result_json"]}

        records.append({
            "id": row["id"],
            "filename": row["filename"],
            "result": result_obj,
            "created_at": row["created_at"],
        })

    # 5. 返回列表。FastAPI 会自动序列化成 JSON 数组。
    return records

# ------------------------------------------------------------
# 九、★ 新增：批量抽取接口
# ------------------------------------------------------------
# 路径：POST /batch-extract
# 请求体：{"texts": ["文本1", "文本2", ...]}
# 返回：{"total": n, "success": m, "failed": k, "results": [...]}
#
# 核心设计原则：单条失败不中断整体。
#   两层 try/except 各司其职：
#     - 内层（for 循环里）：捕获单条失败，记 failed，continue 下一条
#     - 外层（for 循环外）：捕获数据库级别异常，rollback + 抛 500
#
# 为什么用 index + text 双标记：
#   - index 精确定位到输入列表位置，保证唯一
#   - text 方便肉眼扫是哪条（截断到 50 字，避免长文本撑爆响应）
#
# 为什么统一 commit：
#   循环内只 execute，循环外一次 commit，减少磁盘 I/O。
#   配合 rollback，保证「全成功才落盘，中途崩全回滚」。
@app.post("/batch-extract")
def batch_extract(req: BatchExtractRequest):
    """
    批量抽取：
    - 循环调用 extract()
    - 单条失败记录错误，不中断整体
    - 成功的写入 SQLite
    - 返回统计：total / success / failed / results
    """
    total = len(req.texts)
    success_count = 0
    failed_count = 0
    results = []

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        for i, text in enumerate(req.texts):
            # ---- 内层 try/except：单条失败不中断整批 ----
            try:
                # 1. 空文本直接判失败，不调 API，省 token
                if not text or not text.strip():
                    failed_count += 1
                    results.append({
                        "index": i,
                        "text": text[:50],           # 截断，避免长文本膨胀
                        "status": "failed",
                        "error": "文本不能为空",
                    })
                    continue

                # 2. 复用主线抽取函数
                extract_result = extract(text)

                # 3. extract() 返回 None（模型输出解析失败）
                if extract_result is None:
                    failed_count += 1
                    results.append({
                        "index": i,
                        "text": text[:50],
                        "status": "failed",
                        "error": "抽取失败",
                    })
                    continue

                # 4. 成功 → 写库 + 记 success
                cursor.execute(
                    "INSERT INTO extractions (filename, result_json) VALUES (?, ?)",
                    ("batch_request", json.dumps(extract_result, ensure_ascii=False)),
                )
                success_count += 1
                results.append({
                    "index": i,
                    "text": text[:50],
                    "status": "success",
                    "result": extract_result,        # ← 用 result，和接口名统一
                })

            except Exception as e:
                # ← 单条内部异常（网络超时等），只记这一条失败，不打断循环
                failed_count += 1
                results.append({
                    "index": i,
                    "text": text[:50] if text else "",
                    "status": "failed",
                    "error": f"单条处理异常: {e}",
                })
                # 注意：这里不 continue 也行，因为已经是 for 循环最后一件事

        # ---- 全部处理完，统一提交 ----
        conn.commit()

        return {
            "total": total,
            "success": success_count,
            "failed": failed_count,
            "results": results,
        }

    except Exception as e:
        # ---- 外层 try/except：数据库级别异常 ----
        # 走到这里说明是循环外的错误（比如建表失败、磁盘满），
        # 已经处理的数据全部回滚，避免半截写入污染数据库。
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"批量处理异常: {e}")

    finally:
        # ---- 无论成功/失败，连接一定关闭 ----
        conn.close()