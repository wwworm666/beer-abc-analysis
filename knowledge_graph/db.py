"""
Neo4j database connection manager.
Provides connection pooling and query execution.
"""

from typing import Any, Dict, List, Optional
from contextlib import contextmanager
import logging

from neo4j import GraphDatabase, Driver, Session
from neo4j.exceptions import ServiceUnavailable, AuthError

from .config import Neo4jConfig, get_config

logger = logging.getLogger(__name__)


class Neo4jConnection:
    """
    Neo4j database connection manager with connection pooling.

    Usage:
        # As context manager
        with Neo4jConnection() as db:
            result = db.execute("MATCH (n) RETURN count(n) as count")

        # Manual management
        db = Neo4jConnection()
        db.connect()
        result = db.execute("MATCH (n) RETURN n LIMIT 10")
        db.close()
    """

    def __init__(self, config: Optional[Neo4jConfig] = None):
        """
        Initialize connection manager.

        Args:
            config: Neo4j configuration. If None, loads from environment.
        """
        self.config = config or get_config().neo4j
        self._driver: Optional[Driver] = None

    def connect(self) -> "Neo4jConnection":
        """
        Establish connection to Neo4j.

        Returns:
            Self for method chaining.

        Raises:
            AuthError: If authentication fails.
            ServiceUnavailable: If Neo4j is not reachable.
        """
        if self._driver is not None:
            return self

        try:
            self._driver = GraphDatabase.driver(
                self.config.uri,
                auth=(self.config.user, self.config.password),
                max_connection_pool_size=self.config.max_connection_pool_size,
                connection_timeout=self.config.connection_timeout
            )
            # Verify connectivity
            self._driver.verify_connectivity()
            logger.info(f"Connected to Neo4j at {self.config.uri}")
            return self

        except AuthError as e:
            logger.error(f"Neo4j authentication failed: {e}")
            raise
        except ServiceUnavailable as e:
            logger.error(f"Neo4j service unavailable at {self.config.uri}: {e}")
            raise

    def close(self) -> None:
        """Close the database connection."""
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")

    @property
    def driver(self) -> Driver:
        """Get the Neo4j driver, connecting if necessary."""
        if self._driver is None:
            self.connect()
        return self._driver

    @contextmanager
    def session(self) -> Session:
        """
        Get a database session as context manager.

        Yields:
            Neo4j session.
        """
        session = self.driver.session(database=self.config.database)
        try:
            yield session
        finally:
            session.close()

    def execute(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query and return results as list of dicts.

        Args:
            query: Cypher query string.
            parameters: Query parameters.

        Returns:
            List of result records as dictionaries.
        """
        with self.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def execute_write(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a write transaction.

        Args:
            query: Cypher query string.
            parameters: Query parameters.

        Returns:
            List of result records as dictionaries.
        """
        def _write_tx(tx, query, params):
            result = tx.run(query, params)
            return [record.data() for record in result]

        with self.session() as session:
            return session.execute_write(_write_tx, query, parameters or {})

    def execute_batch(
        self,
        query: str,
        batch: List[Dict[str, Any]],
        batch_size: int = 1000
    ) -> int:
        """
        Execute batch operations using UNWIND.

        Args:
            query: Cypher query with $batch parameter for UNWIND.
            batch: List of parameter dicts.
            batch_size: Number of items per transaction.

        Returns:
            Total number of items processed.
        """
        total = 0
        for i in range(0, len(batch), batch_size):
            chunk = batch[i:i + batch_size]
            self.execute_write(query, {"batch": chunk})
            total += len(chunk)
            logger.debug(f"Processed batch {i//batch_size + 1}: {len(chunk)} items")
        return total

    def __enter__(self) -> "Neo4jConnection":
        """Context manager entry."""
        return self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()


# Convenience function for quick queries
def query(cypher: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Execute a quick query using a temporary connection.

    For multiple queries, prefer using Neo4jConnection as context manager.

    Args:
        cypher: Cypher query string.
        parameters: Query parameters.

    Returns:
        List of result records as dictionaries.
    """
    with Neo4jConnection() as db:
        return db.execute(cypher, parameters)
