"""
FastAPI Server cho Chatbot Thư Viện.

Cung cấp 2 nhóm API:
1. /api/library, /api/pdf - Hỏi đáp về sách và PDF (Chatbot Router)
2. /api/admin - Quản trị CRUD sách, độc giả, phiếu mượn (Admin Router)

Để chạy:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Để kết nối từ Android App:
    - Qua Ngrok: ngrok http 8000
"""

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.chatbot.router import router as chatbot_router
# from api.admin.router import router as admin_router

from log.logger_config import setup_logging

logger = setup_logging(__name__)

# Static files directory
STATIC_DIR = Path(__file__).parent / "static"

# PDF directory for serving files
PDF_DIR = Path("data/pdfs")
PDF_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# FASTAPI APP INITIALIZATION
# =============================================================================

app = FastAPI(
    title="Chatbot Thư Viện API",
    description="""
API cho ứng dụng thư viện Android.

## Chatbot Endpoints
- **Library Chat**: Hỏi đáp về sách trong thư viện
- **PDF Reader**: Upload và hỏi đáp về nội dung PDF

## Admin Endpoints
- **Books**: CRUD đầu sách (DauSach)
- **Copies**: CRUD bản sách (Sach)
- **Readers**: CRUD độc giả (DocGia)
- **Loans**: CRUD phiếu mượn (PhieuMuon)
- **Authors**: CRUD tác giả (TacGia)
- **Stats**: Thống kê tổng quan
    """,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware - Cho phép Android App kết nối
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Trong production nên giới hạn origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# STATIC FILES
# =============================================================================

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/pdfs", StaticFiles(directory=PDF_DIR), name="pdfs")


# =============================================================================
# INCLUDE ROUTERS
# =============================================================================

app.include_router(chatbot_router)
# app.include_router(admin_router)


# =============================================================================
# HEALTH CHECK ENDPOINTS
# =============================================================================

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
            # "admin": {
            #     "books": "/api/admin/books",
            #     "copies": "/api/admin/copies",
            #     "readers": "/api/admin/readers",
            #     "loans": "/api/admin/loans",
            #     "authors": "/api/admin/authors",
            #     "stats": "/api/admin/stats/overview"
            # }
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


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    logger.info("🚀 Khởi động Chatbot Thư Viện API Server...")
    
    # Chạy server với host 0.0.0.0 để cho phép kết nối từ bên ngoài
    uvicorn.run(
        "main:app",
        host="0.0.0.0",  # Quan trọng: cho phép kết nối từ máy khác
        port=8000,
        reload=True      # Auto-reload khi code thay đổi
    )
