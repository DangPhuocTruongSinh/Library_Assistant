import uuid
from typing import List, Dict, Any

from langchain_core.documents import Document

from database.connection import (
    chroma_client, 
    embedding_model, 
    LangchainEmbeddingFunction
)

from log.logger_config import setup_logging
logger = setup_logging(__name__)

class ReferenceRetrievalSystem:
    """
    Hệ thống tìm kiếm sử dụng:
    1. Chroma Cloud cho Vector Search (persistent, scalable)
    2. Same-Page Context Expansion (lấy TẤT CẢ chunks cùng trang với kết quả)
    
    Không mở rộng sang trang khác để tránh chiếm dụng context window
    với nội dung không liên quan.
    """
    
    def __init__(self, collection_name: str = "PDF_Reader"):
        """
        Khởi tạo hệ thống tìm kiếm.
        
        Args:
            collection_name: Tên collection trong Chroma Cloud.
                            Mỗi phiên đọc sách có thể dùng collection riêng.
        """
        self.collection_name = collection_name
        self.client = chroma_client
        self.embedding_func = LangchainEmbeddingFunction(embedding_model)
        self.collection = None
        
        self._init_collection()

    def _init_collection(self):
        """Khởi tạo collection - giữ lại dữ liệu nếu đã tồn tại."""
        try:
            # Thử lấy collection đã tồn tại (không truyền embedding_function để tránh conflict)
            self.collection = self.client.get_collection(
                name=self.collection_name,
                embedding_function=self.embedding_func
            )
            logger.info(f"✅ Đã kết nối collection '{self.collection_name}' (đã tồn tại).")
        except Exception:
            # Chưa tồn tại → tạo mới
            self.collection = self.client.create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_func
            )
            logger.info(f"✅ Đã tạo collection mới '{self.collection_name}'.")

    def clear_collection(self):
        """
        Xóa toàn bộ dữ liệu trong collection (dùng khi user mở sách mới).
        """
        if self.collection:
            try:
                self.client.delete_collection(name=self.collection_name)
                self._init_collection()
                logger.info(f"🗑️ Đã xóa và tạo lại collection '{self.collection_name}'.")
            except Exception as e:
                logger.error(f"⚠️ Lỗi khi xóa collection: {e}")

    def index_documents(self, documents: List[Document], batch_size: int = 100):
        """
        Index danh sách tài liệu vào Chroma Cloud sử dụng Multi-threading để tối ưu tốc độ.
        """
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed

        total = len(documents)
        total_batches = (total + batch_size - 1) // batch_size
        logger.info(f"🚀 Bắt đầu Multi-threaded Indexing: {total} chunks, {total_batches} batches...")

        # Chia documents thành các batch
        batches = []
        for i in range(0, total, batch_size):
            batches.append(documents[i : i + batch_size])

        def process_batch(batch_idx, batch_data):
            current_batch = batch_idx + 1
            ids = [str(uuid.uuid4()) for _ in range(len(batch_data))]
            docs = [doc.page_content for doc in batch_data]
            metadatas = [doc.metadata for doc in batch_data]
            
            max_retries = 3
            retry_count = 0
            backoff_time = 15 # Tăng base backoff lên một chút cho multi-threading

            while retry_count <= max_retries:
                try:
                    self.collection.upsert(
                        ids=ids,
                        documents=docs,
                        metadatas=metadatas
                    )
                    return f"✅ Batch {current_batch} OK"
                except Exception as e:
                    error_msg = str(e).lower()
                    if "429" in error_msg or "quota" in error_msg or "limit" in error_msg:
                        retry_count += 1
                        if retry_count > max_retries:
                            return f"❌ Batch {current_batch} FAILED after {max_retries} retries"
                        
                        wait_time = backoff_time * (2 ** (retry_count - 1))
                        logger.warning(f"❄️ Thread-Batch {current_batch}: Rate limit. Retry in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        return f"❌ Batch {current_batch} ERROR: {e}"

        # Thực thi multi-threading
        failed_results = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_to_batch = {executor.submit(process_batch, i, batch): i for i, batch in enumerate(batches)}
            
            for future in as_completed(future_to_batch):
                try:
                    result = future.result()
                    if "OK" in result:
                        logger.info(result)
                    else:
                        logger.error(result)
                        failed_results.append(result)
                except Exception as e:
                    logger.error(f"❌ Critical error in thread: {e}")
                    failed_results.append(str(e))

        if failed_results:
            error_summary = "; ".join(failed_results[:3])
            raise Exception(f"Indexing incomplete. {len(failed_results)} batches failed. Details: {error_summary}")

        logger.info(f"🎉 Hoàn tất Indexing! Tổng: {self.collection.count()} chunks.")

    def search(
        self,
        query: str,
        top_k: int = 5,
        expand_same_page: bool = True,
        filter: Dict[str, Any] = None
    ) -> List[Document]:
        """
        Tìm kiếm với Context Expansion (chỉ lấy chunks cùng trang).
        
        Args:
            query: Câu hỏi của user.
            top_k: Số chunks ban đầu cần tìm.
            expand_same_page: Nếu True, lấy thêm tất cả chunks cùng trang với kết quả.
                              Nếu False, chỉ trả về top_k chunks.
            filter: Dictionary filter cho ChromaDB (vd: {"type": "heading"}).
        
        Returns:
            Danh sách Documents đã được mở rộng context (cùng trang).
        """
        # 1. Vector Search - Tìm Top-K chunks
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=filter,  # Apply filter if provided
                include=["documents", "metadatas", "distances"]
            )
        except Exception as e:
            logger.error(f"❌ Lỗi khi search: {e}")
            return []
        
        # 2. Convert kết quả thành LangChain Documents
        if not results or not results.get("ids") or not results["ids"][0]:
            return []
            
        initial_docs = []
        for i in range(len(results["ids"][0])):
            doc = Document(
                page_content=results["documents"][0][i],
                metadata=results["metadatas"][0][i]
            )
            initial_docs.append(doc)
        
        # 3. Context Expansion - Chỉ lấy chunks cùng trang
        if expand_same_page:
            expanded_docs = self._expand_same_page(initial_docs)
            return expanded_docs
        
        return initial_docs

    def _expand_same_page(self, chunks: List[Document]) -> List[Document]:
        """
        Mở rộng context bằng cách lấy TẤT CẢ chunks cùng trang với kết quả tìm được.
        
        Không lấy chunks từ trang khác để tránh chiếm dụng context window
        với nội dung không liên quan.
        
        Args:
            chunks: Danh sách chunks ban đầu từ vector search.
        
        Returns:
            Danh sách Documents đã mở rộng (cùng trang), sắp xếp theo thứ tự.
        """
        # Thu thập các trang cần lấy (chỉ các trang có trong kết quả)
        pages_to_fetch = set()
        for doc in chunks:
            page = doc.metadata.get("page", 1)
            pages_to_fetch.add(page)
        
        # Query tất cả chunks thuộc các trang này
        expanded_docs = []
        seen_contents = set()  # Tránh duplicate
        
        for page in sorted(pages_to_fetch):
            where_filter = {"page": page}

            try:
                page_results = self.collection.get(
                    where=where_filter,
                    include=["documents", "metadatas"]
                )
                
                if page_results and page_results.get("ids"):
                    for i in range(len(page_results["ids"])):
                        content = page_results["documents"][i]
                        # Tránh duplicate
                        if content not in seen_contents:
                            seen_contents.add(content)
                            expanded_docs.append(Document(
                                page_content=content,
                                metadata=page_results["metadatas"][i]
                            ))
            except Exception as e:
                logger.error(f"⚠️ Lỗi khi lấy chunks trang {page}: {e}")
        
        # Sắp xếp theo số trang để context liền mạch
        expanded_docs.sort(key=lambda d: (d.metadata.get("page", 0), d.page_content[:50]))
        
        logger.info(f"📖 Same-Page Expansion: {len(chunks)} chunks → {len(expanded_docs)} chunks (pages: {sorted(pages_to_fetch)})")
        
        return expanded_docs

    def get_max_page(self) -> int:
        """Lấy số trang lớn nhất trong tài liệu."""
        try:
            # Lấy 1 bản ghi duy nhất, sắp xếp theo page giảm dần
            # Vì Chroma không hỗ trợ order_by trực tiếp trong query, ta lấy hết page rồi tìm max
            # Hoặc đơn giản là query với limit lớn và lấy max page từ metadata
            results = self.collection.get(include=["metadatas"])
            if results and results.get("metadatas"):
                pages = [m.get("page", 0) for m in results["metadatas"]]
                return max(pages) if pages else 1
            return 1
        except Exception as e:
            logger.error(f"⚠️ Không thể lấy max page: {e}")
            return 1

    def get_intro_chunks(self, pages: List[int] = [1]) -> List[Document]:
        """
        Lấy các chunks thuộc các trang đầu để làm context cho câu hỏi tóm tắt.
        Mặc định chỉ lấy trang 1.
        """
        return self.fetch_by_metadata({"page": {"$in": pages}} if len(pages) > 1 else {"page": pages[0]})

    def fetch_by_metadata(self, where_filter: Dict[str, Any], limit: int = 20) -> List[Document]:
        """
        Lấy chunks dựa trên filter metadata chính xác (không dùng vector search).
        """
        fetched_docs = []
        seen_contents = set()
        
        try:
            results = self.collection.get(
                where=where_filter,
                include=["documents", "metadatas"],
                limit=limit
            )
            
            if results and results.get("ids"):
                for i in range(len(results["ids"])):
                    content = results["documents"][i]
                    if content not in seen_contents:
                        seen_contents.add(content)
                        fetched_docs.append(Document(
                            page_content=content,
                            metadata=results["metadatas"][i]
                        ))
        except Exception as e:
            logger.error(f"⚠️ Lỗi khi fetch by metadata {where_filter}: {e}")
            
        # Sort kết quả để đọc liền mạch (ưu tiên page sau đó đến nội dung)
        fetched_docs.sort(key=lambda d: (d.metadata.get("page", 0), d.metadata.get("bboxes", "")))
        
        return fetched_docs

    def get_stats(self) -> Dict[str, Any]:
        """Lấy thống kê về collection hiện tại."""
        return {
            "collection_name": self.collection_name,
            "total_chunks": self.collection.count(),
        }
