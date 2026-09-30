# ============================================================
# day13_api_sqlite.py
# ------------------------------------------------------------
# 作用：
#   在 day13_api.py 的基础上加 SQLite 持久化，把每次抽取结果存进数据库，
#   为后续 Day16 的 GET /records 历史查询、Day18 的批量接口做准备。
#
# 与 day13_api.py 的区别：
#   1. 多了 sqlite3、json 两个 import
#   2. 多了 DB_PATH 常量和 init_db() 函数
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
from fastapi import FastAPI, HTTPException

# BaseModel：Pydantic 的基类，用于定义请求体结构，自动做类型校验
from pydantic import BaseModel

# sqlite3 是 Python 标准库自带，无需 pip 安装。
# 它提供 PEP 249 规范的接口：connect / cursor / execute / commit / close，
# 和 Java 的 JDBC 属于同一套设计模式。
import sqlite3

# json 用于把抽取结果 dict 序列化成 JSON 字符串存库；
# 读库时再 json.loads 还原成 dict。
import json

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
# 三、SQLite 数据库路径
# ------------------------------------------------------------
# 使用相对路径 "extractions.db"，相对的是「启动 uvicorn 时所在目录」。
# 所以在 basic/2-week2/day13/ 下启动 uvicorn，数据库文件就固定生成在该目录。
# 该文件已在 .gitignore 中忽略，不会上传 GitHub。
DB_PATH = "extractions.db"


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