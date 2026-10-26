"""知识库检索工具。

工具返回 JSON 字符串而不是 Document 列表：
1. 模型能直接读到标题、来源和链接，回答时可以自然引用；
2. 服务端从 ToolMessage 里解析同一份 JSON，生成 SSE 的 sources 事件，
   前端展示的来源与模型看到的资料完全一致。
"""
from __future__ import annotations

import json
from typing import Annotated

from langchain_core.tools import tool

from utils.config import FAISS_INDEX_PATH, RETRIEVE_TOP_K
from utils.logger import setup_logger

logger = setup_logger(__name__)

MAX_CONTENT_CHARS = 500


def _doc_to_result(doc, rank: int) -> dict:
    meta = doc.metadata or {}
    content = (doc.page_content or "").strip().replace("\n\n", "\n")
    return {
        "rank": rank,
        "title": meta.get("title", ""),
        "category": meta.get("category", ""),
        "source_name": meta.get("source_name", ""),
        "source_url": meta.get("source_url", ""),
        "published_at": meta.get("published_at", ""),
        "content": content[:MAX_CONTENT_CHARS],
    }


def retrieve_payload(query: str, top_k: int = RETRIEVE_TOP_K) -> dict:
    from retriever.vector_retriever import VectorRetriever

    retriever = VectorRetriever(model_path=FAISS_INDEX_PATH)
    docs = retriever.search(query, top_k=top_k)
    results = [_doc_to_result(doc, i + 1) for i, doc in enumerate(docs)]
    return {"query": query, "count": len(results), "results": results}


@tool
def vector_retrieve(
    query: Annotated[str, "用户想了解的主题或问题，使用知识库检索"],
    top_k: Annotated[int, "需要返回的条目数，默认 5，最多 8"] = 5,
):
    """检索“绿色校园与低碳生活”知识库，返回带标题与来源链接的条目 JSON。

    当用户问题涉及节能用电、垃圾分类、节约用水、绿色出行、减少一次性用品、
    校园生态保护、资源循环利用或个人低碳行动时调用本工具。检索结果不足时
    应如实告诉用户知识库暂时没有足够资料，不要编造来源、政策或数字。
    """
    try:
        top_k = max(1, min(int(top_k or RETRIEVE_TOP_K), 8))
        payload = retrieve_payload(query, top_k=top_k)
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:  # 索引缺失等异常要让模型知道，而不是编造答案
        logger.error("知识库检索失败: %s", exc)
        return json.dumps(
            {"query": query, "count": 0, "results": [], "error": str(exc)[:200]},
            ensure_ascii=False,
        )


if __name__ == "__main__":  # pragma: no cover
    print(retrieve_payload("宿舍空调应该开多少度？"))
