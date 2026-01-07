"""
GraphRAG Engine - Natural Language to Graph Query.
Converts questions to Cypher queries and formats responses.
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from knowledge_graph.db import Neo4jConnection
from knowledge_graph.engine.schema_context import get_full_context, GRAPH_SCHEMA, EXAMPLE_QUERIES
from knowledge_graph.llm.gemini import GeminiProvider

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Result of a GraphRAG query."""
    question: str
    cypher: str
    raw_results: List[Dict[str, Any]]
    answer: str
    success: bool
    error: Optional[str] = None


class GraphRAG:
    """
    GraphRAG Engine for natural language queries on Neo4j.

    Usage:
        rag = GraphRAG()
        result = rag.query("Какое пиво продается лучше всего?")
        print(result.answer)
    """

    def __init__(self, llm_provider: Optional[Any] = None):
        """
        Initialize GraphRAG engine.

        Args:
            llm_provider: LLM provider instance (default: GeminiProvider)
        """
        self.db = Neo4jConnection()
        self.llm = llm_provider or GeminiProvider()

    def query(self, question: str) -> QueryResult:
        """
        Process natural language question and return answer.

        Args:
            question: Natural language question in Russian or English

        Returns:
            QueryResult with answer and metadata
        """
        logger.info(f"Processing question: {question}")

        try:
            # Generate Cypher query
            cypher = self.llm.generate_cypher(
                question=question,
                schema=GRAPH_SCHEMA,
                examples=EXAMPLE_QUERIES
            )
            logger.info(f"Generated Cypher: {cypher}")

            # Execute query
            with self.db:
                results = self.db.execute(cypher)
            logger.info(f"Query returned {len(results)} results")

            # Format response
            answer = self.llm.format_response(
                question=question,
                results=results,
                cypher=cypher
            )

            return QueryResult(
                question=question,
                cypher=cypher,
                raw_results=results,
                answer=answer,
                success=True
            )

        except Exception as e:
            logger.error(f"Query failed: {e}")
            return QueryResult(
                question=question,
                cypher="",
                raw_results=[],
                answer=f"Произошла ошибка: {str(e)}",
                success=False,
                error=str(e)
            )

    def query_raw(self, cypher: str) -> List[Dict[str, Any]]:
        """
        Execute raw Cypher query.

        Args:
            cypher: Cypher query string

        Returns:
            List of result dictionaries
        """
        with self.db:
            return self.db.execute(cypher)

    def get_schema(self) -> str:
        """Get graph schema description."""
        return get_full_context()


def ask(question: str) -> str:
    """
    Convenience function to ask a question.

    Args:
        question: Natural language question

    Returns:
        Answer string
    """
    rag = GraphRAG()
    result = rag.query(question)
    return result.answer


def ask_with_details(question: str) -> QueryResult:
    """
    Ask question and get full result with Cypher and raw data.

    Args:
        question: Natural language question

    Returns:
        QueryResult with all details
    """
    rag = GraphRAG()
    return rag.query(question)


# Interactive CLI
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    print("=" * 50)
    print("GraphRAG - Beer Sales Analytics")
    print("=" * 50)
    print("Ask questions about beer sales in natural language.")
    print("Type 'exit' to quit.\n")

    rag = GraphRAG()

    while True:
        try:
            question = input("\nQuestion: ").strip()
            if question.lower() in ("exit", "quit", "q"):
                break
            if not question:
                continue

            print("\nProcessing...")
            result = rag.query(question)

            print(f"\n[Cypher]: {result.cypher}")
            print(f"\n[Answer]: {result.answer}")

            if result.raw_results:
                print(f"\n[Raw data]: {len(result.raw_results)} rows")
                for row in result.raw_results[:5]:
                    print(f"  {row}")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")

    print("\nGoodbye!")
