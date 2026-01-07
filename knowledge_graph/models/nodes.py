"""
Pydantic models for graph nodes.
Each model represents a node type in Neo4j.
"""

from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


class Beer(BaseModel):
    """Пиво / Beer node"""
    name: str = Field(..., description="Название пива")
    brewery: Optional[str] = Field(None, description="Пивоварня")
    style: Optional[str] = Field(None, description="Стиль пива")
    abv: Optional[float] = Field(None, description="Крепость %")
    ibu: Optional[int] = Field(None, description="Горечь IBU")
    description: Optional[str] = Field(None, description="Описание")
    untappd_url: Optional[str] = Field(None, description="Ссылка на Untappd")
    country: Optional[str] = Field(None, description="Страна")

    def to_cypher_props(self) -> dict:
        """Convert to Cypher properties dict"""
        props = {"name": self.name}
        if self.abv is not None:
            props["abv"] = self.abv
        if self.ibu is not None:
            props["ibu"] = self.ibu
        if self.description:
            props["description"] = self.description
        if self.untappd_url:
            props["untappd_url"] = self.untappd_url
        if self.country:
            props["country"] = self.country
        return props


class Brewery(BaseModel):
    """Пивоварня / Brewery node"""
    name: str = Field(..., description="Название пивоварни")
    country: Optional[str] = Field(None, description="Страна")

    def to_cypher_props(self) -> dict:
        props = {"name": self.name}
        if self.country:
            props["country"] = self.country
        return props


class BeerStyle(BaseModel):
    """Стиль пива / Beer Style node"""
    name: str = Field(..., description="Название стиля")
    category: Optional[str] = Field(None, description="Категория (Lager, Ale, etc)")

    def to_cypher_props(self) -> dict:
        props = {"name": self.name}
        if self.category:
            props["category"] = self.category
        return props


class Bar(BaseModel):
    """Бар / Bar node"""
    id: str = Field(..., description="ID бара (bar1, bar2, etc)")
    name: str = Field(..., description="Название бара")
    tap_count: int = Field(0, description="Количество кранов")

    def to_cypher_props(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "tap_count": self.tap_count
        }


class Tap(BaseModel):
    """Кран / Tap node"""
    id: str = Field(..., description="Уникальный ID (bar1_tap1)")
    bar_id: str = Field(..., description="ID бара")
    tap_number: int = Field(..., description="Номер крана")
    status: str = Field("empty", description="Статус: active, empty")

    def to_cypher_props(self) -> dict:
        return {
            "id": self.id,
            "bar_id": self.bar_id,
            "tap_number": self.tap_number,
            "status": self.status
        }


class Keg(BaseModel):
    """Кег / Keg node"""
    name: str = Field(..., description="Название кега из iiko")
    volume_liters: Optional[float] = Field(None, description="Объем в литрах")
    beer_name: Optional[str] = Field(None, description="Название пива")

    def to_cypher_props(self) -> dict:
        props = {"name": self.name}
        if self.volume_liters:
            props["volume_liters"] = self.volume_liters
        if self.beer_name:
            props["beer_name"] = self.beer_name
        return props


class Dish(BaseModel):
    """Позиция меню / Dish node (from iiko)"""
    name: str = Field(..., description="Название позиции в iiko")
    category: Optional[str] = Field(None, description="Категория")

    def to_cypher_props(self) -> dict:
        props = {"name": self.name}
        if self.category:
            props["category"] = self.category
        return props


class Waiter(BaseModel):
    """Официант / Waiter node"""
    name: str = Field(..., description="Имя официанта")

    def to_cypher_props(self) -> dict:
        return {"name": self.name}


class Sale(BaseModel):
    """Продажа / Sale node"""
    id: str = Field(..., description="Уникальный ID продажи")
    timestamp: datetime = Field(..., description="Дата и время")
    dish_name: str = Field(..., description="Название позиции")
    quantity: float = Field(..., description="Количество")
    revenue: float = Field(..., description="Выручка")
    cost: float = Field(0, description="Себестоимость")
    margin: float = Field(0, description="Маржа")
    discount: float = Field(0, description="Скидка")
    bar_name: Optional[str] = Field(None, description="Название бара")
    waiter_name: Optional[str] = Field(None, description="Официант")

    def to_cypher_props(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "dish_name": self.dish_name,
            "quantity": self.quantity,
            "revenue": self.revenue,
            "cost": self.cost,
            "margin": self.margin,
            "discount": self.discount
        }


class Period(BaseModel):
    """Период / Period node (day, week, month)"""
    id: str = Field(..., description="ID периода (2024-01-15)")
    date: str = Field(..., description="Дата YYYY-MM-DD")
    year: int = Field(..., description="Год")
    month: int = Field(..., description="Месяц 1-12")
    week: int = Field(..., description="Неделя года 1-52")
    day_of_week: int = Field(..., description="День недели 0-6 (пн-вс)")
    day_name: str = Field(..., description="Название дня (Понедельник)")

    def to_cypher_props(self) -> dict:
        return {
            "id": self.id,
            "date": self.date,
            "year": self.year,
            "month": self.month,
            "week": self.week,
            "day_of_week": self.day_of_week,
            "day_name": self.day_name
        }


class DailyMetrics(BaseModel):
    """Метрики за день по бару / Daily Metrics node"""
    id: str = Field(..., description="ID (2024-01-15_bar1)")
    date: str = Field(..., description="Дата")
    bar_id: str = Field(..., description="ID бара")

    # Revenue metrics
    total_revenue: float = Field(0, description="Общая выручка")
    draft_revenue: float = Field(0, description="Выручка розлив")
    bottles_revenue: float = Field(0, description="Выручка фасовка")
    kitchen_revenue: float = Field(0, description="Выручка кухня")

    # Share metrics
    draft_share: float = Field(0, description="Доля розлива %")
    bottles_share: float = Field(0, description="Доля фасовки %")
    kitchen_share: float = Field(0, description="Доля кухни %")

    # Check metrics
    total_checks: int = Field(0, description="Количество чеков")
    avg_check: float = Field(0, description="Средний чек")

    # Margin metrics
    total_margin: float = Field(0, description="Общая маржа")
    avg_markup: float = Field(0, description="Средняя наценка %")
    draft_markup: float = Field(0, description="Наценка розлив %")
    bottles_markup: float = Field(0, description="Наценка фасовка %")
    kitchen_markup: float = Field(0, description="Наценка кухня %")

    # Loyalty
    loyalty_points: float = Field(0, description="Списания баллов")

    def to_cypher_props(self) -> dict:
        return {
            "id": self.id,
            "date": self.date,
            "bar_id": self.bar_id,
            "total_revenue": self.total_revenue,
            "draft_revenue": self.draft_revenue,
            "bottles_revenue": self.bottles_revenue,
            "kitchen_revenue": self.kitchen_revenue,
            "draft_share": self.draft_share,
            "bottles_share": self.bottles_share,
            "kitchen_share": self.kitchen_share,
            "total_checks": self.total_checks,
            "avg_check": self.avg_check,
            "total_margin": self.total_margin,
            "avg_markup": self.avg_markup,
            "draft_markup": self.draft_markup,
            "bottles_markup": self.bottles_markup,
            "kitchen_markup": self.kitchen_markup,
            "loyalty_points": self.loyalty_points
        }
