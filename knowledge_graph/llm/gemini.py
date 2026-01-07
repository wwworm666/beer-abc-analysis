"""
Google Vertex AI Gemini LLM adapter.
"""

import os
import re
import requests
from typing import Optional

from .base import LLMProvider


class GeminiProvider(LLMProvider):
    """Google Vertex AI Gemini provider."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or self._load_api_key()
        if not self.api_key:
            raise ValueError("Vertex AI API key not found.")

        self.model = model
        self.base_url = "https://aiplatform.googleapis.com/v1/publishers/google/models"

    def _load_api_key(self) -> Optional[str]:
        """Load API key from env or file."""
        key = os.environ.get("VERTEX_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if key:
            return key
        try:
            with open("апи", "r", encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            pass
        return None

    def _call_api(self, prompt: str) -> str:
        """Call Vertex AI API."""
        url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            ]
        }

        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=60
        )

        if response.status_code != 200:
            raise Exception(f"Vertex AI API error {response.status_code}: {response.text}")

        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Generate text response."""
        if system:
            full_prompt = system + "\n\n" + prompt
        else:
            full_prompt = prompt
        return self._call_api(full_prompt)

    def generate_cypher(self, question: str, schema: str, examples: str) -> str:
        """Generate Cypher query from natural language question."""
        prompt = f"""You are a Neo4j Cypher expert. Generate a Cypher query.

{schema}

{examples}

RULES:
1. Return ONLY the Cypher query
2. Use exact property names from schema
3. Use SUM, COUNT, AVG for totals
4. Use ORDER BY and LIMIT for top questions

Question: {question}

Cypher:"""

        response = self._call_api(prompt)
        cypher = response.strip()
        cypher = self._extract_cypher(cypher)
        return cypher

    def _extract_cypher(self, text: str) -> str:
        """Extract Cypher query from LLM response."""
        if "```cypher" in text:
            match = re.search(r'```cypher\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                return match.group(1).strip()
        if "```" in text:
            match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                return match.group(1).strip()
        return text.strip().strip('"\'`')

    def format_response(self, question: str, results: list, cypher: str) -> str:
        """Format query results into natural language response."""
        if not results:
            return "По вашему запросу данных не найдено."

        results_text = self._format_results(results)
        prompt = f"""Answer in Russian based on the query results.

Question: {question}

Results:
{results_text}

Give a concise answer (2-3 sentences) with specific numbers. In Russian:"""

        response = self._call_api(prompt)
        return response.strip()

    def _format_results(self, results: list, max_rows: int = 10) -> str:
        """Format results as readable text."""
        if not results:
            return "No results"
        lines = []
        for i, row in enumerate(results[:max_rows]):
            parts = []
            for key, value in row.items():
                if isinstance(value, float):
                    parts.append(f"{key}: {value:,.2f}")
                else:
                    parts.append(f"{key}: {value}")
            lines.append(f"{i+1}. " + ", ".join(parts))
        if len(results) > max_rows:
            lines.append(f"... and {len(results) - max_rows} more rows")
        return "\n".join(lines)
