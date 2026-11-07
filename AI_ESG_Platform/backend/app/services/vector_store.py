import json

try:
    import chromadb

    client = chromadb.PersistentClient(
        path="./chroma_db"
    )

    collection = client.get_or_create_collection(
        name="esg_documents"
    )

except ImportError:
    chromadb = None  # type: ignore
    client = None    # type: ignore

    class _StubCollection:
        def get(self, *a, **kw):
            raise RuntimeError("chromadb is not installed. Run: pip install chromadb")
        def query(self, *a, **kw):
            raise RuntimeError("chromadb is not installed. Run: pip install chromadb")
        def upsert(self, *a, **kw):
            raise RuntimeError("chromadb is not installed. Run: pip install chromadb")
        def update(self, *a, **kw):
            raise RuntimeError("chromadb is not installed. Run: pip install chromadb")

    collection = _StubCollection()  # type: ignore


# --------------------------------------------------
# Store chunks + embeddings
# --------------------------------------------------

def store_chunks(chunks, embeddings, esg_analyses=None):

    ids = []
    documents = []
    metadatas = []

    for index, chunk in enumerate(chunks):

        ids.append(chunk["chunk_id"])

        documents.append(chunk["text"])

        # Get ESG analysis if available
        if esg_analyses:
            esg_analysis = esg_analyses[index]
        else:
            esg_analysis = {
                "commitments": []
            }

        metadatas.append({
            "document_id": chunk["document_id"],
            "filename": chunk["filename"],
            "page": chunk["page"],
            "esg_analysis": json.dumps(esg_analysis)
        })

    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas
    )

    return len(chunks)


# --------------------------------------------------
# Search chunks
# --------------------------------------------------

def search_chunks(query_embedding, n_results=3):

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results
    )

    return results


# --------------------------------------------------
# Update ESG analysis
# --------------------------------------------------

def update_esg_analysis(esg_analysis_map):

    """
    Update ESG analysis for existing chunks.

    esg_analysis_map should look like:

    {
        "chunk-id-1": {
            "commitments": [...]
        },

        "chunk-id-2": {
            "commitments": [...]
        }
    }
    """

    for chunk_id, analysis in esg_analysis_map.items():

        # Get existing chunk
        result = collection.get(
            ids=[chunk_id]
        )

        if not result["ids"]:
            continue

        # Get existing metadata
        metadata = result["metadatas"][0]

        # Replace ESG analysis
        metadata["esg_analysis"] = json.dumps(
            analysis
        )

        # Update metadata
        collection.update(
            ids=[chunk_id],
            metadatas=[metadata]
        )

    return len(esg_analysis_map)