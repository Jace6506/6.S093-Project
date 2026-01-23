"""Document chunking functions for RAG."""
import re
from typing import List, Dict, Any


def chunk_document(content: str, source_id: str, min_chunk_size: int = 100, max_chunk_size: int = 2000) -> List[Dict[str, Any]]:
    """
    Chunk a document by paragraph boundaries.
    
    Args:
        content: Document content to chunk
        source_id: Identifier for the source document
        min_chunk_size: Minimum chunk size in characters
        max_chunk_size: Maximum chunk size in characters (will split if needed)
    
    Returns:
        List of chunk dictionaries with content and metadata
    """
    if not content or not content.strip():
        return []
    
    # Extract document title if present (first # header)
    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    doc_title = title_match.group(1) if title_match else source_id
    
    # Split by paragraph boundaries (double newline or single newline after empty line)
    # Also preserve single newlines that might be part of structure
    paragraphs = re.split(r'\n\s*\n', content.strip())
    
    chunks = []
    current_chunk = []
    current_size = 0
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # Extract section headers if present
        header_match = re.search(r'^(#{1,3})\s+(.+)$', para, re.MULTILINE)
        is_header = header_match is not None
        
        para_size = len(para)
        
        # If paragraph is too large, split it further
        if para_size > max_chunk_size:
            # First, save current chunk if it has content
            if current_chunk:
                chunk_content = "\n\n".join(current_chunk)
                if len(chunk_content) >= min_chunk_size:
                    chunks.append({
                        "content": chunk_content,
                        "metadata": {
                            "source_id": source_id,
                            "doc_title": doc_title,
                            "chunk_type": "paragraph_group"
                        }
                    })
                current_chunk = []
                current_size = 0
            
            # Split large paragraph by sentences
            sentences = re.split(r'(?<=[.!?])\s+', para)
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                
                if current_size + len(sentence) > max_chunk_size and current_chunk:
                    chunk_content = "\n\n".join(current_chunk)
                    if len(chunk_content) >= min_chunk_size:
                        chunks.append({
                            "content": chunk_content,
                            "metadata": {
                                "source_id": source_id,
                                "doc_title": doc_title,
                                "chunk_type": "paragraph_group"
                            }
                        })
                    current_chunk = []
                    current_size = 0
                
                current_chunk.append(sentence)
                current_size += len(sentence) + 2  # +2 for "\n\n"
        else:
            # Normal paragraph - add to current chunk
            if current_size + para_size > max_chunk_size and current_chunk:
                # Save current chunk
                chunk_content = "\n\n".join(current_chunk)
                if len(chunk_content) >= min_chunk_size:
                    chunks.append({
                        "content": chunk_content,
                        "metadata": {
                            "source_id": source_id,
                            "doc_title": doc_title,
                            "chunk_type": "paragraph_group"
                        }
                    })
                current_chunk = []
                current_size = 0
            
            current_chunk.append(para)
            current_size += para_size + 2  # +2 for "\n\n"
    
    # Add final chunk if it exists
    if current_chunk:
        chunk_content = "\n\n".join(current_chunk)
        if len(chunk_content) >= min_chunk_size:
            chunks.append({
                "content": chunk_content,
                "metadata": {
                    "source_id": source_id,
                    "doc_title": doc_title,
                    "chunk_type": "paragraph_group"
                }
            })
    
    # If no chunks created (content too short), create one chunk anyway
    if not chunks:
        chunks.append({
            "content": content,
            "metadata": {
                "source_id": source_id,
                "doc_title": doc_title,
                "chunk_type": "full_document"
            }
        })
    
    # Add document title context to each chunk
    for chunk in chunks:
        if doc_title and doc_title != source_id:
            # Prepend title if not already present
            if not chunk["content"].startswith(f"# {doc_title}"):
                chunk["content"] = f"# {doc_title}\n\n{chunk['content']}"
    
    return chunks


def chunk_notion_content(content: str, source_id: str, source_type: str = "notion_page") -> List[Dict[str, Any]]:
    """
    Chunk Notion content with appropriate metadata.
    
    Args:
        content: Notion page/database content
        source_id: Notion page ID or database ID
        source_type: Type of source ('notion_page' or 'notion_database')
    
    Returns:
        List of chunk dictionaries
    """
    return chunk_document(content, source_id)
