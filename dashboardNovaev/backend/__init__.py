"""
Backend модуль для дашборда с поддержкой мультизаведений
"""
from .venues_config import VENUES, VENUE_KEYS_ORDERED, PHYSICAL_VENUES
from .venues_manager import VenuesManager

__all__ = ['VENUES', 'VENUE_KEYS_ORDERED', 'PHYSICAL_VENUES', 'VenuesManager']
