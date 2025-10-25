from fastapi import FastAPI
app = FastAPI(docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json")

@app.get("/")
def root():
    return {"ok": True}
