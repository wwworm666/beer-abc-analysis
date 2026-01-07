"""
Base LLM provider interface.
"""

from abc import ABC, abstractmethod
from typing import Optional


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """
        Generate text response.

        Args:
            prompt: User prompt
            system: Optional system prompt

        Returns:
            Generated text
        """
        pass

    @abstractmethod
    def generate_cypher(self, question: str, schema: str, examples: str) -> str:
        """
        Generate Cypher query from natural language question.

        Args:
            question: Natural language question
            schema: Graph schema description
            examples: Example queries

        Returns:
            Cypher query string
        """
        pass
