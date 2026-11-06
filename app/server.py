"""FastAPI entrypoint for the Tickers dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.error import HTTPError, URLError

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .auth import AuthManager, AuthUser
from .data_service import DashboardDataStore

store = DashboardDataStore()
auth = AuthManager()

app = FastAPI(
    title="Tickers Dashboard API",
    description="Local study dashboard over forecasting artefacts. Not investment advice.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(store.static_dir)), name="static")


def current_user(request: Request) -> AuthUser | None:
    if not auth.auth_enforced:
        return auth.dev_user()
    token = request.cookies.get(auth.SESSION_COOKIE)
    return auth.user_from_session_cookie(token)


def require_user(request: Request) -> AuthUser:
    if not auth.auth_enforced:
        return auth.dev_user()
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


@app.get("/", include_in_schema=False)
def root(request: Request) -> RedirectResponse:
    """Open the local dashboard. Optional password login is off unless configured."""
    if not auth.auth_enforced:
        return RedirectResponse(url="/dashboard")
    if current_user(request):
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url="/login")


def _public_legal_page() -> FileResponse:
    response = FileResponse(str(store.static_dir / "legal.html"))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/legal", include_in_schema=False)
def legal_page() -> FileResponse:
    """Public legal pack: disclaimer, private license, notice."""
    return _public_legal_page()


@app.get("/disclaimer", include_in_schema=False)
def disclaimer_redirect() -> RedirectResponse:
    return RedirectResponse(url="/legal#disclaimer")


@app.get("/license", include_in_schema=False)
def license_redirect() -> RedirectResponse:
    return RedirectResponse(url="/legal#license")


@app.get("/notice", include_in_schema=False)
def notice_redirect() -> RedirectResponse:
    return RedirectResponse(url="/legal#notice")


@app.get("/login", include_in_schema=False)
def login_page(request: Request) -> Response:
    """Serve dedicated login page."""
    if not auth.auth_enforced:
        return RedirectResponse(url="/dashboard")
    if current_user(request):
        return RedirectResponse(url="/dashboard")
    page = store.static_dir / "login.html"
    response = FileResponse(str(page))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/dashboard", include_in_schema=False)
def dashboard_page(request: Request, _: AuthUser = Depends(require_user)) -> FileResponse:
    """Serve dashboard shell after login."""
    page = store.static_dir / "index.html"
    response = FileResponse(str(page))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/guide", include_in_schema=False)
def guide_page(request: Request, _: AuthUser = Depends(require_user)) -> FileResponse:
    """Serve end-user guide with visual examples."""
    page = store.static_dir / "guide.html"
    response = FileResponse(str(page))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
def health() -> dict[str, str]:
    """Simple health endpoint for local checks."""
    return {
        "status": "ok",
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@app.get("/api/auth/public-config")
def auth_public_config() -> dict[str, object]:
    """Expose non-sensitive auth settings for the login UI."""
    return auth.public_config()


@app.get("/api/me")
def me(user: AuthUser = Depends(require_user)) -> dict[str, object]:
    """Return current authenticated user."""
    return {
        "email": user.email,
        "role": user.role,
        "name": user.name,
        "is_owner": user.is_owner,
        "is_admin": user.is_admin,
        "is_test": user.is_test,
    }


@app.get("/auth/login", include_in_schema=False)
def auth_login(request: Request) -> RedirectResponse:
    """External login is not part of the local study build."""
    raise HTTPException(status_code=404, detail="External login is not enabled.")


@app.get("/auth/callback", include_in_schema=False)
def auth_callback(request: Request, code: str | None = None, state: str | None = None) -> RedirectResponse:
    """External login callback is not part of the local study build."""
    del request, code, state
    raise HTTPException(status_code=404, detail="External login is not enabled.")


@app.get("/auth/logout", include_in_schema=False)
def auth_logout(request: Request) -> RedirectResponse:
    """Clear local session and return to login page."""
    response = RedirectResponse(url="/login" if auth.auth_enforced else "/dashboard", status_code=302)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    response.delete_cookie(auth.STATE_COOKIE, path="/")
    return response


@app.post("/auth/test-login", include_in_schema=False)
async def auth_test_login(request: Request) -> JSONResponse:
    """Issue a session for an optional local password configured by the operator."""
    if not auth.test_user_enabled and not auth.password_login_users:
        raise HTTPException(status_code=404, detail="Test user login is disabled.")

    try:
        payload = await request.json()
    except Exception as exc:  # pragma: no cover - defensive parsing guard
        raise HTTPException(status_code=400, detail="Invalid JSON payload.") from exc

    email = str(payload.get("email", "")).strip()
    password = str(payload.get("password", ""))
    user = auth.user_from_test_credentials(email, password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    response = JSONResponse(
        {
            "ok": True,
            "email": user.email,
            "role": user.role,
            "name": user.name,
        }
    )
    response.set_cookie(
        auth.SESSION_COOKIE,
        auth.issue_session_token(user),
        max_age=int(auth.SESSION_DURATION.total_seconds()),
        **auth.session_cookie_args(request),
    )
    return response


@app.get("/api/tickers")
def list_tickers(_: AuthUser = Depends(require_user)) -> dict[str, object]:
    """Return configured and discovered tickers."""
    configured = store.configured_tickers()
    discovered = store.discovered_tickers()
    return {
        "configured": configured,
        "discovered": discovered,
    }


@app.get("/api/overview")
def overview(_: AuthUser = Depends(require_user)) -> dict[str, object]:
    """Return overview payload for dashboard landing page."""
    return store.build_overview()


@app.get("/api/alerts")
def alerts(_: AuthUser = Depends(require_user)) -> dict[str, object]:
    """Return merged failed-ticker alerts built from overview sources."""
    overview_payload = store.build_overview()
    alerts_payload = overview_payload.get("alerts")
    source_files = overview_payload.get("source_files")
    if not isinstance(alerts_payload, dict):
        alerts_payload = {}
    if not isinstance(source_files, dict):
        source_files = {}
    return {
        "generated_at": overview_payload.get("generated_at"),
        "alerts": alerts_payload,
        "source_files": {
            "automation_state": source_files.get("automation_state"),
            "weekly_alerts": source_files.get("weekly_alerts"),
        },
    }


@app.get("/api/ticker/{symbol}")
def ticker_detail(symbol: str, _: AuthUser = Depends(require_user)) -> dict[str, object]:
    """Return full detail payload for one ticker."""
    try:
        return store.build_ticker_detail(symbol)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticker '{symbol.upper()}' not found.") from exc
