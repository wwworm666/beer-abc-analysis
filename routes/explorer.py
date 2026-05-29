"""HTTP API для iiko Parameter Explorer.

См. core/explorer.py для логики и .claude/docs/explorer.md для контракта.
"""
from flask import Blueprint, jsonify, render_template, request

from core.explorer import (
    GRANULARITIES,
    GROUP_BY_FIELD,
    TOP_CATEGORY_FILTERS,
    build_pivot,
)
from core.venues_config import VENUES
from extensions import BARS

explorer_bp = Blueprint('explorer', __name__)


@explorer_bp.route('/explorer')
def explorer_page():
    """Страница конструктора отчётов."""
    return render_template('explorer.html', bars=BARS)


@explorer_bp.route('/api/explorer/pivot')
def explorer_pivot():
    """Сводная таблица за период.

    GET-параметры:
        date_from, date_to (YYYY-MM-DD)
        venue (bolshoy|ligovskiy|kremenchugskaya|varshavskaya|all)
        granularity (day|week|month)
        group_by (top_category|third_parent|dish_name)
        top_category (опц.: kitchen|draft|bottled)
        metric (опц., default revenue)
    """
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    venue = request.args.get('venue', '').strip()
    granularity = request.args.get('granularity', 'day').strip()
    group_by = request.args.get('group_by', 'third_parent').strip()
    top_category = (request.args.get('top_category') or '').strip() or None
    metric = (request.args.get('metric') or 'revenue').strip()

    if not date_from or not date_to:
        return jsonify({'error': 'date_from и date_to обязательны'}), 400
    if venue not in VENUES:
        return jsonify({'error': f"venue должен быть одним из {list(VENUES.keys())}"}), 400
    if granularity not in GRANULARITIES:
        return jsonify({'error': f"granularity: {sorted(GRANULARITIES)}"}), 400
    if group_by not in GROUP_BY_FIELD:
        return jsonify({'error': f"group_by: {list(GROUP_BY_FIELD)}"}), 400
    if top_category and top_category not in TOP_CATEGORY_FILTERS:
        return jsonify({'error': f"top_category: {sorted(TOP_CATEGORY_FILTERS)} или пусто"}), 400

    try:
        result = build_pivot(
            venue=venue,
            date_from=date_from,
            date_to=date_to,
            granularity=granularity,
            group_by=group_by,
            top_category=top_category,
            metric=metric,
        )
        return jsonify(result)
    except (ValueError, NotImplementedError) as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"[EXPLORER ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f"{type(e).__name__}: {e}"}), 500
