/**
 * Thư Viện AI Assistant - Frontend Application
 *
 * Xử lý giao tiếp với API và hiển thị kết quả cho người dùng.
 */

// =============================================================================
// CONFIGURATION
// =============================================================================

const API_BASE = window.location.origin;

const API_ENDPOINTS = {
  libraryChat: `${API_BASE}/api/library/chat`,
  pdfUpload: `${API_BASE}/api/pdf/upload`,
  pdfLoadUrl: `${API_BASE}/api/pdf/load-from-url`,
  pdfChat: `${API_BASE}/api/pdf/chat`,
  pdfStats: `${API_BASE}/api/pdf/stats`,
};

// =============================================================================
// PDF VIEWER STATE
// =============================================================================

let pdfDoc = null;
let pageNum = 1;
let pageRendering = false;
let pageNumPending = null;
let scale = 1.0;
let currentPdfFilename = null;
const canvas = document.getElementById("the-canvas");
const ctx = canvas.getContext("2d");
const highlightLayer = document.getElementById("highlight-layer");

// =============================================================================
// DOM ELEMENTS (Updated)
// =============================================================================

const elements = {
  // Tabs
  navTabs: document.querySelectorAll(".nav-tab"),
  tabContents: document.querySelectorAll(".tab-content"),

  // Library
  libraryForm: document.getElementById("library-form"),
  libraryInput: document.getElementById("library-input"),
  libraryMessages: document.getElementById("library-messages"),

  // PDF Chat
  pdfForm: document.getElementById("pdf-form"),
  pdfInput: document.getElementById("pdf-input"),
  pdfMessages: document.getElementById("pdf-messages"),

  // PDF Viewer
  uploadZone: document.getElementById("upload-zone"),
  pdfFile: document.getElementById("pdf-file"),
  urlInput: document.getElementById("url-input"),
  loadUrlBtn: document.getElementById("load-url-btn"),
  pdfInfo: document.getElementById("pdf-info"), // Badge in chat header
  pdfPlaceholder: document.getElementById("pdf-placeholder"),
  pdfFilename: document.getElementById("pdf-filename"),
  pdfChunks: document.getElementById("pdf-chunks"),
  removePdf: document.getElementById("remove-pdf"),

  // PDF Controls
  prevPageBtn: document.getElementById("prev-page"),
  nextPageBtn: document.getElementById("next-page"),
  pageCountSpan: document.getElementById("page-count"),
  pageNumSpan: document.getElementById("page-num"),
  zoomInBtn: document.getElementById("zoom-in"),
  zoomOutBtn: document.getElementById("zoom-out"),
  zoomLevelSpan: document.getElementById("zoom-level"),

  // Status
  statusDot: document.querySelector(".status-dot"),
  statusText: document.querySelector(".status-indicator span"),
};

// =============================================================================
// PDF VIEWER FUNCTIONS
// =============================================================================

/**
 * Load PDF binary data vào viewer.
 */
async function loadPdfViewer(data) {
  try {
    const loadingTask = pdfjsLib.getDocument(data);
    pdfDoc = await loadingTask.promise;

    elements.pageCountSpan.textContent = pdfDoc.numPages;
    elements.pdfPlaceholder.style.display = "none"; // Hide upload placeholder
    canvas.style.display = "block";

    // Reset state
    pageNum = 1;
    renderPage(pageNum);
  } catch (error) {
    console.error("Error loading PDF:", error);
    alert("Không thể hiển thị PDF. Vui lòng thử lại.");
  }
}

/**
 * Render trang PDF cụ thể.
 */
async function renderPage(num, highlightBboxes = []) {
  pageRendering = true;

  // Fetch page
  const page = await pdfDoc.getPage(num);

  const viewport = page.getViewport({ scale: scale });
  canvas.height = viewport.height;
  canvas.width = viewport.width;

  // Render context
  const renderContext = {
    canvasContext: ctx,
    viewport: viewport,
  };

  const renderTask = page.render(renderContext);

  // Wait for render to finish
  try {
    await renderTask.promise;
    pageRendering = false;

    // Update page counters
    elements.pageNumSpan.textContent = num;

    // Process pending page
    if (pageNumPending !== null) {
      renderPage(pageNumPending);
      pageNumPending = null;
    }

    // Draw highlights if any
    drawHighlights(highlightBboxes, viewport);
  } catch (error) {
    console.error("Render error:", error);
  }
}

/**
 * Queue render page request.
 */
function queueRenderPage(num) {
  if (pageRendering) {
    pageNumPending = num;
  } else {
    renderPage(num);
  }
}

/**
 * Chuyển trang trước.
 */
function onPrevPage() {
  if (pageNum <= 1) return;
  pageNum--;
  queueRenderPage(pageNum);
}

/**
 * Chuyển trang sau.
 */
function onNextPage() {
  if (pageNum >= pdfDoc.numPages) return;
  pageNum++;
  queueRenderPage(pageNum);
}

elements.prevPageBtn.addEventListener("click", onPrevPage);
elements.nextPageBtn.addEventListener("click", onNextPage);

/**
 * Zoom controls
 */
elements.zoomInBtn.addEventListener("click", () => {
  scale += 0.2;
  elements.zoomLevelSpan.textContent = Math.round(scale * 100) + "%";
  renderPage(pageNum);
});

elements.zoomOutBtn.addEventListener("click", () => {
  if (scale > 0.4) {
    scale -= 0.2;
    elements.zoomLevelSpan.textContent = Math.round(scale * 100) + "%";
    renderPage(pageNum);
  }
});

/**
 * Vẽ highlight boxes lên layer overlay.
 * Input: bboxes (JSON string hoặc Array) format [x_min, y_min, x_max, y_max]
 */
function drawHighlights(bboxes, viewport) {
  highlightLayer.innerHTML = ""; // Xóa highlight cũ

  // Cập nhật kích thước layer trùng với canvas
  highlightLayer.style.width = canvas.width + "px";
  highlightLayer.style.height = canvas.height + "px";

  if (!bboxes || bboxes.length === 0) return;

  // Parse JSON nếu cần
  let boxes = typeof bboxes === "string" ? JSON.parse(bboxes) : bboxes;
  if (!Array.isArray(boxes)) return;

  boxes.forEach((box) => {
    // 1. Lấy tọa độ gốc từ Docling (Bottom-Left Origin)
    // Format: [x_min, y_min, x_max, y_max]
    // Ví dụ: [63.79, 680.17, 548.16, 693.04]
    const [xMin, yMin, xMax, yMax] = box;

    // 2. Chuyển đổi sang hệ tọa độ Viewport của PDF.js (Pixel trên màn hình)
    // Hàm này tự động xử lý tỉ lệ zoom (scale) và lật trục Y (từ dưới lên -> từ trên xuống)
    const rect = viewport.convertToViewportRectangle([xMin, yMin, xMax, yMax]);
    // Kết quả rect là mảng [x1, y1, x2, y2] trong hệ tọa độ pixel trình duyệt

    // 3. Chuẩn hóa để vẽ div (CSS style)
    // Do trục Y bị lật, rect[1] có thể lớn hơn rect[3], nên cần dùng Math.min/Math.abs
    const x = Math.min(rect[0], rect[2]);
    const y = Math.min(rect[1], rect[3]); // Lấy điểm y cao nhất (số nhỏ nhất) làm top
    const w = Math.abs(rect[2] - rect[0]);
    const h = Math.abs(rect[3] - rect[1]);

    // 4. Tạo phần tử Highlight
    const div = document.createElement("div");
    div.className = "highlight-box";
    
    // Gán style tọa độ
    div.style.left = `${Math.round(x)}px`;
    div.style.top = `${Math.round(y)}px`;
    div.style.width = `${Math.round(w)}px`;
    div.style.height = `${Math.round(h)}px`;

    // (Tùy chọn) Thêm hiệu ứng cuộn tới highlight đầu tiên
    // Chỉ cuộn nếu đây là box đầu tiên trong danh sách
    if (box === boxes[0]) {
        div.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    highlightLayer.appendChild(div);
  });
}

// =============================================================================
// TAB NAVIGATION
// =============================================================================

/**
 * Chuyển đổi giữa các tab.
 *
 * @param {string} tabId - ID của tab cần chuyển đến.
 */
function switchTab(tabId) {
  // Update nav tabs
  elements.navTabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tab === tabId);
  });

  // Update content
  elements.tabContents.forEach((content) => {
    content.classList.toggle("active", content.id === `${tabId}-tab`);
  });
}

elements.navTabs.forEach((tab) => {
  tab.addEventListener("click", () => switchTab(tab.dataset.tab));
});

// =============================================================================
// MESSAGE HANDLING
// =============================================================================

/**
 * Tạo HTML cho một message.
 *
 * @param {string} content - Nội dung message.
 * @param {string} type - Loại message ('user' hoặc 'assistant').
 * @returns {string} HTML string.
 */
function createMessageHTML(content, type) {
  const avatarIcon =
    type === "user"
      ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>'
      : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';

  // Format content với markdown cơ bản
  let formattedContent = formatMessage(content);

  return `
        <div class="message ${type}">
            <div class="message-avatar">${avatarIcon}</div>
            <div class="message-content">
                ${formattedContent}
            </div>
        </div>
    `;
}

/**
 * Tạo HTML cho loading indicator.
 *
 * @returns {string} HTML string.
 */
function createLoadingHTML() {
  return `
        <div class="message assistant loading" id="loading-message">
            <div class="message-avatar">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
                    <line x1="12" y1="17" x2="12.01" y2="17"/>
                </svg>
            </div>
            <div class="message-content">
                <div class="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        </div>
    `;
}

/**
 * Format message với markdown cơ bản.
 *
 * @param {string} text - Nội dung cần format.
 * @returns {string} HTML string.
 */
function formatMessage(text) {
  // Escape HTML trước
  let formatted = escapeHtml(text);

  // Code blocks
  formatted = formatted.replace(
    /```(\w*)\n?([\s\S]*?)```/g,
    "<pre><code>$2</code></pre>"
  );

  // Inline code
  formatted = formatted.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Bold
  formatted = formatted.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  // Italic
  formatted = formatted.replace(/\*([^*]+)\*/g, "<em>$1</em>");

  // Line breaks
  formatted = formatted.replace(/\n/g, "<br>");

  // Wrap in paragraph
  return `<p>${formatted}</p>`;
}

/**
 * Escape HTML để tránh XSS.
 *
 * @param {string} text - Text cần escape.
 * @returns {string} Escaped text.
 */
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Thêm message vào chat container.
 *
 * @param {HTMLElement} container - Container chứa messages.
 * @param {string} content - Nội dung message.
 * @param {string} type - Loại message.
 */
function addMessage(container, content, type) {
  container.insertAdjacentHTML(
    "beforeend",
    createMessageHTML(content, type)
  );
  container.scrollTop = container.scrollHeight;
}

/**
 * Hiển thị loading indicator.
 *
 * @param {HTMLElement} container - Container chứa messages.
 */
function showLoading(container) {
  container.insertAdjacentHTML("beforeend", createLoadingHTML());
  container.scrollTop = container.scrollHeight;
}

/**
 * Ẩn loading indicator.
 */
function hideLoading() {
  const loading = document.getElementById("loading-message");
  if (loading) loading.remove();
}

// =============================================================================
// LIBRARY CHAT
// =============================================================================

elements.libraryForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const message = elements.libraryInput.value.trim();
  if (!message) return;

  // Clear input
  elements.libraryInput.value = "";

  // Add user message
  addMessage(elements.libraryMessages, message, "user");

  // Show loading
  showLoading(elements.libraryMessages);

  try {
    const response = await fetch(API_ENDPOINTS.libraryChat, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });

    hideLoading();

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    addMessage(elements.libraryMessages, data.answer, "assistant");
  } catch (error) {
    hideLoading();
    addMessage(
      elements.libraryMessages,
      `❌ Lỗi: ${error.message}. Vui lòng thử lại.`,
      "assistant"
    );
    console.error("Library chat error:", error);
  }
});

// =============================================================================
// PDF UPLOAD
// =============================================================================

// Upload button click -> trigger file input
const uploadBtn = document.getElementById("upload-btn");
uploadBtn.addEventListener("click", () => {
  elements.pdfFile.click();
});

// Drag & Drop
elements.uploadZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  elements.uploadZone.classList.add("dragover");
});

elements.uploadZone.addEventListener("dragleave", () => {
  elements.uploadZone.classList.remove("dragover");
});

elements.uploadZone.addEventListener("drop", (e) => {
  e.preventDefault();
  elements.uploadZone.classList.remove("dragover");

  const files = e.dataTransfer.files;
  if (files.length > 0 && files[0].type === "application/pdf") {
    uploadPDF(files[0]);
  }
});

// File input change
elements.pdfFile.addEventListener("change", (e) => {
  if (e.target.files.length > 0) {
    uploadPDF(e.target.files[0]);
  }
});

// Load URL click
if (elements.loadUrlBtn) {
  elements.loadUrlBtn.addEventListener("click", () => {
    loadPdfFromUrl();
  });
}

// URL input enter
if (elements.urlInput) {
  elements.urlInput.addEventListener("keypress", (e) => {
    if (e.key === "Enter") {
      loadPdfFromUrl();
    }
  });
}

/**
 * Load PDF từ URL.
 */
async function loadPdfFromUrl() {
  const url = elements.urlInput.value.trim();
  if (!url) return;

  elements.uploadZone.classList.add("uploading");

  try {
    const response = await fetch(API_ENDPOINTS.pdfLoadUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();

    // Load PDF into viewer from server static path
    // Backend saved file to data/pdfs, which is mounted at /pdfs
    const pdfUrl = `${API_BASE}/pdfs/${data.filename}`;
    await loadPdfViewer(pdfUrl);

    // Update UI
    currentPdfFilename = data.filename;
    if (elements.pdfFilename) elements.pdfFilename.textContent = data.filename;
    if (elements.pdfChunks)
      elements.pdfChunks.textContent = `${data.total_chunks} chunks`;

    // Show PDF info badge (chat header)
    if (elements.pdfInfo) elements.pdfInfo.style.display = "flex";

    // Enable input
    elements.pdfInput.disabled = false;
    elements.pdfForm.querySelector(".send-btn").disabled = false;

    // Add success message
    addMessage(
      elements.pdfMessages,
      `✅ Đã tải và xử lý **${data.filename}** thành công! (${data.total_chunks} chunks)\n\nBạn có thể đặt câu hỏi về nội dung PDF ngay bây giờ.`,
      "assistant"
    );
  } catch (error) {
    addMessage(
      elements.pdfMessages,
      `❌ Lỗi load URL: ${error.message}`,
      "assistant"
    );
    console.error("Load URL error:", error);
  } finally {
    elements.uploadZone.classList.remove("uploading");
  }
}

/**
 * Upload file PDF lên server.
 *
 * @param {File} file - File PDF cần upload.
 */
async function uploadPDF(file) {
  elements.uploadZone.classList.add("uploading");

  // 1. Load PDF vào viewer locally ngay lập tức
  const reader = new FileReader();
  reader.onload = function (e) {
    const typedarray = new Uint8Array(e.target.result);
    loadPdfViewer(typedarray);
  };
  reader.readAsArrayBuffer(file);

  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch(API_ENDPOINTS.pdfUpload, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();

    // Update UI
    currentPdfFilename = data.filename;
    if (elements.pdfFilename) elements.pdfFilename.textContent = data.filename;
    if (elements.pdfChunks)
      elements.pdfChunks.textContent = `${data.total_chunks} chunks`;

    // Show PDF info badge (chat header)
    if (elements.pdfInfo) elements.pdfInfo.style.display = "flex";

    // Enable input
    elements.pdfInput.disabled = false;
    elements.pdfForm.querySelector(".send-btn").disabled = false;

    // Add success message
    addMessage(
      elements.pdfMessages,
      `✅ Đã upload và xử lý **${data.filename}** thành công! (${data.total_chunks} chunks)\n\nBạn có thể đặt câu hỏi về nội dung PDF ngay bây giờ.`,
      "assistant"
    );
  } catch (error) {
    addMessage(
      elements.pdfMessages,
      `❌ Lỗi upload: ${error.message}`,
      "assistant"
    );
    console.error("Upload error:", error);
  } finally {
    elements.uploadZone.classList.remove("uploading");
  }
}

// Remove PDF
elements.removePdf.addEventListener("click", () => {
  currentPdfFilename = null;

  // Reset Viewer
  pdfDoc = null;
  canvas.style.display = "none";
  highlightLayer.innerHTML = "";
  elements.pdfPlaceholder.style.display = "block"; // Show upload again

  // Reset Chat UI
  elements.pdfInfo.style.display = "none";
  elements.pdfFile.value = "";

  // Disable input
  elements.pdfInput.disabled = true;
  elements.pdfForm.querySelector(".send-btn").disabled = true;

  // Clear messages except first
  const messages = elements.pdfMessages.querySelectorAll(".message");
  messages.forEach((msg, i) => {
    if (i > 0) msg.remove();
  });
});

// =============================================================================
// PDF CHAT
// =============================================================================

elements.pdfForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const message = elements.pdfInput.value.trim();
  if (!message || !currentPdfFilename) return;

  // Clear input
  elements.pdfInput.value = "";

  // Add user message
  addMessage(elements.pdfMessages, message, "user");

  // Show loading
  showLoading(elements.pdfMessages);

  try {
    const response = await fetch(API_ENDPOINTS.pdfChat, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: currentPdfFilename,
        message,
      }),
    });

    hideLoading();

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();
    addMessage(
      elements.pdfMessages,
      data.answer,
      "assistant"
    );
  } catch (error) {
    hideLoading();
    addMessage(elements.pdfMessages, `❌ Lỗi: ${error.message}`, "assistant");
    console.error("PDF chat error:", error);
  }
});

// =============================================================================
// HEALTH CHECK
// =============================================================================

/**
 * Kiểm tra trạng thái server.
 */
async function checkServerHealth() {
  try {
    const response = await fetch(`${API_BASE}/health`);
    const isHealthy = response.ok;

    elements.statusDot.style.background = isHealthy
      ? "var(--success)"
      : "var(--error)";
    elements.statusText.textContent = isHealthy
      ? "Server Online"
      : "Server Offline";
  } catch (error) {
    elements.statusDot.style.background = "var(--error)";
    elements.statusText.textContent = "Server Offline";
  }
}

// Check health on load and every 30 seconds
checkServerHealth();
setInterval(checkServerHealth, 30000);

// =============================================================================
// KEYBOARD SHORTCUTS
// =============================================================================

document.addEventListener("keydown", (e) => {
  // Ctrl/Cmd + 1: Library tab
  if ((e.ctrlKey || e.metaKey) && e.key === "1") {
    e.preventDefault();
    switchTab("library");
    elements.libraryInput.focus();
  }

  // Ctrl/Cmd + 2: PDF tab
  if ((e.ctrlKey || e.metaKey) && e.key === "2") {
    e.preventDefault();
    switchTab("pdf");
    if (!elements.pdfInput.disabled) {
      elements.pdfInput.focus();
    }
  }
});

// =============================================================================
// INIT
// =============================================================================

console.log("🚀 Thư Viện AI Assistant initialized");
