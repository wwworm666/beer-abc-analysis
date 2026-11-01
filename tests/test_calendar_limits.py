"""Календари без зашитых дат (план единого виджета, этап 0, 2026-11-01).

На «Сотрудниках» предел календаря был зашит датой 31.12.2026: с 1 января 2027 года новые даты
было бы не выбрать. Предел — «сегодня» или первый/последний день данных с сервера, а не год в
коде. Проверка ищет в шаблонах и скриптах `maxDate`/`minDate` с годом-числом.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# maxDate: new Date(2026, …) | maxDate: '2026-12-31' | minDate: "2025-…"
HARD_LIMIT = re.compile(r"""(?:max|min)Date\s*:\s*(?:new\s+Date\s*\(\s*20\d\d|['"]20\d\d)""")


def _sources():
    for base, exts in (('templates', ('.html',)), ('static/js', ('.js',))):
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, base)):
            for name in files:
                if name.endswith(exts):
                    yield os.path.join(dirpath, name)


class CalendarLimitsTest(unittest.TestCase):
    def test_no_hard_coded_year_in_calendar_limits(self):
        found = []
        for path in _sources():
            with open(path, encoding='utf-8') as fh:
                for no, line in enumerate(fh, 1):
                    if HARD_LIMIT.search(line):
                        found.append('%s:%d: %s' % (os.path.relpath(path, ROOT), no, line.strip()[:90]))
        self.assertEqual(found, [], 'зашитый год в пределе календаря:\n' + '\n'.join(found))

    def test_employee_and_salary_calendars_stop_at_today(self):
        """Своего календаря нет — период из полосы «Бар и период» (этап 4 плана): её пределы —
        последний доступный день и первый день данных с сервера (core/periods.page_config)."""
        for name in ('employee.html',):
            with open(os.path.join(ROOT, 'templates', name), encoding='utf-8') as fh:
                text = fh.read()
            self.assertNotIn('flatpickr', text, name)
            self.assertIn('kultura_strip(', text, name)
        for name in ('bonus.html',):
            with open(os.path.join(ROOT, 'templates', name), encoding='utf-8') as fh:
                self.assertIn("maxDate: 'today'", fh.read(), name)


if __name__ == '__main__':
    unittest.main()
