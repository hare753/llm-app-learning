# day24_embedding.py
# Week4 Day24: 本地嵌入模型 + 向量化
#
# ========== 先讲个比喻 ==========
# 想象你给每段文字都拍了一张“身份证照片”。
# 但相机不输出图像，而是输出一串数字，比如 512 个。
#
#   “RAG 是检索增强生成”     → 一串数字：[0.12, -0.03, 0.88, ...]
#   “检索增强生成是什么”       → 一串数字：[0.11, -0.02, 0.86, ...]  ← 跟上面很像
#   “今天天气不错”            → 一串数字：[-0.71, 0.42, 0.05, ...]  ← 跟上面差很远
#
# 意思差不多的文字，拍出来的数字串也差不多；意思差得远，数字串就差得远。
# 这就是电脑“看懂意思”的办法——它看不懂字，但它会算数字像不像。
#
# Day24 做的事：给 Day23 切好的每个块，拍一张这样的“数字身份证”。
# Day26 检索做的事：把你的问题也拍一张，然后找“数字最像”的那几个块。
#
# 这一步在整个 RAG 流程里的位置：
#   加载 PDF → 切块 → 【向量化（拍身份证）】 → 存入 Chroma → 检索 → 拼 Prompt → 生成
#
# 工作流：AI 写完整代码 -> 用户复制 -> 用户跑命令 -> 用户审核。

import os

# 关键：必须在 import sentence_transformers 之前设置 HF_ENDPOINT。
# 原因：sentence_transformers 一旦被导入，内部就会去读 HuggingFace 的下载地址。
#       必须先改地址，再让它读，镜像才会生效，否则还是走外网。
# setdefault 的含义：如果系统里已经设了 HF_ENDPOINT，就用系统的；没设才用这行默认值。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import time
import numpy as np
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

# 用脚本所在目录锚定路径，不依赖当前工作目录（沿用 Day22/Day23 沉淀）。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DAY22_DIR = os.path.join(BASE_DIR, "..", "day22")
PDF_PATH = os.path.normpath(os.path.join(DAY22_DIR, "sample.pdf"))

# 模型名：BAAI/bge-small-zh-v1.5
#   - 中文效果好、体积小（约 100MB）、可离线用
#   - 它拍的“身份证”固定是 512 个数字，不多不少
#     换别的模型，数字个数可能不同（比如 768），但今天是 512。
MODEL_NAME = "BAAI/bge-small-zh-v1.5"

# 切块参数，与 Day23 保持一致，保证 Day24 的输入就是 Day23 的输出。
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def load_pdf_text(pdf_path):
    """逐页加载 PDF，返回每页文本列表。

    保留“逐页”结构，是为了后面切块时能准确记录每一块来自第几页。
    页码信息 Day26 会用来做来源引用（“来源：xxx.pdf 第 N 页”）。
    """
    reader = PdfReader(pdf_path)
    return [page.extract_text() or "" for page in reader.pages]


def build_chunks(pages, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP):
    """逐页切块，元数据保持平铺，和 Day23 对齐。

    切块可以理解为：把一整篇文章，剪成几段小短文，
    后面好给每一小段单独拍一张“数字身份证”。

    分隔符为什么中英文都写：
      RecursiveCharacterTextSplitter 会按列表顺序，先试最靠前的分隔符。
      先试段落（\n\n），切不动再试换行，再试中文句号/问号/感叹号，
      再试英文句号/问号，最后才退到空格、单字。
      PDF 里中英文混排，只写中文标点的话，遇到英文句子切不动，
      只能一路退到空格，切出来的块边界会很怪。
      中英都写，是为了尽量在“句子结束的地方”剪，而不是在句子中间剪断。
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=[
            "\n\n", "\n",
            "。", "！", "？", "；", "，",
            ". ", "! ", "? ", "; ", ", ",
            " ", ""
        ],
    )

    chunks = []
    global_id = 0  # 全局唯一 chunk_id，跨页不重复

    for page_no, page_text in enumerate(pages, start=1):
        # 空白页直接跳过，避免剪出空片段
        if not page_text.strip():
            continue

        for piece in splitter.split_text(page_text):
            chunks.append({
                "text": piece,                              # 这一段的原文
                "source": os.path.basename(PDF_PATH),       # 来源文件名
                "page": page_no,                            # 来自第几页
                "chunk_id": global_id,                      # 全局唯一段号
            })
            global_id += 1

    return chunks


def main():
    if not os.path.exists(PDF_PATH):
        raise FileNotFoundError(
            f"找不到 PDF：{PDF_PATH}\n"
            f"请确认 basic/4-week4/day22/sample.pdf 存在。"
        )

    # ---- 1. 加载 + 切块 ----
    # 这一步和 Day23 完全一致，保证 Day24 的输入就是 Day23 的输出。
    # 现在有了 4 段小短文，等下要给这 4 段各拍一张“数字身份证”。
    pages = load_pdf_text(PDF_PATH)
    total_chars = sum(len(p) for p in pages)
    chunks = build_chunks(pages)
    texts = [c["text"] for c in chunks]

    print(f"[加载] 共 {len(pages)} 页，{total_chars} 字符，切出 {len(chunks)} 个块")

    if not chunks:
        print("没有切出任何文本块，请检查 PDF 是否有文字层。")
        return

    # ---- 2. 加载本地嵌入模型 ----
    # 这个模型就是那台“拍身份证的相机”。
    # 首次联网下载约 100MB，之后走本地缓存，通常几秒内加载完。
    # 相机开机（一次性成本）和真正拍照（每次检索都要拍）是两件事。
    print(f"[模型] 正在加载 {MODEL_NAME}（首次约 100MB）...")
    t_model = time.time()
    model = SentenceTransformer(MODEL_NAME)
    print(f"[模型] 加载成功，耗时 {time.time() - t_model:.2f} 秒")

    # ---- 3. 向量化（给每段文字拍数字身份证） ----
    # model.encode 做的事：把 texts 里每一段文字，变成一串 512 个数字。
    #   输入：4 段文字（4 个切块）
    #   输出：4 串数字，每串 512 个
    #   程序里存成一个表格：4 行，每行 512 个数。
    #
    # 第 1 行 = 第 1 段的身份证
    # 第 2 行 = 第 2 段的身份证
    # 第 3 行 = 第 3 段的身份证
    # 第 4 行 = 第 4 段的身份证
    #
    # normalize_embeddings=True（归一化）：
    #   想象每串数字都是一个箭头，箭头有长有短。
    #   归一化就是把所有箭头都缩放到一样长（长度为 1），只留下方向不同。
    #   这样 Day26 比较“两段文字像不像”时，只看方向就够了，
    #   不用管这串数字原本是长是短，算得又快又公平。
    t0 = time.time()
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=True,
        batch_size=16,
    )
    cost = time.time() - t0

    # ---- 4. 验收打印 ----
    print("\n================ Day24 验收 ================")
    print(f"切块数        : {len(texts)}")

    # embeddings.shape 是 (行数, 每行几个数)：
    #   (4, 512) = 4 段文字，每段文字拍了 512 个数字。
    #   行数 = 切块数；512 = 这台相机固定拍多少个数。
    print(f"向量矩阵 shape: {embeddings.shape}")

    # shape[1] 是“每行几个数”，也就是每张身份证上的数字个数。
    # 今天用的是 bge-small-zh-v1.5，它固定拍 512 个数。
    print(f"单个向量维度  : {embeddings.shape[1]}")

    # 换错模型时，这个数会变（比如 bge-base 拍 768 个数），这里会提醒你。
    if embeddings.shape[1] != 512:
        print("[警告] 维度不是 512，请确认模型是否为 BAAI/bge-small-zh-v1.5")

    print(f"编码总耗时    : {cost:.3f} 秒")

    # 算一下每串数字的“总长度”（把所有数平方加起来，再开根号）。
    # axis=1 表示按行算：4 串数字，算出来 4 个长度。
    # 归一化生效的话，每个长度都应接近 1（所有箭头都缩放到一样长）。
    norms = np.linalg.norm(embeddings, axis=1)
    print(f"向量模长(前5个): {np.round(norms[:5], 4)}")

    # 下面这三行是“抽样展示”，不是功能代码，只为了让人肉眼确认数据长什么样。
    print("\n[示例] 第 1 块：")
    # 第 1 段的原文前 60 字
    print("  文本前 60 字 :", chunks[0]["text"][:60].replace("\n", " "))
    # 第 1 段的元数据：来源文件、页码、段号
    print("  元数据       :", {
        "source": chunks[0]["source"],
        "page": chunks[0]["page"],
        "chunk_id": chunks[0]["chunk_id"],
    })
    # 第 1 段的身份证上的前 5 个数字（整张身份证有 512 个数字，这里只看前 5 个）
    print("  向量前 5 维  :", np.round(embeddings[0][:5], 4).tolist())
    print("============================================")

    # TODO: Day27+ 起，把 model.encode(...) 封成 POST /upload 的“向量化”核心步骤


if __name__ == "__main__":
    main()