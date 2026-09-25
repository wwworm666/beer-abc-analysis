"""Очередь и разбор команд таплист-бота. Сети нет."""
import pytest

from core.taplist_polling import WebhookConflict, consume_batch, label_bars, plan_update


def test_empty_and_error_keep_offset():
    assert consume_batch(None, 7, lambda upd: None) == 7
    assert consume_batch({'ok': False, 'error_code': 500}, 7, lambda upd: None) == 7
    assert consume_batch({'ok': True, 'result': []}, None, lambda upd: None) is None


def test_offset_moves_past_every_update():
    seen = []
    offset = consume_batch(
        {'ok': True, 'result': [{'update_id': 4, 'message': {}}, {'update_id': 5}]},
        None,
        seen.append,
    )
    assert offset == 6
    assert [item['update_id'] for item in seen] == [4, 5]


def test_bad_update_does_not_stall_the_queue():
    seen = []
    errors = []

    def feed(upd):
        seen.append(upd['update_id'])
        if upd['update_id'] == 1:
            raise RuntimeError('boom')

    offset = consume_batch(
        {'ok': True, 'result': [{'update_id': 1}, {'update_id': 2}]},
        0,
        feed,
        errors.append,
    )
    assert offset == 3
    assert seen == [1, 2]
    assert len(errors) == 1


def test_webhook_conflict_does_not_move_offset():
    with pytest.raises(WebhookConflict):
        consume_batch({'ok': False, 'error_code': 409, 'description': 'conflict'}, 3, lambda upd: None)


def test_start_and_button_plan_without_network():
    assert plan_update({'message': {'chat': {'id': 5}, 'text': '/start@kult_taplist_bot'}}) == [
        {'op': 'menu', 'chat_id': 5},
    ]
    assert plan_update({'message': {'chat': {'id': 5}, 'text': '/taplist2'}}) == [
        {'op': 'taplist', 'chat_id': 5, 'bar_id': 'bar2'},
    ]
    assert plan_update({
        'callback_query': {
            'id': 'cb',
            'data': 'taplist_all',
            'message': {'chat': {'id': 5}},
        },
    }) == [
        {'op': 'ack', 'callback_id': 'cb'},
        {'op': 'taplist', 'chat_id': 5, 'bar_id': None},
    ]
    assert plan_update({'message': {'chat': {'id': 5}, 'text': 'привет'}}) == []


def test_label_bars_replaces_internal_names():
    data = {'taplist': [{'bar_id': 'bar1', 'bar': 'Бар 1'}]}
    assert label_bars(data)['taplist'][0]['bar'] == 'Большой пр. В.О'
