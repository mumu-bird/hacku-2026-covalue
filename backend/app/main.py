from fastapi import FastAPI

app = FastAPI(
    title="CoValue API",
    version="0.1.0",
    description="Backend API for the HacKU 2026 CoValue prototype.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
