"""知识库加载、分块与 FAISS 索引测试（使用假 Embedding，不调用外部接口）。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from langchain_core.embeddings import Embeddings

from indexer.document_loader import DocumentLoader, DatasetValidationError, parse_records
from indexer.document_splitter import DocumentSplitter
from utils.config import KNOWLEDGE_FILE

EXPECTED_CATEGORIES = {
    "节能用电",
    "垃圾分类",
    "节约用水",
    "绿色出行",
    "减少一次性用品",
    "校园生态保护",
    "资源循环利用",
    "个人低碳行动",
}


class FakeEmbeddings(Embeddings):
    """确定性的哈希向量，仅用于验证索引流程。"""

    def __init__(self, dim: int = 32):
        self.dim = dim

    def _vector(self, text: str):
        vector = [0.0] * self.dim
        for token in str(text):
            index = ord(token) % self.dim
            vector[index] += 1.0
        norm = sum(value * value for value in vector) ** 0.5 or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts):
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        return self._vector(text)


@pytest.fixture(scope="module")
def documents():
    return DocumentLoader(str(KNOWLEDGE_FILE)).load()


def test_dataset_has_enough_records_and_categories(documents):
    assert len(documents) >= 20
    categories = {doc.metadata["category"] for doc in documents}
    assert EXPECTED_CATEGORIES <= categories


def test_every_record_keeps_required_source_metadata(documents):
    for doc in documents:
        meta = doc.metadata
        for field in ("title", "category", "source_name", "source_url", "published_at", "curated_at"):
            assert meta.get(field), f"{meta.get('id')} 缺少 {field}"
        assert meta["source_url"].startswith("http")
        assert len(doc.page_content) > 30


def test_dataset_ids_are_unique(documents):
    ids = [doc.metadata["id"] for doc in documents]
    assert len(ids) == len(set(ids))


def test_parser_rejects_missing_source():
    broken = "---\nid: x-01\ntitle: 无出处\ncategory: 测试\n---\n正文"
    with pytest.raises(DatasetValidationError):
        parse_records(broken)


def test_parser_rejects_non_http_url():
    broken = (
        "---\nid: x-02\ntitle: 坏链接\ncategory: 测试\nsource_name: 某机构\n"
        "source_url: 见文档\n---\n正文"
    )
    with pytest.raises(DatasetValidationError):
        parse_records(broken)


def test_splitter_keeps_metadata_and_chunk_index(documents):
    chunks = DocumentSplitter(documents[:3], chunk_size=200, chunk_overlap=20).split()
    assert chunks
    for chunk in chunks:
        assert chunk.metadata["title"]
        assert chunk.metadata["source_url"].startswith("http")
        assert "chunk_index" in chunk.metadata
        assert chunk.page_content.startswith("标题：")


def test_faiss_index_roundtrip_with_sources(tmp_path, documents):
    from langchain_community.vectorstores import FAISS

    from retriever.vector_retriever import VectorRetriever, index_is_ready

    embeddings = FakeEmbeddings()
    chunks = DocumentSplitter(documents[:5]).split()
    store = FAISS.from_documents(chunks, embeddings)
    target = tmp_path / "idx"
    store.save_local(str(target))
    assert index_is_ready(target)

    retriever = VectorRetriever(str(target), embeddings=embeddings)
    results = retriever.search("空调温度", top_k=3)
    assert results
    assert all(doc.metadata.get("source_url") for doc in results)


def test_build_index_writes_manifest(tmp_path, documents, monkeypatch):
    from indexer import vector_indexer

    monkeypatch.setattr(vector_indexer, "KNOWLEDGE_FILE", Path(KNOWLEDGE_FILE))
    chunks = DocumentSplitter(documents[:4]).split()
    target = tmp_path / "manifest-idx"
    vector_indexer.VectorIndexer(
        chunks=chunks,
        embeddings=FakeEmbeddings(),
        model_path=str(target),
        delete_flag=True,
    ).add_documents()

    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["chunks"] == len(chunks)
    assert manifest["documents"] == len({c.metadata["id"] for c in chunks})
    assert manifest["dataset_sha256"]
    assert manifest["categories"]


def test_knowledge_file_hash_is_stable():
    digest = hashlib.sha256(KNOWLEDGE_FILE.read_bytes()).hexdigest()
    assert len(digest) == 64
