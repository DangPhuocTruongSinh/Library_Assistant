import os
from dotenv import load_dotenv
from sqlalchemy import create_engine

from langchain_ollama import ChatOllama
from langchain_community.embeddings import HuggingFaceEmbeddings
from chromadb import CloudClient as Client
from chromadb import Documents, Embeddings, EmbeddingFunction

from log.logger_config import setup_logging

logger = setup_logging(__name__)

load_dotenv()

# ---------------------------------------------------------------------------
# Ollama settings
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL         = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL_LIBRARY_ASSISTANT = os.getenv("MODEL_LIBRARY_ASSISTANT", "qwen3:8b")
MODEL_PDF_READER        = os.getenv("MODEL_PDF_READER", "qwen3:8b")

# ---------------------------------------------------------------------------
# BGE embedding settings
# BAAI/bge-m3 is multilingual and well-suited for Vietnamese text.
# ---------------------------------------------------------------------------
MODEL_EMBEDDING = os.getenv("MODEL_EMBEDDING", "BAAI/bge-m3")

# ---------------------------------------------------------------------------
# Database connection settings
# ---------------------------------------------------------------------------
DIALECT   = os.getenv("DIALECT")
DB_SERVER = os.getenv("DB_SERVER")
DB_PORT   = int(os.getenv("DB_PORT"))
DB_USER   = os.getenv("DB_USER")
DB_PASS   = os.getenv("DB_PASS")
DBNAME    = os.getenv("DB_NAME")


# ---------------------------------------------------------------------------
# SQL Server engine
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Embedding model (BGE-M3 via HuggingFace / sentence-transformers)
# normalize_embeddings=True is required for correct cosine similarity with BGE.
# ---------------------------------------------------------------------------

import torch
_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
logger.info(f"🖥️ Embedding device: {_DEVICE}")

embedding_model = HuggingFaceEmbeddings(
    model_name=MODEL_EMBEDDING,
    model_kwargs={"device": _DEVICE},
    encode_kwargs={"normalize_embeddings": True},
)


class LangchainEmbeddingFunction(EmbeddingFunction):
    """
    Adapter wrapping a LangChain embedding model for use with ChromaDB collections.

    ChromaDB requires an EmbeddingFunction with a name() method and a
    __call__ that accepts a list of strings and returns a list of float vectors.
    """

    def __init__(self, langchain_embedding_model: HuggingFaceEmbeddings):
        """
        Args:
            langchain_embedding_model: Initialized HuggingFaceEmbeddings instance.
        """
        self._model = langchain_embedding_model
        self._name = MODEL_EMBEDDING

    def name(self) -> str:
        return self._name

    def __call__(self, texts: Documents) -> Embeddings:
        return self._model.embed_documents(texts)


# ---------------------------------------------------------------------------
# LLM factories
# ---------------------------------------------------------------------------

def get_library_assistant_llm() -> ChatOllama:
    """
    Returns a ChatOllama instance for the Library Assistant agent.

    temperature=0 keeps tool-use and ReAct reasoning deterministic.
    """
    return ChatOllama(
        model=MODEL_LIBRARY_ASSISTANT,
        base_url=OLLAMA_BASE_URL,
        temperature=0,
    )


def get_pdf_reader_llm() -> ChatOllama:
    """
    Returns a ChatOllama instance for the PDF Reader agent.

    temperature=0.3 allows slightly more natural answers for reading comprehension.
    """
    return ChatOllama(
        model=MODEL_PDF_READER,
        base_url=OLLAMA_BASE_URL,
        temperature=0.3,
    )


# Singleton instances shared across the application.
library_assistant_llm = get_library_assistant_llm()
pdf_reader_llm = get_pdf_reader_llm()

# ---------------------------------------------------------------------------
# Chroma Cloud client
# ---------------------------------------------------------------------------

try:
    chroma_client = Client(
        api_key="ck-GKDFH1baFNx6mypKH7syPhtxFXvDHyvgBaKescbDfDTk",
        tenant="b7614964-1d3d-4bed-b402-69bfe2f4e618",
        database="QLTV"
    )
    chroma_client.heartbeat()
except Exception as e:
    logger.error(f"❌ Lỗi khi kết nối Chroma Cloud: {e}")
    chroma_client = None
