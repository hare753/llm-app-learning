# ============================================================
# day13_api.py
# 作用：给 day13_extractor.py 里的 extract() 函数套一层 HTTP 外壳，
#      让原本只能命令行运行的抽取器，变成一个可以通过接口调用的服务。
# 启动目录：必须在 basic/2-week2/day13/ 目录下启动，
#          因为 2-week2 带连字符不能作为 Python 包名，
#          且要保证能 import 到同目录的 day13_extractor.py。
# 启动命令：python -m uvicorn day13_api:app --reload --port 8000
# ============================================================

# 从 FastAPI 导入两个核心东西：
# - FastAPI：应用类，用来创建整个 Web 应用实例
# - HTTPException：用来主动抛出 HTTP 错误码（如 400、500）
from fastapi import FastAPI, HTTPException

# 从 pydantic 导入 BaseModel，用于定义请求体结构并自动做参数校验
from pydantic import BaseModel

# 导入 day13 主线脚本里的抽取函数。
# 注意：这里能 import 成功，是因为 day13_extractor.py 里
#      用 if __name__ == "__main__": 包住了命令行逻辑，
#      否则导入时会直接执行 sys.argv 判断并退出。
from day13_extractor import extract


# 创建 FastAPI 应用实例，title 会显示在 /docs 页面顶部
app = FastAPI(title="LLM 信息抽取 API")


# 定义请求体模型：客户端 POST 过来的 JSON 必须包含一个 text 字段
# Pydantic 会自动做类型校验：传的不是字符串、或缺字段，都会返回 422
class ExtractRequest(BaseModel):
    text: str


# ---------- 健康检查接口 ----------
# 路径：GET /health
# 作用：给运维/部署用，确认服务是否存活。
#      很多平台会定时请求这个接口来判断服务状态。
@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- 核心抽取接口 ----------
# 路径：POST /extract
# 请求体：{"text": "待抽取的文本"}
# 返回：{"result": {抽取出的四字段字典}}
@app.post("/extract")
def extract_api(req: ExtractRequest):
    # 1. 参数校验：如果 text 为空或全是空格，返回 400 参数错误
    #    这里用 400 而不是 422，是为了与规划里的统一错误码保持一致
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="text 不能为空")

    # 2. 调用 day13_extractor.py 里的 extract() 函数
    #    extract() 内部会：调用 DeepSeek API → 清洗返回 → 解析 JSON
    #    解析失败时返回 None
    result = extract(req.text)

    # 3. 如果 extract() 返回 None，说明模型输出解析失败或服务异常
    #    返回 500 服务内部错误，提示去看服务端日志
    if result is None:
        raise HTTPException(status_code=500, detail="抽取失败，请查看服务端日志")

    # 4. 成功：把抽取结果包一层 {"result": ...} 返回
    #    FastAPI 会自动把 dict 序列化为 JSON 响应
    return {"result": result}