import json
from typing import List, Dict, Sequence, Optional, Union
from typing_extensions import TypedDict
from sqlalchemy import text
from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun

# Standard LangChain Retrievers
from langchain.retrievers import EnsembleRetriever, ContextualCompressionRetriever
from langchain.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.vectorstores import Chroma
from langchain_community.cross_encoders import HuggingFaceCrossEncoder

from database.connection import get_db_connection, chroma_client, embedding_model
from log.logger_config import setup_logging
logger = setup_logging(__name__)


# === TYPE DEFINITIONS ===
class DauSachDaXem(TypedDict):
    """Thông tin sách đã xem."""
    isbn: str
    tensach: Optional[str]
    khosach: Optional[str]
    noidung: Optional[str]
    hinhanh: Optional[str]
    ngayxb: Optional[str]
    lanxb: Optional[str]
    sotrang: Optional[int]
    gia: Optional[float]
    nhaxb: Optional[str]
    language_code: Optional[int]
    genres: Optional[list]

# === GLOBALS ===
_bm25_retriever = None
_reranker_model = None


class SQLFullTextRetriever(BaseRetriever):
    """
    Retriever sử dụng SQL Server Full-Text Search.
    """
    top_k: int = 20

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        sql = text(f"""
            SELECT TOP (:top_k) [ISBN], [TENSACH], [NOIDUNG], [HINHANHPATH]
            FROM DAUSACH
            WHERE FREETEXT((TENSACH, NOIDUNG), :query)
        """)
        
        try:
            with get_db_connection() as conn:
                results = conn.execute(sql, {"top_k": self.top_k, "query": query}).mappings().fetchall()
        except Exception as e:
            logger.error(f"SQL FTS Error: {e}")
            return []
        
        docs = []
        logger.debug(f"🔍 [SQL FullText] Found {len(results)} docs.")
        for row in results:
            clean_isbn = str(row['ISBN']).strip()
            doc = Document(
                page_content=f"{row['TENSACH']}\n{row['NOIDUNG']}",
                metadata={
                    "isbn": clean_isbn, 
                    "tensach": row['TENSACH'],
                    "hinhanh": row['HINHANHPATH'],
                    # "source": "sql_fulltext"
                }
            )
            docs.append(doc)
            
        return docs

class LoggingChromaRetriever(BaseRetriever):
    """Wrapper for Chroma Retriever to add logging."""
    vectorstore: Chroma
    search_kwargs: dict

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        docs = self.vectorstore.similarity_search(query, **self.search_kwargs)
        logger.debug(f"🧠 [Semantic Search] Found {len(docs)} docs.")
        for doc in docs:
            # Chuẩn hóa metadata ngay khi lấy ra
            raw_isbn = doc.metadata.get("isbn", "")
            doc.metadata["isbn"] = str(raw_isbn)
            # doc.metadata["source"] = "chroma_semantic"
        return docs

class UniqueEnsembleRetriever(EnsembleRetriever):
    """
    Custom Retriever thay thế cho EnsembleRetriever mặc định.
    Nhiệm vụ:
    1. Gọi RRF để trộn kết quả.
    2. CƯỠNG CHẾ lọc trùng lặp ISBN trước khi trả về.
    """
    
    def invoke(self, input: str, config: dict = None, **kwargs) -> List[Document]:
        # 1. Lấy kết quả trộn từ thuật toán RRF (vẫn chứa trùng lặp)
        docs = super().invoke(input, config, **kwargs)
        
        logger.debug(f"🔗 [Ensemble Raw] Merged {len(docs)} candidates (contains duplicates).")
        
        # 2. Logic lọc trùng lặp cứng (Hard Filter)
        unique_docs = []
        seen_isbns = set()
        
        for doc in docs:
            raw_isbn = doc.metadata.get("isbn", "")
            isbn = str(raw_isbn).strip()
            
            # Chỉ lấy document đầu tiên gặp được (có rank cao nhất trong RRF)
            if isbn and isbn not in seen_isbns:
                unique_docs.append(doc)
                seen_isbns.add(isbn)
        logger.debug(f"✅ [Ensemble Final] Sending {len(unique_docs)} unique docs to Reranker.")
        return unique_docs

class LoggingCrossEncoderReranker(CrossEncoderReranker):
    """Wrapper to log rerank scores."""
    def compress_documents(
        self, documents: Sequence[Document], query: str, callbacks = None
    ) -> Sequence[Document]:
        if not documents:
            return []
        compressed = super().compress_documents(documents, query, callbacks)
        logger.debug(f"🎯 [Reranker] Selected top {len(compressed)}.")
        for i, doc in enumerate(compressed):
            # Lưu ý: Điểm số có thể nằm ở 'relevance_score' hoặc doc.state['query_score'] tùy phiên bản
            score = doc.metadata.get("relevance_score", 0.0)
            isbn = doc.metadata.get("isbn", "N/A")
            tensach = doc.metadata.get("tensach", "N/A")
            logger.debug(f"  {i+1}. Score: {score:.4f} - {tensach} (ISBN: {isbn})")
        return compressed

# === FACTORY FUNCTIONS ===

def _get_bm25_retriever(top_k=20):
    global _bm25_retriever
    if _bm25_retriever is None:
        _bm25_retriever = SQLFullTextRetriever(top_k=top_k)
    return _bm25_retriever

def _get_chroma_retriever(top_k=20):
    vectorstore = Chroma(
        client=chroma_client,
        collection_name="QLTV",
        embedding_function=embedding_model,
        collection_metadata={"hnsw:space": "cosine"}
    )
    return LoggingChromaRetriever(vectorstore=vectorstore, search_kwargs={"k": top_k})

def _get_reranker_model():
    global _reranker_model
    if _reranker_model is not None:
        return _reranker_model
    _reranker_model = HuggingFaceCrossEncoder(model_name="BAAI/bge-reranker-base")
    return _reranker_model

def _get_retrieval_chain():
    logger.info("Đang xây dựng Retrieval Pipeline (Ensemble + Rerank)...")
    
    bm25 = _get_bm25_retriever()
    chroma = _get_chroma_retriever()
    
    # SỬ DỤNG UNIQUE ENSEMBLE RETRIEVER
    ensemble_retriever = UniqueEnsembleRetriever(
        retrievers=[bm25, chroma],
        weights=[0.5, 0.5],
        deduplicate=True,
        deduplicate_by_metadata=["isbn"] 
    )
    
    model = _get_reranker_model()
    # Reranker bây giờ nhận danh sách sạch
    compressor = LoggingCrossEncoderReranker(model=model, top_n=5)
    
    compression_retriever = ContextualCompressionRetriever(
        base_compressor=compressor,
        base_retriever=ensemble_retriever
    )
    logger.success("Đã xây dựng xong Retrieval Pipeline.")
    return compression_retriever
    

def _fetch_full_book_details(isbns: List[str]) -> Dict[str, dict]:
    if not isbns: return {}
    params = {f"isbn{i}": isbn for i, isbn in enumerate(isbns)}
    placeholders = ", ".join([f":isbn{i}" for i in range(len(isbns))])
    
    sql = text(f"""
        SELECT [ISBN], [TENSACH], [NOIDUNG], [HINHANHPATH] ,[GIA]
        FROM DAUSACH 
        WHERE ISBN IN ({placeholders})
    """)
    
    try:
        with get_db_connection() as conn:
            result = conn.execute(sql, params).mappings().fetchall()
        return {str(row['ISBN']).strip(): dict(row) for row in result}
    except Exception as e:
        logger.error(f"Error fetching book details: {e}")
        return {}

def _update_dausachdaxem(seen_books, books_details, ranked_docs) -> dict:
    for doc in ranked_docs:
        isbn = doc.metadata.get("isbn")
        if not isbn: continue
        details = books_details.get(isbn, {})
        
        seen_books[isbn] = DauSachDaXem(
            isbn=isbn,
            tensach=details.get("TENSACH") or doc.metadata.get("tensach"),
            khosach=details.get("KHOSACH"),
            noidung=details.get("NOIDUNG") or doc.metadata.get("noidung"),
            hinhanh=details.get("HINHANHPATH") or doc.metadata.get("hinhanh"),
            ngayxb=str(details.get("NGAYXB")) if details.get("NGAYXB") else None,
            lanxb=str(details.get("LANXB")) if details.get("LANXB") else None,
            sotrang=details.get("SOTRANG"),
            gia=float(details.get("GIA")) if details.get("GIA") else None,
            nhaxb=details.get("NHAXB"),
            language_code=details.get("LANGUAGE_CODE"),
            genres=None
        )
    return seen_books

# === TOOL DEFINITION ===

@tool("book_search_tool")
def book_search_tool(query: Union[str, dict]) -> str:
    """
    Công cụ tìm kiếm sách trong thư viện.
    Sử dụng Hybrid Search (SQL Full-Text + Semantic) và Reranking.
    
    Args:
        query: Từ khóa tìm kiếm (tên sách, chủ đề, nội dung...). Có thể là string hoặc JSON string.
        
    Returns:
        Danh sách sách tìm được với thông tin chi tiết.
    """
    # Xử lý input nếu là dict hoặc json string
    clean_query = query
    if isinstance(query, dict):
        clean_query = query.get("query") or list(query.values())[0]
    elif isinstance(query, str):
        try:
            if query.strip().startswith("{"):
                data = json.loads(query)
                clean_query = data.get("query") or list(data.values())[0]
        except:
            pass
            
    if not clean_query:
        return "Lỗi: Không tìm thấy từ khóa tìm kiếm hợp lệ."
        
    clean_query = str(clean_query).strip()

    retriever = _get_retrieval_chain()
    final_docs = retriever.invoke(clean_query)
    
    top_isbns = [doc.metadata.get("isbn") for doc in final_docs]
    full_details = _fetch_full_book_details(top_isbns)

    context_parts = []
    for i, doc in enumerate(final_docs):
        isbn = doc.metadata.get("isbn")
        details = full_details.get(isbn, {})
        tensach = details.get("TENSACH") or doc.metadata.get("tensach")
        noidung = details.get("NOIDUNG") or doc.metadata.get("noidung")
        gia = details.get("GIA", "N/A")
        
        context_parts.append(
            f"--- Sách {i+1} (ISBN: {isbn}) ---\n"
            f"Tên sách: {tensach}\n"
            f"Giá: {gia}\n"
            f"Nội dung: {noidung}"
        )

    if not context_parts:
        return "Không tìm thấy sách nào phù hợp với từ khóa."
    
    return f"Tìm thấy {len(context_parts)} sách phù hợp:\n\n" + "\n\n".join(context_parts)

# === HELPER FUNCTION FOR LANGCHAIN AGENT ===

def search_books_simple(query: str) -> List[dict]:
    """
    Hàm helper đơn giản để tìm kiếm sách.
    Dùng cho LangChain Agent (không dùng LangGraph Command).
    
    Args:
        query: Từ khóa tìm kiếm
        
    Returns:
        Danh sách dict chứa thông tin sách
    """
    retriever = _get_retrieval_chain()
    final_docs = retriever.invoke(query)
    
    top_isbns = [doc.metadata.get("isbn") for doc in final_docs]
    full_details = _fetch_full_book_details(top_isbns)
    
    results = []
    for doc in final_docs:
        isbn = doc.metadata.get("isbn")
        details = full_details.get(isbn, {})
        results.append({
            "isbn": isbn,
            "tensach": details.get("TENSACH") or doc.metadata.get("tensach"),
            "noidung": details.get("NOIDUNG") or doc.metadata.get("noidung"),
            "hinhanh": details.get("HINHANHPATH") or doc.metadata.get("hinhanh"),
            "gia": details.get("GIA"),
        })
    
    return results


if __name__ == "__main__":
    print("--- Bắt đầu Test ---")
    test_query = "Lập trình Python"
    
    chain = _get_retrieval_chain()
    if chain:
        docs = chain.invoke(test_query)
        print("\n--- KẾT QUẢ CUỐI CÙNG (Đã qua Reranker & Lọc trùng) ---")
        for i, doc in enumerate(docs):
            print(f"{i+1}. {doc.metadata.get('tensach')} (ISBN: {doc.metadata.get('isbn')})")