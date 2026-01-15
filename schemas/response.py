from pydantic import BaseModel, Field
from typing import List

class ChatResponse(BaseModel):
    """Response body cho endpoint chat."""
    answer: str = Field(..., description="Câu trả lời từ AI")
    status: str = Field(default="success")


class PDFUploadResponse(BaseModel):
    """Response sau khi upload PDF."""
    status: str
    filename: str
    message: str
    total_chunks: int = Field(0, description="Số chunks đã index")

class PDFChatResponse(BaseModel):
    """Response cho endpoint chat PDF."""
    answer: str = Field(..., description="Câu trả lời từ AI")
    status: str = Field(default="success")