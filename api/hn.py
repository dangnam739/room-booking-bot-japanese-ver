"""
The Keangnam office spans two floors, with two separate `location` values:
 - HN-KN     : 13F
 - HN-KN-18F : 18F

This file creates a wrapper to call the two needed queries with only one API call.
The functions' signatures are identical to the ones in `rb_helper.py`.

3 affected APIs are
 - booking_modify_add_book
 - booking_query_empty
 - check_recurring_room
"""

from api.rb_helper import (
    booking_modify_cancel,
    booking_modify_add_book as _booking_modify_add_book,
    booking_query_room_status,
    booking_query_room_schedule,
    booking_query_empty as _booking_query_empty,
    check_recurring_room as _check_recurring_room,
    get_free,
    get_headcount,
    attention,
    AlreadyBookedException,
    InvalidParameterException,
    NotLoggedInException
)
ROOM_IDS = frozenset([
    "13F", "18F", "fizz", "buzz", "abuja", "astana", "bangkok",
    "booth", "booth1", "booth2", "booth3", "booth4", "cebu",
    "dhaka", "dili", "jakarta", "napyidaw",
    "phnompenh", "singapore", "tokyo", "vientiane",
])

ROOM_IDS_JP = {
    'abuja'     : 'アブジャ',
    'astana'    : 'アスタナ',
    'bangkok'   : 'バンコク',
    'booth1'    : 'ブース1',
    'booth2'    : 'ブース2',
    'booth3'    : 'ブース3',
    'booth4'    : 'ブース4',
    'cebu'      : 'セブ',
    'dhaka'     : 'ダッカ',
    'jakarta'   : 'ジャカルタ',
    'phnompenh' : 'プノンペン',
    'singapore' : 'シンガポール',
    'tokyo'     : '東京',
    'vientiane' : 'ヴィエンチャン',
    'napyidaw'  : 'ネピドー',
    'dili'      : 'ディリ',
}

import pytz
tz = pytz.timezone('Asia/Bangkok')

PROPER_NAMES = {
    'abuja'     : 'HN-KN-13F-Fizz-Abuja (8)',
    'astana'    : 'HN-KN-13F-Fizz-Astana (8)',
    'bangkok'   : 'HN-KN-13F-Buzz-Bangkok (6)',
    'booth1'    : 'HN-KN-13F-Booth1 (4)',
    'booth2'    : 'HN-KN-13F-Booth2 (4)',
    'booth3'    : 'HN-KN-13F-Booth3 (4)',
    'booth4'    : 'HN-KN-13F-Booth4 (4)',
    'cebu'      : 'HN-KN-13F-Buzz-Cebu (8)',
    'dhaka'     : 'HN-KN-13F-Buzz-Dhaka (14)',
    'jakarta'   : 'HN-KN-13F-Buzz-Jakarta (6)',
    'phnompenh' : 'HN-KN-13F-Fizz-PhnomPenh (4)',
    'singapore' : 'HN-KN-13F-Fizz-Singapore (8)',
    'tokyo'     : 'HN-KN-13F-Fizz-Tokyo (4)',
    'vientiane' : 'HN-KN-13F-Buzz-Vientiane (22)',
    'napyidaw'  : 'HN-KN-18F-Naypyidaw (14)',
    'dili'      : 'HN-KN-18F-Dili (7)',
}

ROOM_GROUPS = {
    '13F': ['abuja', 'astana', 'bangkok', 'booth1', 'booth2',
            'booth3', 'booth4', 'cebu', 'dhaka', 'jakarta',
            'phnompenh', 'singapore', 'tokyo', 'vientiane'],
    '18F': ['napyidaw', 'dili'],
    'fizz': ['abuja', 'astana', 'phnompenh', 'singapore', 'tokyo'],
    'buzz': ['bangkok', 'cebu', 'dhaka', 'vientiane',
             'booth1', 'booth2', 'booth3', 'booth4']
}

location = 'HN-KN'

def booking_modify_add_book(*args, **kwargs):
    args = list(args)
    room_id = args[2]
    args[1] = 'HN-KN' if room_id in ROOM_GROUPS['13F'] else 'HN-KN-18F'

    return _booking_modify_add_book(*args, **kwargs)


def booking_query_empty(*args, **kwargs):
    ret = dict()
    args = list(args)
    for x in ['HN-KN', 'HN-KN-18F']:
        args[0] = x
        ret.update(_booking_query_empty(*args, **kwargs))

    return ret


def check_recurring_room(*args, **kwargs):
    ret = list()
    args = list(args)
    for x in ['HN-KN', 'HN-KN-18F']:
        args[1] = x
        ret.extend(_check_recurring_room(*args, **kwargs))

    return ret
