"""Сохранённые ответы Opus → контрольный прогон Astra без Claude API и доставки.

По умолчанию только инвентаризация, без сети. --run запускает выбранные --ids;
рабочий MCP допускается только с readOnlyHint=true. Карточки валидируются локально.
Старый ответ — материал для оценки полноты, не безусловная истина: живые данные
могли измениться. Отчёт требует ручной сверки цифр, периода и источников.
Частные ответы/отчёты хранятся вне Git. Секреты — только environment variables.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kultura_bot import settings
from kultura_bot.engine import agent, astra, providers, tools
from kultura_bot.engine.site import Site, SiteError
from kultura_bot.engine.store import Store


def cases_from_saved(data):
    cases = []
    reports = data.get('reports', {})
    web = {item['question']: item for item in data.get('web', [])}
    for record in data.get('records', []):
        question = str(record.get('question') or '').strip()
        # Короткое продолжение и служебные команды без истории не самостоятельный тест.
        if len(question) < 30 or question.startswith('/'):
            continue
        reference_cards = []
        for card in record.get('cards', []):
            if card.get('report_id') in reports:
                reference_cards.append(reports[card['report_id']])
        reference_cards += web.get(question, {}).get('cards', [])
        cases.append({'id': record['uid'], 'question': question, 'asked_at': record.get('asked_at', ''),
                      'mode': record.get('mode', 'answer'), 'reference_answer': record.get('answer', ''),
                      'reference_cards': reference_cards, 'reference_model': record.get('model', ''),
                      'reference_cost_usd': record.get('cost_usd', 0), 'rating': record.get('rating', ''),
                      'reference_tools': sorted({c['name'] for c in record.get('calls', []) if c.get('name')})})
    return cases


class ReadOnlySite:
    """Закрытая граница прогона: не может отправлять сообщения или менять бизнес-данные."""
    def __init__(self, source):
        self.source = source
        self.allowed = set()
        self.cards = []
        self.denied = []

    def instructions(self, connector='/mcp'):
        return self.source.instructions(connector)

    def tools(self, connector='/mcp'):
        selected = []
        for tool in self.source.tools(connector):
            name = tool['name']
            if name in settings.HIDDEN_TOOLS:
                continue
            if name in tools.SENDING_TOOLS or (tool.get('annotations') or {}).get('readOnlyHint') is True:
                selected.append(tool)
                if name not in tools.SENDING_TOOLS:
                    self.allowed.add(name)
        return selected

    def call_tool(self, name, args):
        if name in tools.SENDING_TOOLS:
            from kultura_bot.charts import reports, spec
            try:
                value = reports.normalize_report(args.get('report')) if name == tools.REPORT_TOOL else spec.normalize(args.get('chart'))
            except ValueError as exc:
                return {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]}
            self.cards.append({'tool': name, 'body': value})
            key = 'report_id' if name == tools.REPORT_TOOL else 'chart_id'
            return {'content': [{'type': 'text', 'text': json.dumps({key: 'eval-' + str(len(self.cards)),
                                                                    'format': 'local'})}]}
        if name not in self.allowed:
            self.denied.append(name)
            raise SiteError('denied', 'Контрольный прогон: действие запрещено, доступны только инструменты чтения.')
        return self.source.call_tool(name, args)

    def web_card(self, qid, name, args):
        if name not in tools.SENDING_TOOLS:
            raise SiteError('denied', 'Неизвестный вид карточки')
        return self.call_tool(name, args)


def private_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Защита и при перезаписи существующего файла.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as out:
        json.dump(value, out, ensure_ascii=False, indent=2)


def evaluate(case, client, catalog, site, store, budget):
    """Reference answer не входит в запрос модели: сравнение делается после генерации."""
    site.cards.clear()
    site.denied.clear()
    spend = agent.Spend(limit=budget)
    ctx = tools.ToolContext(site=site, chat_id='eval', allowed=catalog.bot.toolset.names,
                            spend=spend, user='evaluation', report_mode=case['mode'] == 'report')
    dated = ('Контрольный вопрос был задан ' + case['asked_at'] + '. Относительные даты в нём считай от этой даты. '
             'Если данные относятся к текущему состоянию и прошлое восстановить нельзя, явно скажи это. '
             'Работаем только на чтение.\n' + case['question'])
    usage = []

    def on_usage(model, tokens, cost):
        usage.append({'model': model, 'tokens': dict(tokens), 'cost_usd': cost})

    def run_agent(name, task):
        return agent.run_agent(client, catalog.agents[name], task, parent=ctx, store=store,
                               header='Дата исходного вопроса: ' + case['asked_at'], on_usage=on_usage)
    ctx.run_agent = run_agent
    started = time.monotonic()
    status, error = 'done', ''
    try:
        result = agent.run_turn(client, system_text=catalog.bot.system, tool_list=catalog.bot.toolset.defs,
                                history=[], user_content=[{'type': 'text', 'text': dated}], ctx=ctx, store=store,
                                max_rounds=12, on_usage=on_usage)
    except agent.BudgetExceeded as exc:
        status, error = 'budget', str(exc)
        result = agent.TurnResult(text='', messages=[], notes=['daily_budget'])
    return {**case, 'status': status, 'error': error, 'usage': usage,
            'candidate_model': client.model, 'candidate_answer': result.text,
            'candidate_cards': list(site.cards), 'cost_usd': spend.usd, 'steps': spend.steps,
            'seconds': round(time.monotonic() - started, 1), 'notes': result.notes,
            'used_tools': sorted({c['name'] for c in ctx.calls}), 'blocked_tools': list(site.denied),
            'data_basis': 'live_readonly_at_original_dates; historical snapshots are not available',
            'quality': 'requires_review',
            'review': ['Совпадают ли период и бары?', 'Подтверждены ли цифры источником?',
                       'Объяснены ли расхождения с сохранённым ответом?', 'Полны ли отчёт, графики и пояснения?']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--ids', default='', help='ID сохранённых вопросов через запятую; обязательно для --run')
    parser.add_argument('--max-cost-usd', type=float, default=0.5, help='Мягкий предел всего прогона, проверяется между шагами')
    parser.add_argument('--max-output-tokens', type=int, default=4096, help='Для короткой проверки; для качества использовать 64000')
    args = parser.parse_args(argv)
    cases = cases_from_saved(json.loads(args.baseline.read_text(encoding='utf-8')))
    if not args.run:
        private_json(args.out, {'status': 'prepared', 'cases': cases, 'requires': 'KULTURA_BOT_OPENAI_KEY'})
        print(f'Подготовлено {len(cases)} самостоятельных вопросов. API не вызывался.')
        return 0
    ids = set(filter(None, args.ids.split(',')))
    if not ids or ids - {c['id'] for c in cases}:
        parser.error('Укажите существующие --ids из подготовленного файла')
    if not 0 < args.max_cost_usd <= 10 or not 256 <= args.max_output_tokens <= 64000:
        parser.error('Бюджет должен быть >0 и <=10 USD; max-output-tokens: 256..64000')
    api_key = os.environ.get('KULTURA_BOT_OPENAI_KEY', '')
    site_key = os.environ.get('KULTURA_BOT_KEY', '')
    if not api_key or not site_key:
        print('Нужны KULTURA_BOT_OPENAI_KEY и KULTURA_BOT_KEY в окружении. Значения не выводятся.')
        return 2
    kind, _ = astra.check_key(api_key, settings.OPENAI_MODEL)
    if kind != 'ok':
        print('Проверка доступа к Astra: ' + kind)
        return 2
    settings.MAX_TOKENS = args.max_output_tokens
    settings.DAILY_BUDGET_USD = args.max_cost_usd
    selected = providers.selection({'provider': 'openai'})
    client = providers.client_for(api_key, selected)
    site = ReadOnlySite(Site(settings.SITE_URL, site_key))
    catalog = tools.load_catalog(site)
    outcomes = []
    with tempfile.TemporaryDirectory(prefix='kultura-astra-eval-') as folder:
        store = Store(str(Path(folder) / 'eval.db'))
        try:
            for case in cases:
                if case['id'] not in ids:
                    continue
                remaining = args.max_cost_usd - store.spent_on()
                if remaining <= 0:
                    outcomes.append({'id': case['id'], 'status': 'budget'})
                    continue
                try:
                    spent_before = store.spent_on()
                    outcomes.append(evaluate(case, client, catalog, site, store, remaining))
                except Exception as exc:
                    kind, message = providers.describe_error(exc, selected, (api_key, site_key))
                    outcomes.append({'id': case['id'], 'status': 'error', 'kind': kind, 'error': message,
                                     'cost_usd': store.spent_on() - spent_before})
                private_json(args.out, {'status': 'requires_review', 'results': outcomes})
        finally:
            store.close()
    print(f'Прогон завершён: {len(outcomes)}. Отчёт сохранён локально; отправок в Telegram нет.')
    return 1 if any(o.get('status') in ('error', 'budget') for o in outcomes) else 0


if __name__ == '__main__':
    raise SystemExit(main())
