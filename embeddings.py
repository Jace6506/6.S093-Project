"""Local embedding generation using fastembed."""
import os
from typing import List
from fastembed import TextEmbedding

# Suppress Hugging Face token warning
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"

# Global model instance (lazy loaded)
_embedding_model = None


def get_embedding_model():
    """Get or initialize the embedding model (lazy loading)."""
    global _embedding_model
    if _embedding_model is None:
        print("Loading MiniLM-L6-v2 embedding model (ONNX)...")
        _embedding_model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
        print("Model loaded successfully!")
    return _embedding_model


def generate_embedding(text: str) -> List[float]:
    """
    Generate a 384-dimensional embedding for the given text.
    
    Args:
        text: Text to embed
    
    Returns:
        384-dimensional embedding vector
    """
    if not text or not text.strip():
        # Return zero vector for empty text
        return [0.0] * 384
    
    model = get_embedding_model()
    embeddings = list(model.embed([text]))
    return embeddings[0].tolist()


def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for multiple texts in a batch (more efficient).
    
    Args:
        texts: List of texts to embed
    
    Returns:
        List of 384-dimensional embedding vectors
    """
    if not texts:
        return []
    
    # Filter out empty texts
    non_empty_texts = [t for t in texts if t and t.strip()]
    if not non_empty_texts:
        return [[0.0] * 384] * len(texts)
    
    model = get_embedding_model()
    embeddings = list(model.embed(non_empty_texts))
    
    # Map back to original list (with zero vectors for empty texts)
    result = []
    text_idx = 0
    for text in texts:
        if text and text.strip():
            result.append(embeddings[text_idx].tolist())
            text_idx += 1
        else:
            result.append([0.0] * 384)
    
    return result
