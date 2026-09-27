"""ABC/XYZ анализ кухни: один расчёт на всю страницу /kitchen.

Что это
-------
Страница «Кухня» — клон «Фасовки» (решение владельца 2026-09-27: «полное
клонирование интерфейса, только про еду»). Считает тот же ответ: сводка, все
категории, все позиции, группы решений, баланс и потери. Разрез — один бар или
«Общая».

Формулы общие с фасовкой
------------------------
KitchenAnalysis наследует core/packaging_analysis.py::PackagingAnalysis: сбор
строк, сведение баров в «Общую», ABC по выручке, XYZ по недельным продажам,
группы решений, категории и итоги — один код. Отличаются только:

- пороги наценки — 180% (минимум сети и буква A) и 150% (граница B/C),
  core/abc_thresholds.py, KITCHEN_MARKUP_A_MIN / KITCHEN_MARKUP_B_MIN;
- категория — самая глубокая заполненная группа под «ЕДА»: третий уровень
  дерева, если его нет — второй (у блюд кухни дерево мельче, чем у пива);
- соусы-модификаторы (DishType = MODIFIER) не становятся позициями: их отдают к
  блюдам бесплатно, и в таблице они навсегда висели бы в «Сверить учёт».
  Решение владельца 2026-09-27. Их количество и закупка уходят в блок
  modifiers ответа и в сверку склада;
- баланс и потери — в рублях по закупке (core/kitchen_losses.py).

Файлы
-----
- core/kitchen_loader.py — сырьё (продажи + проводки) под одним ключом кэша
- routes/analysis.py — эндпоинт /api/kitchen
- docs/kitchen.md — формулы, примеры, оговорки
"""

from core.abc_thresholds import (
    KITCHEN_MARKUP_A_MIN,
    KITCHEN_MARKUP_B_MIN,
    UNCATEGORIZED_KITCHEN,
)
from core.kitchen_losses import build_kitchen_losses
from core.packaging_analysis import PackagingAnalysis, _num, _text

# Значение поля DishType у модификатора в OLAP SALES (docs/iiko-api/
# kody-bazovykh-tipov.md, «Тип товара»: DISH, GOOD, MODIFIER).
MODIFIER_TYPE = 'MODIFIER'


class KitchenAnalysis(PackagingAnalysis):
    """Расчёт страницы кухни по строкам OLAP-отчёта продаж группы «ЕДА».

    rows — строки iiko (Store.Name, DishName, DishGroup.SecondParent,
    DishGroup.ThirdParent, DishType, OpenDate.Typed, DishId, DishAmountInt,
    DishDiscountSumInt, ProductCostBase.ProductCost). transactions — проводки
    склада группы «ЕДА» с суммами (Sum.Outgoing, Sum.Incoming).
    """

    A_MIN = KITCHEN_MARKUP_A_MIN
    B_MIN = KITCHEN_MARKUP_B_MIN
    UNCATEGORIZED_LABEL = UNCATEGORIZED_KITCHEN

    def build(self, bar_name=None):
        # Модификаторы копятся в _skip_row во время сбора строк разреза.
        self._modifiers = {}
        block = super().build(bar_name)
        items = sorted(self._modifiers.values(), key=lambda m: (-m['Cost'], m['Name']))
        block['modifiers'] = {
            'count': len(items),
            'qty': sum(m['Qty'] for m in items),
            'revenue': sum(m['Revenue'] for m in items),
            'cost': sum(m['Cost'] for m in items),
            'items': items,
        }
        return block

    def _category_of(self, row):
        """Третий уровень дерева, если он есть, иначе второй, иначе подпись."""
        third = _text(row.get('DishGroup.ThirdParent'))
        second = _text(row.get('DishGroup.SecondParent'))
        return third or second or self.UNCATEGORIZED_LABEL

    def _skip_row(self, row):
        """Модификатор — не позиция: его сумма копится отдельно."""
        if _text(row.get('DishType')) != MODIFIER_TYPE:
            return False
        name = _text(row.get('DishName'))
        entry = self._modifiers.get(name)
        if entry is None:
            entry = self._modifiers[name] = {'Name': name, 'Qty': 0.0, 'Revenue': 0.0, 'Cost': 0.0}
        entry['Qty'] += _num(row.get('DishAmountInt'))
        entry['Revenue'] += _num(row.get('DishDiscountSumInt'))
        entry['Cost'] += _num(row.get('ProductCostBase.ProductCost'))
        return True

    def _losses(self, rows, bar_name, totals):
        modifiers_cost = sum(m['Cost'] for m in self._modifiers.values())
        return build_kitchen_losses(self.transactions, bar_name, rows, totals['cost'],
                                    modifiers_cost)
