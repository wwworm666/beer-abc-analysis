"""Кто может открыть график в мини-приложении: участники чата, куда он отправлен.

## Правило

Решение владельца 2026-10-18: «не буду вписывать айди каждого пользователя руками».
Список допущенных не ведём — доступ выводится из того, кто видит картинку:

- личный чат (chat_id > 0) — только этот человек: id из initData == chat_id;
- группа (chat_id < 0) — те, кто сейчас в группе: getChatMember(chat_id, user_id) со
  статусом creator, administrator, member или restricted с is_member. Вышел из группы —
  доступа больше нет; бота удалили из группы — проверить нельзя, доступа нет.

Интерактивная версия не открывает цифры никому новому: картинку в чате видят те же люди.
Пересланная в другой чат картинка тянет за собой кнопку, но график откроется только
участникам исходного чата.

## Кэш

Ответ Telegram запоминается в памяти воркера: «состоит» — на MEMBER_OK_CACHE_S (5 минут),
«не состоит» — на MEMBER_NO_CACHE_S (1 минута, чтобы только что добавленный в группу ждал
недолго). Нет связи с Telegram — AccessCheckError (API отвечает 503 «попробуйте ещё раз»),
а не «нет доступа»: сбой сети не должен выглядеть как запрет.
"""
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

MEMBER_OK_CACHE_S = 300
MEMBER_NO_CACHE_S = 60
MEMBER_CACHE_MAX = 2000          # записей на воркер; переполнение — кэш сбрасывается целиком
MEMBER_STATUSES = ('creator', 'administrator', 'member')

GetChatMember = Callable[[str, int, str], Optional[Dict[str, Any]]]

_cache: Dict[Tuple[str, int], Tuple[bool, float]] = {}
_lock = threading.Lock()


class AccessCheckError(Exception):
    """Telegram не ответил — проверить участие в чате нельзя."""


def _get_chat_member(chat_id: str, user_id: int, token: str) -> Optional[Dict[str, Any]]:
    from core.open_check_telegram import api_call
    return api_call('getChatMember', {'chat_id': chat_id, 'user_id': user_id}, token=token)


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _member(answer: Dict[str, Any]) -> bool:
    if not answer.get('ok'):
        return False                       # «user not found», «chat not found», бот не в группе
    result = answer.get('result') or {}
    status = result.get('status')
    return status in MEMBER_STATUSES or (status == 'restricted' and bool(result.get('is_member')))


def can_view(chat_id: Any, user_id: int, token: str, *, get_member: GetChatMember = None,
             now: Optional[float] = None) -> bool:
    """Может ли человек user_id открыть график, отправленный в чат chat_id."""
    chat = str(chat_id or '').strip()
    if not chat:
        return False
    if not chat.startswith('-'):
        return chat == str(user_id)        # личка: только сам получатель
    now = time.monotonic() if now is None else now
    key = (chat, int(user_id))
    with _lock:
        cached = _cache.get(key)
    if cached and cached[1] > now:
        return cached[0]
    answer = (get_member or _get_chat_member)(chat, int(user_id), token)
    if answer is None:
        raise AccessCheckError('Telegram не ответил')
    allowed = _member(answer)
    with _lock:
        if len(_cache) >= MEMBER_CACHE_MAX:
            _cache.clear()
        _cache[key] = (allowed, now + (MEMBER_OK_CACHE_S if allowed else MEMBER_NO_CACHE_S))
    return allowed
