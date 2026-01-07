#!/usr/bin/env python3
"""
Test script for Neo4j connection.
Run this to verify Neo4j is accessible and credentials are correct.

Usage:
    python -m knowledge_graph.test_connection
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_graph.db import Neo4jConnection
from knowledge_graph.config import get_config


def test_connection():
    """Test Neo4j connection and run basic queries."""
    print("=" * 50)
    print("Neo4j Connection Test")
    print("=" * 50)

    # Load config
    try:
        config = get_config()
        print(f"\n[OK] Config loaded")
        print(f"  URI: {config.neo4j.uri}")
        print(f"  User: {config.neo4j.user}")
        print(f"  Database: {config.neo4j.database}")
    except ValueError as e:
        print(f"\n[FAIL] Config error: {e}")
        return False

    # Test connection
    print("\n--- Testing Connection ---")
    try:
        with Neo4jConnection() as db:
            print("[OK] Connection established")

            # Get Neo4j version
            result = db.execute("CALL dbms.components() YIELD name, versions RETURN name, versions")
            if result:
                name = result[0].get('name', 'Unknown')
                versions = result[0].get('versions', ['Unknown'])
                print(f"[OK] Neo4j {name} version: {versions[0]}")

            # Count nodes
            result = db.execute("MATCH (n) RETURN count(n) as count")
            count = result[0]['count'] if result else 0
            print(f"[OK] Total nodes in database: {count}")

            # Count relationships
            result = db.execute("MATCH ()-[r]->() RETURN count(r) as count")
            count = result[0]['count'] if result else 0
            print(f"[OK] Total relationships: {count}")

            # List node labels
            result = db.execute("CALL db.labels() YIELD label RETURN collect(label) as labels")
            labels = result[0]['labels'] if result else []
            if labels:
                print(f"[OK] Node labels: {', '.join(labels)}")
            else:
                print("  (No node labels yet - database is empty)")

            # List relationship types
            result = db.execute("CALL db.relationshipTypes() YIELD relationshipType RETURN collect(relationshipType) as types")
            types = result[0]['types'] if result else []
            if types:
                print(f"[OK] Relationship types: {', '.join(types)}")
            else:
                print("  (No relationship types yet)")

            print("\n" + "=" * 50)
            print("CONNECTION TEST PASSED")
            print("=" * 50)
            return True

    except Exception as e:
        print(f"\n[FAIL] Connection failed: {e}")
        print("\nTroubleshooting:")
        print("  1. Check if Neo4j is running on the VPS")
        print("  2. Verify credentials in .env file")
        print("  3. Check firewall allows port 7687")
        print("  4. Try: curl -I http://95.81.123.157:7474")
        return False


if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
