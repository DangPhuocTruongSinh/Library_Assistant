"""
Utility functions để download file PDF từ URL, bao gồm hỗ trợ OneDrive links.

Hỗ trợ:
- Direct download URLs
- OneDrive sharing links (1drv.ms)
- OneDrive direct links (onedrive.live.com)
"""
import base64
import requests
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from log.logger_config import setup_logging

logger = setup_logging(__name__)


def convert_onedrive_link(url: str) -> str:
    """
    Convert OneDrive link sang API download link dùng Base64 encoding.
    Đây là cách chính thống và ổn định nhất.
    """
    try:
        # 1. Giải mã link rút gọn (1drv.ms) để lấy link gốc đầy đủ
        if "1drv.ms" in url:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            # Chỉ lấy header để check URL đích
            response = requests.head(url, headers=headers, allow_redirects=True, timeout=10)
            url = response.url
            logger.info(f"🔄 Resolved 1drv.ms to: {url}")

        # 2. Tạo API Link từ Sharing URL
        # Quy tắc của MS: "u!" + Base64UrlEncoded(SharingURL)
        # Bỏ các ký tự padding '=' ở cuối
        
        data_bytes = url.encode('utf-8')
        encoded_bytes = base64.urlsafe_b64encode(data_bytes)
        encoded_str = encoded_bytes.decode('utf-8').rstrip('=')
        
        api_url = f"https://api.onedrive.com/v1.0/shares/u!{encoded_str}/root/content"
        
        logger.info(f"✅ Generated OneDrive API Link: {api_url}")
        return api_url

    except Exception as e:
        logger.warning(f"⚠️ Lỗi khi convert OneDrive link: {e}")
        return url


def is_valid_pdf_url(url: str) -> bool:
    """
    Kiểm tra xem URL có phải là link PDF hợp lệ không.
    
    Args:
        url: URL cần kiểm tra.
        
    Returns:
        True nếu có vẻ là PDF URL.
    """
    # Check extension trong URL
    url_lower = url.lower()
    if url_lower.endswith('.pdf'):
        return True
    
    # Check OneDrive links (không có extension nhưng có thể là PDF)
    if "onedrive.live.com" in url or "1drv.ms" in url:
        return True
    
    # Check Google Drive, Dropbox, etc. (có thể mở rộng sau)
    
    return False


def download_pdf_from_url(
    url: str,
    save_path: Path,
    timeout: int = 300,
    max_size_mb: int = 500
) -> bool:
    """
    Download file PDF từ URL và lưu vào local path.
    
    Args:
        url: URL của file PDF.
        save_path: Đường dẫn để lưu file.
        timeout: Timeout cho request (seconds).
        max_size_mb: Kích thước file tối đa (MB).
        
    Returns:
        True nếu download thành công, False nếu có lỗi.
    """
    try:
        # Convert OneDrive link nếu cần
        if "onedrive.live.com" in url or "1drv.ms" in url:
            url = convert_onedrive_link(url)
            logger.info(f"📥 Đang download từ OneDrive: {url}")
        else:
            logger.info(f"📥 Đang download từ URL: {url}")
        
        # Download file với streaming
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.get(
            url,
            headers=headers,
            stream=True,
            timeout=timeout,
            allow_redirects=True
        )
        response.raise_for_status()
        
        # Check Content-Type
        content_type = response.headers.get("Content-Type", "").lower()
        if "application/pdf" not in content_type and not url.lower().endswith('.pdf'):
            logger.warning(f"⚠️ Content-Type không phải PDF: {content_type}")
            # Vẫn tiếp tục, có thể server không set đúng Content-Type
        
        # Check file size
        content_length = response.headers.get("Content-Length")
        if content_length:
            size_mb = int(content_length) / (1024 * 1024)
            if size_mb > max_size_mb:
                logger.error(f"❌ File quá lớn: {size_mb:.2f}MB (max: {max_size_mb}MB)")
                return False
        
        # Download và lưu file
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        total_size = 0
        max_size_bytes = max_size_mb * 1024 * 1024
        
        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    total_size += len(chunk)
                    
                    # Check size trong quá trình download
                    if total_size > max_size_bytes:
                        logger.error(f"❌ File quá lớn: {total_size / (1024*1024):.2f}MB (max: {max_size_mb}MB)")
                        save_path.unlink()  # Xóa file đã tải một phần
                        return False
        
        logger.info(f"✅ Đã download thành công: {save_path} ({total_size / (1024*1024):.2f}MB)")
        return True
        
    except requests.exceptions.Timeout:
        logger.error(f"❌ Timeout khi download: {url}")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Lỗi khi download: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Lỗi không mong đợi: {e}")
        if save_path.exists():
            save_path.unlink()  # Xóa file nếu có lỗi
        return False


def extract_filename_from_url(url: str, default: str = "document.pdf") -> str:
    """
    Trích xuất tên file từ URL.
    
    Args:
        url: URL của file.
        default: Tên file mặc định nếu không tìm thấy.
        
    Returns:
        Tên file.
    """
    try:
        parsed = urlparse(url)
        
        # Lấy filename từ path
        filename = Path(parsed.path).name
        
        # Nếu có filename và có extension
        if filename and "." in filename:
            return filename
        
        # Nếu không có, thử lấy từ query params (một số services dùng ?download=filename.pdf)
        query_params = parse_qs(parsed.query)
        if "download" in query_params:
            filename = query_params["download"][0]
            if filename:
                return filename
        
        # Mặc định
        return default
        
    except Exception as e:
        logger.warning(f"⚠️ Không thể extract filename từ URL: {e}")
        return default

