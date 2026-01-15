from typing import List, Optional
from pathlib import Path
from pydantic import BaseModel, Field

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from database.connection import pdf_reader_llm
from core.pdf_reader_toolbox.reference_search import ReferenceRetrievalSystem
from core.ingestion.docling_loader import PDFIngestionPipeline

from log.logger_config import setup_logging
logger = setup_logging(__name__)


# --- Data Models for Structured Output ---
class Answer(BaseModel):
    answer: str = Field(description="The answer to the user's question based on the provided context.")

class QueryAnalysis(BaseModel):
    """Phân tích ý định người dùng để chọn chiến lược tìm kiếm."""
    intent: str = Field(description="Ý định: 'summary' (tóm tắt/tổng quan/tiêu đề/tên file), 'section' (tìm mục cụ thể), hoặc 'general' (hỏi đáp thông thường)")
    target_heading: Optional[str] = Field(description="Tên đề mục tiềm năng cần tìm (nếu intent là 'section')")
    refined_query: str = Field(description="Câu truy vấn đã được tối ưu để tìm kiếm vector")


# --- Retriever Instance ---
retriever = ReferenceRetrievalSystem(collection_name="PDF_Reader")


# --- Load System Prompt ---
def _load_prompt() -> str:
    """Load system prompt from file."""
    prompt_path = Path(__file__).parent.parent / "prompts" / "book_reader_prompt.md"
    if prompt_path.exists():
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


class PDFReaderAgent:
    """
    Agent for reading and answering questions about PDFs using Structured RAG.
    """
    
    def __init__(self):
        self.llm = pdf_reader_llm
        self.system_prompt = _load_prompt()
        
        self.structured_llm = self.llm.with_structured_output(Answer)
        
        # PLANNER: Analyzes query intent to choose search strategy
        self.planner = self.llm.with_structured_output(QueryAnalysis)
        
        # Setup Prompt Template
        self.prompt = PromptTemplate(
            template="""
{system_prompt}

## Context Information:
{context}

## Conversation History:
{chat_history}

## User Question:
{question}

## Instructions:
1. Answer the question based ONLY on the provided context.
2. If the context does not contain the answer, say "I cannot find the information in the document."
3. DO NOT use any [ref_x] markers or source references in your answer.
4. Answer in a natural, helpful way.
5. You MUST return a valid JSON object matching the requested schema.
""",
            input_variables=["system_prompt", "context", "chat_history", "question"]
        )
        
        logger.info("✅ PDFReaderAgent (Structured Output Mode) initialized.")
    
    def ask(self, question: str, chat_history: list = None) -> dict:
        """
        Ask a question about the PDF.
        
        Returns:
            dict: {
                "answer": str
            }
        """
        try:
            logger.info(f"❓ PDF Chat Question: {question}")

            # --- STEP 1: QUERY ANALYSIS ---
            # Để Agent tự hiểu ý định thay vì dùng hardcode keywords
            analysis = self.planner.invoke(f"""
            Phân tích câu hỏi của người dùng để xác định chiến lược tìm kiếm RAG tối ưu.
            - 'summary': Các câu hỏi chung về tài liệu (nội dung chính, tóm tắt, tiêu đề, tác giả, ý nghĩa, bài học, chủ đề).
            - 'section': Các câu hỏi về một phần cụ thể (ví dụ: Methodology, Conclusion, Kết quả, Kiến trúc).
            - 'general': Các câu hỏi cụ thể về sự kiện/thông tin bên trong.
            
            Câu hỏi: {question}
            """)
            
            logger.info(f"🧠 Intent: {analysis.intent} | Target: {analysis.target_heading} | Query: {analysis.refined_query}")

            docs = []
            
            # --- STEP 2: EXECUTE SEARCH STRATEGY ---
            
            # Luôn bắt đầu bằng Semantic Search cơ bản (Top 5 trang)
            base_docs = retriever.search(analysis.refined_query, top_k=5, expand_same_page=True)
            docs.extend(base_docs)
            
            # Chiến lược bổ sung dựa trên intent
            if analysis.intent == "summary":
                logger.info("🔍 Strategy: SUMMARY. Fetching Page 1, Last Page and Headings...")
                # Lấy trang 1 và trang cuối làm context tổng quan
                max_p = retriever.get_max_page()
                target_pages = [1]
                if max_p > 1:
                    target_pages.append(max_p)
                
                docs.extend(retriever.get_intro_chunks(pages=target_pages))
                # Tìm thêm các heading quan trọng
                docs.extend(retriever.search(analysis.refined_query, top_k=3, filter={"type": "heading"}))

            elif analysis.intent == "section":
                target = analysis.target_heading or analysis.refined_query
                logger.info(f"🔍 Strategy: SECTION. Finding heading: '{target}'")
                
                heading_candidates = retriever.search(target, top_k=1, filter={"type": "heading"})
                if heading_candidates:
                    best_heading = heading_candidates[0]
                    heading_text = best_heading.page_content
                    logger.info(f"    Found heading: '{heading_text}'. Fetching related content...")
                    
                    section_content = retriever.fetch_by_metadata({"parent_heading": heading_text}, limit=30)
                    docs.append(best_heading)
                    docs.extend(section_content)
            
            # --- STEP 3: DEDUPLICATE CONTEXT ---
            unique_docs = []
            seen_contents = set()
            for d in docs:
                if d.page_content not in seen_contents:
                    unique_docs.append(d)
                    seen_contents.add(d.page_content)
            
            docs = unique_docs
            logger.info(f"📄 Final Context Size: {len(docs)} unique chunks.")
            
            if not docs:
                logger.warning("⚠️ No documents found for the query.")
                return {
                    "answer": "Chưa có tài liệu nào được mở hoặc không tìm thấy thông tin liên quan."
                }
            
            # 2. Format Context
            context_parts = []
            doc_map = {} # Map ref_id to document object
            
            for i, doc in enumerate(docs):
                ref_id = f"ref_{i+1}"
                doc_map[ref_id] = doc
                
                # Extract metadata
                meta = doc.metadata
                page = meta.get("page", "N/A")
                source = meta.get("filename", "Unknown PDF")
                heading = meta.get("parent_heading", "")
                content_type = meta.get("type", "")
                content = doc.page_content
                
                # Construct context block with available metadata
                context_block = f"--- DOCUMENT CHUNK {ref_id} ---\n"
                context_block += f"Source: {source}\n"
                context_block += f"Page: {page}\n"
                if heading:
                    context_block += f"Section: {heading}\n"
                if content_type:
                    context_block += f"Type: {content_type}\n"
                context_block += f"Content:\n{content}\n"
                
                context_parts.append(context_block)
            
            context_str = "\n\n".join(context_parts)
            
            # 3. Generate Answer
            if chat_history is None:
                chat_history = []
            
            history_str = "\n".join([f"{role}: {content}" for role, content in chat_history])
            
            _input = self.prompt.format_prompt(
                system_prompt=self.system_prompt,
                context=context_str,
                chat_history=history_str,
                question=question
            )
            
            parsed_result = self.structured_llm.invoke(_input.to_string())
            
            answer_text = parsed_result.answer

            logger.info(f"🤖 AI Answer: {answer_text[:200]}...") # Log first 200 chars

            return {
                "answer": answer_text
            }

        except Exception as e:
            logger.error(f"❌ Error in PDFReaderAgent.ask: {e}")
            return {
                "answer": f"Đã xảy ra lỗi: {str(e)}"
            }

    
    def load_pdf(self, pdf_path: str) -> bool:
        """Load and index a new PDF file."""
        try:
            # 1. Clear old data
            retriever.clear_collection()
            
            # 2. Parse PDF
            loader = PDFIngestionPipeline()
            docs = loader.process_pdf(pdf_path)
            
            # 3. Index into Chroma
            retriever.index_documents(docs)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error loading PDF: {e}")
            return False
    
    def get_stats(self) -> dict:
        """Get stats about the current PDF."""
        return retriever.get_stats()


# --- Factory function ---
def get_pdf_reader_agent() -> PDFReaderAgent:
    """Return PDFReaderAgent instance."""
    return PDFReaderAgent()


# # --- Test ---
# if __name__ == "__main__":
#     agent = PDFReaderAgent()
    
#     # Test load PDF (optional, comment out if already loaded)
#     # pdf_path = "/home/sinhdang/Documents/Program/Chatbot_ThuVien/2501.17887v1.pdf"
#     # agent.load_pdf(pdf_path)
    
#     print("="*50)
#     print("🧪 Test Structured RAG with History:")
#     print("="*50)
    
#     chat_history = []
    
#     questions = [
#         "Docling là gì?",
#         "Nó có hỗ trợ OCR không?",
#     ]
    
#     for q in questions:
#         print(f"\n❓ {q}")
#         result = agent.ask(q, chat_history=chat_history)
#         print(f"💬 Answer: {result['answer']}")
            
#         # Update history
#         chat_history.append(("human", q))
#         chat_history.append(("ai", result['answer']))
