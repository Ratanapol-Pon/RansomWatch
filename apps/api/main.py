from fastapi import FastAPI

app = FastAPI(title="RansomWatch TH API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
