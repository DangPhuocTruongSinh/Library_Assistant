"""
Chatbot Router - Xử lý các request hỏi đáp từ ứng dụng Android.

Endpoints:
- POST /library/chat - Hỏi đáp về sách trong thư viện
- POST /pdf/upload - Upload file PDF để đọc
- POST /pdf/chat - Hỏi đáp về nội dung PDF đã upload
- GET /pdf/stats - Lấy thống kê PDF đang được load
"""

import shutil
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException

from core.agents.library_agent import LibraryAgent
from core.agents.pdf_reader_agent import PDFReaderAgent
# from core.utils.url_downloader import download_pdf_from_url, extract_filename_from_url
from schemas.request import ChatRequest, PDFChatRequest, PDFUrlRequest
from schemas.response import ChatResponse, PDFUploadResponse, PDFChatResponse

from log.logger_config import setup_logging

logger = setup_logging(__name__)

# =============================================================================
# ROUTER CONFIGURATION
# =============================================================================

router = APIRouter(prefix="/api", tags=["Chatbot"])

# =============================================================================
# USER CHAT HISTORY
# =============================================================================
USER_CHAT_HISTORY = {}

# Thư mục lưu PDF
UPLOAD_DIR = Path("data/pdfs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# AGENT SINGLETONS
# =============================================================================

_library_agent: Optional[LibraryAgent] = None
_pdf_agent: Optional[PDFReaderAgent] = None


def get_library_agent() -> LibraryAgent:
    """
    Lấy hoặc tạo LibraryAgent singleton.
    
    Returns:
        LibraryAgent: Instance duy nhất của LibraryAgent.
    """
    global _library_agent
    if _library_agent is None:
        _library_agent = LibraryAgent()
        logger.info("✅ LibraryAgent đã được khởi tạo.")
    return _library_agent


def get_pdf_agent() -> PDFReaderAgent:
    """
    Lấy hoặc tạo PDFReaderAgent singleton.
    
    Returns:
        PDFReaderAgent: Instance duy nhất của PDFReaderAgent.
    """
    global _pdf_agent
    if _pdf_agent is None:
        _pdf_agent = PDFReaderAgent()
        logger.info("✅ PDFReaderAgent đã được khởi tạo.")
    return _pdf_agent


# =============================================================================
# LIBRARY ENDPOINTS
# =============================================================================

@router.post("/library/chat", response_model=ChatResponse)
async def library_chat(request: ChatRequest):
    """
    Hỏi đáp về sách trong thư viện.
    
    Chức năng:
    - Tìm kiếm sách theo tên, chủ đề, nội dung
    - Kiểm tra tình trạng sách (còn/hết)
    - Gợi ý sách theo yêu cầu
    
    Args:
        request (ChatRequest): Chứa message và user_id (optional).
        
    Returns:
        ChatResponse: Câu trả lời từ AI.
        
    Raises:
        HTTPException: 500 nếu có lỗi xử lý.
        
    Example:
        POST /api/library/chat
        {
            "message": "Tìm sách về Python",
            "user_id": "user123"
        }
    """
    try:
        agent = get_library_agent()
        
        # 1. Lấy user_id (nếu không có thì dùng default hoặc session_id)
        user_id = request.user_id or "anonymous"
        
        # KEY CHANGE: Separate history key for Library Assistant
        history_key = f"lib_{user_id}"
        
        # 2. Lấy lịch sử cũ của user này
        history = USER_CHAT_HISTORY.get(history_key, [])
        
        # LOGGING REQUEST
        logger.info(f"👤 User Question ({user_id}): {request.message}")
        logger.info(f"📜 Current Chat History ({len(history)} turns): {history}")
        
        # 3. Truyền lịch sử vào hàm ask
        answer = agent.ask(request.message, chat_history=history)
        
        # LOGGING RESPONSE
        logger.info(f"🤖 Agent Response: {answer}")
        
        # 4. Cập nhật lịch sử mới sau khi có câu trả lời
        # Giới hạn nhớ 10 turn gần nhất để tránh prompt quá dài (Context Window Limit)
        if len(history) > 20: 
            history = history[-20:]
            
        history.append(("Human", request.message))
        history.append(("AI", answer))
        USER_CHAT_HISTORY[history_key] = history
        logger.info(f"📝 Lịch sử hội thoại đã được cập nhật: {history}")
        
        return ChatResponse(
            answer=answer,
            status="success"
        )
        
    except Exception as e:
        logger.error(f"❌ Lỗi library_chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# PDF READER ENDPOINTS
# =============================================================================

@router.post("/pdf/upload", response_model=PDFUploadResponse)
async def upload_pdf(file: UploadFile = File(...)):
    """
    Upload file PDF và index nội dung.
    
    Sau khi upload, PDF sẽ được parse và index vào vector store
    để sẵn sàng cho việc hỏi đáp.
    
    Args:
        file (UploadFile): File PDF cần upload.
        
    Returns:
        PDFUploadResponse: Thông tin upload thành công.
        
    Raises:
        HTTPException: 400 nếu không phải file PDF.
        HTTPException: 500 nếu có lỗi xử lý.
        
    Note: 
        Upload PDF mới sẽ ghi đè dữ liệu PDF cũ.
    """
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400, 
            detail="Chỉ chấp nhận file PDF."
        )
    
    try:
        # 1. Lưu file
        file_path = UPLOAD_DIR / file.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        logger.info(f"📁 Đã lưu file: {file_path}")
        
        # 2. Load và index PDF
        agent = get_pdf_agent()
        success = agent.load_pdf(str(file_path))
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Không thể xử lý file PDF. Vui lòng thử lại."
            )
        
        # 3. Lấy thống kê
        stats = agent.get_stats()
        
        return PDFUploadResponse(
            status="success",
            filename=file.filename,
            message="PDF đã được upload và index thành công!",
            total_chunks=stats.get("total_chunks", 0)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Lỗi upload_pdf: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# @router.post("/pdf/load-from-url", response_model=PDFUploadResponse)
# async def load_pdf_from_url(request: PDFUrlRequest):
#     """
#     Load PDF từ URL (hỗ trợ OneDrive sharing links).
    
#     Quy trình:
#     1. Convert OneDrive link (nếu cần) sang direct download link.
#     2. Download file PDF về server.
#     3. Index nội dung PDF.
    
#     Args:
#         request (PDFUrlRequest): URL của file PDF.
        
#     Returns:
#         PDFUploadResponse: Thông tin xử lý thành công.
#     """
#     try:
#         # 1. Xác định filename
#         if request.filename:
#             filename = request.filename
#             if not filename.lower().endswith('.pdf'):
#                 filename += ".pdf"
#         else:
#             filename = extract_filename_from_url(request.url)
            
#         file_path = UPLOAD_DIR / filename
        
#         # 2. Download file
#         logger.info(f"📥 Bắt đầu download từ URL: {request.url}")
#         success = download_pdf_from_url(request.url, file_path)
        
#         if not success:
#             raise HTTPException(
#                 status_code=400,
#                 detail="Không thể tải file từ URL. Vui lòng kiểm tra lại link (đảm bảo link công khai)."
#             )
            
#         logger.info(f"📁 Đã lưu file từ URL: {file_path}")
        
#         # 3. Load và index PDF
#         agent = get_pdf_agent()
#         success = agent.load_pdf(str(file_path))
        
#         if not success:
#             raise HTTPException(
#                 status_code=500,
#                 detail="Không thể xử lý file PDF. File có thể bị lỗi hoặc không đọc được."
#             )
            
#         # 4. Lấy thống kê
#         stats = agent.get_stats()
        
#         return PDFUploadResponse(
#             status="success",
#             filename=filename,
#             message="PDF đã được tải về và index thành công!",
#             total_chunks=stats.get("total_chunks", 0)
#         )
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"❌ Lỗi load_pdf_from_url: {e}")
#         raise HTTPException(status_code=500, detail=str(e))


@router.post("/pdf/chat", response_model=PDFChatResponse)
async def pdf_chat(request: PDFChatRequest):
    """
    Hỏi đáp về nội dung PDF đã upload.
    
    Args:
        request (PDFChatRequest): Chứa filename và message.
        
    Returns:
        PDFChatResponse: Câu trả lời từ AI.
        
    Raises:
        HTTPException: 404 nếu file không tồn tại.
        HTTPException: 500 nếu có lỗi xử lý.
        
    Example:
        POST /api/pdf/chat
        {
            "filename": "document.pdf",
            "message": "Tóm tắt nội dung chính của tài liệu"
        }
        
    Response:
        {
            "answer": "Tài liệu nói về...",
            "status": "success"
        }
    """
    # Kiểm tra file tồn tại
    file_path = UPLOAD_DIR / request.filename
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy file '{request.filename}'. Vui lòng upload trước."
        )

    try:
        agent = get_pdf_agent()
        
        # 1. Lấy user_id và history
        user_id = request.user_id or "anonymous_pdf"
        
        # KEY CHANGE: Separate history key for PDF Reader
        history_key = f"pdf_{user_id}"
        history = USER_CHAT_HISTORY.get(history_key, [])
        
        # LOGGING REQUEST
        logger.info(f"👤 User Question ({user_id}) - File {request.filename}: {request.message}")
        logger.info(f"📜 Current Chat History ({len(history)} turns): {history}")
        
        # 2. Lấy câu trả lời từ agent
        result = agent.ask(request.message, chat_history=history)
        
        answer = result.get("answer", "Không có câu trả lời.")
        
        # LOGGING RESPONSE
        logger.info(f"🤖 Agent Response: {answer}")
        
        # 3. Cập nhật lịch sử
        if len(history) > 20:
            history = history[-20:]
        history.append(("Human", request.message))
        history.append(("AI", answer))
        USER_CHAT_HISTORY[history_key] = history
        
        return PDFChatResponse(
            answer=answer,
            status="success"
        )

    except Exception as e:
        logger.error(f"❌ Lỗi pdf_chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pdf/stats")
async def pdf_stats():
    """
    Lấy thống kê về PDF đang được load.
    
    Returns:
        dict: Thông tin thống kê bao gồm:
            - status: "success" hoặc "error"
            - total_chunks: Số chunks đã index
            - current_file: Tên file đang được load
    """
    try:
        agent = get_pdf_agent()
        stats = agent.get_stats()
        return {
            "status": "success",
            **stats
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

