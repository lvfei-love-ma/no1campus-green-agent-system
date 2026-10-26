"""知识库加载器。

数据集格式（datasets/green_campus_low_carbon.md）由若干条记录组成：

    ---
    id: energy-01
    title: 宿舍空调温度怎么设置
    category: 节能用电
    source_name: 国务院办公厅
    source_url: https://www.gov.cn/...
    published_at: 2007-06-01
    curated_at: 2026-10-24
    ---
    正文段落……

每条记录解析成一个 Document，八个字段全部写入 metadata，分块和检索过程中
不会丢失来源信息。加载时会校验必填字段和来源链接，避免“无出处”的条目进入索引。
"""
from __future__ import annotations

import re
from typing import Iterable, List

from langchain_core.documents import Document

from utils.config import DATASETS_DIR, KNOWLEDGE_FILE
from utils.logger import setup_logger

logger = setup_logger(__name__)

REQUIRED_FIELDS = ("title", "category", "source_name", "source_url")
OPTIONAL_FIELDS = ("id", "published_at", "curated_at")
FIELD_RE = re.compile(r"^([a-z_]+)\s*:\s*(.*)$")
URL_RE = re.compile(r"^https?://\S+$")


class DatasetValidationError(ValueError):
    """数据集字段不完整或格式错误。"""


def parse_records(text: str) -> List[Document]:
    lines = text.splitlines()
    records: List[Document] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == "---" and i + 1 < len(lines) and FIELD_RE.match(lines[i + 1]):
            i += 1
            meta: dict = {}
            while i < len(lines) and lines[i].strip() != "":
                match = FIELD_RE.match(lines[i])
                if match:
                    meta[match.group(1)] = match.group(2).strip()
                i += 1
            body: List[str] = []
            while i < len(lines):
                if (
                    lines[i].strip() == "---"
                    and i + 1 < len(lines)
                    and FIELD_RE.match(lines[i + 1])
                ):
                    break
                body.append(lines[i])
                i += 1
            content = "\n".join(body).strip()
            if not content:
                raise DatasetValidationError(f"记录 {meta.get('id', '?')} 正文为空")
            missing = [f for f in REQUIRED_FIELDS if not meta.get(f)]
            if missing:
                raise DatasetValidationError(
                    f"记录 {meta.get('id', meta.get('title', '?'))} 缺少字段: {', '.join(missing)}"
                )
            if not URL_RE.match(meta["source_url"]):
                raise DatasetValidationError(
                    f"记录 {meta.get('id', '?')} 的来源链接不是 http(s) 地址"
                )
            meta.setdefault("published_at", "未注明")
            meta.setdefault("curated_at", "未注明")
            meta.setdefault("id", f"doc-{len(records) + 1:02d}")
            records.append(Document(page_content=content, metadata=meta))
        else:
            i += 1
    if not records:
        raise DatasetValidationError("未解析到任何知识库记录，请检查 --- 分隔的字段格式")
    return records


class DocumentLoader:
    def __init__(self, file_path: str | None = None):
        self.file_path = str(file_path or KNOWLEDGE_FILE)

    def markdown_load(self) -> List[Document]:
        """按 ## 小节切分的通用 markdown 读取，保留整节作为一篇文档。"""
        with open(self.file_path, encoding="utf-8") as f:
            text = f.read()
        sections = [s.strip() for s in re.split(r"\n(?=##\s)", text) if s.strip()]
        return [Document(page_content=s) for s in sections]

    def markdown_load_with_pairs(self) -> List[Document]:
        """兼容旧方法的名称，实际执行带元数据的记录解析。"""
        with open(self.file_path, encoding="utf-8") as f:
            text = f.read()
        docs = parse_records(text)
        logger.info("加载知识库成功，共 %s 条记录", len(docs))
        return docs

    def load(self) -> List[Document]:
        suffix = self.file_path.rsplit(".", 1)[-1].lower()
        if suffix == "md":
            return self.markdown_load_with_pairs()
        logger.error("不支持该文件格式: %s", suffix)
        raise ValueError("不支持该文件格式")


def load_dataset(path: str | None = None) -> List[Document]:
    return DocumentLoader(path or str(KNOWLEDGE_FILE)).load()


def categories(docs: Iterable[Document]) -> dict:
    result: dict = {}
    for doc in docs:
        result.setdefault(doc.metadata.get("category", "未分类"), 0)
        result[doc.metadata.get("category", "未分类")] += 1
    return result


if __name__ == "__main__":  # pragma: no cover
    documents = DocumentLoader(str(DATASETS_DIR / "green_campus_low_carbon.md")).load()
    print(len(documents), categories(documents))
