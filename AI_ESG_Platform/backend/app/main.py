from app.routers import documents
from app.green.router import router as green_router
from app.cloud_carbon.router import router as cloud_carbon_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="AI ESG Sustainability Platform",
    description="Document Intelligence, Green Software & Cloud Carbon Intelligence for ESG Analysis",
    version="1.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:5501",
        "http://127.0.0.1:5501",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "null",  # file:// origin
    ],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(documents.router)
app.include_router(green_router)
app.include_router(cloud_carbon_router)

@app.get("/")
def home():
    return {"message": "AI ESG Document Intelligence API is running!"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
