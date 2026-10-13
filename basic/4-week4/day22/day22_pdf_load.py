"""
Day22: RAG 第一步 —— 用 pypdf 加载 PDF 并抽取文本。

RAG 完整链路：加载 → 切块 → 向量化 → 检索 → 拼 Prompt → 生成
本文件只负责「加载」，产出纯文本，作为后续切块的输入。
"""

import os
from pypdf import PdfReader

# 用 __file__ 锚定脚本所在目录，避免依赖当前工作目录（Week3 踩坑沉淀）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_pdf(pdf_path: str) -> str:
    """逐页读 PDF，返回拼接后的全文。"""
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    print(f"总页数: {total_pages}")

    texts = []
    for i, page in enumerate(reader.pages):
        # extract_text() 可能返回 None（比如空页），用 or "" 兜底
        text = page.extract_text() or ""
        print(f"--- 第 {i + 1} 页前 200 字 ---")
        print(text[:200])
        print()  # 空行分隔，输出好读
        texts.append(text)

    return "\n".join(texts)


# TODO: Day26+ 起把 load_pdf 封成 POST /upload 的核心步骤

if __name__ == "__main__":
    pdf_name = "sample.pdf"  # 换成你放进 day22/ 目录的 PDF 文件名
    pdf_path = os.path.join(BASE_DIR, pdf_name)

    if not os.path.exists(pdf_path):
        print(f"找不到 PDF: {pdf_path}")
        print("请把一份有文字层的 PDF 放进 day22/ 目录，并改上面的 pdf_name")
    else:
        full_text = load_pdf(pdf_path)
        print(f"总字符数: {len(full_text)}")

        out_path = os.path.join(BASE_DIR, "day22_output.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        print(f"已写入: {out_path}")