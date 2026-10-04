"""
Режимы доступа MCP после проверки безопасности (2026-09-28): что разрешено агенту
в коннекторах …/read и …/draft и какие проверки держит сервер, а не инструкция.

Self-runnable: `py -3 tests/test_mcp_modes.py` (совместимо с pytest).

Что проверяется:
- поверхность настоящего реестра: в режиме draft пишут ровно девять инструментов
  черновиков (с 2026-10-02 — и поиск картинок с прикреплением найденного, с 2026-10-04 —
  предложение связи кеги с Untappd), в режиме read — только сообщение владельцу;
  расширение списка — осознанная правка этого теста;
- сообщение владельцу (owner_notice) видно и вызывается в любом режиме, а чужие
  ссылки из его текста вырезаются (защита от фишинга через внедрённый текст);
- сценарий «план месяца» (mode_required='draft') не показывается в коннекторе
  …/read и не собирается там по имени;
- контент-план: в режиме draft повтор по дням недели — только для своего черновика;
- отзывы: в режиме draft меняется только черновик ответа, сам отзыв — нет.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.environ.setdefault('SESSION_COOKIE_SECURE', '0')

import test_mcp_protocol as tp  # noqa: E402  (окружение Env, разбор ответов)
from core.mcp import registry  # noqa: E402
from core.mcp.spec import PromptSpec, ToolSpec, allowed_in_mode, prompt_allowed_in_mode  # noqa: E402
from core.mcp.tools.common import NOTIFY_LINK_STUB, _strip_foreign_links  # noqa: E402

NO_ARGS = {'type': 'object', 'additionalProperties': False, 'properties': {}}

# Инструменты, которые пишут в режиме «чтение и черновики». Черновик остаётся внутри
# сервиса и никуда не уходит без утверждения владельца; сервер дополнительно пускает
# агента только к его собственным черновикам (guard_draft_mode, отзывы — только reply_draft).
EXPECTED_DRAFT_WRITES = {
    'content_material_create', 'content_material_update', 'content_placements_add',
    'content_placement_update', 'content_material_repeat', 'content_review_update',
    # 2026-10-02: картинки к постам. Поиск пишет файл поиска и тратит платный суточный предел
    # (150 на сеть, 60 на подключение) — поэтому запись, а не чтение. Прикрепление кладёт
    # картинку только в черновик агента (add_media -> guard_draft_mode); сервер качает только
    # вариант из своего файла поиска и только с проверенного публичного IP —
    # см. core/content_image_search.py.
    'content_image_search', 'content_media_add_found',
    # 2026-10-04: предложение связи кеги с Untappd — черновик до «Верно» администратора на
    # /taps/untappd; в режиме draft предложение сотрудника не заменяется (core/untappd_live).
    'stocks_untappd_propose',
}
EXPECTED_OWNER_NOTICE = {'common_notify_owner'}


def _notice(args, principal):
    return {'sent': True}


def _modules():
    common = registry.module_from_parts(
        tools=[ToolSpec(name='common_notify_owner', domain='common', title='Владельцу',
                        description='Сообщение владельцу: разрешено в любом режиме доступа.',
                        input_schema=NO_ARGS, handler=_notice, read_only=False, destructive=True,
                        open_world=True, owner_notice=True)],
        instructions='ОБЩИЕ ПРАВИЛА ТЕСТА.')
    content = registry.module_from_parts(
        tools=[ToolSpec(name='content_read', domain='content', title='Чтение',
                        description='Инструмент только для чтения в тесте режимов.',
                        input_schema=NO_ARGS, handler=_notice)],
        prompts=[PromptSpec(name='content_plan_month', domain='content', title='План',
                            description='Создаёт черновики', render=lambda a: 'план',
                            mode_required='draft'),
                 PromptSpec(name='content_digest', domain='content', title='Разбор',
                            description='Только читает', render=lambda a: 'разбор')],
        instructions='ПРАВИЛА КОНТЕНТА.')
    return {'common': common, 'content': content}


def test_real_registry_mode_surface():
    registry.use_modules(None)
    registry.load(force=True)
    tools = registry.all_tools()
    draft_writes = {t.name for t in tools if not t.read_only and allowed_in_mode(t, 'draft')
                    and not t.owner_notice}
    assert draft_writes == EXPECTED_DRAFT_WRITES, sorted(draft_writes ^ EXPECTED_DRAFT_WRITES)
    read_writes = {t.name for t in tools if not t.read_only and allowed_in_mode(t, 'read')}
    assert read_writes == EXPECTED_OWNER_NOTICE, read_writes
    assert {t.name for t in tools if t.owner_notice} == EXPECTED_OWNER_NOTICE
    for t in tools:
        if t.destructive or t.open_world:
            assert not t.draft_write, t.name
    month_prompt = registry.get_prompt('content_plan_month')
    assert month_prompt is not None and month_prompt.mode_required == 'draft'
    assert not prompt_allowed_in_mode(month_prompt, 'read') and prompt_allowed_in_mode(month_prompt, 'draft')


def test_owner_notice_visible_and_callable_in_read_mode():
    with tp.Env(_modules()) as env:
        names = tp._names(env.rpc('/mcp/content/read', 'tools/list'))
        assert names == ['common_notify_owner', 'content_read'], names
        result = tp._result(env.rpc('/mcp/content/read', 'tools/call', {'name': 'common_notify_owner'}))
        assert result['isError'] is False and json.loads(result['content'][0]['text']) == {'sent': True}


def test_prompts_filtered_by_mode():
    with tp.Env(_modules()) as env:
        def prompt_names(path):
            return [p['name'] for p in tp._result(env.rpc(path, 'prompts/list'))['prompts']]
        assert prompt_names('/mcp/content/read') == ['content_digest']
        assert prompt_names('/mcp/content/draft') == ['content_plan_month', 'content_digest']
        assert prompt_names('/mcp/content') == ['content_plan_month', 'content_digest']
        denied = env.rpc('/mcp/content/read', 'prompts/get', {'name': 'content_plan_month'})
        err = tp._error(denied)
        assert 'Чтение и черновики' in err['message'] and 'Только чтение' in err['message'], err
        ok = tp._result(env.rpc('/mcp/content/draft', 'prompts/get', {'name': 'content_plan_month'}))
        assert ok['messages'][0]['content']['text'] == 'план'


def test_strip_foreign_links():
    cases = {
        'План: https://beerkultura.ru/content-plan?month=2026-11&origin=agent':
            'План: https://beerkultura.ru/content-plan?month=2026-11&origin=agent',
        'Срочно https://evil.example/login': 'Срочно ' + NOTIFY_LINK_STUB,
        'или www.evil.com/x': 'или ' + NOTIFY_LINK_STUB,
        'голый evil-site.ru/pay тут': 'голый ' + NOTIFY_LINK_STUB + ' тут',
        'сайт пиво.рф/акция': 'сайт ' + NOTIFY_LINK_STUB,
        'Пиво 5.2% и 0.33 л, т.е. норм': 'Пиво 5.2% и 0.33 л, т.е. норм',
        'beerkultura.ru/reviews': 'beerkultura.ru/reviews',
        # Кириллические зоны из явного списка и punycode (проверка 2026-09-28: раньше
        # проходили evil.рус и пиво.москва).
        'зайди на evil.рус/login': 'зайди на ' + NOTIFY_LINK_STUB,
        'пиво.москва и акция.онлайн': NOTIFY_LINK_STUB + ' и ' + NOTIFY_LINK_STUB,
        'бар.дети, пиво.сайт, клуб.орг, мой.ком': ', '.join([NOTIFY_LINK_STUB] * 4),
        'сайт.укр сайт.бел сайт.срб сайт.мкд сайт.қаз': ' '.join([NOTIFY_LINK_STUB] * 5),
        'ПИВО.РФ/Скидка': NOTIFY_LINK_STUB,
        'магазин.бг, пиво.мон, пиво.ею, храм.католик': ', '.join([NOTIFY_LINK_STUB] * 4),
        'evil.xn--p1ai/pay и xn--80ak6aa92e.com': NOTIFY_LINK_STUB + ' и ' + NOTIFY_LINK_STUB,
        'sub.пиво.рф': NOTIFY_LINK_STUB,
        # Голые IPv4 (с портом и путём); точка в конце фразы остаётся.
        'Сервер 185.12.3.4/login': 'Сервер ' + NOTIFY_LINK_STUB,
        'панель 10.0.0.1:8080/admin, резерв 192.168.1.254.': 'панель ' + NOTIFY_LINK_STUB + ', резерв '
                                                               + NOTIFY_LINK_STUB + '.',
        'https://1.2.3.4/x': NOTIFY_LINK_STUB,
        # Не ссылки: даты, версии, сокращения, города, слова после «зоны».
        'Смена 28.09.2026, версия 2.1.3, сборка 1.2.3.4.5': 'Смена 28.09.2026, версия 2.1.3, сборка 1.2.3.4.5',
        'г.Москва, т.е. т.д. и т.п.': 'г.Москва, т.е. т.д. и т.п.',
        'выручка 1 250.50 руб., 999.1.1.1 не адрес': 'выручка 1 250.50 руб., 999.1.1.1 не адрес',
        'BEERKULTURA.RU/menu и www.beerkultura.ru': 'BEERKULTURA.RU/menu и www.beerkultura.ru',
    }
    for text, expected in cases.items():
        assert _strip_foreign_links(text) == expected, (text, _strip_foreign_links(text))


def test_content_repeat_only_own_draft_in_draft_mode():
    import test_content_plan as tcp
    import core.content_plan as cp
    store = tcp._store()
    agent_draft = dict(tcp.AGENT, mcp_mode='draft')
    owners = tcp._material(store, title='Материал владельца', planned_date='2026-10-09')
    try:
        store.repeat(owners['id'], [4], tcp.MONTH, agent_draft)
    except cp.ContentPlanConflict:
        pass
    else:
        raise AssertionError('в режиме draft агент размножил материал владельца')
    own = store.create_material({'month': tcp.MONTH, 'title': 'Таплист пятницы', 'planned_date': '2026-10-09',
                                 'base_text': 'Текст'}, agent_draft)
    result = store.repeat(own['id'], [4], tcp.MONTH, agent_draft)
    created = result.get('created') or []
    assert created, result
    for mid in created:
        assert store.get_material(mid)['origin'] == 'agent'


def test_reviews_only_reply_draft_in_draft_mode():
    import test_guest_reviews as tgr
    from core.guest_reviews import ReviewConflict
    store = tgr._store()
    review = tgr._add(store, bar='kremenchugskaya', rating=5, text='Отличный вечер', author='Ира')
    agent_draft = {'login': 'owner', 'via_mcp': True, 'mcp_mode': 'draft'}
    saved = store.update(review['id'], {'reply_draft': 'Спасибо, Ира!'}, agent_draft)
    assert saved['reply_draft'] == 'Спасибо, Ира!'
    for fields in ({'text': 'Ужасно'}, {'rating': 1}, {'reply_draft': 'x', 'bar': 'bolshoy'}):
        try:
            store.update(review['id'], fields, agent_draft)
        except ReviewConflict:
            pass
        else:
            raise AssertionError(f'в режиме draft агент изменил отзыв: {fields}')
    full = dict(agent_draft, mcp_mode='full')
    assert store.update(review['id'], {'rating': 4}, full)['rating'] == 4


if __name__ == '__main__':
    import inspect
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith('test_') and inspect.isfunction(fn):
            try:
                fn()
                print(f'ok   {name}')
            except Exception as e:  # noqa: BLE001
                failed += 1
                import traceback
                traceback.print_exc()
                print(f'FAIL {name}: {e!r}')
    sys.exit(1 if failed else 0)
