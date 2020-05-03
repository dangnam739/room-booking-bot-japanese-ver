import re
import requests
import json
import string
from datetime import datetime, timezone, timedelta
from constants import ROOM_IDS, tz, PROPER_NAMES, ROOM_IDS_JP
from typing import Dict
from dateutil.parser import parse, ParserError

#Japanese tokenizer
from sudachipy import tokenizer
from sudachipy import dictionary

tokenizer_obj = dictionary.Dictionary().create()
mode = tokenizer.Tokenizer.SplitMode.C


def jp_tokenizer(message):
    return [m.surface() for m in tokenizer_obj.tokenize(message, mode)]


def damerau_levenshtein_distance(s1, s2):
    '''
    replacing original method
    '''
    d = {}
    lenstr1 = len(s1)
    lenstr2 = len(s2)
    for i in range(-1, lenstr1+1):
        d[(i, -1)] = i+1
    for j in range(-1, lenstr2+1):
        d[(-1, j)] = j+1

    for i in range(lenstr1):
        for j in range(lenstr2):
            if s1[i] == s2[j]:
                cost = 0
            else:
                cost = 1
            d[(i, j)] = min(
                d[(i-1, j)] + 1,  # deletion
                d[(i, j-1)] + 1,  # insertion
                d[(i-1, j-1)] + cost,  # substitution
            )
            if i and j and s1[i] == s2[j-1] and s1[i-1] == s2[j]:
                d[(i, j)] = min(d[(i, j)], d[i-2, j-2] + cost)  # transposition

    return d[lenstr1-1, lenstr2-1]


day_abs = {
    '月曜日': 0,
    '月': 0,
    'げつようび': 0,
    'げつ': 0,
    '火曜日': 1,
    '火': 1,
    'かようび': 1,
    'か': 1,
    '水曜日': 2,
    '水': 2,
    'すいようび': 2,
    'すい': 2,
    '木曜日': 3,
    '木': 3,
    'もくようび': 3,
    'もく': 3,
    '金曜日': 4,
    '金': 4,
    'きんようび': 4,
    'きん': 4
}

day_rel = {
    '明日': 1,
    'あした': 1,
    'あす': 1,
    '今日': 0,
    'きょう': 0,
    '本日': 0,
    'ほんじつ': 0,
    'きのう': -1,
    '昨日': -1,
    '明後日': 2,
    'あさって': 2
}

at_the_moment = {
    'いま': 0,
    '今': 0,
    '今から': 0,
    'いまから': 0,
    '現在に': 0,
    'げんざい': 0,
    '今は': 0,
    '現在に': 0
}

START_TIME = '08:00:00'
END_TIME = '17:00:00'
START_NOON = '12:00:00'
END_NOON = '13:00:00'

# to be reused
date_regexes = [
    r'((午前|午後)?(きょう|きのう)+)',
    r'((午前|午後)?(あした|あさって)+)',
    r'((午前|午後)?(今日|昨日)+)',
    r'((午前|午後)?(明日|明後日)+)',
    r'(((今|来|再来)*(週))(の)?((午前|午後)?(月|火|水|木|金|土)*(曜日)))',
    # for experimental support with t2-6 // EDIT: re.sub in correct_sentence handled it
    # r'(((sáng|chiều)?\s*(ngày)?\s*t[2-7])(( tuần)* (này|sau|tới)( nữa)*)*)',
    r'(((20)?[0-9]{2})[年\/.\-・](1[0-2]{1}|0*[1-9]{1})[月\/.\-・](0*[1-9]|[12][0-9]|3[01])[日 ]+)',
    r'((1[0-2]{1}|0*[1-9]{1})[月\/.\-・](0*[1-9]|[12][0-9]|3[01])[日 ]+)',
    # combined with the above
    # r'((0*[1-9]|[12][0-9]|3[01])[-](1[0-2]{1}|0*[1-9]{1})[-](20)?[0-9]{2})',
    # only use this if needed (like with TTS)
    # r'((sáng|chiều)?(ngày)*(\s)*[0-9]+(\s)*(tháng)(\s)*[0-9]+)'
]


def date_regex(message):
    date = re.findall('(' + '|'.join(date_regexes) + ')', message)
    # print(date)
    return date


def time1_regex(message):
    # proper format
    time = re.findall(
        r'((1[0-9]|2[0-3]|0?[0-9]):([1-5][0-9]|0?[0-9])(:([1-5][0-9]|0?[0-9]))*)', message)
    time += re.findall(
        r'((1[0-9]|2[0-3]|0?[0-9])(\s)*(時半|時|半|h|am|pm|:)(\s)*([1-5][0-9]|0?[0-9])*)', message)
    if len(time) > 0:
        return [x[0] for x in time]


def time_regex(message):
    time = re.findall(
        r'(((1[0-9]|2[0-3]|0?[0-9])*(時半|時|半|h|am|pm|:)*([1-5][0-9]|0?[0-9])*(|分)*)(\s)*(-|~|から|->|〜|>)(\s)*((1[0-9]|2[0-3]|0?[0-9])*(時半|時|半|h|am|pm|:)*([1-5][0-9]|0?[0-9])*(|分)*)(?!\/|\-))', message)
    if len(time) > 0:
        time_split = re.split(r'(-|~|から|->|〜|>)', time[0][0])
        time = [[time_split[0]], [time_split[-1]]]
        time += re.findall(r'(今|今から|いま|いまから|現在)', message)
    return time


def room_regex(message):
    # patch first: NOTE: có thể cần comment lại 2 dòng này trước khi implement chức năng vùng.
    message = re.sub(r"18階|18f", "18F", message)
    message = re.sub(r"13階|13f", "13F", message)

    tokenizer = jp_tokenizer(message)

    for i in range(len(tokenizer)):
        # match official names first
        for room, proper_name in PROPER_NAMES.items():
            if proper_name == tokenizer[i]:
                return room

        for room_vn, room_jp in ROOM_IDS_JP.items():
            if room_jp == tokenizer[i]:
                return room_vn

        if tokenizer[i] in ROOM_IDS:
            if 'fizz' in message:
                return 'fizz'
            elif 'buzz' in message:
                return 'buzz'
            return tokenizer[i]

        if tokenizer[i] == '13' and tokenizer[i + 1] == 'F':
            return '13F'
        if tokenizer[i] == '18' and tokenizer[i + 1] == 'F':
            return '18F'

    return None


def capacity_regex(message):
    capacity = re.findall(
        r'((人数|サイズ|size|キャパシティ)\s*(\：|は)+(\s)*([0-9]|ー|二|三)*(人)+)', message)
    capacity += re.findall(r'([0-9]*(人|ひと|にん)\b)', message)
    if len(capacity) > 0:
        number = re.findall(r'\d+', capacity[0][0])
        if len(number) > 0:
            return number[0]
    return None


def repeat_regex(message):
    '''
    returns day start, day end, and mode (weekly/monthly/daily)
    may return None for the fields it doesn't get (fallback on normal)
    '''
    repeat = re.findall(
        r'(?i)((毎)((二|2))?(週|月|日))', message)
    repeat += re.findall(r'(?i)((month|(bi)?week|dai)ly)', message)
    repeat += re.findall(r'(?i)(every\s?(two|2)?\s?(month|week|day))', message)
    recurring = ["定期", "固定", "繰り返す"]
    for regex in recurring:
        repeat += re.findall(r'(?i)(' + regex + ')', message)

    if len(repeat) == 0:
        return None, None, None

    date_start = re.search(
        '((' + '|'.join(date_regexes) + ')' + r'(?i)((から|〜|・|ー|->|-)+)' + ')', message) or re.search(r'(?i)(開始日は|開始日：|開始日:)(' + '|'.join(date_regexes) + ')', message)

    if date_start is None:
        date_start = None
    else:
        date_start = normalize_date(date_start.group(2))[0]

    date_end = re.search('((' + '|'.join(date_regexes) + ')' + r'(?i)((まで)+)' + ')', message) or \
            re.search(r'(?i)(終了日は|終了日：|終了日:)(' + '|'.join(date_regexes) + ')', message) or \
            re.search(r'(?i)(から|〜|・|ー|->|-)(' + '|'.join(date_regexes) + ')', message)

    if date_end is None:
        date_end = None
    else:
        date_end = normalize_date(date_end.group(2))[0]

    repeat_str = repeat[0][0]

    if '週' in repeat_str or 'week' in repeat_str:
        repeat = 'W'
    if '月' in repeat_str or 'month'in repeat_str:
        repeat = 'M'
    if '日' in repeat_str or 'dai' in repeat_str or 'day' in repeat_str:
        repeat = 'D'
    if '2' in repeat_str or 'hai' in repeat_str or 'cách' in repeat_str:
        repeat += '-2'
    # experimental
    if 'cách nhật' in message:
        repeat = 'D-2'
    if message in recurring:
        repeat = '_'
    return date_start, date_end, repeat


def subject_regex(message):
    message = message.split('\n')
    subject = []
    for line in message:
        regex = re.findall(
            r'(?i)(タイトル|title|題名|内容)\s*(\：|は)*\s*(.+)', line)
        if len(regex) > 0:
            subject += regex
    if len(subject) > 0:
        title = ''
        for t in subject:
            if t[0].lower() in ['プロジェクト', 'project']:
                title += '[' + t[2] + '] '
        for t in subject:
            if t[0].lower() in ['タイトル', 'title', '題名']:
                title += t[2] + ' '
        for t in subject:
            if t[0].lower() == '内容':
                title += t[2] + ' '
        title = title.strip()
        if title != '':
            return title
    return None


def correct_sentence(sentence):
    sentence = re.sub(r'booth(\s)*', "booth", sentence)
    sentence = sentence.translate(str.maketrans('\n', ' ', ";,!%.。"))

    new_sentence = []
    for word in jp_tokenizer(sentence):
        # ignore multiple consecutive spaces
        if word == '':
            continue
        budget = 2
        n = len(word)
        if n <= 3:
            budget = 0
        elif 3 < n < 6:
            budget = 1
        if budget:
            costs = {}
            for keyword in ROOM_IDS:
                val = damerau_levenshtein_distance(word.lower(), keyword)
                if val <= budget:
                    costs[keyword] = val
            if len(costs) == 0:
                new_sentence.append(word)
            else:
                new_sentence.append(min(costs, key=costs.get))
        else:
            new_sentence.append(word)
    return "".join(new_sentence)


def normalize_date(date):
    now = datetime.now(tz)
    monday = now + timedelta(days=-now.weekday())

    if '午後' in date:
        apm = 'pm'
    elif '午前' in date:
        apm = 'am'
    else:
        apm = None

    try:
        if (date not in day_abs.keys()) & (date not in day_rel.keys()):
            date = date.replace("年", "/")
            date = date.replace("月", "/")
            date = date.replace("日", "")
        return parse(date, dayfirst=False).strftime("%Y-%m-%d"), apm
    except ParserError:
        day_delta = 0
        week_delta = 0

        for key in day_rel:
            if key in date:
                return (now + timedelta(days=day_rel[key])).strftime("%Y-%m-%d"), apm

        for key in day_abs:
            if key in date:
                day_delta += day_abs[key]
                break

        if '週' in date:
            if '来' in date:
                week_delta += 1
            elif '再' in date:
                week_delta += 1
            # tuần sau nữa nữa
            week_delta += date.count('再')

        normalized_date = monday + timedelta(days=day_delta, weeks=week_delta)
        if now > normalized_date:
            normalized_date += timedelta(weeks=1)

        return normalized_date.strftime("%Y-%m-%d"), apm


def afternoon_normalize(time):
    if time.hour < 7:
        time += timedelta(hours=12)
    return time.strftime("%H:%M:00")


def normalize_time(time):
    time = time.strip()
    try:
        # if it's just a number
        if time.isnumeric():
            raise ParserError
        return afternoon_normalize(parse(time))
    except ParserError:
        now = datetime.now(tz)
        zero = now + timedelta(hours=-now.hour, minutes=-now.minute)

        delta_hours = 0
        delta_minutes = 0

        for key in at_the_moment:
            if key in time:
                return now.strftime("%H:%M:00")

        int_time = [int(t) for t in re.findall(r'\d+', time)]
        if len(int_time) > 0:
            delta_hours = int_time[0]
        if len(int_time) > 1:
            delta_minutes = int_time[1]
        if '時半' in time:
            delta_minutes = 30
        if '半' in time:
            delta_minutes = 30
        return afternoon_normalize(zero + timedelta(hours=delta_hours, minutes=delta_minutes))


def email_regex(message):
    # pattern = r'([^@\s,]+@([^@\s\.,]+\.)+[^@\s\.,]+)'
    # from here: https://stackoverflow.com/questions/201323/how-to-validate-an-email-address-using-a-regular-expression
    pattern = r'''((?:[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*|"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|\[(?:(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9]))\.){3}(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9])|[a-z0-9-]*[a-z0-9]:(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)\]))'''
    return [x[0] for x in re.findall(pattern, message)]


def processing_nlu(message):
    # print(message)
    # get emails before fixing message
    attendees = email_regex(message)
    subject = subject_regex(message)

    message = message.lower()
    message = correct_sentence(message)
    room_id = room_regex(message)

    date = date_regex(message)
    time = time_regex(message)
    repeat_start, repeat_end, repeat = repeat_regex(message)
    capacity = capacity_regex(message)
    time1 = time1_regex(message)

    date_start = date_end = time_start = time_end = \
        datetime_ = datetime_1 = None

    # search for fullsize message
    res = re.search(r'(\d{1,2})[\/.\-](\d{1,2})[\/.\-](\d{2}|\d{4})\s+(\d{1,2}):(\d{1,2})(:\d{1,2})?\s*(?:->|から|~|〜|-|>)\s*(\d{1,2})[\/.\-](\d{1,2})[\/.\-](\d{2}|\d{4})\s+(\d{1,2}):(\d{1,2})(:\d{1,2})?', message) or \
        re.search(r'(\d{2}|\d{4})[\/.\-](\d{1,2})[\/.\-](\d{1,2})\s+(\d{1,2}):(\d{1,2})(:\d{1,2})?\s*(?:->|から|~|〜|-|>)\s*(\d{2}|\d{4})[\/.\-](\d{1,2})[\/.\-](\d{1,2})\s+(\d{1,2}):(\d{1,2})(:\d{1,2})?', message)

    fullsize = False
    if res is not None:
        d_f, d_t = res.group(0).split('->')
        try:
            d_f = parse(d_f)
            d_t = parse(d_t)

            date_start = d_f.strftime("%Y-%m-%d")
            date_end = d_t.strftime("%Y-%m-%d")
            time_start = d_f.strftime("%H:%M:%S")
            time_end = d_t.strftime("%H:%M:%S")

            datetime_1 = f'{date_start} {time_start}'
            fullsize = True
        except ParserError:
            pass

    if not fullsize:
        # deal with captured dates
        if len(date) > 0:
            date_start, apm_start = normalize_date(date[0][0])
            date_end, apm_end = date_start, apm_start
            if len(date) > 1:
                date_end, apm_end = normalize_date(date[1][0])

            list_date = []
            for d in date:
                list_date.append(normalize_date(d[0])[0])
            if len(list_date) > 1 and repeat_end is not None:
                repeat_end = max(list_date)

        # deal with captured times
        if len(time) > 0:
            time_start = time_end = normalize_time(time[0][0])
            if len(time) > 1:
                time_end = normalize_time(time[1][0])
        elif time1 is not None:
            time_start = time_end = normalize_time(time1[0])

            if len(time1) > 1:
                time_end = normalize_time(time1[1])
            else:
                h_to = int(time_start[:2])
                if h_to < 23:
                    h_to += 1
                    time_end = f'{h_to:02}{time_end[2:]}'

        if date_start is not None and time_start is None:
            if apm_start == 'pm':
                time_start = END_NOON
            else:
                time_start = START_TIME
            if apm_end == 'am':
                time_end = START_NOON
            else:
                time_end = END_TIME

            if time1 is not None:
                datetime_1 = f'{date_start} {normalize_time(time1[0])}'
        elif date_start is None and time_start is not None:
            date_start = date_end = datetime.now(tz).strftime("%Y-%m-%d")
        elif date_start is not None and time_start is not None:
            datetime_1 = f'{date_start} {time_start}'

        # deal with repeat_start: replace time if needed
        if repeat is not None:
            if repeat_start is not None:
                if repeat_start > date_start:
                    date_start = repeat_start
                    if repeat_start > date_end:
                        date_end = repeat_start
                    # if time_start > time_end, tough fucking luck.
            else:
                repeat_start = date_start

    if date_start is not None:
        datetime_ = f'{date_start} {time_start} -> {date_end} {time_end}'

    if len(attendees) == 0:
        attendees = None
    else:
        attendees = ','.join(attendees)

    def wrap(title:str) -> Dict or None:
        # to trigger locals
        subject, room_id, capacity, repeat, attendees
        datetime_, datetime_1, repeat_start, repeat_end
        # and once triggered this works (LOL)
        obj = eval(title)
        if obj is None:
            return None
        return {
            "start": 0,
            "end": 1,
            "value": obj,
            "confidence": 1.0,
            "entity": title,
        }

    extracted = [x for x in map(wrap,
                                ["subject", "room_id", "capacity",
                                 "datetime_", "datetime_1",
                                 "repeat", "repeat_start", "repeat_end",
                                 'attendees']) \
                            if x is not None]
    return extracted

if __name__ == '__main__':
    import pprint
    while True:
        pprint.pprint(processing_nlu(input("Text to test => ")))
