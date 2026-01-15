# Library Assistant (Chatbot Thư Viện)

Backend **FastAPI** cho ứng dụng trợ lý thư viện: hỏi đáp tìm sách trong thư viện và hỏi đáp nội dung **PDF** (RAG). Repo có sẵn **Web UI** trong `static/` để test nhanh (đường dẫn `/`).

## Tính năng chính

- **Chatbot thư viện** (`/api/library/chat`)
  - Tìm sách theo từ khóa (tên sách/chủ đề/nội dung).
  - Pipeline tìm kiếm **Hybrid**: SQL Server **Full-Text Search** + **Semantic Search** (Chroma) + **Rerank**.
  - Kiểm tra tình trạng sách còn/hết theo **ISBN**.
- **Đọc & hỏi đáp PDF (RAG)** (`/api/pdf/upload`, `/api/pdf/chat`)
  - Upload PDF, parse bằng **Docling** (có OCR, trích xuất bảng), chia chunk + index vào **Chroma**.
  - Hỏi đáp dựa trên context lấy từ vector search (có mở rộng “cùng trang”).
  - Xem thống kê collection hiện tại: `/api/pdf/stats`.
- **Web UI test** (`/`)
  - Tab “Tìm Sách” gọi API library chat.
  - Tab “Đọc PDF” có viewer (PDF.js) + khung chat hỏi đáp.

## Kiến trúc & thành phần

- **`LibraryAgent`** (`core/agents/library_agent.py`)
  - Dùng LangChain ReAct agent và 2 tool:
    - `book_search_tool`: tìm sách hybrid + rerank.
    - `sql_check_book_status`: kiểm tra còn/hết theo ISBN.
- **`PDFReaderAgent`** (`core/agents/pdf_reader_agent.py`)
  - Structured RAG: phân tích ý định câu hỏi (summary/section/general) → chọn chiến lược tìm context → trả lời theo schema JSON.
- **Vector store**
  - Dùng **Chroma Cloud** qua `chroma_client` (xem `database/connection.py`).
- **Database**
  - SQL Server (pyodbc + SQLAlchemy). Schema có các bảng tiêu biểu: `DAUSACH`, `SACH`, `DOCGIA`, `PHIEUMUON`, `CT_PHIEUMUON`, `TACGIA`, `THELOAI`, ...

## Yêu cầu

- **Python**: khuyến nghị 3.10+
- **SQL Server**: có thể chạy local hoặc Docker
- **ODBC Driver 18 for SQL Server** (phù hợp chuỗi kết nối đang dùng)
- **API key LLM**: hiện code đang dùng Google Gemini qua `langchain-google-genai`

## Cấu hình môi trường (.env)

Tạo file `.env` ở thư mục gốc project:

```env
# Gemini / Embedding
GEMINI_API_KEY=...
MODEL_EMBEDDING=...
MODEL_PDF_READER=...
MODEL_LIBRARY_ASSISTANT=...

# Database (SQL Server)
DIALECT=mssql+pyodbc
DB_SERVER=localhost
DB_PORT=1433
DB_USER=sa
DB_PASS=...
DB_NAME=QLTV

# Cloudinary (nếu dùng lưu ảnh)
CLOUD_NAME=...
CLOUD_KEY=...
CLOUD_SECRET=...
```

## Chạy project (Local)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

- **Swagger**: `/docs`
- **Redoc**: `/redoc`
- **Web UI test**: `/`
- **Health check**: `/health`
- **API info**: `/api`

## Chạy SQL Server bằng Docker (tuỳ chọn)

Repo có `docker-compose.yml` để khởi tạo container SQL Server.

```bash
docker compose up -d
```

Lưu ý: `docker-compose.yml` hiện chỉ mount file `init-db.sql` vào container tại `/tmp/init-db.sql`. Bạn cần chạy script thủ công trong container (ví dụ dùng `sqlcmd`) để tạo schema và dữ liệu mẫu.

## API Endpoints (đang bật)

### Chatbot thư viện

- `POST /api/library/chat`

Body:

```json
{ "message": "Tìm sách về Python", "user_id": "user123" }
```

Response:

```json
{ "answer": "…", "status": "success" }
```

### Upload PDF

- `POST /api/pdf/upload` (multipart form-data, field `file`)

Response:

```json
{
  "status": "success",
  "filename": "document.pdf",
  "message": "…",
  "total_chunks": 123
}
```

### Chat PDF

- `POST /api/pdf/chat`

Body:

```json
{
  "filename": "document.pdf",
  "message": "Tóm tắt nội dung chính",
  "user_id": "user123"
}
```

### PDF Stats

- `GET /api/pdf/stats`

## Admin API (đang có code nhưng chưa bật)

Router admin nằm ở `api/admin/router.py` và có các nhóm endpoint:

- `GET/POST/PUT/DELETE /api/admin/books`
- `GET/POST/PUT/DELETE /api/admin/copies`
- `GET/POST/PUT/DELETE /api/admin/readers`
- `GET/POST/PUT /api/admin/loans` (trả sách qua endpoint return)
- `GET/POST/PUT/DELETE /api/admin/authors`
- `GET /api/admin/stats/overview`

Để bật, bạn cần **uncomment** phần import + `include_router` trong `main.py`.

## Lưu ý quan trọng

- **Endpoint load PDF từ URL**: Frontend (`static/app.js`) có gọi `POST /api/pdf/load-from-url`, nhưng endpoint này hiện đang **comment** trong `api/chatbot/router.py` → sẽ không dùng được nếu không bật lại.
- **Bảo mật**: Không commit API key/secret thật vào repo. Các thông tin kết nối DB, Gemini key, Cloudinary key nên đặt trong `.env`.
- **Dữ liệu PDF**: file upload được lưu trong `data/pdfs/` và được serve qua `/pdfs/*`.
