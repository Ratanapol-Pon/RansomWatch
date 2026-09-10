from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.dashboard import router
from apps.api.line_webhook import router as line_router
from packages.shared.config import get_settings

app = FastAPI(title="RansomWatch TH API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().web_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(router)
app.include_router(line_router)


@app.middleware("http")
async def private_responses(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("apps.api.main:app", host="0.0.0.0", port=get_settings().api_port)
