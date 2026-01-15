from core.tools.book_search_tool import book_search_tool
from core.tools.sql_check_book_status_tool import sql_check_book_status_tool
from core.tools.pdf_reader_tool import pdf_reader_tool

# Tools cho Library Agent
library_tools = [
    book_search_tool,
    sql_check_book_status_tool,
]

# Tool cho PDF Reader Agent  
pdf_reader_tools = [
    pdf_reader_tool,
]

__all__ = [
    "library_tools",
    "pdf_reader_tools",
]
