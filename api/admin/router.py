"""
Admin Router - Quản lý CRUD cho dữ liệu thư viện.

Endpoints:
- /books - CRUD đầu sách (DauSach)
- /copies - CRUD bản sách (Sach)
- /readers - CRUD độc giả (DocGia)
- /loans - CRUD phiếu mượn (PhieuMuon)
- /authors - CRUD tác giả (TacGia)
"""

from typing import List, Optional
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from database.connection import get_db_connection
from log.logger_config import setup_logging

logger = setup_logging(__name__)

# =============================================================================
# ROUTER CONFIGURATION
# =============================================================================

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# =============================================================================
# REQUEST/RESPONSE SCHEMAS
# =============================================================================

class BookCreate(BaseModel):
    """Schema tạo đầu sách mới."""
    ISBN: str = Field(..., max_length=13)
    Tensach: str = Field(..., max_length=255)
    Khosach: Optional[str] = None
    Noidung: Optional[str] = None
    Sotrang: Optional[int] = None
    Gia: Optional[int] = None
    HinhAnhPath: Optional[str] = None
    Ngayxuatban: Optional[date] = None
    Lanxuatban: Optional[int] = None
    NHAXB: Optional[str] = None
    MaTL: Optional[str] = None
    MANN: Optional[int] = None


class BookUpdate(BaseModel):
    """Schema cập nhật đầu sách."""
    Tensach: Optional[str] = None
    Khosach: Optional[str] = None
    Noidung: Optional[str] = None
    Sotrang: Optional[int] = None
    Gia: Optional[int] = None
    HinhAnhPath: Optional[str] = None
    Ngayxuatban: Optional[date] = None
    Lanxuatban: Optional[int] = None
    NHAXB: Optional[str] = None
    MaTL: Optional[str] = None
    MANN: Optional[int] = None


class CopyCreate(BaseModel):
    """Schema tạo bản sách mới."""
    Masach: str = Field(..., max_length=20)
    ISBN: str = Field(..., max_length=13)
    Tinhtrang: bool = True
    Chomuon: bool = True
    MaNgantu: Optional[int] = None


class CopyUpdate(BaseModel):
    """Schema cập nhật bản sách."""
    Tinhtrang: Optional[bool] = None
    Chomuon: Optional[bool] = None
    MaNgantu: Optional[int] = None


class ReaderCreate(BaseModel):
    """Schema tạo độc giả mới."""
    HoDG: Optional[str] = None
    TenDG: Optional[str] = None
    EmailDG: Optional[str] = None
    Gioitinh: Optional[bool] = None
    Ngaysinh: Optional[date] = None
    DiachiDG: Optional[str] = None
    DienthoaiDG: Optional[str] = None
    SoCMND: Optional[str] = None
    Ngaylamthe: Optional[date] = None
    Ngayhethan: Optional[date] = None
    Hoatdong: Optional[bool] = True


class ReaderUpdate(BaseModel):
    """Schema cập nhật độc giả."""
    HoDG: Optional[str] = None
    TenDG: Optional[str] = None
    EmailDG: Optional[str] = None
    Gioitinh: Optional[bool] = None
    Ngaysinh: Optional[date] = None
    DiachiDG: Optional[str] = None
    DienthoaiDG: Optional[str] = None
    SoCMND: Optional[str] = None
    Ngayhethan: Optional[date] = None
    Hoatdong: Optional[bool] = None


class LoanCreate(BaseModel):
    """Schema tạo phiếu mượn mới."""
    MaDG: int
    Hinhthuc: bool = True
    Ngaymuon: Optional[datetime] = None
    MaNV: int


class LoanDetailCreate(BaseModel):
    """Schema tạo chi tiết phiếu mượn."""
    Masach: str
    Maphieu: int
    Tinhtrangmuon: bool = True
    Tra: bool = False


class LoanDetailUpdate(BaseModel):
    """Schema cập nhật chi tiết phiếu mượn (trả sách)."""
    Ngaytra: Optional[datetime] = None
    Tra: bool = True
    MaNVNS: Optional[int] = None


class AuthorCreate(BaseModel):
    """Schema tạo tác giả mới."""
    HotenTG: Optional[str] = None
    DiachiTG: Optional[str] = None
    DienthoaiTG: Optional[str] = None


class AuthorUpdate(BaseModel):
    """Schema cập nhật tác giả."""
    HotenTG: Optional[str] = None
    DiachiTG: Optional[str] = None
    DienthoaiTG: Optional[str] = None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def execute_query(query: str, params: dict = None, fetch: bool = True):
    """
    Thực thi truy vấn SQL.
    
    Args:
        query (str): Câu truy vấn SQL.
        params (dict): Tham số cho truy vấn.
        fetch (bool): True nếu cần lấy kết quả (SELECT), False nếu không (INSERT/UPDATE/DELETE).
        
    Returns:
        list | int: Danh sách kết quả hoặc số dòng bị ảnh hưởng.
        
    Raises:
        HTTPException: 500 nếu có lỗi database.
    """
    try:
        conn = get_db_connection()
        if conn is None:
            raise HTTPException(status_code=500, detail="Không thể kết nối database.")
        
        with conn:
            result = conn.execute(text(query), params or {})
            if fetch:
                rows = result.fetchall()
                columns = result.keys()
                return [dict(zip(columns, row)) for row in rows]
            else:
                conn.commit()
                return result.rowcount
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Lỗi database: {e}")
        raise HTTPException(status_code=500, detail=f"Lỗi database: {str(e)}")


# =============================================================================
# BOOK ENDPOINTS (DAUSACH)
# =============================================================================

@router.get("/books")
async def get_books(
    search: Optional[str] = Query(None, description="Tìm theo tên sách"),
    ma_tl: Optional[str] = Query(None, description="Lọc theo mã thể loại"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0)
):
    """
    Lấy danh sách đầu sách.
    
    Args:
        search: Tìm kiếm theo tên sách (LIKE).
        ma_tl: Lọc theo mã thể loại.
        limit: Số lượng tối đa trả về.
        offset: Vị trí bắt đầu.
        
    Returns:
        list: Danh sách đầu sách.
    """
    query = "SELECT * FROM DAUSACH WHERE 1=1"
    params = {}
    
    if search:
        query += " AND Tensach LIKE :search"
        params["search"] = f"%{search}%"
    
    if ma_tl:
        query += " AND MaTL = :ma_tl"
        params["ma_tl"] = ma_tl
    
    query += " ORDER BY ISBN OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY"
    params["limit"] = limit
    params["offset"] = offset
    
    return execute_query(query, params)


@router.get("/books/{isbn}")
async def get_book(isbn: str):
    """
    Lấy thông tin đầu sách theo ISBN.
    
    Args:
        isbn: Mã ISBN của sách.
        
    Returns:
        dict: Thông tin đầu sách.
        
    Raises:
        HTTPException: 404 nếu không tìm thấy.
    """
    query = "SELECT * FROM DAUSACH WHERE ISBN = :isbn"
    result = execute_query(query, {"isbn": isbn})
    
    if not result:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy sách với ISBN: {isbn}")
    
    return result[0]


@router.post("/books", status_code=201)
async def create_book(book: BookCreate):
    """
    Tạo đầu sách mới.
    
    Args:
        book: Thông tin đầu sách.
        
    Returns:
        dict: Thông tin đầu sách vừa tạo.
    """
    query = """
        INSERT INTO DAUSACH (ISBN, Tensach, Khosach, Noidung, Sotrang, Gia, 
                            HinhAnhPath, Ngayxuatban, Lanxuatban, NHAXB, MaTL, MANN)
        VALUES (:ISBN, :Tensach, :Khosach, :Noidung, :Sotrang, :Gia,
                :HinhAnhPath, :Ngayxuatban, :Lanxuatban, :NHAXB, :MaTL, :MANN)
    """
    execute_query(query, book.model_dump(), fetch=False)
    return {"status": "success", "message": "Đã tạo đầu sách mới", "ISBN": book.ISBN}


@router.put("/books/{isbn}")
async def update_book(isbn: str, book: BookUpdate):
    """
    Cập nhật đầu sách.
    
    Args:
        isbn: Mã ISBN của sách cần cập nhật.
        book: Thông tin cập nhật.
        
    Returns:
        dict: Kết quả cập nhật.
    """
    # Lọc các trường không None
    updates = {k: v for k, v in book.model_dump().items() if v is not None}
    
    if not updates:
        raise HTTPException(status_code=400, detail="Không có dữ liệu để cập nhật")
    
    set_clause = ", ".join([f"{k} = :{k}" for k in updates.keys()])
    query = f"UPDATE DAUSACH SET {set_clause} WHERE ISBN = :isbn"
    updates["isbn"] = isbn
    
    affected = execute_query(query, updates, fetch=False)
    
    if affected == 0:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy sách với ISBN: {isbn}")
    
    return {"status": "success", "message": "Đã cập nhật đầu sách"}


@router.delete("/books/{isbn}")
async def delete_book(isbn: str):
    """
    Xóa đầu sách.
    
    Args:
        isbn: Mã ISBN của sách cần xóa.
        
    Returns:
        dict: Kết quả xóa.
        
    Raises:
        HTTPException: 404 nếu không tìm thấy.
    """
    query = "DELETE FROM DAUSACH WHERE ISBN = :isbn"
    affected = execute_query(query, {"isbn": isbn}, fetch=False)
    
    if affected == 0:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy sách với ISBN: {isbn}")
    
    return {"status": "success", "message": "Đã xóa đầu sách"}


# =============================================================================
# COPY ENDPOINTS (SACH - Bản sách)
# =============================================================================

@router.get("/copies")
async def get_copies(
    isbn: Optional[str] = Query(None, description="Lọc theo ISBN"),
    available: Optional[bool] = Query(None, description="Lọc theo tình trạng cho mượn"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0)
):
    """
    Lấy danh sách bản sách.
    
    Args:
        isbn: Lọc theo ISBN.
        available: True = còn cho mượn, False = đang mượn.
        limit: Số lượng tối đa.
        offset: Vị trí bắt đầu.
        
    Returns:
        list: Danh sách bản sách.
    """
    query = "SELECT * FROM SACH WHERE 1=1"
    params = {}
    
    if isbn:
        query += " AND ISBN = :isbn"
        params["isbn"] = isbn
    
    if available is not None:
        query += " AND Chomuon = :available"
        params["available"] = available
    
    query += " ORDER BY Masach OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY"
    params["limit"] = limit
    params["offset"] = offset
    
    return execute_query(query, params)


@router.get("/copies/{masach}")
async def get_copy(masach: str):
    """Lấy thông tin bản sách theo mã sách."""
    query = "SELECT * FROM SACH WHERE Masach = :masach"
    result = execute_query(query, {"masach": masach})
    
    if not result:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy bản sách: {masach}")
    
    return result[0]


@router.post("/copies", status_code=201)
async def create_copy(copy: CopyCreate):
    """Tạo bản sách mới."""
    query = """
        INSERT INTO SACH (Masach, ISBN, Tinhtrang, Chomuon, MaNgantu)
        VALUES (:Masach, :ISBN, :Tinhtrang, :Chomuon, :MaNgantu)
    """
    execute_query(query, copy.model_dump(), fetch=False)
    return {"status": "success", "message": "Đã tạo bản sách mới", "Masach": copy.Masach}


@router.put("/copies/{masach}")
async def update_copy(masach: str, copy: CopyUpdate):
    """Cập nhật bản sách."""
    updates = {k: v for k, v in copy.model_dump().items() if v is not None}
    
    if not updates:
        raise HTTPException(status_code=400, detail="Không có dữ liệu để cập nhật")
    
    set_clause = ", ".join([f"{k} = :{k}" for k in updates.keys()])
    query = f"UPDATE SACH SET {set_clause} WHERE Masach = :masach"
    updates["masach"] = masach
    
    affected = execute_query(query, updates, fetch=False)
    
    if affected == 0:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy bản sách: {masach}")
    
    return {"status": "success", "message": "Đã cập nhật bản sách"}


@router.delete("/copies/{masach}")
async def delete_copy(masach: str):
    """Xóa bản sách."""
    query = "DELETE FROM SACH WHERE Masach = :masach"
    affected = execute_query(query, {"masach": masach}, fetch=False)
    
    if affected == 0:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy bản sách: {masach}")
    
    return {"status": "success", "message": "Đã xóa bản sách"}


# =============================================================================
# READER ENDPOINTS (DOCGIA)
# =============================================================================

@router.get("/readers")
async def get_readers(
    search: Optional[str] = Query(None, description="Tìm theo họ tên"),
    active: Optional[bool] = Query(None, description="Lọc theo trạng thái hoạt động"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0)
):
    """Lấy danh sách độc giả."""
    query = "SELECT * FROM DOCGIA WHERE 1=1"
    params = {}
    
    if search:
        query += " AND (HoDG LIKE :search OR TenDG LIKE :search)"
        params["search"] = f"%{search}%"
    
    if active is not None:
        query += " AND Hoatdong = :active"
        params["active"] = active
    
    query += " ORDER BY MaDG OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY"
    params["limit"] = limit
    params["offset"] = offset
    
    return execute_query(query, params)


@router.get("/readers/{ma_dg}")
async def get_reader(ma_dg: int):
    """Lấy thông tin độc giả theo mã."""
    query = "SELECT * FROM DOCGIA WHERE MaDG = :ma_dg"
    result = execute_query(query, {"ma_dg": ma_dg})
    
    if not result:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy độc giả: {ma_dg}")
    
    return result[0]


@router.post("/readers", status_code=201)
async def create_reader(reader: ReaderCreate):
    """Tạo độc giả mới."""
    query = """
        INSERT INTO DOCGIA (HoDG, TenDG, EmailDG, Gioitinh, Ngaysinh, 
                           DiachiDG, DienthoaiDG, SoCMND, Ngaylamthe, Ngayhethan, Hoatdong)
        OUTPUT INSERTED.MaDG
        VALUES (:HoDG, :TenDG, :EmailDG, :Gioitinh, :Ngaysinh,
                :DiachiDG, :DienthoaiDG, :SoCMND, :Ngaylamthe, :Ngayhethan, :Hoatdong)
    """
    result = execute_query(query, reader.model_dump())
    return {"status": "success", "message": "Đã tạo độc giả mới", "MaDG": result[0]["MaDG"]}


@router.put("/readers/{ma_dg}")
async def update_reader(ma_dg: int, reader: ReaderUpdate):
    """Cập nhật độc giả."""
    updates = {k: v for k, v in reader.model_dump().items() if v is not None}
    
    if not updates:
        raise HTTPException(status_code=400, detail="Không có dữ liệu để cập nhật")
    
    set_clause = ", ".join([f"{k} = :{k}" for k in updates.keys()])
    query = f"UPDATE DOCGIA SET {set_clause} WHERE MaDG = :ma_dg"
    updates["ma_dg"] = ma_dg
    
    affected = execute_query(query, updates, fetch=False)
    
    if affected == 0:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy độc giả: {ma_dg}")
    
    return {"status": "success", "message": "Đã cập nhật độc giả"}


@router.delete("/readers/{ma_dg}")
async def delete_reader(ma_dg: int):
    """Xóa độc giả (soft delete - set Hoatdong = False)."""
    query = "UPDATE DOCGIA SET Hoatdong = 0 WHERE MaDG = :ma_dg"
    affected = execute_query(query, {"ma_dg": ma_dg}, fetch=False)
    
    if affected == 0:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy độc giả: {ma_dg}")
    
    return {"status": "success", "message": "Đã vô hiệu hóa độc giả"}


# =============================================================================
# LOAN ENDPOINTS (PHIEUMUON)
# =============================================================================

@router.get("/loans")
async def get_loans(
    ma_dg: Optional[int] = Query(None, description="Lọc theo mã độc giả"),
    from_date: Optional[date] = Query(None, description="Từ ngày"),
    to_date: Optional[date] = Query(None, description="Đến ngày"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0)
):
    """Lấy danh sách phiếu mượn."""
    query = "SELECT * FROM PHIEUMUON WHERE 1=1"
    params = {}
    
    if ma_dg:
        query += " AND MaDG = :ma_dg"
        params["ma_dg"] = ma_dg
    
    if from_date:
        query += " AND CAST(Ngaymuon AS DATE) >= :from_date"
        params["from_date"] = from_date
    
    if to_date:
        query += " AND CAST(Ngaymuon AS DATE) <= :to_date"
        params["to_date"] = to_date
    
    query += " ORDER BY Ngaymuon DESC OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY"
    params["limit"] = limit
    params["offset"] = offset
    
    return execute_query(query, params)


@router.get("/loans/{maphieu}")
async def get_loan(maphieu: int):
    """Lấy thông tin phiếu mượn và chi tiết."""
    # Lấy thông tin phiếu
    loan_query = "SELECT * FROM PHIEUMUON WHERE Maphieu = :maphieu"
    loan = execute_query(loan_query, {"maphieu": maphieu})
    
    if not loan:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy phiếu mượn: {maphieu}")
    
    # Lấy chi tiết phiếu
    detail_query = "SELECT * FROM CTPHIEUMUON WHERE Maphieu = :maphieu"
    details = execute_query(detail_query, {"maphieu": maphieu})
    
    return {
        "loan": loan[0],
        "details": details
    }


@router.post("/loans", status_code=201)
async def create_loan(loan: LoanCreate):
    """Tạo phiếu mượn mới."""
    ngaymuon = loan.Ngaymuon or datetime.now()
    
    query = """
        INSERT INTO PHIEUMUON (MaDG, Hinhthuc, Ngaymuon, MaNV)
        OUTPUT INSERTED.Maphieu
        VALUES (:MaDG, :Hinhthuc, :Ngaymuon, :MaNV)
    """
    params = {
        "MaDG": loan.MaDG,
        "Hinhthuc": loan.Hinhthuc,
        "Ngaymuon": ngaymuon,
        "MaNV": loan.MaNV
    }
    
    result = execute_query(query, params)
    return {"status": "success", "message": "Đã tạo phiếu mượn", "Maphieu": result[0]["Maphieu"]}


@router.post("/loans/{maphieu}/details", status_code=201)
async def add_loan_detail(maphieu: int, detail: LoanDetailCreate):
    """Thêm sách vào phiếu mượn."""
    # Cập nhật Maphieu từ URL
    detail_data = detail.model_dump()
    detail_data["Maphieu"] = maphieu
    
    query = """
        INSERT INTO CTPHIEUMUON (Masach, Maphieu, Tinhtrangmuon, Tra)
        VALUES (:Masach, :Maphieu, :Tinhtrangmuon, :Tra)
    """
    execute_query(query, detail_data, fetch=False)
    
    # Cập nhật trạng thái sách (không còn cho mượn)
    update_query = "UPDATE SACH SET Chomuon = 0 WHERE Masach = :Masach"
    execute_query(update_query, {"Masach": detail.Masach}, fetch=False)
    
    return {"status": "success", "message": "Đã thêm sách vào phiếu mượn"}


@router.put("/loans/{maphieu}/return/{masach}")
async def return_book(maphieu: int, masach: str, detail: LoanDetailUpdate):
    """Trả sách."""
    ngaytra = detail.Ngaytra or datetime.now()
    
    # Cập nhật chi tiết phiếu
    query = """
        UPDATE CTPHIEUMUON 
        SET Ngaytra = :ngaytra, Tra = :tra, MaNVNS = :manvns
        WHERE Maphieu = :maphieu AND Masach = :masach
    """
    params = {
        "ngaytra": ngaytra,
        "tra": detail.Tra,
        "manvns": detail.MaNVNS,
        "maphieu": maphieu,
        "masach": masach
    }
    
    affected = execute_query(query, params, fetch=False)
    
    if affected == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy chi tiết phiếu mượn")
    
    # Cập nhật trạng thái sách (cho mượn lại)
    update_query = "UPDATE SACH SET Chomuon = 1 WHERE Masach = :masach"
    execute_query(update_query, {"masach": masach}, fetch=False)
    
    return {"status": "success", "message": "Đã trả sách thành công"}


# =============================================================================
# AUTHOR ENDPOINTS (TACGIA)
# =============================================================================

@router.get("/authors")
async def get_authors(
    search: Optional[str] = Query(None, description="Tìm theo tên tác giả"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0)
):
    """Lấy danh sách tác giả."""
    query = "SELECT * FROM TACGIA WHERE 1=1"
    params = {}
    
    if search:
        query += " AND HotenTG LIKE :search"
        params["search"] = f"%{search}%"
    
    query += " ORDER BY MaTacgia OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY"
    params["limit"] = limit
    params["offset"] = offset
    
    return execute_query(query, params)


@router.get("/authors/{ma_tg}")
async def get_author(ma_tg: int):
    """Lấy thông tin tác giả."""
    query = "SELECT * FROM TACGIA WHERE MaTacgia = :ma_tg"
    result = execute_query(query, {"ma_tg": ma_tg})
    
    if not result:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tác giả: {ma_tg}")
    
    return result[0]


@router.post("/authors", status_code=201)
async def create_author(author: AuthorCreate):
    """Tạo tác giả mới."""
    query = """
        INSERT INTO TACGIA (HotenTG, DiachiTG, DienthoaiTG)
        OUTPUT INSERTED.MaTacgia
        VALUES (:HotenTG, :DiachiTG, :DienthoaiTG)
    """
    result = execute_query(query, author.model_dump())
    return {"status": "success", "message": "Đã tạo tác giả mới", "MaTacgia": result[0]["MaTacgia"]}


@router.put("/authors/{ma_tg}")
async def update_author(ma_tg: int, author: AuthorUpdate):
    """Cập nhật tác giả."""
    updates = {k: v for k, v in author.model_dump().items() if v is not None}
    
    if not updates:
        raise HTTPException(status_code=400, detail="Không có dữ liệu để cập nhật")
    
    set_clause = ", ".join([f"{k} = :{k}" for k in updates.keys()])
    query = f"UPDATE TACGIA SET {set_clause} WHERE MaTacgia = :ma_tg"
    updates["ma_tg"] = ma_tg
    
    affected = execute_query(query, updates, fetch=False)
    
    if affected == 0:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tác giả: {ma_tg}")
    
    return {"status": "success", "message": "Đã cập nhật tác giả"}


@router.delete("/authors/{ma_tg}")
async def delete_author(ma_tg: int):
    """Xóa tác giả."""
    query = "DELETE FROM TACGIA WHERE MaTacgia = :ma_tg"
    affected = execute_query(query, {"ma_tg": ma_tg}, fetch=False)
    
    if affected == 0:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tác giả: {ma_tg}")
    
    return {"status": "success", "message": "Đã xóa tác giả"}


# =============================================================================
# STATISTICS ENDPOINTS
# =============================================================================

@router.get("/stats/overview")
async def get_overview_stats():
    """
    Lấy thống kê tổng quan về thư viện.
    
    Returns:
        dict: Các số liệu thống kê.
    """
    queries = {
        "total_books": "SELECT COUNT(*) as count FROM DAUSACH",
        "total_copies": "SELECT COUNT(*) as count FROM SACH",
        "available_copies": "SELECT COUNT(*) as count FROM SACH WHERE Chomuon = 1",
        "total_readers": "SELECT COUNT(*) as count FROM DOCGIA WHERE Hoatdong = 1",
        "total_loans_this_month": """
            SELECT COUNT(*) as count FROM PHIEUMUON 
            WHERE MONTH(Ngaymuon) = MONTH(GETDATE()) AND YEAR(Ngaymuon) = YEAR(GETDATE())
        """,
        "overdue_books": """
            SELECT COUNT(*) as count FROM CTPHIEUMUON ct
            JOIN PHIEUMUON pm ON ct.Maphieu = pm.Maphieu
            WHERE ct.Tra = 0 AND DATEDIFF(day, pm.Ngaymuon, GETDATE()) > 14
        """
    }
    
    stats = {}
    for key, query in queries.items():
        result = execute_query(query)
        stats[key] = result[0]["count"] if result else 0
    
    return {"status": "success", "stats": stats}


