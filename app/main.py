"""CareSync application factory."""

import logging
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from app.clock import Clock, utc_now
from app.config import Settings, get_settings
from app.db.base import Repository
from app.routers import activity, appointments, assistant, auth, doses, medications, members
from app.security import RateLimiter, SessionManager
from app.services.ai import AssistantModel, build_assistant

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

_CSP = (
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; "
    "connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
    "form-action 'self'; object-src 'none'"
)
_SECURITY_HEADERS = {
    "Content-Security-Policy": _CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}
# Interactive API docs load assets from a CDN, so they get a relaxed policy (local only).
_DOCS_PATHS = ("/docs", "/openapi.json")


def _build_repo(settings: Settings) -> Repository:
    if settings.db_backend == "firestore":
        from app.db.firestore import FirestoreRepository

        return FirestoreRepository(project=settings.gcp_project)
    from app.db.memory import InMemoryRepository

    return InMemoryRepository()


def create_app(
    settings: Settings | None = None,
    repo: Repository | None = None,
    clock: Clock | None = None,
    ai: AssistantModel | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    app = FastAPI(
        title="CareSync API",
        version="1.0.0",
        description="Shared elderly care and medication management.",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.settings = settings
    app.state.repo = repo or _build_repo(settings)
    app.state.clock = clock or utc_now
    app.state.sessions = SessionManager(settings.session_secret, settings.session_max_age_seconds)
    app.state.login_limiter = RateLimiter(settings.login_max_attempts, settings.login_window_seconds)
    app.state.ai = ai if ai is not None else build_assistant(settings.gemini_api_key, settings.gemini_model)
    app.state.ai_limiter = RateLimiter(max_attempts=10, window_seconds=600)  # 10 questions / 10 min each

    @app.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        if not request.url.path.startswith(_DOCS_PATHS):
            response.headers.update(_SECURITY_HEADERS)
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/healthz", tags=["health"])
    def health() -> dict:
        return {"status": "ok"}

    for module in (auth, members, medications, doses, appointments, activity, assistant):
        app.include_router(module.router)

    if STATIC_DIR.joinpath("index.html").exists():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app


app = create_app()
