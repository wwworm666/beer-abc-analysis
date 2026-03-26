"""
API endpoints для работы с Честным ЗНАКом
Отслеживание сроков годности пива
"""

from flask import Blueprint, request, jsonify
from core.chestny_znak import ChestnyZnakAPI
from datetime import datetime

chestny_znak_bp = Blueprint('chestny_znak', __name__)

# Глобальный экземпляр API (singleton)
cz_api = ChestnyZnakAPI(use_sandbox=True)


@chestny_znak_bp.route('/api/chestny-znak/connect', methods=['POST'])
def connect():
    """
    Подключение к API Честный ЗНАК

    Body:
    {
        "token": "uuid-token"  // Опционально: готовый токен
    }
    """
    try:
        data = request.json or {}
        token = data.get('token')

        success = cz_api.connect(token)

        if success:
            return jsonify({
                'success': True,
                'message': 'Подключение успешно'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Не удалось подключиться к API Честный ЗНАК'
            }), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@chestny_znak_bp.route('/api/chestny-znak/balance', methods=['POST'])
def get_balance():
    """
    Получение баланса на виртуальном складе

    Body:
    {
        "participantInn": "7777777777",  // ИНН участника (10/12 цифр)
        "date": "2026-03-26",            // Опционально: дата (YYYY-MM-DD)
        "productCodes": ["GTIN1", ...],   // Опционально: список GTIN
        "limit": 100                      // Опционально: лимит записей (макс. 100)
    }
    """
    try:
        data = request.json
        participant_inn = data.get('participantInn')

        if not participant_inn:
            return jsonify({'error': 'Требуется participantInn'}), 400

        balance = cz_api.get_warehouse_balance(
            participant_inn=participant_inn,
            date=data.get('date'),
            product_codes=data.get('productCodes'),
            limit=data.get('limit', 100)
        )

        if balance:
            return jsonify({
                'success': True,
                'data': balance
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Не удалось получить баланс'
            }), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@chestny_znak_bp.route('/api/chestny-znak/search', methods=['POST'])
def search_codes():
    """
    Поиск кодов маркировки

    Body:
    {
        "participantInn": "7777777777",
        "gtins": ["GTIN1", ...],         // Опционально: фильтр по GTIN
        "status": "INTRODUCED",          // Статус кодов
        "limit": 1000,                   // Лимит записей (макс. 1000)
        "includeExpired": false,         // Включать ли истекшие
        "daysUntilExpiry": 30            // Фильтр по дням до истечения
    }
    """
    try:
        data = request.json
        participant_inn = data.get('participantInn')

        if not participant_inn:
            return jsonify({'error': 'Требуется participantInn'}), 400

        result = cz_api.search_codes(
            participant_inn=participant_inn,
            gtins=data.get('gtins'),
            status=data.get('status', 'INTRODUCED'),
            limit=data.get('limit', 1000),
            include_expired=data.get('includeExpired', False),
            days_until_expiry=data.get('daysUntilExpiry')
        )

        if result:
            return jsonify({
                'success': True,
                'data': result
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Не удалось выполнить поиск'
            }), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@chestny_znak_bp.route('/api/chestny-znak/expiring', methods=['POST'])
def get_expiring_codes():
    """
    Получение кодов с истекающим сроком годности

    Body:
    {
        "participantInn": "7777777777",
        "daysThreshold": 30    // Порог в днях (по умолчанию 30)
    }
    """
    try:
        data = request.json
        participant_inn = data.get('participantInn')

        if not participant_inn:
            return jsonify({'error': 'Требуется participantInn'}), 400

        days_threshold = data.get('daysThreshold', 30)

        expiring_codes = cz_api.get_expiring_codes(
            participant_inn=participant_inn,
            days_threshold=days_threshold
        )

        # Группировка по статусу
        expired = [c for c in expiring_codes if c['isExpired']]
        expiring_soon = [c for c in expiring_codes if not c['isExpired']]

        return jsonify({
            'success': True,
            'summary': {
                'total': len(expiring_codes),
                'expired': len(expired),
                'expiringSoon': len(expiring_soon),
                'threshold': days_threshold
            },
            'codes': expiring_codes
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@chestny_znak_bp.route('/api/chestny-znak/codes-info', methods=['POST'])
def get_codes_info():
    """
    Получение детальной информации о конкретных кодах

    Body:
    {
        "codes": ["CODE1", "CODE2", ...]  // Список кодов (макс. 1000)
    }
    """
    try:
        data = request.json
        codes = data.get('codes', [])

        if not codes:
            return jsonify({'error': 'Требуется список codes'}), 400

        info = cz_api.get_codes_info(codes)

        if info is not None:
            return jsonify({
                'success': True,
                'data': info
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Не удалось получить информацию'
            }), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@chestny_znak_bp.route('/api/chestny-znak/status', methods=['GET'])
def get_status():
    """
    Проверка статуса подключения к API
    """
    return jsonify({
        'connected': cz_api.token is not None,
        'sandbox': cz_api.use_sandbox,
        'base_url': cz_api.base_url
    })
