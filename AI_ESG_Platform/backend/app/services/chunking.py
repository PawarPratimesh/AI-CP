import re
import uuid


def clean_text(text):
    """
    Clean unnecessary whitespace from extracted PDF text.
    """

    # Replace multiple spaces/tabs with one space
    text = re.sub(r"[ \t]+", " ", text)

    # Replace excessive newlines
    text = re.sub(r"\n{2,}", "\n", text)

    return text.strip()


def chunk_text(
    pages,
    document_id=None,
    filename=None,
    chunk_size=1000,
    overlap=150
):
    chunks = []

    for page in pages:

        page_number = page["page"]
        text = clean_text(page["text"])

        if not text:
            continue

        # Split into sentences
        sentences = re.split(r"(?<=[.!?])\s+", text)

        current_sentences = []
        current_length = 0

        for sentence in sentences:

            sentence = sentence.strip()

            if not sentence:
                continue

            # If adding this sentence stays within chunk size
            if current_length + len(sentence) + 1 <= chunk_size:

                current_sentences.append(sentence)
                current_length += len(sentence) + 1

            else:

                # Create the current chunk
                current_chunk = " ".join(current_sentences)

                if current_chunk:
                    chunks.append({
                        "chunk_id": str(uuid.uuid4()),
                        "text": current_chunk,
                        "document_id": document_id,
                        "filename": filename,
                        "page": page_number
                    })

                # Create overlap using COMPLETE sentences
                overlap_sentences = []
                overlap_length = 0

                for previous_sentence in reversed(current_sentences):

                    if overlap_length + len(previous_sentence) + 1 <= overlap:
                        overlap_sentences.insert(0, previous_sentence)
                        overlap_length += len(previous_sentence) + 1
                    else:
                        break

                current_sentences = overlap_sentences + [sentence]

                current_length = sum(
                    len(s) + 1 for s in current_sentences
                )

        # Add final chunk
        if current_sentences:

            final_chunk = " ".join(current_sentences)

            chunks.append({
                "chunk_id": str(uuid.uuid4()),
                "text": final_chunk,
                "document_id": document_id,
                "filename": filename,
                "page": page_number
            })

    return chunks