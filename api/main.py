"""MSM Quote System — FastAPI Server"""
from fastapi import FastAPI
from api.routes.quote import router as quote_router

app = FastAPI(title="MSM Quote System", version="0.1.0")
app.include_router(quote_router)


@app.get("/")
def root():
    return {"status": "ok", "service": "MSM Quote System"}
