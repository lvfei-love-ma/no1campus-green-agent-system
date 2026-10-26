"""检查知识库中所有来源链接：能否打开、是否被重定向到 404 页面、是否真有内容。

只看 HTTP 200 不够——部分政府站点会把失效链接用 200 状态渲染成“404 页面”。
本脚本额外检查最终 URL、正文长度和“页面不存在”等提示，失败时返回非零退出码。

用法：
    python -m scripts.check_sources
    python -m scripts.check_sources --dataset datasets/green_campus_low_carbon.md
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from indexer.document_loader import DocumentLoader  # noqa: E402
from utils.config import KNOWLEDGE_FILE  # noqa: E402

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
NOT_FOUND_MARKERS = ("页面不存在", "您访问的页面不存在", "页面已删除", "404 Not Found")


def strip_tags(html: str) -> str:
    html = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def check(url: str) -> tuple[bool, str]:
    try:
        response = requests.get(url, timeout=30, headers={"User-Agent": UA})
    except Exception as exc:  # 网络错误
        return False, f"请求失败：{type(exc).__name__}"

    if response.status_code != 200:
        return False, f"HTTP {response.status_code}"

    final_url = response.url
    if "/404/" in final_url or final_url.rstrip("/").endswith("/404"):
        return False, f"被重定向到 404 页面：{final_url}"

    content_type = (response.headers.get("content-type") or "").lower()
    if "pdf" in content_type:
        if len(response.content) < 10_000:
            return False, f"PDF 过小：{len(response.content)} 字节"
        return True, f"PDF {len(response.content) // 1024} KB"

    text = strip_tags(response.text)
    if len(text) < 300:
        return False, f"正文过短（{len(text)} 字），可能是空白页或脚本页"
    for marker in NOT_FOUND_MARKERS:
        if marker in text:
            return False, f"页面提示“{marker}”"
    return True, f"正文约 {len(text)} 字"


def main() -> int:
    parser = argparse.ArgumentParser(description="检查知识库来源链接可用性")
    parser.add_argument("--dataset", default=str(KNOWLEDGE_FILE))
    args = parser.parse_args()

    documents = DocumentLoader(args.dataset).load()
    unique: dict[str, list[str]] = {}
    for doc in documents:
        unique.setdefault(doc.metadata["source_url"], []).append(doc.metadata["title"])

    print(f"知识库 {len(documents)} 条记录，共 {len(unique)} 个来源链接\n")
    failures = 0
    for url, titles in unique.items():
        ok, detail = check(url)
        marker = "PASS" if ok else "FAIL"
        print(f"[{marker}] {detail}\n       {url}\n       引用于：{titles[0]}（{len(titles)} 条）")
        if not ok:
            failures += 1
    print(f"\n结果：{len(unique) - failures} 个可访问，{failures} 个失败")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
