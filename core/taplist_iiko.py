"""Read the current iiko price orders and reference data for one V2 export."""
from datetime import datetime, timedelta, timezone
import hashlib
from uuid import UUID
import xml.etree.ElementTree as ET

import requests

MSK = timezone(timedelta(hours=3))


def fetch_price_sources():
    # Lazy config import lets isolated tests use only the deterministic pricing code.
    from config import IIKO_BASE_URL, IIKO_LOGIN, IIKO_PASSWORD
    if not IIKO_LOGIN or not IIKO_PASSWORD:
        raise RuntimeError('Не настроено подключение к iiko')
    checked = datetime.now(MSK)
    day = checked.date()
    token = None
    with requests.Session() as session:
        def get(path, params=None, xml=False):
            query = dict(params or {})
            if token:
                query['key'] = token
            try:
                response = session.get(IIKO_BASE_URL + path, params=query,
                    headers={'Accept': ('*/*' if path in ('/auth', '/logout') else
                                        'application/xml' if xml else 'application/json')},
                    timeout=(5, 35), allow_redirects=False)
                if response.status_code != 200:
                    raise RuntimeError(f'iiko: HTTP {response.status_code}')
                if xml:
                    return response.text
                payload = response.json()
                if isinstance(payload, dict) and 'result' in payload:
                    if payload['result'] != 'SUCCESS':
                        raise RuntimeError('iiko отклонил запрос справочника')
                    return payload['response']
                return payload
            except requests.RequestException:
                # Exception URLs may contain the authentication token.
                raise RuntimeError('Не удалось получить актуальные данные iiko') from None

        try:
            raw = get('/auth', {'login': IIKO_LOGIN,
                'pass': hashlib.sha1(IIKO_PASSWORD.encode()).hexdigest()}, xml=True).strip()
            if raw.startswith('<'):
                raw = ''.join(ET.fromstring(raw).itertext()).strip()
            token = str(UUID(raw))
            period = {'dateFrom': str(day), 'dateTo': str(day + timedelta(days=1))}
            prices = get('/v2/price', {**period, 'includeOutOfSale': 'true'})
            charts = get('/v2/assemblyCharts/getAll', {**period,
                'includeDeletedProducts': 'false', 'includePreparedCharts': 'true'})
            groups = get('/corporation/groups', xml=True)
            products = get('/v2/entities/products/list', {'types': 'DISH', 'includeDeleted': 'false'})
            product_groups = get('/v2/entities/products/group/list', {'includeDeleted': 'false'})
            scales = get('/v2/entities/products/productScales', {'includeDeletedProducts': 'false'})
            if datetime.now(MSK).date() != day:
                raise RuntimeError('Сменилась дата прайса: повторите выгрузку')
            return {'date': str(day), 'checked_at': checked.isoformat(), 'prices': prices,
                    'charts': charts['preparedCharts'], 'groups': groups,
                    'products': products, 'product_groups': product_groups, 'scales': scales}
        finally:
            if token:
                try:
                    get('/logout', xml=True)
                except RuntimeError:
                    pass
