try:
    from sentence_transformers import SentenceTransformer
    # Load the embedding model once
    _model = SentenceTransformer("all-MiniLM-L6-v2")
except ImportError:
    _model = None  # type: ignore


def generate_embeddings(texts):
    """
    Convert a list of text chunks into embedding vectors.
    """
    if _model is None:
        raise RuntimeError(
            "sentence-transformers is not installed. Run: pip install sentence-transformers"
        )

    embeddings = _model.encode(texts)

    return embeddings.tolist()