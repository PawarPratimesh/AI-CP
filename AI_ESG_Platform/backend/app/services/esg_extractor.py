import json

from app.services.llm import _call_with_retry


def extract_esg_commitments_batch(chunks):
    """
    Analyze multiple document chunks using ONE Gemini request.

    chunks:
        List of dictionaries containing:
        - chunk_id
        - text
        - filename
        - page
    """

    # --------------------------------------------------
    # 1. Prepare all chunks for Gemini
    # --------------------------------------------------

    chunk_texts = []

    for chunk in chunks:

        chunk_texts.append({
            "chunk_id": chunk["chunk_id"],
            "text": chunk["text"]
        })

    # Convert Python list into JSON text
    chunks_json = json.dumps(
        chunk_texts,
        indent=2
    )

    # --------------------------------------------------
    # 2. Create ESG analysis prompt
    # --------------------------------------------------

    prompt = f"""
You are an ESG document analysis system.

Analyze the following document chunks.

For EACH chunk, identify every ESG commitment,
target, goal, sustainability-related action,
weakness, or risk mentioned in that chunk.

Return the analysis for every chunk using its
original chunk_id.

For EACH commitment, extract:

- category
- topic
- commitment
- target
- baseline
- deadline
- measurable
- risk

IMPORTANT RULES:

1. category MUST be exactly one of:
   "Environmental"
   "Social"
   "Governance"

2. topic should describe the specific ESG area.

Examples:
"Renewable Energy"
"Greenhouse Gas Emissions"
"Water Management"
"Employee Safety"
"Supplier Sustainability"

3. commitment should describe what the organization
says it will do or is doing.

4. target:
Extract the explicit numerical or measurable
target if one exists.

Examples:
"35%"
"60%"
"1.8 million cubic metres"

If there is no explicit target, use null.

5. baseline:
Extract the baseline if explicitly mentioned.

Example:
"2022 baseline"

If there is no baseline, use null.

6. deadline:
Extract the deadline if explicitly mentioned.

Examples:
"2030"
"2028"

If there is no deadline, use null.

7. measurable:
Set this to true when the commitment contains
a concrete target, quantity, percentage, metric,
or clearly defined deadline that allows progress
to be objectively tracked.

Set this to false when the commitment is vague
and cannot be objectively measured.

8. risk:
If the source text explicitly mentions a risk,
weakness, concern, limitation, or problem related
to the commitment, copy that information.

DO NOT invent a risk.

If no risk is mentioned, use null.

9. Do not invent targets, baselines, deadlines,
measurements, or risks.

10. Preserve the meaning of the original text.

11. Return ONLY valid JSON.

12. Do NOT use Markdown code fences.

Expected format:

{{
    "chunks": [
        {{
            "chunk_id": "original-chunk-id",
            "commitments": [
                {{
                    "category": "Environmental",
                    "topic": "Renewable Energy",
                    "commitment": "Source electricity from renewable sources",
                    "target": "60%",
                    "baseline": null,
                    "deadline": "2028",
                    "measurable": true,
                    "risk": null
                }}
            ]
        }}
    ]
}}

DOCUMENT CHUNKS:

{chunks_json}
"""

    # --------------------------------------------------
    # 3. ONE Gemini request
    # --------------------------------------------------

    response = _call_with_retry(prompt)

    # --------------------------------------------------
    # 4. Convert Gemini response to Python dictionary
    # --------------------------------------------------

    return parse_json_response(response)


def parse_json_response(response):
    """
    Convert Gemini response into a Python dictionary.

    Handles Markdown code fences if Gemini
    accidentally adds them.
    """

    try:

        response = response.strip()

        if response.startswith("```json"):
            response = response[7:]

        elif response.startswith("```"):
            response = response[3:]

        if response.endswith("```"):
            response = response[:-3]

        response = response.strip()

        return json.loads(response)

    except json.JSONDecodeError:

        return {
            "error": "LLM returned invalid JSON",
            "raw_response": response
        }