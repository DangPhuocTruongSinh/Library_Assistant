import json
import sys
from typing import List
from pathlib import Path

# Đảm bảo project root trong sys.path
project_root = Path.cwd()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from langchain_core.documents import Document
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice
from docling.datamodel.document import DoclingDocument, SectionHeaderItem, TableItem, TextItem, PictureItem
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

# Custom Backend that bypasses validation checks for PyPdfium2
# Giải quyết lỗi "Input document ... is not valid" với các file PDF lớn hoặc có cấu trúc lạ
class ForcedPyPdfiumDocumentBackend(PyPdfiumDocumentBackend):
    def is_valid(self) -> bool:
        return True

from log.logger_config import setup_logging
logger = setup_logging(__name__)

class PDFIngestionPipeline:
    """
    Pipeline xử lý PDF sử dụng Docling để trích xuất văn bản kèm metadata chi tiết 
    (số trang, tọa độ bbox, loại nội dung) phục vụ cho tính năng RAG.
    """
    
    def __init__(self):
        # Khởi tạo converter của Docling
        # Cấu hình pipeline options để sửa lỗi "page-dimensions" với PDF tiếng Việt
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        
        # Sử dụng CPU để đảm bảo ổn định, tránh lỗi CUDA nếu có
        pipeline_options.accelerator_options = AcceleratorOptions(num_threads=4, device=AcceleratorDevice.CUDA)

        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options,
                    backend=ForcedPyPdfiumDocumentBackend
                )
            }
        )

    def _get_bbox_list(self, item) -> List[List[float]]:
        """
        Trích xuất danh sách các bounding box từ item.
        Xử lý trường hợp item nằm trên nhiều dòng hoặc nhiều trang.
        """
        bboxes = []
        if not item.prov:
            return []
            
        # Chuẩn hóa thành list để xử lý đồng nhất
        provs = item.prov
        
        for p in provs:
            if p.bbox:
                # Docling bbox: [left, top, right, bottom]
                bboxes.append(p.bbox.as_tuple())
        return bboxes

    def process_pdf(self, file_path: str, max_pages: int = None) -> List[Document]:
        """
        Xử lý một file PDF và trả về danh sách các LangChain Documents.
        
        Args:
            file_path (str): Đường dẫn đến file PDF.
            max_pages (int, optional): Giới hạn số trang cần xử lý. 
                                       Mặc định None = xử lý toàn bộ sách.
            
        Returns:
            List[Document]: Danh sách các document với metadata phong phú.
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(f"File not found: {file_path}")
            return []

        # 1. Convert PDF sang cấu trúc Docling
        if max_pages:
            logger.info(f"Đang xử lý file PDF với Docling: {file_path} (Giới hạn: {max_pages} trang)...")
        else:
            logger.info(f"Đang xử lý file PDF với Docling: {file_path} (Toàn bộ sách)...")
        
        # Cấu hình convert
        # raises_on_error=False: Bỏ qua các trang lỗi thay vì dừng toàn bộ quá trình
        convert_kwargs = {"raises_on_error": False}
        
        # Chỉ thêm page_range nếu có giới hạn số trang
        if max_pages:
            convert_kwargs["page_range"] = (1, max_pages)
        
        conversion_result = self.converter.convert(path, **convert_kwargs)
        doc: DoclingDocument = conversion_result.document
        
        langchain_docs = []
        
        # Theo dõi context hiện tại (Tiêu đề gần nhất)
        current_heading = "N/A"
        
        # 2. Duyệt qua các element và gom nhóm (Grouping Strategy)
        # Thay vì index từng dòng lẻ tẻ, ta gom các đoạn văn bản lại để giảm số lượng chunk
        # và tăng chất lượng ngữ nghĩa.
        for item, level in doc.iterate_items():
            content = ""
            item_type = "text"
            
            if isinstance(item, SectionHeaderItem):
                content = item.text.strip()
                item_type = "heading"
                current_heading = content 
                
            elif isinstance(item, TableItem):
                content = item.export_to_markdown(doc=doc)
                item_type = "table"
                
            elif isinstance(item, TextItem):
                content = item.text.strip()
                item_type = "text"
            
            elif hasattr(item, 'text'):
                content = item.text.strip()
            
            if not content:
                continue

            # Trích xuất Metadata
            page_no = 1
            if item.prov:
                prov_entry = item.prov[0] if isinstance(item.prov, list) else item.prov
                page_no = prov_entry.page_no

            # Gom nhóm: Nếu item hiện tại cùng loại 'text', cùng trang và cùng heading với item trước đó
            # thì ta nối nội dung lại thay vì tạo chunk mới.
            if (langchain_docs and 
                item_type == "text" and 
                langchain_docs[-1].metadata["type"] == "text" and
                langchain_docs[-1].metadata["page"] == page_no and
                langchain_docs[-1].metadata["parent_heading"] == current_heading and
                len(langchain_docs[-1].page_content) < 1000): # Giới hạn size mỗi chunk khoảng 1000 ký tự
                
                # Cập nhật nội dung
                langchain_docs[-1].page_content += "\n" + content
                # Cập nhật bboxes (nối thêm các tọa độ mới)
                existing_bboxes = json.loads(langchain_docs[-1].metadata["bboxes"])
                new_bboxes = self._get_bbox_list(item)
                langchain_docs[-1].metadata["bboxes"] = json.dumps(existing_bboxes + new_bboxes)
            else:
                # Tạo Document mới
                metadata = {
                    "source": str(path),
                    "filename": path.name,
                    "page": page_no,
                    "bboxes": json.dumps(self._get_bbox_list(item)),
                    "type": item_type,
                    "parent_heading": current_heading
                }
                langchain_docs.append(Document(page_content=content, metadata=metadata))

        logger.info(f"Đã trích xuất và tối ưu thành {len(langchain_docs)} chunks dữ liệu từ {path.name}.")
        return langchain_docs

# Helper function để test nhanh
if __name__ == "__main__":
    import json
    
    # Xác định đường dẫn file PDF để test
    # Mặc định tìm file 2501.17887v1.pdf ở thư mục gốc dự án
    project_root = Path(__file__).resolve().parent.parent.parent
    default_pdf = project_root / "Test" / "Machine_Learning.pdf"
    
    if len(sys.argv) > 1:
        input_pdf = sys.argv[1]
    elif default_pdf.exists():
        input_pdf = str(default_pdf)
    else:
        print("Vui lòng cung cấp đường dẫn file PDF hoặc đặt file 'Machine_Learning.pdf' vào thư mục Test.")
        sys.exit(1)

    logger.info(f"--- Bắt đầu test với file: {input_pdf} ---")
    
    try:
        pipeline = PDFIngestionPipeline()
        docs = pipeline.process_pdf(input_pdf)
        
        logger.info(f"\n✅ Xử lý thành công! Tổng số chunk: {len(docs)}")
        
        # In chi tiết 3 chunk đầu tiên để kiểm tra
        print("\n--- Chi tiết 3 chunk đầu tiên ---")
        for i, d in enumerate(docs[:3]):
            print(f"\n[Chunk {i}]")
            print(f"Type: {d.metadata.get('type')}")
            print(f"Parent Heading: {d.metadata.get('parent_heading')}")
            print(f"Page: {d.metadata.get('page')}")
            # Chỉ in số lượng bbox để gọn
            bboxes = d.metadata.get('bboxes', [])
            print(f"BBoxes count: {len(bboxes)}")
            content_preview = d.page_content[:150].replace('\n', ' ')
            print(f"Content preview: {content_preview}...")
            
        # In thử metadata dạng JSON của chunk đầu tiên
        if docs:
            print("\n--- Metadata Sample (JSON) ---")
            print(json.dumps(docs[0].metadata, indent=2, ensure_ascii=False))
            
    except Exception as e:
        logger.error(f"\n❌ Có lỗi xảy ra: {e}")
        import traceback
        traceback.print_exc()
