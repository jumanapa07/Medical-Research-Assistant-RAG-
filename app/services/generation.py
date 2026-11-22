import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class GenerationService:
    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-5.5")

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is missing")

        self.client = OpenAI(api_key=self.api_key)

    def _build_context(
        self,
        chunks: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:

        context_parts = []
        citations = []

        for index, chunk in enumerate(chunks, start=1):
            source_id = chunk.get("chunk_id", str(index))
            title = chunk.get("title", "Unknown document")
            page_start = chunk.get("page_start")
            page_end = chunk.get("page_end")
            content = chunk.get("text") or chunk.get("content", "")

            if not content:
                continue

            page_reference = (
                f"{page_start}-{page_end}"
                if page_start and page_end and page_start != page_end
                else str(page_start or "Unknown")
            )

            context_parts.append(f"""
[Source {index}]
Title: {title}
Page: {page_reference}
Content:
{content}
""")

            citations.append(
                {
                    "source_id": source_id,
                    "title": title,
                    "page_start": page_start,
                    "page_end": page_end,
                }
            )

        return "\n".join(context_parts), citations

    def generate(
        self,
        query: str,
        chunks: list[dict[str, Any]],
    ) -> dict[str, Any]:

        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        if not chunks:
            return {
                "answer": (
                    "I could not find relevant research material "
                    "to answer this question."
                ),
                "citations": [],
            }

        context, citations = self._build_context(chunks)

        instructions = """
You are a biomedical literature research assistant.

Answer questions using the supplied research context.

Rules:
1. Base factual claims on the supplied context.
2. Do not invent facts, studies, authors or references.
3. If the context does not contain sufficient information,
   explicitly state that.
4. Cite supporting information using [Source 1],
   [Source 2], etc.
5. Do not generate page numbers or document titles yourself.
6. Explain technical concepts clearly.
7. Distinguish evidence from interpretation.
"""

        prompt = f"""
Research context:

{context}

User question:

{query}

Provide a clear, structured answer.
Include source markers next to the claims they support.
"""

        response = self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=prompt,
        )

        return {
            "answer": response.output_text,
            "citations": citations,
            "model": self.model,
        }
