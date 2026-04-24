"""
LibraryConversationManager

Manages the conversation pipeline for Library Chat:
- Query validation: decide if query is relevant, ambiguous, or clear.
- Suggestion generation: produce follow-up questions after each answer.
- History summarization: compress long conversations into short/long-term memory.
"""

import re
from pathlib import Path

from jinja2 import Template
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage


from log.logger_config import setup_logging

logger = setup_logging(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Static context describing what the library assistant covers.
# Used as the knowledge base when validating query relevance.
_LIBRARY_DOMAIN_CONTEXT = (
    "Hệ thống thư viện hỗ trợ: tra cứu sách theo tên, tác giả, thể loại, chủ đề, ISBN; "
    "kiểm tra tình trạng mượn/trả sách; gợi ý sách phù hợp; "
    "thông tin về vị trí ngăn tủ; thông tin thể loại và ngôn ngữ sách."
)


def _load_template(filename: str) -> Template:
    """
    Load a Jinja2 template from the prompts directory.

    Args:
        filename: Template filename (e.g. 'validate_query.jinja').

    Returns:
        Compiled Jinja2 Template.
    """
    path = _PROMPTS_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return Template(f.read())


class LibraryConversationManager:
    """
    Manages conversation-level logic for Library Chat.

    Responsibilities:
    - validate_query: classify query as VALID / IRRELEVANT / SUGGESTION.
    - generate_suggestions: generate 4 follow-up questions after agent answers.
    - summarize_history: compress turns into short-term + long-term memory.
    """

    # Summarize when stored turns exceed this item count (each turn = 1 item).
    SUMMARY_THRESHOLD = 10
    # Number of most-recent turns to keep after summarization.
    KEEP_RECENT_TURNS = 4

    def __init__(self, llm: BaseChatModel):
        """
        Args:
            llm: Gemini LLM instance (shared with LibraryAgent).
        """
        self.llm = llm
        self._validate_tmpl = _load_template("validate_query.jinja")
        self._suggestion_tmpl = _load_template("suggestion.jinja")
        self._summary_tmpl = _load_template("summary.jinja")
        logger.info("✅ LibraryConversationManager initialized.")

    # -------------------------------------------------------------------------
    # Query Validation
    # -------------------------------------------------------------------------

    def validate_query(self, user_query: str, extra_context: str = "") -> dict:
        """
        Validate user query against the library domain.

        Combines the static library domain description with an optional extra
        context (e.g. recent summary) and calls the validate_query prompt.

        Args:
            user_query: Raw message from the user.
            extra_context: Optional text to append to the domain context
                           (e.g. short-term memory summary).

        Returns:
            dict with:
                - "type": "VALID" | "IRRELEVANT" | "SUGGESTION"
                - "content":
                    VALID      → comma-separated keywords extracted from the query.
                    IRRELEVANT → short reason why query is out of scope.
                    SUGGESTION → pipe-separated clarification questions.
        """
        context = _LIBRARY_DOMAIN_CONTEXT
        if extra_context:
            context += f"\n\nNgữ cảnh hội thoại gần đây:\n{extra_context}"

        prompt = self._validate_tmpl.render(contents=context, user_query=user_query)

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            raw = response.content.strip()
            logger.info(f"🔍 validate_query → {raw}")

            if raw.startswith("IRRELEVANT:"):
                return {"type": "IRRELEVANT", "content": raw[len("IRRELEVANT:"):].strip()}
            if raw.startswith("SUGGESTION:"):
                return {"type": "SUGGESTION", "content": raw[len("SUGGESTION:"):].strip()}
            if raw.startswith("VALID:"):
                return {"type": "VALID", "content": raw[len("VALID:"):].strip()}

            # Unexpected format — treat as valid to avoid blocking the user.
            logger.warning(f"⚠️ Unexpected validate_query format, falling back to VALID: {raw}")
            return {"type": "VALID", "content": user_query}

        except Exception as e:
            logger.error(f"❌ validate_query error: {e}")
            return {"type": "VALID", "content": user_query}

    # -------------------------------------------------------------------------
    # Suggestion Generation
    # -------------------------------------------------------------------------

    def generate_suggestions(self, answer: str, user_query: str) -> list[str]:
        """
        Generate 4 follow-up suggestion questions based on the agent's answer.

        The answer serves as the knowledge context; the user_query provides the
        current focus so suggestions stay on topic.

        Args:
            answer: Agent's response text.
            user_query: Original question from the user.

        Returns:
            List of up to 4 suggestion question strings (Vietnamese).
            Returns empty list on failure.
        """
        prompt = self._suggestion_tmpl.render(contents=answer, user_query=user_query)

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            raw = response.content.strip()
            logger.info(f"💡 generate_suggestions → {raw}")

            suggestions = []
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                match = re.match(r"^\d+\.\s+(.+)$", line)
                suggestions.append(match.group(1).strip() if match else line)

            return suggestions[:4]

        except Exception as e:
            logger.error(f"❌ generate_suggestions error: {e}")
            return []

    # -------------------------------------------------------------------------
    # History Summarization
    # -------------------------------------------------------------------------

    def should_summarize(self, turns: list) -> bool:
        """
        Returns True when the turn list is long enough to warrant summarization.

        Args:
            turns: List of (role, content) tuples.
        """
        return len(turns) > self.SUMMARY_THRESHOLD

    def summarize_history(self, turns: list) -> dict:
        """
        Compress conversation turns into short-term and long-term memory strings.

        Short-term memory captures the recent goal, constraints, and key facts
        for immediate continuity. Long-term memory captures stable user preferences
        or profile information.

        Args:
            turns: Full list of (role, content) tuples.

        Returns:
            dict with:
                - "short_term": 3-5 sentence summary of recent context.
                - "long_term": Pipe-separated bullet points of stable user info,
                               or "NONE" if nothing stable was found.
        """
        history_str = "\n".join(f"{role}: {content}" for role, content in turns)
        prompt = self._summary_tmpl.render(contents=history_str, user_query="")

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            raw = response.content.strip()
            logger.info(f"📝 summarize_history → {raw}")

            short_term = ""
            long_term = "NONE"
            for line in raw.splitlines():
                line = line.strip()
                if line.startswith("SHORT_TERM:"):
                    short_term = line[len("SHORT_TERM:"):].strip()
                elif line.startswith("LONG_TERM:"):
                    long_term = line[len("LONG_TERM:"):].strip()

            return {"short_term": short_term, "long_term": long_term}

        except Exception as e:
            logger.error(f"❌ summarize_history error: {e}")
            return {"short_term": "", "long_term": "NONE"}
