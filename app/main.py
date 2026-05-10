# from sys import prefix
# from xml.sax.handler import version

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
from .api import endpoints

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Aura",version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(endpoints.router,prefix="/api",tags=["Directory"])

app.get("/")
def health_check():
    return {"status": "Online", "message": "Aura is running"}
