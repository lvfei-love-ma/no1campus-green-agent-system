"""构建知识库索引。

用法（项目根目录，激活虚拟环境后）：
    python -m scripts.build_index
    python -m scripts.build_index --dataset datasets/green_campus_low_carbon.md --output faiss-index/default
    python -m scripts.build_index --skip-verify

脚本会输出记录数、分类分布、chunk 数，并用三个示例问题做检索自检。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许直接 `python scripts/build_index.py` 运行
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from indexer.document_loader import DocumentLoader  # noqa: E402
from indexer.document_splitter import DocumentSplitter  # noqa: E402
from indexer.vector_indexer import VectorIndexer  # noqa: E402
from utils.config import FAISS_INDEX_PATH, KNOWLEDGE_FILE, RETRIEVE_TOP_K  # noqa: E402

DEMO_QUERIES = [
    "宿舍空调设置多少度比较省电",
    "废电池和过期药品应该扔到哪里",
    "怎么少用一次性塑料制品",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="构建绿色校园知识库 FAISS 索引")
    parser.add_argument("--dataset", default=str(KNOWLEDGE_FILE))
    parser.add_argument("--output", default=FAISS_INDEX_PATH)
    parser.add_argument("--skip-verify", action="store_true", help="只建索引，不做检索自检")
    args = parser.parse_args()

    print(f"[1/4] 读取数据集: {args.dataset}")
    documents = DocumentLoader(args.dataset).load()
    print(f"      记录数: {len(documents)}")

    categories: dict[str, int] = {}
    for doc in documents:
        key = doc.metadata.get("category", "未分类")
        categories[key] = categories.get(key, 0) + 1
    for name, count in sorted(categories.items()):
        print(f"      - {name}: {count}")

    print("[2/4] 分块")
    chunks = DocumentSplitter(documents).split()
    print(f"      chunk 数: {len(chunks)}")

    print("[3/4] 生成向量并写入 FAISS（需要可用的 Embedding 接口）")
    from models.llm import get_embeddings

    indexer = VectorIndexer(
        chunks=chunks,
        embeddings=get_embeddings(),
        model_path=args.output,
        delete_flag=True,
    )
    indexer.add_documents()

    if args.skip_verify:
        print("完成（已跳过检索自检）")
        return 0

    print("[4/4] 检索自检")
    from retriever.vector_retriever import VectorRetriever

    retriever = VectorRetriever(args.output)
    ok = True
    for query in DEMO_QUERIES:
        docs = retriever.search(query, top_k=RETRIEVE_TOP_K)
        print(f"\n  问题: {query}")
        if not docs:
            ok = False
            print("    !! 没有检索结果")
            continue
        for doc in docs[:3]:
            meta = doc.metadata
            print(f"    - {meta.get('title', '')} [{meta.get('category', '')}] <- {meta.get('source_name', '')}")
    print("\n索引构建完成。" if ok else "\n索引已写入，但检索自检存在空结果，请检查数据。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
