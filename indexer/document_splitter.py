"""文档分块：保留来源元数据，并在每个 chunk 前加上标题与分类作为检索线索。"""
from __future__ import annotations

from typing import List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from utils.config import DATASETS_DIR, KNOWLEDGE_FILE
from utils.logger import setup_logger

logger = setup_logger(__name__)


class DocumentSplitter:
    def __init__(self, docs: List[Document], chunk_size: int = 600, chunk_overlap: int = 80):
        self.docs = docs
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split(self) -> List[Document]:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", "。", "；", "，", " "],
            length_function=len,
        )
        chunks: List[Document] = []
        for doc in self.docs:
            meta = dict(doc.metadata or {})
            header = f"标题：{meta.get('title', '')}\n分类：{meta.get('category', '')}\n\n"
            pieces = splitter.split_documents([Document(page_content=doc.page_content, metadata=meta)])
            for index, piece in enumerate(pieces):
                # 标题与分类前缀加到每个 chunk 之前，短文本也能被语义检索命中；
                # 来源字段始终随 metadata 传递，不会在分块过程中丢失。
                piece.page_content = header + piece.page_content
                piece.metadata["chunk_index"] = index
                piece.metadata["chunk_total"] = len(pieces)
                chunks.append(piece)
        logger.info("文档分割完成，共 %s 个 chunk（来自 %s 条记录）", len(chunks), len(self.docs))
        return chunks


if __name__ == "__main__":  # pragma: no cover
    from indexer.document_loader import DocumentLoader

    doc_loader = DocumentLoader(str(DATASETS_DIR / KNOWLEDGE_FILE.name))
    docs = doc_loader.load()
    split_chunks = DocumentSplitter(docs).split()
    for idx, chunk in enumerate(split_chunks[:3]):
        print(idx, chunk.metadata.get("title"), "|", chunk.page_content[:60])
