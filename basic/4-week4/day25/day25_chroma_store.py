# day25_chroma_store.py
# Day25: 把 Day23 切块 + Day24 向量 + 元数据存入 Chroma，并验证持久化

import os

# 关键提醒 1：必须在 import sentence_transformers 之前设置 HF_ENDPOINT。
# 原因：sentence_transformers 一旦被导入，内部就会去读 HuggingFace 的下载地址。
# 这里加了 OFFLINE=1，意思是：模型本地已经有了，别去外网查有没有新版本了，直接读本地缓存！
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import time
import chromadb
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

# ---------- 路径与常量锚定（不依赖你在哪个目录下运行代码） ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))          # basic/4-week4/day25
WEEK4_DIR = os.path.dirname(BASE_DIR)                          # basic/4-week4
PDF_PATH = os.path.join(WEEK4_DIR, "day22", "sample.pdf")

# 关键提醒 2：这个目录会生成各种 .bin 文件和 sqlite 数据库。
# 里面几十张表全是 Chroma 底层自己建的，千万别去手动改！我们只通过代码接口调用。
# 最重要的一点：这玩意是运行时产物，千万记得在 .gitignore 里加上 chroma_db/，别推上 GitHub！
CHROMA_DIR = os.path.join(WEEK4_DIR, "chroma_db") 

# 命名空间就像数据库里的表名。到了 Day27 写 API 时，不管是 /upload 存数据，还是 /chat 查数据，都认准这个 week4_docs 抽屉。
COLLECTION_NAME = "week4_docs"                                  


def load_pdf(pdf_path):
    """Day22 逻辑：把 PDF 里的字抠出来，变成 Python 字典列表。"""
    reader = PdfReader(pdf_path)
    pages = []
    
    # 为什么不用列表推导式？
    # 因为真实业务里，以后可能要在这里加“判断空页跳过”、“替换乱码”等逻辑。
    # 用 for 循环虽然多写两行，但留出了扩展口，可读性也更好。
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append({"page": i + 1, "text": text})
    return pages


def chunk_pages(pages, chunk_size=500, chunk_overlap=50):
    """Day23 逻辑：把长文本切成小段，并挂上元数据标签。"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        
        # separators 是裁剪优先级，从上到下依次尝试：
        # 1. 优先在“连续两个换行（大段落）”切；
        # 2. 不够小就在“单个换行”切；
        # 3. 还不够就在中文标点“。！？；，”处切；
        # 4. 最后的空格和空字符串是兜底策略，英文单词靠空格断开，实在不行逐字符硬切。
        # 本次没写英文标点，是因为英文有空格兜底，切出来不会连成一个长词。后续可优化加上。
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
    )
    
    chunks = []
    chunk_id = 0
    for page in pages:
        for s in splitter.split_text(page["text"]):
            chunks.append({
                "text": s,
                "metadata": {
                    "source": os.path.basename(PDF_PATH),
                    "page": page["page"],
                    "chunk_id": chunk_id,
                },
            })
            chunk_id += 1
    return chunks


def main():
    print("=" * 60)
    print("Day25: 建一个离线图书馆（Chroma 向量库 + 持久化）")
    print("=" * 60)

    # 1. 加载 PDF
    pages = load_pdf(PDF_PATH)
    print(f"[1] PDF 加载：{len(pages)} 页")

    # 2. 切块
    chunks = chunk_pages(pages)
    print(f"[2] 切块：{len(chunks)} 块")

    # 3. 向量化（给每块菜贴上语义条形码）
    print("[3] 加载 BGE 模型并向量化...")
    model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
    texts = [c["text"] for c in chunks]
    t0 = time.time()
    embeddings = model.encode(texts, normalize_embeddings=True, batch_size=16)
    print(f"    shape={embeddings.shape}, 耗时={time.time() - t0:.3f}s")

    # 4. 建库 + 存入
    print("[4] 创建 PersistentClient 并写入 collection...")
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # 防呆设计：如果重复运行这段代码，直接 add 会因为 ID 重复报错。
    # 所以先尝试删掉同名的旧表（collection），如果没找到旧表（抛异常），就当无事发生（pass）。
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"    已删除旧 collection: {COLLECTION_NAME}（防止重复运行报错）")
    except Exception:
        pass

    # 新建表。BGE 向量做了归一化，所以这里指定用余弦距离（cosine）来算相似度。
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},  
    )

    # 四件套入库：
    # ids: 书的编号；documents: 书的原文；embeddings: 语义条形码；metadatas: 书的来源标签
    collection.add(
        ids=[f"chunk_{c['metadata']['chunk_id']}" for c in chunks],
        documents=[c["text"] for c in chunks],
        embeddings=embeddings.tolist(),
        metadatas=[c["metadata"] for c in chunks],
    )
    print(f"    写入完成，count = {collection.count()}")

    # 5. 持久化验证：模拟拔电源重启
    # 重新创建一个全新的 client2 连接数据库，看看东西还在不在硬盘上。
    print("[5] 持久化验证：重新打开 Chroma 读取...")
    client2 = chromadb.PersistentClient(path=CHROMA_DIR)
    collection2 = client2.get_collection(COLLECTION_NAME)
    count2 = collection2.count()
    ok = "一致" if count2 == len(chunks) else "不一致"
    print(f"    重新读取 count = {count2}，{ok}")

    # 6. 眼见为实：随便抽前 2 条数据出来看看，证明存的不仅有数字，还有原文本和页码
    print("[6] 元数据示例（前 2 条）：")
    sample = collection.get(limit=2)
    for i in range(len(sample["ids"])):
        print(f"    id={sample['ids'][i]}")
        print(f"    metadata={sample['metadatas'][i]}")
        print(f"    document[:60]={sample['documents'][i][:60]!r}")

    print("=" * 60)
    print("Day25 完成。你的本地图书馆建好了！")
    print(f"Chroma 目录: {CHROMA_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()