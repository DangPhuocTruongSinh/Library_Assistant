from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from chromadb import CloudClient as Client
from chromadb import Documents, Embeddings, EmbeddingFunction # Giữ lại vì đây là của ChromaDB

from log.logger_config import setup_logging
logger = setup_logging(__name__)


load_dotenv()

# Chatbot model settings
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY")
MODEL_EMBEDDING  = os.getenv("MODEL_EMBEDDING")
MODEL_PDF_READER = os.getenv("MODEL_PDF_READER")
MODEL_LIBRARY_ASSISTANT = os.getenv("MODEL_LIBRARY_ASSISTANT")


# Database connection settings from environment variables
DIALECT     = os.getenv("DIALECT")
DB_SERVER   = os.getenv("DB_SERVER")
DB_PORT     = int(os.getenv("DB_PORT"))
DB_USER     = os.getenv("DB_USER")
DB_PASS     = os.getenv("DB_PASS")
DBNAME      = os.getenv("DB_NAME")


# Cloudinary settings
CLOUD_NAME     =os.getenv("CLOUD_NAME")
CLOUD_KEY      =os.getenv("CLOUD_KEY")
CLOUD_SECRET   =os.getenv("CLOUD_SECRET")
CLOUDINARY_URL =f"cloudinary://{CLOUD_KEY}:{CLOUD_SECRET}@{CLOUD_NAME}"

def create_db_engine():
    try:
        conn_str = (
            f"mssql+pyodbc://{DB_USER}:{DB_PASS}@{DB_SERVER}:{DB_PORT}/{DBNAME}"
            "?driver=ODBC+Driver+18+for+SQL+Server"
            "&Encrypt=yes"
            "&TrustServerCertificate=yes"
            "&CipherSuite=DEFAULT@SECLEVEL=1"
            "&LoginTimeout=10"
        )
        return create_engine(conn_str, pool_pre_ping=True, pool_size=10, max_overflow=20)
    except Exception as e:
        logger.error(f"Lỗi khi tạo Engine: {e}")
        return None

engine = create_db_engine()

def get_db_connection():
    try:
        if engine:
            return engine.connect()
        return None
    except Exception as e:
        logger.error(f"Lỗi khi kết nối DB: {e}")
        return None

class LangchainEmbeddingFunction(EmbeddingFunction):
    def __init__(self, langchain_embedding_model: GoogleGenerativeAIEmbeddings):
        self._model = langchain_embedding_model
        self._name = os.getenv("MODEL_EMBEDDING", "gemini-embedding-001")
    # ChromaDB yêu cầu method name() để khởi tạo collection
    def name(self) -> str:
        return self._name

    def __call__(self, texts: Documents) -> Embeddings:
        return self._model.embed_documents(texts)

embedding_model = GoogleGenerativeAIEmbeddings(
    model=MODEL_EMBEDDING,
    google_api_key=GEMINI_API_KEY,
    task_type="retrieval_document"
)

def get_library_assistant_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=MODEL_LIBRARY_ASSISTANT,
        temperature=0,
        max_retries=2,
        google_api_key=GEMINI_API_KEY
    )

def get_pdf_reader_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=MODEL_PDF_READER,
        temperature=1,
        max_retries=2,
        google_api_key=GEMINI_API_KEY
    )

# Khởi tạo các đối tượng
library_assistant_llm = get_library_assistant_llm()
pdf_reader_llm = get_pdf_reader_llm()
# db_connection = get_db_connection() # REMOVED: Do not use global connection object

try:
        chroma_client = Client(
            api_key="ck-GKDFH1baFNx6mypKH7syPhtxFXvDHyvgBaKescbDfDTk",
            tenant="b7614964-1d3d-4bed-b402-69bfe2f4e618",
            database="QLTV"
        )
        chroma_client.heartbeat() # Gửi 1 tín hiệu ping
        
except Exception as e:
    logger.error(f"❌ Lỗi khi kết nối Chroma Cloud: {e}")
    chroma_client = None

# if __name__ == "__main__":
#     ... (commented out code)