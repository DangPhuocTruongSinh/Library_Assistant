# Library Assistant

## Tong quan
Du an cung cap API chatbot thu vien va bo doc PDF. He thong gom:
- Chatbot thu vien: tim sach, kiem tra tinh trang muon, goi y sach.
- PDF Reader: upload PDF, index noi dung, hoi dap theo tai lieu.
- UI test nhanh tren web tai `/` va tai lieu API tai `/docs`.

## Tinh nang chinh
- Hoi dap ve sach trong thu vien thong qua `/api/library/chat`.
- Upload va hoi dap tren PDF thong qua `/api/pdf/upload`, `/api/pdf/chat`.
- Thong ke PDF dang duoc load qua `/api/pdf/stats`.
- API quan tri (CRUD) co san trong `api/admin/router.py` (hien dang comment trong `main.py`).

## Kien truc
He thong duoc thiet ke theo mo hinh multi-agent. Moi agent phu trach mot nhiem vu:
- `LibraryAgent`: ReAct agent cho truy van va kiem tra sach.
- `PDFReaderAgent`: Structured RAG cho tai lieu PDF, tu dong chon chien luoc tim kiem.

## Cong nghe su dung
- Backend: `FastAPI`
- LLM/Agent: `LangChain`, `LangGraph`
- LLM: `Google Gemini` (qua `langchain_google_genai`)
- Vector store: `Chroma Cloud`
- Database: `SQL Server` (qua `pyodbc`)

## Cau truc thu muc
- `api/`: router cho chatbot va admin
- `core/agents/`: agent cho thu vien va PDF
- `core/library_assistant_toolbox/`: tool truy van sach, kiem tra tinh trang
- `core/ingestion/`: pipeline doc PDF
- `database/`: ket noi DB va cau hinh LLM
- `static/`: giao dien web test
- `data/pdfs/`: noi luu file PDF upload

## Cai dat
1. **Tao moi truong ao va cai dependency**
```
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. **Cau hinh bien moi truong**
Tao file `.env` tai thu muc goc voi cac bien toi thieu:
```
GEMINI_API_KEY=...
MODEL_EMBEDDING=...
MODEL_PDF_READER=...
MODEL_LIBRARY_ASSISTANT=...

DIALECT=mssql
DB_SERVER=...
DB_PORT=1433
DB_USER=...
DB_PASS=...
DB_NAME=...

CLOUD_NAME=...
CLOUD_KEY=...
CLOUD_SECRET=...
```

3. **Chay server**
```
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Docker cho SQL Server
File `docker-compose.yml` co san de khoi tao SQL Server:
```
docker compose up -d
```
Luu y: can cai `ODBC Driver 18 for SQL Server` de ket noi tu app.

## API nhanh
- `POST /api/library/chat`
```
{
  "message": "Tim sach ve Python",
  "user_id": "user123"
}
```
- `POST /api/pdf/upload` (multipart form-data, field `file`)
- `POST /api/pdf/chat`
```
{
  "filename": "document.pdf",
  "message": "Tom tat noi dung chinh",
  "user_id": "user123"
}
```
- `GET /api/pdf/stats`

## Bat admin API (tuy chon)
Mo comment dong `app.include_router(admin_router)` trong `main.py`, sau do khoi dong lai server.
