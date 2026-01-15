import json
from typing import Optional, Union
from langchain_core.tools import tool
from sqlalchemy import text

from database.connection import get_db_connection


@tool("sql_check_book_status")
def sql_check_book_status_tool(isbn: Union[str, dict]) -> str:
    """
    Kiểm tra sách còn trong kho và số lượng đang được mượn dựa trên ISBN.
    Sử dụng tool này khi người dùng muốn biết sách còn hay hết.
    
    Args:
        isbn (str): Mã ISBN của cuốn sách cần kiểm tra.
    """
    clean_isbn = isbn
    if isinstance(isbn, dict):
        clean_isbn = isbn.get("isbn") or list(isbn.values())[0]
    elif isinstance(isbn, str):
        try:
            # Thử parse JSON nếu là string dạng json
            if isbn.strip().startswith("{"):
                data = json.loads(isbn)
                clean_isbn = data.get("isbn") or list(data.values())[0]
        except:
            pass
            
    if not clean_isbn:
        return "Lỗi: Không tìm thấy mã ISBN hợp lệ trong yêu cầu."

    clean_isbn = str(clean_isbn).strip()

    sql_query = text("""
        SELECT
            d.TENSACH,
            COUNT(CASE WHEN s.CHOMUON = 0 THEN 1 END) AS SoLuongCoSan,
            COUNT(CASE WHEN s.CHOMUON = 1 THEN 1 END) AS SoLuongDangMuon
        FROM SACH s
        JOIN DAUSACH d ON s.ISBN = d.ISBN
        WHERE s.ISBN = :isbn AND s.TINHTRANG = 1
        GROUP BY d.TENSACH
    """)

    try:
        with get_db_connection() as conn:
            result = conn.execute(sql_query, {"isbn": clean_isbn}).mappings().first()
    except Exception as e:
        return f"Lỗi khi truy vấn database: {e}"

    if result is None:
        return f"Không tìm thấy thông tin cho sách có ISBN: {clean_isbn}."

    book_info = dict(result)
    tensach = book_info.get("TENSACH", "Không rõ tên")
    so_luong_co_san = book_info.get("SoLuongCoSan", 0)
    so_luong_dang_muon = book_info.get("SoLuongDangMuon", 0)

    if so_luong_co_san > 0:
        return f"Sách '{tensach}' (ISBN: {clean_isbn}) hiện còn {so_luong_co_san} cuốn có sẵn và có {so_luong_dang_muon} cuốn đang được mượn."
    else:
        return f"Rất tiếc, sách '{tensach}' (ISBN: {clean_isbn}) hiện đã được mượn hết. Có {so_luong_dang_muon} cuốn đang được mượn."


# === HELPER FUNCTION FOR LANGCHAIN AGENT ===

def check_book_status_simple(isbn: str) -> dict:
    """
    Hàm helper đơn giản để kiểm tra tình trạng sách.
    Dùng cho LangChain Agent (không dùng LangGraph Command).
    
    Args:
        isbn: ISBN của sách cần kiểm tra
        
    Returns:
        Dict chứa thông tin tình trạng sách, hoặc None nếu không tìm thấy
    """
    sql_query = text("""
        SELECT
            d.TENSACH,
            COUNT(CASE WHEN s.CHOMUON = 0 THEN 1 END) AS SoLuongCoSan,
            COUNT(CASE WHEN s.CHOMUON = 1 THEN 1 END) AS SoLuongDangMuon
        FROM SACH s
        JOIN DAUSACH d ON s.ISBN = d.ISBN
        WHERE s.ISBN = :isbn AND s.TINHTRANG = 1
        GROUP BY d.TENSACH
    """)

    try:
        with get_db_connection() as conn:
            result = conn.execute(sql_query, {"isbn": isbn.strip()}).mappings().first()
    except Exception as e:
        return None
    
    if result is None:
        return None
    
    return dict(result)
