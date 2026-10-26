"""FAISS 检索封装。

索引只加载一次（按目录 mtime 失效），检索结果保留来源元数据，供 SSE 的
sources 事件和前端来源区使用。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from utils.config import FAISS_INDEX_PATH, RETRIEVE_FETCH_K, RETRIEVE_TOP_K
from utils.logger import setup_logger

logger = setup_logger(__name__)


class IndexNotReady(RuntimeError):
    """索引文件缺失时抛出，接口层转换为可读提示。"""


def index_is_ready(path: str | Path = FAISS_INDEX_PATH) -> bool:
    folder = Path(path)
    return (folder / "index.faiss").is_file() and (folder / "index.pkl").is_file()


class VectorRetriever:
    _lock = threading.Lock()
    _cache: dict[tuple[str, float], FAISS] = {}

    def __init__(self, model_path: str = FAISS_INDEX_PATH, embeddings=None):
        self.path = str(model_path)
        self.embeddings = embeddings

    # ------------------------------------------------------------ 加载
    def _load(self) -> FAISS:
        if not index_is_ready(self.path):
            raise IndexNotReady("知识库索引不存在，请先运行 python -m scripts.build_index")
        if self.embeddings is None:
            from models.llm import get_embeddings

            self.embeddings = get_embeddings()
        mtime = (Path(self.path) / "index.faiss").stat().st_mtime
        key = (self.path, mtime)
        with self._lock:
            if key not in self._cache:
                self._cache[key] = FAISS.load_local(
                    folder_path=self.path,
                    embeddings=self.embeddings,
                    allow_dangerous_deserialization=True,
                )
            return self._cache[key]

    # ------------------------------------------------------------ 检索
    def search(self, query: str, top_k: int = RETRIEVE_TOP_K) -> list[Document]:
        query = (query or "").strip()
        if not query:
            return []
        fetch_k = max(top_k, RETRIEVE_FETCH_K)
        docs = self._load().similarity_search(query, k=fetch_k)
        return docs[:top_k]

    def search_with_score(self, query: str, top_k: int = RETRIEVE_TOP_K):
        return self._load().similarity_search_with_score(query, k=max(top_k, RETRIEVE_FETCH_K))[:top_k]

    def get_retriever(self):
        """兼容旧调用方：返回可直接 invoke 的 retriever。"""
        return self._load().as_retriever()

    @staticmethod
    def manifest(path: str | Path = FAISS_INDEX_PATH) -> Optional[dict]:
        manifest_path = Path(path) / "manifest.json"
        if not manifest_path.is_file():
            return None
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover
            return None
