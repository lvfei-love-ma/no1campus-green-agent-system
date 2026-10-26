"""FastAPI 入口。

启动：
    uvicorn main:app --host 127.0.0.1 --port 8800
页面：
    http://127.0.0.1:8800/          -> 聊天工作区（未登录会跳转登录页）
    http://127.0.0.1:8800/login      -> 登录页
    http://127.0.0.1:8800/docs       -> OpenAPI 文档
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.staticfiles import StaticFiles

from api_router.auth_router import auth_router
from api_router.chat_router import chat_router
from api_router.conversation_router import conversation_router
from service.runtime import get_runtime
from utils.config import KNOWLEDGE_TITLE
from utils.logger import setup_logger

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
logger = setup_logger(__name__)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # 测试可以先 init_runtime(tmp_db)，这里就复用已初始化的运行期容器
        runtime = get_runtime()
        runtime.storage.purge_expired_sessions()
        logger.info("服务启动完成，知识库主题：%s", KNOWLEDGE_TITLE)
        yield

    app = FastAPI(
        title="绿知助手 · 绿色校园与低碳生活知识问答",
        version="2.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(conversation_router, prefix="/api")

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # ------------------------------------------------------------ 错误格式
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.status_code, "msg": str(exc.detail), "data": None},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"code": 422, "msg": "请求参数不合法", "data": None},
        )

    # ------------------------------------------------------------ 页面
    @app.get("/", include_in_schema=False)
    def index():
        return RedirectResponse(url="/chat")

    @app.get("/chat", include_in_schema=False)
    def chat_page():
        return FileResponse(STATIC_DIR / "chat.html")

    @app.get("/login", include_in_schema=False)
    def login_page():
        return FileResponse(STATIC_DIR / "login.html")

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"status": "ok", "knowledge_title": KNOWLEDGE_TITLE}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
