"""不启动服务的检索验证脚本。

用法：
    python -m scripts.check_retrieval "垃圾分类怎么分"
    python -m scripts.check_retrieval            # 使用内置问题
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from retriever.vector_retriever import VectorRetriever, index_is_ready, IndexNotReady  # noqa: E402
from utils.config import FAISS_INDEX_PATH, RETRIEVE_TOP_K  # noqa: E402

DEFAULT_QUERIES = [
    "空调开多少度合适",
    "快递纸箱怎么回收",
    "校园里发现漏水找谁",
    "旧手机可以扔垃圾桶吗",
]


def main() -> int:
    if not index_is_ready(FAISS_INDEX_PATH):
        print(f"索引不存在: {FAISS_INDEX_PATH}")
        print("请先运行: python -m scripts.build_index")
        return 1

    queries = sys.argv[1:] or DEFAULT_QUERIES
    retriever = VectorRetriever(FAISS_INDEX_PATH)
    try:
        for query in queries:
            print(f"\n== {query}")
            for doc in retriever.search(query, top_k=RETRIEVE_TOP_K):
                meta = doc.metadata
                print(f"  [{meta.get('category', '')}] {meta.get('title', '')}")
                print(f"    来源: {meta.get('source_name', '')} {meta.get('source_url', '')}")
    except IndexNotReady as exc:
        print(exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
