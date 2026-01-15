from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime

class DauSach(BaseModel):
    ISBN: str
    Tensach: str
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

class Sach(BaseModel):
    Masach: str
    ISBN: str
    Tinhtrang: bool
    Chomuon: bool
    MaNgantu: Optional[int] = None

class TacGia(BaseModel):
    MaTacgia: int
    HotenTG: Optional[str] = None
    DiachiTG: Optional[str] = None
    DienthoaiTG: Optional[str] = None

class DocGia(BaseModel):
    MaDG: int
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
    Hoatdong: Optional[bool] = None

class PhieuMuon(BaseModel):
    Maphieu: int
    MaDG: int
    Hinhthuc: bool
    Ngaymuon: datetime
    MaNV: int

class CTPhieuMuon(BaseModel):
    Masach: str
    Maphieu: int
    Ngaytra: Optional[datetime] = None
    Tinhtrangmuon: bool
    Tra: bool
    MaNVNS: Optional[int] = None

class RAGContentInput(BaseModel):
    """Input schema cho PDF Reader Tool."""
    query: str = Field(..., description="Câu hỏi của người dùng về nội dung tài liệu PDF đang mở")


