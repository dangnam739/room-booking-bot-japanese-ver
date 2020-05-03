import pytz

ROOM_IDS = frozenset([
    "13F", "18F", "fizz", "buzz", "abuja", "astana", "bangkok",
    "booth1", "booth2", "booth3", "booth4", "cebu",
    "dhaka", "dili", "jakarta", "napyidaw",
    "phnompenh", "singapore", "tokyo", "vientiane",
])

tz = pytz.timezone('Asia/Bangkok')

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
            'phnompenh', 'singapore', 'tokyo','vientiane'],
    '18F': ['napyidaw', 'dili'],
    'fizz': ['abuja', 'astana', 'phnompenh', 'singapore', 'tokyo'],
    'buzz': ['bangkok', 'cebu', 'dhaka', 'vientiane',
             'booth1', 'booth2', 'booth3', 'booth4']
}
