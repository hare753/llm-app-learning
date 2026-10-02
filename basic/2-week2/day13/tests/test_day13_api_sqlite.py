# ============================================================
# Day17 并行后端：day13_api_sqlite.py 的 pytest 基础用例
# 目标：用 TestClient 内存调用接口，不启动 uvicorn
# 覆盖：健康检查、正常抽取、缺失字段、空文本参数错误
# ============================================================

import sys
from pathlib import Path

# 把 tests/ 的上一级目录（即 day13 目录）加入模块搜索路径，
# 否则 pytest 从 tests/ 里跑时找不到 day13_api_sqlite 模块
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from day13_api_sqlite import app

# TestClient 是 FastAPI 提供的假 HTTP 客户端：
# 请求在内存里直接发给 app，不走网络、不占端口、不需要 uvicorn
client = TestClient(app)


def test_health():
    """健康检查：服务能启动，/health 返回 200"""
    resp = client.get("/health")
    assert resp.status_code == 200


def test_extract_normal_text():
    """正常文本：返回 200，四字段值完整且正确"""
    resp = client.post(
        "/extract",
        json={"text": "张三，28岁，本科，5年Python开发经验，熟悉FastAPI。"},
    )

    # 1. 状态码必须是 200
    assert resp.status_code == 200

    # 2. 响应体必须是 {"result": {...}} 结构
    data = resp.json()
    assert "result" in data

    # 3. 逐个字段检查值，不只是检查 key 在不在
    #    严格断言能抓到「字段在但值错」的 bug，比只查 key 更有价值
    result = data["result"]
    assert result["name"] == "张三"
    assert result["years"] == 5
    assert result["education"] == "本科"

    # 4. skills 必须是 list 且非空
    assert isinstance(result["skills"], list)
    assert len(result["skills"]) > 0


def test_extract_missing_fields():
    """缺失字段文本：返回 200，未提及字段为 null（Python 里是 None）"""
    resp = client.post(
        "/extract",
        json={"text": "李四，熟悉Java后端开发。"},
    )

    # 1. 模型正常返回时仍是 200，不是 400
    #    业务上「缺失字段」是合法输入，不算参数错误
    assert resp.status_code == 200

    result = resp.json()["result"]

    # 2. name 有值，skills 有值
    assert result["name"] == "李四"
    assert isinstance(result["skills"], list)

    # 3. 文本里没提到年限和学历，必须为 None，不能瞎编
    assert result["years"] is None
    assert result["education"] is None


def test_extract_empty_text():
    """空文本/全空格：返回 400 参数错误"""
    # 空字符串
    resp1 = client.post("/extract", json={"text": ""})
    assert resp1.status_code == 400

    # 全空格字符串（strip 后为空，也应被拒绝）
    resp2 = client.post("/extract", json={"text": "   "})
    assert resp2.status_code == 400