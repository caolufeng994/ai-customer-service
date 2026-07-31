"""
Text Splitter Module
Splits text into chunks for embedding and retrieval
Uses recursive character splitting optimized for Chinese text
"""
from typing import List
import re
import logging

logger = logging.getLogger(__name__)


class TextSplitter:
    """
    Text splitter for chunking documents
    This step splits long documents into smaller chunks for better embedding and retrieval
    Uses recursive splitting with Chinese-specific separators
    """
    
    # Chinese-specific separators in priority order
    SEPARATORS = [
        '\n\n',  # Paragraph breaks (highest priority)
        '\n',    # Line breaks
        '。',    # Chinese period
        '！',    # Chinese exclamation
        '？',    # Chinese question mark
        '；',    # Chinese semicolon
        '，',    # Chinese comma
        ' ',     # Space
        '',      # Character level (last resort)
    ]
    
    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 80,
        separators: List[str] = None
    ):
        """
        Initialize text splitter
        
        Args:
            chunk_size: Target chunk size in characters
            chunk_overlap: Overlap between chunks in characters
            separators: Custom separators (uses default if None)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or self.SEPARATORS
    
    def split_text(self, text: str) -> List[str]:
        """
        Split text into chunks
        
        Args:
            text: Input text to split
            
        Returns:
            List of text chunks
        """
        if not text:
            return []
        
        # Clean text - remove excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()
        
        if len(text) <= self.chunk_size:
            return [text]
        
        chunks = []
        self._recursive_split(text, chunks)
        
        # Post-process: remove empty chunks and very small chunks
        chunks = [c for c in chunks if len(c) >= 10]
        
        logger.info(f"Split text into {len(chunks)} chunks")
        return chunks
    
    def _recursive_split(self, text: str, chunks: List[str]) -> None:
        """
        Recursively split text using separators
        
        Args:
            text: Text to split
            chunks: List to accumulate chunks
        """
        # If text is small enough, add as chunk
        if len(text) <= self.chunk_size:
            chunks.append(text)
            return
        
        # Try each separator in priority order
        for separator in self.separATORS:
            if separator == '':
                # Last resort: split by character
                self._split_by_character(text, chunks)
                return
            
            # Split by current separator
            parts = text.split(separator)
            
            if len(parts) <= 1:
                # Separator not found, try next one
                continue
            
            # Build chunks from parts
            current_chunk = ""
            for part in parts:
                # Add separator back (except for empty separator)
                if separator:
                    part_with_sep = part + separator
                else:
                    part_with_sep = part
                
                # Check if adding this part would exceed chunk size
                if len(current_chunk) + len(part_with_sep) <= self.chunk_size:
                    current_chunk += part_with_sep
                else:
                    # Current chunk is full, save it
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    
                    # Start new chunk with overlap
                    if self.chunk_overlap > 0 and len(current_chunk) > self.chunk_overlap:
                        overlap_text = current_chunk[-self.chunk_overlap:]
                        current_chunk = overlap_text + part_with_sep
                    else:
                        current_chunk = part_with_sep
            
            # Add remaining chunk
            if current_chunk:
                chunks.append(current_chunk.strip())
            
            # If we successfully split, return
            if chunks:
                return
        
        # If all separators failed, split by character
        self._split_by_character(text, chunks)
    
    def _split_by_character(self, text: str, chunks: List[str]) -> None:
        """
        Split text by character (last resort)
        
        Args:
            text: Text to split
            chunks: List to accumulate chunks
        """
        for i in range(0, len(text), self.chunk_size - self.chunk_overlap):
            chunk = text[i:i + self.chunk_size]
            chunks.append(chunk)
    
    def get_chunk_count(self, text: str) -> int:
        """
        Get number of chunks without actually splitting
        
        Args:
            text: Input text
            
        Returns:
            Estimated chunk count
        """
        if not text:
            return 0
        
        effective_size = self.chunk_size - self.chunk_overlap
        return max(1, (len(text) + effective_size - 1) // effective_size)
