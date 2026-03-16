from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.chatbot.router import router as chatbot_router
from log.logger_config import setup_logging

logger = setup_logging(__name__)

# Static files directory
STATIC_DIR = Path(__file__).parent / "static"

# PDF directory for serving files
PDF_DIR = Path("data/pdfs")
PDF_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Chatbot Thư Viện API",
    description="""
API cho ứng dụng thư viện Android.

## Chatbot Endpoints
- **Library Chat**: Hỏi đáp về sách trong thư viện
- **PDF Reader**: Upload và hỏi đáp về nội dung PDF
""",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware - Cho phép Android App kết nối
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/pdfs", StaticFiles(directory=PDF_DIR), name="pdfs")
app.include_router(chatbot_router)


@app.get("/", tags=["UI"])
async def serve_ui():
    """
    Phục vụ giao diện web UI cho testing.
    
    Returns:
        FileResponse: File index.html.
    """
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api", tags=["Health"])
async def api_info():
    """
    API info endpoint - danh sách endpoints.
    
    Returns:
        dict: Thông tin về API và danh sách endpoints.
    """
    return {
        "message": "Chatbot Thư Viện API đang hoạt động!",
        "version": "2.0.0",
        "docs": "/docs",
        "ui": "/",
        "endpoints": {
            "chatbot": {
                "library_chat": "POST /api/library/chat",
                "pdf_upload": "POST /api/pdf/upload",
                "pdf_chat": "POST /api/pdf/chat",
                "pdf_stats": "GET /api/pdf/stats"
            },
        }
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint cho monitoring.
    
    Returns:
        dict: Status của server.
    """
    return {"status": "healthy"}

if __name__ == "__main__":
    logger.info("🚀 Khởi động Chatbot Thư Viện API Server...")
    
    # Chạy server với host 0.0.0.0 để cho phép kết nối từ bên ngoài
    uvicorn.run(
        "main:app",
        host="0.0.0.0",  
        port=8000,
        reload=True     
    )
