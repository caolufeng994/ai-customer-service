"""
Document Loader Module
Loads and parses documents from various file formats (txt, md, pdf, docx)
"""
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

from docx import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger(__name__)

# 单一事实来源:扩展名 -> 入库 file_type。API 校验、种子初始化、loader
# 分发三处共用,避免各写一份导致漂移。
SUPPORTED_EXTENSIONS: Dict[str, str] = {
    "txt": "txt",
    "md": "md",
    "markdown": "md",
    "pdf": "pdf",
    "docx": "docx",
}

# 面向用户展示的规范格式列表(不含 markdown 别名)。
ALLOWED_UPLOAD_EXTS: Tuple[str, ...] = ("txt", "md", "pdf", "docx")


class DocumentLoader:
    """
    Document loader for parsing different file formats
    This step extracts raw text content from uploaded files
    """

    @staticmethod
    def _read_text_file(file_path: str, label: str) -> str:
        """按 utf-8 读取纯文本,失败回退 gbk(兼容 Windows 导出的文档)。"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='gbk') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Failed to load {label} file {file_path}: {e}")
                raise
        except Exception as e:
            logger.error(f"Failed to load {label} file {file_path}: {e}")
            raise

    @staticmethod
    def load_txt(file_path: str) -> str:
        """
        Load text from .txt file

        Args:
            file_path: Path to the text file

        Returns:
            Raw text content
        """
        return DocumentLoader._read_text_file(file_path, "txt")

    @staticmethod
    def load_md(file_path: str) -> str:
        """
        Load text from .md (Markdown) file

        Args:
            file_path: Path to the markdown file

        Returns:
            Raw text content (markdown format preserved)
        """
        return DocumentLoader._read_text_file(file_path, "md")

    @staticmethod
    def load_pdf(file_path: str) -> str:
        """
        Load text from .pdf file using pypdf

        逐页抽取文本后按页拼接。加密 PDF 先尝试空口令解密;纯扫描件
        (无文本层)抽不到文字时显式报错,避免上游把空文档切成 0 个分块
        却仍标记为 ready。

        Args:
            file_path: Path to the PDF file

        Returns:
            Raw text content extracted from PDF

        Raises:
            ValueError: PDF 损坏、需要口令,或不含可提取的文本层
        """
        try:
            reader = PdfReader(file_path)

            if reader.is_encrypted:
                # 常见于"仅设置了权限密码"的 PDF,空口令即可解密。
                try:
                    decrypted = reader.decrypt("")
                except Exception:
                    decrypted = 0
                if not decrypted:
                    raise ValueError("PDF is password-protected and cannot be parsed")

            pages: List[str] = []
            for page in reader.pages:
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(text)

            if not pages:
                raise ValueError(
                    "No extractable text found in PDF "
                    "(it may be a scanned image; OCR is not supported)"
                )

            return '\n\n'.join(pages)

        except ValueError:
            raise
        except PdfReadError as e:
            logger.error(f"Failed to load PDF file {file_path}: {e}")
            raise ValueError(f"Invalid or corrupted PDF file: {e}")
        except Exception as e:
            logger.error(f"Failed to load PDF file {file_path}: {e}")
            raise

    @staticmethod
    def load_docx(file_path: str) -> str:
        """
        Load text from .docx file using python-docx

        按文档流顺序遍历段落与表格,保持正文与表格的原始先后关系
        (顺序错乱会破坏分块后的语义连贯性)。表格按行输出,单元格以
        " | " 分隔。仅支持 OOXML 的 .docx,不支持旧版二进制 .doc。

        Args:
            file_path: Path to the Word document

        Returns:
            Raw text content extracted from the document

        Raises:
            ValueError: 文件损坏或非 .docx 格式(如旧版 .doc)
        """
        try:
            document = DocxDocument(file_path)
        except Exception as e:
            logger.error(f"Failed to load docx file {file_path}: {e}")
            raise ValueError(
                f"Invalid or corrupted .docx file (legacy .doc is not supported): {e}"
            )

        body = document.element.body
        blocks: List[str] = []

        for child in body.iterchildren():
            tag = child.tag.split('}')[-1]
            if tag == 'p':
                text = Paragraph(child, document).text.strip()
                if text:
                    blocks.append(text)
            elif tag == 'tbl':
                for row in Table(child, document).rows:
                    cells = [c.text.strip() for c in row.cells]
                    line = ' | '.join(c for c in cells if c)
                    if line:
                        blocks.append(line)

        return '\n'.join(blocks)

    @staticmethod
    def load(file_path: str, file_type: Optional[str] = None) -> str:
        """
        Load document based on file type

        Args:
            file_path: Path to the document
            file_type: File type (txt, md, pdf, docx). If None, inferred from extension

        Returns:
            Raw text content

        Raises:
            ValueError: If file type is not supported
            FileNotFoundError: If file doesn't exist
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Infer file type if not provided
        if file_type is None:
            file_type = path.suffix.lower().lstrip('.')

        # Map file types to loader methods
        loaders = {
            'txt': DocumentLoader.load_txt,
            'md': DocumentLoader.load_md,
            'markdown': DocumentLoader.load_md,
            'pdf': DocumentLoader.load_pdf,
            'docx': DocumentLoader.load_docx,
        }

        loader = loaders.get(file_type.lower())
        if loader is None:
            raise ValueError(
                f"Unsupported file type: {file_type}. "
                f"Supported types: {list(loaders.keys())}"
            )

        return loader(file_path)

    @staticmethod
    def get_char_count(text: str) -> int:
        """
        Get character count of text

        Args:
            text: Input text

        Returns:
            Character count
        """
        return len(text)
