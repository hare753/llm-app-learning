"""
Week4 Day23: 文本切块 + 元数据
目标：把 Day22 加载的 PDF 长文本切成 500 字左右的小块，每块带元数据。
依赖：pip install langchain-text-splitters pypdf

复用说明：load_pdf 与 Day22 逻辑一致，此处内联，保证本脚本独立可运行。
"""

import os
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 路径锚定：不依赖当前工作目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DAY22_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "day22"))
PDF_PATH = os.path.join(DAY22_DIR, "sample.pdf")


def load_pdf(pdf_path):
    """加载 PDF，返回 [(page_number, page_text), ...]，页号从 1 开始。"""
    reader = PdfReader(pdf_path)
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append((i, text))
    return pages


def build_chunks(pages, source_name, chunk_size=500, chunk_overlap=50):
    """
    把每页文本切块，并附加元数据。
    返回：[{"text": ..., "metadata": {"source":..., "page":..., "chunk_id":...}}, ...]
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        # 中文场景补充标点分隔符，优先按段落/句子切
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
    )

    chunks = []
    chunk_id = 0
    for page_num, page_text in pages:
        if not page_text.strip():
            continue
        pieces = splitter.split_text(page_text)
        for piece in pieces:
            chunks.append({
                "text": piece,
                "metadata": {
                    "source": source_name,
                    "page": page_num,
                    "chunk_id": chunk_id,
                },
            })
            chunk_id += 1
    return chunks


def main():
    # ---------- 1. 加载 ----------
    pages = load_pdf(PDF_PATH)
    full_text = "".join(t for _, t in pages)
    print(f"[加载] 总页数：{len(pages)}，总字符数：{len(full_text)}")

    # ---------- 2. 默认切块 500 / 50 ----------
    source_name = os.path.basename(PDF_PATH)
    chunks = build_chunks(pages, source_name, chunk_size=500, chunk_overlap=50)

    print(f"\n[切块] chunk_size=500, chunk_overlap=50 → 共 {len(chunks)} 块")
    print("[切块] 前 3 块预览：")
    for c in chunks[:3]:
        print("-" * 60)
        print(f"  chunk_id={c['metadata']['chunk_id']}, "
              f"page={c['metadata']['page']}, "
              f"len={len(c['text'])}")
        print("  " + c["text"][:200].replace("\n", " "))

    # ---------- 3. 对比不同 chunk_size ----------
    print("\n[对比] 不同 chunk_size 的块数差异：")
    for size in (200, 500, 1000):
        cs = build_chunks(pages, source_name, chunk_size=size, chunk_overlap=50)
        print(f"  chunk_size={size:4d} → {len(cs):3d} 块")

    # ---------- 4. 元数据样例 ----------
    print("\n[元数据] 每块结构示例：")
    if chunks:
        print(" ", chunks[0]["metadata"])

    # TODO: 切块参数（chunk_size / chunk_overlap）就是后续调优入口。
    # TODO: Day26+ 起，这些块会被向量化后存入 Chroma。


if __name__ == "__main__":
    main()