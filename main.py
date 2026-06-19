from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import cv

app = FastAPI(
    title="CV Analyzer API",
    description="تحليل السيرة الذاتية والتوصية بالمسار المهني",
    version="1.0.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# عشان الـ Frontend (React) يقدر يتكلم مع الـ Backend

# ربط الـ Router
app.include_router(cv.router)

@app.get("/")
def root():
    return {"status": "CV Analyzer API شغال ✅"}