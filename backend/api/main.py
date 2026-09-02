from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes import documents, export, review, usage
from backend.api.middleware import RateLimitMiddleware
from backend.core.config import settings


is_prod = settings.environment == "production"

app = FastAPI(
    title="docflow-agent",
    version="0.1.0",
    # Disable interactive docs in production — don't expose the API schema
    docs_url=None if is_prod else "/docs",
    redoc_url=None if is_prod else "/redoc",
    openapi_url=None if is_prod else "/openapi.json",
)

# Rate limiting — must be added BEFORE CORS so it can intercept early
app.add_middleware(RateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    # Expose rate limit headers to the browser
    allow_headers=["*"],
    expose_headers=[
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
        "X-RateLimit-Bypassed",
    ],
)

app.include_router(documents.router, prefix="/api/v1")
app.include_router(review.router, prefix="/api/v1")
app.include_router(export.router, prefix="/api/v1")
app.include_router(usage.router, prefix="/api/v1")

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
