from fastapi import Request
from fastapi.responses import JSONResponse
from config import settings
import re

# Endpoints that bypass the API key check
EXEMPT_PATTERNS = [
    r"^/api/health$",
    r"^/docs",
    r"^/openapi\.json$",
    r"^/api/webhooks/",  # Webhook tokens are their own auth
]

async def api_key_middleware(request: Request, call_next):
    """
    Optional API key guard for VPS/cloud deployment.
    Set API_KEY_ENABLED=true and API_KEY=<secret> in .env to activate.
    Pass the key via 'X-API-Key' request header.
    """
    if not settings.api_key_enabled:
        return await call_next(request)

    path = request.url.path
    if any(re.match(p, path) for p in EXEMPT_PATTERNS):
        return await call_next(request)

    api_key = request.headers.get("X-API-Key")
    if api_key != settings.api_key:
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or missing API key. Pass it in the X-API-Key header."}
        )

    return await call_next(request)
