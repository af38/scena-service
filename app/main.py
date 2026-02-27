from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import media  # , thumbnail (if you separate)
from .database import init_db

init_db()  # ensure table exists

app = FastAPI(title="Scena Media Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(media.router)
# app.include_router(thumbnail.router) if split

@app.get("/")
async def root():
    return {"message": "scena service"}