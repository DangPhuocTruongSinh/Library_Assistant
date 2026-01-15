import os
from typing import Dict

from langchain.tools import StructuredTool
from pydantic.v1 import BaseModel, Field

from core.ingestion.docling_loader import PDFIngestionPipeline
from core.retrieval.reference_search import ReferenceRetrievalSystem

# --- Global Cache ---
# Key: PDF file path (str)
# Value: ReferenceRetrievalSystem instance (đã index dữ liệu của file đó)
PDF_RETRIEVAL_CACHE: Dict[str, ReferenceRetrievalSystem] = {}

# Pipeline ingestion chỉ cần khởi tạo 1 lần
ingestion_pipeline = PDFIngestionPipeline()

def get_or_create_retriever(pdf_path: str) -> ReferenceRetrievalSystem:
    """
    Lấy retriever từ cache hoặc tạo mới (Lazy loading).
    """
    if pdf_path in PDF_RETRIEVAL_CACHE:
        print(f"Cache hit: Sử dụng retriever có sẵn cho {pdf_path}")
        return PDF_RETRIEVAL_CACHE[pdf_path]
    
    print(f"Cache miss: Khởi tạo retriever mới cho {pdf_path}")
    
    # 1. Ingestion (Docling) - Mặc định xử lý toàn bộ sách
    docs = ingestion_pipeline.process_pdf(pdf_path)
    
    # 2. Indexing (Hybrid Search)
    # Tạo tên collection unique để tránh xung đột trong Chroma (nếu persist)
    collection_name = f"pdf_{os.path.basename(pdf_path).replace('.', '_')}"
    retriever_system = ReferenceRetrievalSystem(collection_name=collection_name)
    retriever_system.index_documents(docs)
    
    # 3. Lưu vào Cache
    PDF_RETRIEVAL_CACHE[pdf_path] = retriever_system
    return retriever_system

def pdf_reader_search(pdf_path: str, query: str) -> str:
    """
    Hàm logic chính: Tìm kiếm thông tin trong file PDF.
    """
    if not os.path.exists(pdf_path):
        return f"Lỗi: Không tìm thấy file PDF tại đường dẫn: {pdf_path}"

    try:
        # Lấy hệ thống tìm kiếm cho file này
        retriever = get_or_create_retriever(pdf_path)
        
        # Thực hiện tìm kiếm Hybrid
        results = retriever.search(query, top_k=5)
        
        if not results:
            return "Không tìm thấy thông tin nào liên quan trong tài liệu này."
        
        # Format kết quả trả về để LLM dễ đọc và trích dẫn
        # Format: [ID] Nội dung (Page X)
        context_parts = []
        for i, doc in enumerate(results):
            page = doc.metadata.get('page', '?')
            bbox = doc.metadata.get('bbox', [])
            content = doc.page_content.replace('\n', ' ') # Xóa xuống dòng thừa
            
            # Tạo một ID tham chiếu ngắn gọn cho LLM, ví dụ: [ref_1], [ref_2]
            ref_id = f"ref_{i+1}"
            
            # Chúng ta nhúng metadata (JSON) vào chuỗi context để Agent có thể nhìn thấy
            # nhưng hướng dẫn Agent chỉ output cái ref_id thôi.
            # Metadata chi tiết (bbox) sẽ được Frontend dùng sau này, 
            # hiện tại chúng ta chỉ cần Agent biết nó tồn tại.
            context_part = (
                f"[{ref_id}] (Trang {page}): {content}\n"
                f"Metadata_Hidden: {{'bbox': {bbox}, 'source': '{pdf_path}'}}" 
            )
            context_parts.append(context_part)
            
        final_context = "\n\n".join(context_parts)
        return f"Dưới đây là các đoạn trích tìm được từ tài liệu:\n\n{final_context}"

    except Exception as e:
        return f"Đã xảy ra lỗi khi xử lý file PDF: {str(e)}"

class PDFReaderInput(BaseModel):
    pdf_path: str = Field(description="Đường dẫn đầy đủ đến file PDF cần đọc.")
    query: str = Field(description="Câu hỏi hoặc vấn đề cần tìm kiếm trong tài liệu.")

# Định nghĩa Tool
pdf_reader_tool = StructuredTool.from_function(
    func=pdf_reader_search,
    name="pdf_reader_tool",
    description="Công cụ chuyên dụng để đọc và tìm kiếm thông tin chi tiết bên trong một file PDF. Sử dụng công nghệ Hybrid Search (Vector + Keyword) để đảm bảo độ chính xác. Trả về nội dung kèm số trang và metadata.",
    args_schema=PDFReaderInput
)

