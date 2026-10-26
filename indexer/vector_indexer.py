"""构建 FAISS 向量索引，并写入 manifest.json 方便确认索引来源。"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime
from typing import List

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from utils.config import DATASETS_DIR, FAISS_INDEX_PATH, KNOWLEDGE_FILE
from utils.logger import setup_logger

logger = setup_logger(__name__)


def file_sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


class VectorIndexer:
    def __init__(
        self,
        chunks: List[Document],
        embeddings,
        model_path: str = FAISS_INDEX_PATH,
        delete_flag: bool = False,
    ):
        self.chunks = chunks
        self.embeddings = embeddings
        self.path = model_path
        self.delete_flag = delete_flag

    def add_documents(self, manifest_extra: dict | None = None) -> str:
        if not self.chunks:
            raise ValueError("没有可索引的文档块，构建已取消")
        if self.delete_flag and os.path.exists(self.path):
            shutil.rmtree(self.path)
            logger.info("删除旧索引目录: %s", self.path)
        os.makedirs(self.path, exist_ok=True)

        vectorstore = FAISS.from_documents(self.chunks, self.embeddings)
        vectorstore.save_local(self.path)

        manifest = {
            "built_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "documents": len({c.metadata.get("id") for c in self.chunks if c.metadata.get("id")}),
            "chunks": len(self.chunks),
            "embedding_model": os.getenv("EMBEDDINGS_MODEL_NAME", ""),
            "dataset": KNOWLEDGE_FILE.name,
            "dataset_sha256": file_sha256(KNOWLEDGE_FILE) if KNOWLEDGE_FILE.is_file() else "",
            "categories": sorted({c.metadata.get("category", "") for c in self.chunks}),
        }
        if manifest_extra:
            manifest.update(manifest_extra)
        with open(os.path.join(self.path, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        logger.info("索引构建完成: %s 个 chunk -> %s", len(self.chunks), self.path)
        return self.path


if __name__ == "__main__":  # pragma: no cover
    from indexer.document_loader import DocumentLoader
    from indexer.document_splitter import DocumentSplitter
    from models.llm import get_embeddings

    docs = DocumentLoader(str(DATASETS_DIR / KNOWLEDGE_FILE.name)).load()
    chunks = DocumentSplitter(docs).split()
    VectorIndexer(chunks, get_embeddings(), delete_flag=True).add_documents()
