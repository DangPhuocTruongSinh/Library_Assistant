import os
from pathlib import Path
from typing import Optional, Dict, Any

from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate

from database.connection import library_assistant_llm
from core.library_assistant_toolbox import library_tools

from log.logger_config import setup_logging
logger = setup_logging(__name__)


# --- Load System Prompt ---
def _load_prompt() -> str:
    """Load system prompt từ file."""
    prompt_path = Path(__file__).parent.parent / "prompts" / "library_agent_system_prompt.md"
    if prompt_path.exists():
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()

# --- ReAct Prompt Template ---
REACT_PROMPT = PromptTemplate.from_template("""
{system_prompt}

## Thông tin người dùng:
{user_info}

## Lịch sử hội thoại (Context):
{chat_history}

## Công cụ có sẵn:
{tools}

## Tên công cụ:
{tool_names}

## Quy tắc QUAN TRỌNG:
1. Khi người dùng hỏi tìm sách → dùng tool `book_search_tool` với từ khóa ngắn gọn (Ví dụ: "Lập trình Python").
2. Khi người dùng hỏi tình trạng sách (còn/hết) → dùng tool `sql_check_book_status` (BẮT BUỘC phải có ISBN).
3. Nếu chưa có ISBN, hãy tìm sách trước bằng `book_search_tool` để lấy ISBN, sau đó mới kiểm tra tình trạng.
4. Trả lời bằng tiếng Việt, xưng "em", gọi người dùng "anh/chị".
5. Khi đã có kết quả từ tool, hãy dừng suy nghĩ và đưa ra câu trả lời cuối cùng ngay lập tức. KHÔNG lặp lại việc gọi tool nếu đã có kết quả.

## Format BẮT BUỘC (Hãy tuân thủ chính xác):
Question: câu hỏi của người dùng
Thought: suy nghĩ về bước tiếp theo (tìm sách hay kiểm tra tình trạng?)
Action: tên tool cần dùng (chỉ 1 trong 2: book_search_tool, sql_check_book_status)
Action Input: input cho tool (ví dụ: "Lập trình Python" hoặc {{"isbn": "ISBN..."}})
Observation: kết quả trả về từ tool
... (lặp lại Thought/Action/Observation tối đa 3 lần)
Thought: Tôi đã có đủ thông tin.
Final Answer: câu trả lời cuối cùng gửi đến người dùng (tổng hợp thông tin tìm được).

## Bắt đầu:
Question: {input}
Thought: {agent_scratchpad}
""")


class LibraryAgent:
    """
    Agent hỗ trợ thư viện.
    Sử dụng LangChain ReAct Agent.
    """
    
    def __init__(self, user_info: Optional[Dict[str, Any]] = None):
        """
        Khởi tạo Library Agent.
        
        Args:
            user_info: Thông tin người dùng (nếu đã đăng nhập)
        """
        self.llm = library_assistant_llm
        self.tools = library_tools
        self.system_prompt = _load_prompt()
        self.user_info = user_info or {}
        
        # Tạo ReAct Agent
        self.agent = create_react_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=REACT_PROMPT.partial(system_prompt=self.system_prompt, user_info=self.user_info)
        )
        
        # Tạo AgentExecutor
        self.executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=5
        )
        
        logger.info("✅ LibraryAgent đã khởi tạo.")
    
    def ask(self, question: str, chat_history: list = None, summary: str = "") -> str:
        """
        Hỏi agent về sách trong thư viện.

        Args:
            question: Câu hỏi của user (đã được chuẩn hóa bởi ConversationManager).
            chat_history: Danh sách các turn gần nhất dạng [(role, content), ...].
            summary: Tóm tắt short-term từ ConversationManager (nếu lịch sử đã được nén).
                     Sẽ được ghép trước các turn gần nhất để cung cấp ngữ cảnh đầy đủ.

        Returns:
            Câu trả lời từ agent.
        """
        if chat_history is None:
            chat_history = []

        # Build history string: prepend summary (if any) before recent turns.
        recent_turns = "\n".join(f"{role}: {content}" for role, content in chat_history)
        if summary:
            history_str = f"[TÓM TẮT HỘI THOẠI TRƯỚC]: {summary}\n\n[CÁC LƯỢT GẦN ĐÂY]:\n{recent_turns}"
        else:
            history_str = recent_turns

        logger.info(f"📝 Lịch sử hội thoại: {history_str}")
        try:
            result = self.executor.invoke({
                "input": question, 
                "chat_history": history_str})
            return result.get("output", "Dạ em không thể trả lời câu hỏi này ạ.")
        except Exception as e:
            logger.error(f"Lỗi khi xử lý câu hỏi: {e}")
            return f"Dạ em xin lỗi, đã xảy ra lỗi: {e}"
    
    def set_user_info(self, user_info: Dict[str, Any]):
        """Cập nhật thông tin người dùng."""
        self.user_info = user_info


# --- Factory function ---
def get_library_agent(user_info: Optional[Dict[str, Any]] = None) -> LibraryAgent:
    """Trả về instance của LibraryAgent."""
    return LibraryAgent(user_info=user_info)


# # --- Test ---
# if __name__ == "__main__":
#     agent = LibraryAgent()
    
#     print("="*50)
#     print("🧪 Test Library Agent:")
#     print("="*50)
    
#     questions = [
#         "Tìm sách về Python",
#         "Sách Nhà Giả Kim còn không?",
#     ]
    
#     for q in questions:
#         print(f"\n❓ {q}")
#         answer = agent.ask(q)
#         print(f"💬 {answer}")

