from pydantic import BaseModel, Field
from typing import Optional

class ChatRequest(BaseModel):
    """Request body cho endpoint chat."""
    message: str = Field(..., description="Câu hỏi của người dùng")
    user_id: Optional[str] = Field(None, description="ID người dùng (nếu đã đăng nhập)")

class PDFChatRequest(BaseModel):
    """Request body cho endpoint chat PDF."""
    filename: str = Field(..., description="Tên file PDF đã upload")
    message: str = Field(..., description="Câu hỏi về nội dung PDF")
    user_id: Optional[str] = Field(None, description="ID người dùng (để lưu lịch sử chat)")

class PDFUrlRequest(BaseModel):
    """Request body cho endpoint load PDF từ URL/OneDrive."""
    url: str = Field(..., description="URL của file PDF (hỗ trợ OneDrive links)")
    filename: Optional[str] = Field(None, description="Tên file PDF (nếu không có sẽ tự động lấy từ URL)")