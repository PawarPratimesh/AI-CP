from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from app.services.chunking import chunk_text
from app.services.text_extraction import extract_text_from_pdf
from app.services.embeddings import generate_embeddings

from app.services.vector_store import (
    store_chunks,
    search_chunks,
    update_esg_analysis,
    collection
)

from app.services.llm import generate_answer

from app.services.esg_extractor import (
    extract_esg_commitments_batch
)

import os
import uuid
import shutil
import json


router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)


# --------------------------------------------------
# Request Models
# --------------------------------------------------

class SearchRequest(BaseModel):
    query: str
    n_results: int = 3


class AskRequest(BaseModel):
    query: str
    n_results: int = 3


class ESGAnalysisRequest(BaseModel):
    document_id: str


# --------------------------------------------------
# Upload Folder
# --------------------------------------------------

UPLOAD_FOLDER = "uploads"

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


# --------------------------------------------------
# Upload Document
# --------------------------------------------------

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...)
):

    # 1. Check file type
    if file.content_type != "application/pdf":

        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed."
        )

    # 2. Generate unique document ID
    unique_id = str(uuid.uuid4())

    original_filename = file.filename

    # 3. Create file path
    file_path = os.path.join(
        UPLOAD_FOLDER,
        f"{unique_id}_{original_filename}"
    )

    # 4. Save uploaded PDF
    with open(file_path, "wb") as buffer:

        shutil.copyfileobj(
            file.file,
            buffer
        )

    # 5. Extract text from PDF
    pages = extract_text_from_pdf(
        file_path
    )

    # 6. Create meaningful chunks
    chunks = chunk_text(
        pages,
        document_id=unique_id,
        filename=original_filename
    )

    # 7. Generate embeddings
    texts = [
        chunk["text"]
        for chunk in chunks
    ]

    embeddings = generate_embeddings(
        texts
    )

    # 8. Store chunks and embeddings in ChromaDB
    #
    # IMPORTANT:
    # No Gemini call happens during upload.

    stored_count = store_chunks(
        chunks,
        embeddings
    )

    # 9. Return upload result
    return {

        "message": (
            "Document uploaded, text extracted, "
            "chunked and embedded successfully"
        ),

        "document_id": unique_id,

        "filename": original_filename,

        "chunks_created": len(chunks),

        "chunks_stored": stored_count
    }


# --------------------------------------------------
# Analyze ESG Document
# --------------------------------------------------

@router.post("/analyze-esg")
async def analyze_esg_document(
    request: ESGAnalysisRequest
):

    # --------------------------------------------------
    # 1. Find all chunks belonging to this document
    # --------------------------------------------------

    results = collection.get(
        where={
            "document_id": request.document_id
        }
    )

    # --------------------------------------------------
    # 2. Check whether document exists
    # --------------------------------------------------

    if not results["ids"]:

        raise HTTPException(
            status_code=404,
            detail="Document not found."
        )

    # --------------------------------------------------
    # 3. Prepare chunks for batch ESG analysis
    # --------------------------------------------------

    chunks = []

    for i in range(
        len(results["ids"])
    ):

        chunks.append({

            "chunk_id": results["ids"][i],

            "text": results["documents"][i]

        })

    # --------------------------------------------------
    # 4. Send ALL chunks to batch ESG extractor
    #
    # IMPORTANT:
    # The batch extractor makes ONE Gemini request.
    # --------------------------------------------------

    analysis_result = extract_esg_commitments_batch(
        chunks
    )

    # --------------------------------------------------
    # 5. Check whether Gemini returned an error
    # --------------------------------------------------

    if "error" in analysis_result:

        raise HTTPException(
            status_code=500,
            detail=analysis_result
        )

    # --------------------------------------------------
    # 6. Create chunk_id → ESG analysis mapping
    # --------------------------------------------------

    esg_analysis_map = {}

    for chunk_result in analysis_result.get(
        "chunks",
        []
    ):

        chunk_id = chunk_result.get(
            "chunk_id"
        )

        if not chunk_id:
            continue

        esg_analysis_map[chunk_id] = {

            "commitments": chunk_result.get(
                "commitments",
                []
            )

        }

    # --------------------------------------------------
    # 7. Store ESG analysis in ChromaDB
    # --------------------------------------------------

    updated_count = update_esg_analysis(
        esg_analysis_map
    )

    # --------------------------------------------------
    # 8. Return analysis result
    # --------------------------------------------------

    return {

        "message": (
            "ESG analysis completed successfully"
        ),

        "document_id": request.document_id,

        "chunks_analyzed": len(chunks),

        "chunks_updated": updated_count

    }


# --------------------------------------------------
# Search Documents
# --------------------------------------------------

@router.post("/search")
async def search_documents(
    request: SearchRequest
):

    # 1. Convert user's question
    #    into an embedding

    query_embedding = generate_embeddings(
        [request.query]
    )[0]

    # 2. Search ChromaDB

    results = search_chunks(
        query_embedding,
        request.n_results
    )

    # 3. Return search results

    return {

        "query": request.query,

        "results": results

    }


# --------------------------------------------------
# Ask Question
# --------------------------------------------------

@router.post("/ask")
async def ask_document(
    request: AskRequest
):

    # --------------------------------------------------
    # 1. Convert user's question into an embedding
    # --------------------------------------------------

    query_embedding = generate_embeddings(
        [request.query]
    )[0]

    # --------------------------------------------------
    # 2. Retrieve relevant chunks from ChromaDB
    # --------------------------------------------------

    results = search_chunks(
        query_embedding,
        request.n_results
    )

    # --------------------------------------------------
    # 3. Extract retrieved documents
    # --------------------------------------------------

    retrieved_documents = results["documents"][0]

    # --------------------------------------------------
    # 4. Combine retrieved chunks into context
    # --------------------------------------------------

    context = "\n\n---\n\n".join(
        retrieved_documents
    )

    # --------------------------------------------------
    # 5. Send question + context to Gemini
    # --------------------------------------------------

    answer = generate_answer(
        request.query,
        context
    )

    # --------------------------------------------------
    # 6. Build source information
    # --------------------------------------------------

    sources = []

    for i in range(
        len(retrieved_documents)
    ):

        metadata = results["metadatas"][0][i]

        # --------------------------------------------------
        # Retrieve ESG analysis stored in ChromaDB
        # --------------------------------------------------

        esg_analysis_raw = metadata.get(
            "esg_analysis"
        )

        # ChromaDB stores ESG analysis
        # as a JSON string.

        if esg_analysis_raw:

            try:

                esg_analysis = json.loads(
                    esg_analysis_raw
                )

            except json.JSONDecodeError:

                esg_analysis = {
                    "error": (
                        "Stored ESG analysis "
                        "is invalid JSON"
                    )
                }

        else:

            esg_analysis = {
                "commitments": []
            }

        # --------------------------------------------------
        # Add source + context + ESG analysis
        # --------------------------------------------------

        sources.append({

            # Original document
            "filename": metadata["filename"],

            # PDF page
            "page": metadata["page"],

            # Full retrieved chunk
            "content": retrieved_documents[i],

            # ChromaDB similarity distance
            "distance": results["distances"][0][i],

            # ESG analysis
            "esg_analysis": esg_analysis

        })

    # --------------------------------------------------
    # 7. Return final response
    # --------------------------------------------------

    return {

        "question": request.query,

        "answer": answer,

        "sources": sources

    }