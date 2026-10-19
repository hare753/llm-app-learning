# basic/4-week4/day26/day26_rag_query.py
"""
Day 26: RAG 检索 + 拼 Prompt + 生成（RAG 核心闭环）

作用：
    输入一个问题 -> 把问题编码成向量 -> 从 Chroma 检索最相关的 top_k 个切块
    -> 把切块拼成 context -> 写 system prompt -> 调 DeepSeek 生成回答。
    这一步跑通，Week4 RAG 主线达标。

前置：
    Day25 已把 sample.pdf 的 4 个切块连同向量+元数据存入本地 Chroma
    （collection = week4_docs，库目录 4-week4/chroma_db）。
    本脚本只读取 Day25 建好的库，不再重新入库。

运行：python day26_rag_query.py
依赖：sentence-transformers / chromadb / openai / python-dotenv
      （Day22-25 已装过，本脚本不需要再装）
需要 .env 里有 DEEPSEEK_API_KEY / BASE_URL / MODEL_NAME 三行。
"""

import os
import sys

# 离线防呆：本地已缓存 BGE 模型时，彻底跳过 HuggingFace 联网检查。
# Day25 踩过的坑：不设这个，SentenceTransformer 加载时会发 HEAD 请求检查更新，
# 国内直连会报 WinError 10060，重试 5 次后中断。设成 1 后走本地缓存，秒加载。
os.environ["HF_HUB_OFFLINE"] = "1"

from dotenv import load_dotenv
import chromadb
from sentence_transformers import SentenceTransformer
from openai import OpenAI

# ---------------------------------------------------------------------------
# 路径锚定（沿用 Week3 沉淀，不依赖当前工作目录）
#   BASE_DIR   = 本脚本所在目录（basic/4-week4/day26/）
#   WEEK4_DIR  = 上一级（basic/4-week4/）
#   CHROMA_DIR = WEEK4_DIR/chroma_db，即 Day25 落盘的向量库目录
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEEK4_DIR = os.path.dirname(BASE_DIR)
CHROMA_DIR = os.path.join(WEEK4_DIR, "chroma_db")

# 与 Day25 保持一致的 collection 名称，是后续 /upload 和 /chat 共用的命名空间
COLLECTION_NAME = "week4_docs"

# 与 Day24/Day25 同一个嵌入模型，保证问题向量和文档向量在同一坐标系
EMBED_MODEL_NAME = "BAAI/bge-small-zh-v1.5"

# 检索返回的切块数量。3 是入门经验值：够模型答题，又不至于塞太多噪音进 context
TOP_K = 3

# 要问的问题。可改成你自己的问题，例如 "作者用了什么方法？"
QUESTION = "RAG 的完整流程分几步？核心思想是什么？"

# 读取 .env（依次尝试 week4 根、code 根、当前目录，最后走系统环境变量兜底）
load_dotenv(os.path.join(WEEK4_DIR, ".env"))
load_dotenv(os.path.join(os.path.dirname(WEEK4_DIR), ".env"))
load_dotenv()


def encode_query(model, text):
    """
    把问题编码成向量，并做归一化。

    两个细节：
    1. [text] 套列表：model.encode() 按"批量"设计，参数要求一组文本。
       哪怕只有一个问题，也要包成 ["一个问题"]。入库时 Day24 也是这么调的，
       两边调用方式一致，向量空间才可比。
    2. normalize_embeddings=True：入库的文档向量是归一化过的（模长=1），
       问题向量也必须归一化，否则两边长度不同，算余弦距离不公平。
    3. [0] 取下标的第 0 行：encode(["一个问题"]) 返回 shape (1, 512) 的二维数组，
       [0] 取出唯一的 512 维向量，变成一维，供下一步 query 使用。
    """
    return model.encode([text], normalize_embeddings=True)[0]


def retrieve(collection, query_vec, top_k):
    """
    从 Chroma 检索最相关的 top_k 个切块，返回原文 + 元数据 + 距离三个列表。

    1. query_embeddings=[query_vec] 又套列表：Chroma 也按"批量查询"设计，
       可以一次传多个问题向量，单个问题也要包成列表。
    2. n_results=top_k：告诉 Chroma 返回最相似的 top_k 条。
       Chroma 内部对所有向量算余弦距离，排序后取前 top_k。
    3. 返回结构是嵌套的：外层对应"第几个查询"，内层对应"这次查询命中的 N 条"。
       我们只查了一个问题，所以每条都取 [0] 拿到平铺的 3 条结果。
    4. 返回的三个列表下标一一对应：
       docs[0] 的元数据是 metas[0]，距离是 dists[0]。
       这是后面 zip 能正确配对的前提。
    """
    res = collection.query(query_embeddings=[query_vec], n_results=top_k)
    return res["documents"][0], res["metadatas"][0], res["distances"][0]


def build_context(docs, metas):
    """
    把命中的切块拼成带来源标注的 context 段，准备喂给大模型。

    1. zip(docs, metas)：把原文和元数据"拉链式"配对，逐条产出。
       保证每条原文都配上自己的 source/page，不会错位。
    2. enumerate(..., start=1)：编号从 1 开始，给模型看"资料1/资料2/资料3"
       比"资料0"更自然。
    3. meta.get('source', '未知文件')：字典安全取键。
       缺字段时返回默认值，不抛 KeyError，防止整个脚本崩。
    4. tag 形如 [资料1 | sample.pdf 第 1 页]，作用有两个：
       - 给模型看：知道这段话来自哪份文件哪一页，回答时可引用
       - 给人看：出问题时能快速定位来源
    5. "\n\n".join(parts)：3 条之间空一行，让模型视觉上能分清
       "资料1 结束、资料2 开始"，避免不同来源内容读串。
    """
    parts = []
    for i, (doc, meta) in enumerate(zip(docs, metas), start=1):
        # 带默认值的取键：source 缺失显示"未知文件"，page 缺失显示"?"
        tag = f"[资料{i} | {meta.get('source', '未知文件')} 第 {meta.get('page', '?')} 页]"
        parts.append(f"{tag}\n{doc}")
    return "\n\n".join(parts)


def ask_llm(context, question):
    """
    调 DeepSeek 生成回答。核心约束：只根据 context 回答。

    1. OpenAI 客户端：DeepSeek 走 OpenAI 兼容协议，用同一个 SDK，
       只换 base_url 和 api_key。
    2. system_prompt 三条规定：
       - 只用资料里的内容，不用资料外的知识
       - 资料里没有就直说"未找到"，不编造（防幻觉的兜底）
       - 末尾注明引用了哪几条资料（方便溯源）
       不加这三条会怎样：模型会用训练时的通用知识补全，
       答得"看起来很对"但和你的文档无关，RAG 就失去意义。
    3. user_prompt 把 context 和问题一起塞进去，格式清晰，模型好分辨。
    4. temperature=0：知识问答要稳定、可复现，不要发散。
       同一问题多次跑，回答基本一致；调高会变随机。
    """
    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url=os.environ["BASE_URL"],
    )
    system_prompt = (
        "你是一个严格的知识库问答助手。"
        "只根据下面提供的【资料】回答问题；"
        "如果资料里没有相关信息，直接回答“知识库中未找到相关内容”，不要编造。"
        "回答末尾请注明你引用了哪几条资料。"
    )
    user_prompt = f"【资料】\n{context}\n\n【问题】\n{question}"
    resp = client.chat.completions.create(
        model=os.environ["MODEL_NAME"],
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return resp.choices[0].message.content


def main():
    """
    五步走：加载模型 -> 连库 -> 检索 -> 拼 context -> 生成回答。
    与 Day25 相比，前两步（加载模型、连库）是复用，后三步（检索、拼 context、
    生成）是 Day26 新增。Day25 把向量"存进去"，Day26 把向量"取出来用"。
    """
    print("=== Day26 RAG 检索 + 生成闭环 ===")

    # [1/5] 加载嵌入模型
    # 和 Day24/Day25 同一模型，保证问题向量和库里的文档向量在同一空间
    print(f"[1/5] 加载嵌入模型 {EMBED_MODEL_NAME} ...")
    model = SentenceTransformer(EMBED_MODEL_NAME)
    print(f"      模型加载完成，向量维度 = {model.get_sentence_embedding_dimension()}")

    # [2/5] 连接 Day25 建好的 Chroma 库
    # PersistentClient 才能读落盘的库；Client 只在内存里，读不到历史数据
    print(f"[2/5] 连接 Chroma 库：{CHROMA_DIR}")
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)
    count = collection.count()
    print(f"      库中切块总数 count() = {count}")
    if count == 0:
        print("Chroma 里没有数据，请先运行 Day25 的 day25_chroma_store.py 入库。")
        sys.exit(1)

    # [3/5] 问题 -> 向量 -> 检索 top_k
    print(f"[3/5] 检索问题：{QUESTION}（top_k={TOP_K}）")
    query_vec = encode_query(model, QUESTION)
    docs, metas, dists = retrieve(collection, query_vec, TOP_K)

    # 打印命中结果（这一块不是给模型看的，是给你审核用的）
    # 要亲眼确认：距离是不是越小越相关、命中的内容跟问题对不对得上
    print(f"--- 检索命中的切块（top_{TOP_K}）---")
    for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists), start=1):
        # 取前 60 字做预览，换行换成空格，让预览显示在一行里
        preview = doc[:60].replace("\n", " ")
        print(f"[{i}] {meta.get('source')} 第{meta.get('page')}页 "
              f"(距离={dist:.4f}) 预览: {preview}...")

    # [4/5] 把命中切块拼成带来源标注的 context
    print("[4/5] 拼装 context ...")
    context = build_context(docs, metas)

    # [5/5] 调 DeepSeek 生成回答
    print("[5/5] 调 DeepSeek 生成回答（temperature=0）...")
    answer = ask_llm(context, QUESTION)
    print("--- 模型回答 ---")
    print(answer)

    # TODO: Day27+ 起把"检索+生成"整段封成 POST /chat 的核心步骤。
    #       届时入参改为请求体里的 question，返回值改为 {"answer": ..., "sources": [...]}。


if __name__ == "__main__":
    main()