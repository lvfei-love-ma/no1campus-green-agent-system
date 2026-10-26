"""启动后的端到端冒烟检查（使用真实模型与真实索引）。

用法（先启动服务，再新开一个终端）：
    python -m scripts.smoke_test
    python -m scripts.smoke_test --base-url http://127.0.0.1:8800 --account A
    python -m scripts.smoke_test --skip-chat        # 只检查登录与会话接口

流程：演示账号登录 -> 新建会话 -> 流式提问 -> 校验 SSE 事件与来源 -> 读取历史
-> 清空短期记忆 -> 删除会话。任何一步失败都会以非零退出码结束。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_events(lines):
    """把 SSE 文本行解析成 [(event, data)]。"""
    events = []
    name = None
    for raw in lines:
        if not raw:
            continue
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if line.startswith("event:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            payload = line.split(":", 1)[1].strip()
            try:
                events.append((name, json.loads(payload)))
            except json.JSONDecodeError:
                events.append((name, {"raw": payload}))
            name = None
    return events


def main() -> int:
    parser = argparse.ArgumentParser(description="绿知助手端到端冒烟检查")
    parser.add_argument("--base-url", default="http://127.0.0.1:8800")
    parser.add_argument("--account", default="A", choices=["A", "B"])
    parser.add_argument("--query", default="宿舍空调开到多少度比较省电？")
    parser.add_argument("--skip-chat", action="store_true")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    session = requests.Session()
    try:
        health = session.get(f"{base}/healthz", timeout=10).json()
        print(f"[ok] 服务在线：{health.get('knowledge_title')}")
    except Exception as exc:
        print(f"[fail] 无法连接 {base}，请先启动 uvicorn main:app --port 8800（{exc}）")
        return 1

    status = session.get(f"{base}/api/auth/status", timeout=10).json().get("data", {})
    print(f"[ok] 认证配置：demo_login_enabled={status.get('demo_login_enabled')} redis_ok={status.get('redis_ok')}")

    res = session.post(f"{base}/api/auth/demo-login", json={"account": args.account}, timeout=10)
    if res.status_code != 200:
        print(f"[fail] 演示账号登录失败：{res.status_code} {res.text[:200]}")
        return 1
    user = res.json()["data"]["user"]
    print(f"[ok] 已登录：{user['display_name']} <{user['email']}>")

    me = session.get(f"{base}/api/auth/me", timeout=10)
    assert me.status_code == 200, me.text

    conv = session.post(f"{base}/api/conversations", json={"title": "冒烟检查"}, timeout=10).json()["data"]
    print(f"[ok] 新建会话：{conv['id']}")

    if args.skip_chat:
        session.delete(f"{base}/api/conversations/{conv['id']}", timeout=10)
        print("[ok] 已删除测试会话（跳过问答）")
        return 0

    print(f"[..] 提问：{args.query}")
    res = session.post(
        f"{base}/api/chat/stream",
        json={"query": args.query, "conversation_id": conv["id"]},
        stream=True,
        timeout=180,
    )
    if res.status_code != 200:
        print(f"[fail] 提问失败：{res.status_code} {res.text[:200]}")
        return 1

    events = parse_events(res.iter_lines())
    names = [name for name, _ in events]
    answer = "".join(data.get("delta", "") for name, data in events if name == "answer")
    sources = [src for name, data in events if name == "sources" for src in data.get("sources", [])]
    done = next((data for name, data in reversed(events) if name == "done"), {})
    errors = [data for name, data in events if name == "error"]

    print(f"[ok] SSE 事件：{names[:3]} … {names[-2:]}")
    print(f"[ok] 回答长度：{len(answer)} 字；来源：{len(sources)} 条；状态：{done.get('status')}")
    for src in sources[:3]:
        print(f"     - {src['title']} | {src['source_name']}")

    if not answer:
        print("[fail] 没有收到回答内容")
        return 1
    if errors:
        print(f"[fail] 收到错误事件：{errors[0]}")
        return 1
    if done.get("status") != "complete":
        print(f"[fail] 回答没有正常完成：{done.get('status')}")
        return 1

    detail = session.get(f"{base}/api/conversations/{conv['id']}", timeout=10).json()["data"]
    roles = [m["role"] for m in detail["messages"]]
    print(f"[ok] 历史消息：{roles}")
    assert roles == ["user", "assistant"], roles
    assert detail["messages"][1]["sources"], "助手消息没有保存来源"

    res = session.post(f"{base}/api/conversations/{conv['id']}/memory/clear", timeout=10)
    assert res.status_code == 200, res.text
    print(f"[ok] 清空短期记忆：{res.json()['msg']}")

    res = session.delete(f"{base}/api/conversations/{conv['id']}", timeout=10)
    assert res.status_code == 200, res.text
    print("[ok] 已删除测试会话，冒烟检查全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
