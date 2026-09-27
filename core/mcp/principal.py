"""Кто вызывает инструмент: владелец, токен и разрешённые домены.

Principal создают только проверки токенов (core/mcp/tokens.py для статических,
core/mcp/oauth.py для OAuth). Дальше он едет в протокол, мост и журнал.

Правило доступа (решение владельца 2026-09-27, «доступ пока только для меня»):
токен действует, только пока его владелец — активный администратор. Проверка
повторяется на КАЖДОМ вызове (core/mcp/auth.py), поэтому снятие флага
администратора или отключение аккаунта сразу останавливает все его токены;
удаление, отключение и снятие админа ещё и отзывают их (routes/auth.py), чтобы
возврат флага не оживлял старые токены.

mode — режим доступа токена (core/mcp/spec.MODES: read / draft / full). Действует
более строгий из режима токена и режима адреса коннектора (protocol.py).
"""
from dataclasses import dataclass, field
from typing import Optional, Tuple

ALL_DOMAINS = '*'


@dataclass(frozen=True)
class Principal:
    user_id: int
    login: str
    display_name: str
    token_id: str                 # 'st_…' — статический токен, 'oa_…' — OAuth access token
    token_kind: str               # 'static' | 'oauth'
    client_name: str              # имя токена или имя OAuth-клиента («Claude», «Claude Code»)
    domains: Tuple[str, ...] = field(default=(ALL_DOMAINS,))
    expires_at: Optional[str] = None   # ISO; None — бессрочный статический токен
    mode: str = 'full'                 # режим токена: read | draft | full

    def allows(self, domain: Optional[str]) -> bool:
        """Можно ли этим токеном ходить в домен. None — полный коннектор /mcp."""
        if ALL_DOMAINS in self.domains:
            return True
        if domain is None:
            return False            # полный коннектор требует токен на все домены
        return domain in self.domains

    def label(self) -> str:
        """Подпись для журналов: «login · агент (имя клиента)»."""
        return f'{self.login} · агент ({self.client_name})'
