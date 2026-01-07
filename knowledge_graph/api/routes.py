"""
Flask API routes for GraphRAG chat.
"""

from flask import Blueprint, request, jsonify
from knowledge_graph.engine.rag import GraphRAG

chat_bp = Blueprint('chat', __name__, url_prefix='/api/chat')

# Singleton GraphRAG instance
_rag = None

def get_rag():
    """Get or create GraphRAG instance."""
    global _rag
    if _rag is None:
        _rag = GraphRAG()
    return _rag


@chat_bp.route('/ask', methods=['POST'])
def ask_question():
    """
    Process natural language question about beer sales.

    Request JSON:
        {"question": "Какое пиво продается лучше всего?"}

    Response JSON:
        {
            "success": true,
            "answer": "...",
            "cypher": "MATCH ...",
            "results_count": 10
        }
    """
    data = request.get_json()
    if not data or 'question' not in data:
        return jsonify({
            'success': False,
            'error': 'Missing "question" in request body'
        }), 400

    question = data['question'].strip()
    if not question:
        return jsonify({
            'success': False,
            'error': 'Empty question'
        }), 400

    try:
        rag = get_rag()
        result = rag.query(question)

        return jsonify({
            'success': result.success,
            'answer': result.answer,
            'cypher': result.cypher,
            'results_count': len(result.raw_results),
            'error': result.error
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@chat_bp.route('/schema', methods=['GET'])
def get_schema():
    """Get graph schema description."""
    try:
        rag = get_rag()
        return jsonify({
            'success': True,
            'schema': rag.get_schema()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@chat_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    try:
        rag = get_rag()
        # Quick check - count beers
        results = rag.query_raw("MATCH (b:Beer) RETURN count(b) as count LIMIT 1")
        return jsonify({
            'status': 'healthy',
            'neo4j': 'connected',
            'beer_count': results[0]['count'] if results else 0
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500
