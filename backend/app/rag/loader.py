"""
Document Loader Module
Loads and parses documents from various file formats (txt, md, pdf)
"""
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class DocumentLoader:
    """
    Document loader for parsing different file formats
    This step extracts raw text content from uploaded files
    """
    
    @staticmethod
    def load_txt(file_path: str) -> str:
        """
        Load text from .txt file
        
        Args:
            file_path: Path to the text file
            
        Returns:
            Raw text content
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            # Try with different encoding
            try:
                with open(file_path, 'r', encoding='gbk') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Failed to load txt file {file_path}: {e}")
                raise
        except Exception as e:
            logger.error(f"Failed to load txt file {file_path}: {e}")
            raise
    
    @staticmethod
    def load_md(file_path: str) -> str:
        """
        Load text from .md (Markdown) file
        
        Args:
            file_path: Path to the markdown file
            
        Returns:
            Raw text content (markdown format preserved)
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='gbk') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Failed to load md file {file_path}: {e}")
                raise
        except Exception as e:
            logger.error(f"Failed to load md file {file_path}: {e}")
            raise
    
    @staticmethod
    def load_pdf(file_path: str) -> str:
        """
        Load text from .pdf file using PyMuPDF
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Raw text content extracted from PDF
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.error("PyMuPDF not installed. Install with: pip install pymupdf")
            raise ImportError("PyMuPDF is required for PDF parsing")
        
        try:
            doc = fitz.open(file_path)
            text_content = []
            
            for page in doc:
                text = page.get_text()
                if text.strip():
                    text_content.append(text)
            
            doc.close()
            return '\n\n'.join(text_content)
            
        except Exception as e:
            logger.error(f"Failed to load PDF file {file_path}: {e}")
            raise
    
    @staticmethod
    def load(file_path: str, file_type: Optional[str] = None) -> str:
        """
        Load document based on file type
        
        Args:
            file_path: Path to the document
            file_type: File type (txt, md, pdf). If None, inferred from extension
            
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
        }
        
        loader = loaders.get(file_type.lower())
        if loader is None:
            raise ValueError(f"Unsupported file type: {file_type}. Supported types: {list(loaders.keys())}")
        
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
