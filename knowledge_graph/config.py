"""
Configuration for Knowledge Graph module.
Loads Neo4j and LLM settings from environment variables.
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

# Load .env file
load_dotenv()


@dataclass
class Neo4jConfig:
    """Neo4j database connection configuration."""
    uri: str = field(default_factory=lambda: os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    user: str = field(default_factory=lambda: os.getenv("NEO4J_USER", "neo4j"))
    password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", ""))
    database: str = field(default_factory=lambda: os.getenv("NEO4J_DATABASE", "neo4j"))
    max_connection_pool_size: int = 50
    connection_timeout: int = 30

    def validate(self) -> "Neo4jConfig":
        """Validate configuration and return self for chaining."""
        if not self.password:
            raise ValueError("NEO4J_PASSWORD is required. Set it in .env file.")
        if not self.uri:
            raise ValueError("NEO4J_URI is required.")
        return self


@dataclass
class LLMConfig:
    """LLM provider configuration (for future use)."""
    provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "claude"))
    api_key: Optional[str] = field(default_factory=lambda: os.getenv("LLM_API_KEY"))
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "claude-3-5-sonnet-20241022"))
    temperature: float = 0.0
    max_tokens: int = 4096


@dataclass
class KnowledgeGraphConfig:
    """Main configuration container."""
    neo4j: Neo4jConfig = field(default_factory=Neo4jConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)

    @classmethod
    def from_env(cls) -> "KnowledgeGraphConfig":
        """Create configuration from environment variables."""
        config = cls()
        config.neo4j.validate()
        return config


# Global config instance (lazy loaded)
_config: Optional[KnowledgeGraphConfig] = None


def get_config() -> KnowledgeGraphConfig:
    """Get or create global configuration instance."""
    global _config
    if _config is None:
        _config = KnowledgeGraphConfig.from_env()
    return _config
