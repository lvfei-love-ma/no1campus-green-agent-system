"""前端与接口契约测试。

不启动浏览器，检查：
- 新页面不再依赖 Vue/Element 旧实现，也不再使用 localStorage 保存身份；
- app.js 引用的接口与后端路由一致；
- app.js 中通过 $('id') 获取的元素在 chat.html 中都存在；
- 前端引用的静态资源确实存在。
"""
from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"
CHAT_HTML = STATIC / "chat.html"
LOGIN_HTML = STATIC / "login.html"
APP_JS = STATIC / "assets" / "app.js"
APP_CSS = STATIC / "assets" / "app.css"


def test_new_pages_exist():
    for path in (CHAT_HTML, LOGIN_HTML, APP_JS, APP_CSS):
        assert path.is_file(), f"缺少 {path}"


def test_chat_page_does_not_use_local_storage_identity():
    for path in (CHAT_HTML, APP_JS, LOGIN_HTML):
        text = path.read_text(encoding="utf-8")
        assert "localStorage" not in text, f"{path.name} 不应再用 localStorage 保存身份"


def test_chat_page_no_longer_loads_vue_or_element():
    html = CHAT_HTML.read_text(encoding="utf-8")
    for forbidden in ("vue.min.js", "element.js", "element.css", "createElement"):
        assert forbidden not in html
    assert 'id="app"' in html
    assert "绿知助手" in html


def test_frontend_endpoints_match_backend_routes(client, login):
    js = APP_JS.read_text(encoding="utf-8")
    for endpoint in (
        "/api/auth/me",
        "/api/auth/logout",
        "/api/conversations",
        "/api/chat/stream",
        "/memory/clear",
    ):
        assert endpoint in js, f"前端未调用 {endpoint}"

    login("A")
    conv = client.post("/api/conversations", json={"title": "契约测试"}).json()["data"]
    assert client.get(f"/api/conversations/{conv['id']}").status_code == 200
    assert client.post(f"/api/conversations/{conv['id']}/memory/clear").status_code == 200


def test_every_element_id_used_by_app_js_exists_in_html():
    html = CHAT_HTML.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")
    ids = set(re.findall(r"\$\('([a-zA-Z0-9_]+)'\)", js))
    assert ids, "app.js 未发现 $('id') 调用"
    missing = [element_id for element_id in sorted(ids) if f'id="{element_id}"' not in html]
    assert not missing, f"chat.html 缺少元素: {missing}"


def test_chat_html_references_existing_assets():
    from urllib.parse import urlsplit

    html = CHAT_HTML.read_text(encoding="utf-8")
    refs = [urlsplit(ref).path for ref in re.findall(r'/static/([^"\']+)', html)]
    missing = [ref for ref in refs if not (STATIC / ref).is_file()]
    assert not missing, f"静态资源缺失: {missing}"


def test_login_page_has_required_controls():
    html = LOGIN_HTML.read_text(encoding="utf-8")
    for marker in ('id="email"', 'id="vcode"', 'id="codeBtn"', 'id="loginBtn"', "demo-login"):
        assert marker in html, f"登录页缺少 {marker}"
    assert 'aria-label' in html


def test_sse_event_names_are_documented_and_handled():
    from service import sse

    source = (STATIC / "assets" / "app.js").read_text(encoding="utf-8")
    for event in ("meta", "answer", "sources", "done", "error"):
        assert f"'{event}'" in sse.__doc__ or event in sse.__doc__
        assert event in source or f"'{event}'" in source


def test_chat_page_has_accessibility_and_responsive_hooks():
    html = CHAT_HTML.read_text(encoding="utf-8")
    css = APP_CSS.read_text(encoding="utf-8")
    assert 'aria-live="polite"' in html
    assert 'aria-label' in html
    assert ":focus-visible" in css
    assert "@media (max-width: 900px)" in css
    assert "#16856b" in css.lower()


def test_login_page_has_no_placeholder_sms_or_homepage_marketing():
    html = LOGIN_HTML.read_text(encoding="utf-8")
    assert "本地体验" in html or "演示账号" in html
    assert "/api/auth/vcode" in html
