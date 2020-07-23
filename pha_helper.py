import re
import requests
import json
import string
from datetime import datetime, timezone, timedelta
from api.hn import ROOM_IDS, tz, PROPER_NAMES, ROOM_IDS_JP
from typing import Dict
from dateutil.parser import parse, ParserError

#Japanese tokenizer
from sudachipy import tokenizer
from sudachipy import dictionary

#convert full-width character to half-width character
import jaconv

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
    r'((きょう|きのう)(の)?((朝|午前|午後|あさ|ごぜん|ごご)?)+)',
    r'((あした|あす|あさって)(の)?((朝|午前|午後|あさ|ごぜん|ごご)?)+)',
    r'((今日|昨日)(の)?((朝|午前|午後|あさ|ごぜん|ごご)?)+)',
    r'((明日|明後日)(の)?((朝|午前|午後|あさ|ごぜん|ごご)?)+)',
    r'(((今|来|再来)(週))(の)?((月|火|水|木|金|土)*(曜日)?((朝|午前|午後|あさ|ごぜん|ごご)?)))',
    # for experimental support with t2-6 // EDIT: re.sub in correct_sentence handled it
    # r'(((sáng|chiều)?\s*(ngày)?\s*t[2-7])(( tuần)* (này|sau|tới)( nữa)*)*)',
    r'(((20)?[0-9]{2})[年\/.\-・](1[0-2]{1}|0*[1-9]{1})[月\/.\-・](0*[1-9]|[12][0-9]|3[01])[日 ](の)?((朝|午前|午後|あさ|ごぜん|ごご)?)+)',
    r'((1[0-2]{1}|0*[1-9]{1})[月\/.\-・](0*[1-9]|[12][0-9]|3[01])[日 ](の)?((朝|午前|午後|あさ|ごぜん|ごご)?)+)',
    # combined with the above
    # r'((0*[1-9]|[12][0-9]|3[01])[-](1[0-2]{1}|0*[1-9]{1})[-](20)?[0-9]{2})',
    # only use this if needed (like with TTS)
    # r'((sáng|chiều)?(ngày)*(\s)*[0-9]+(\s)*(tháng)(\s)*[0-9]+)'
    r'((午前|午後|朝|ごぜん|ごご|あさ))',
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
        r'((1[0-9]|2[0-3]|0?[0-9])(\s)*(時半|時|半|じ|じはん|h|am|pm|:)(\s)*([1-5][0-9]|0?[0-9])*)', message)
    if len(time) > 0:
        return [x[0] for x in time]


def time_regex(message):
    time = re.findall(
        r'(((1[0-9]|2[0-3]|0?[0-9])*(時半|時|半|じ|じはん|h|am|pm|:)*([1-5][0-9]|0?[0-9])*(|分|ふん|ぶん|ぷん)*)(\s)*(-|~|から|->|〜|>)(\s)*((1[0-9]|2[0-3]|0?[0-9])*(時半|時|半|じ|じはん|h|am|pm|:)*([1-5][0-9]|0?[0-9])*(|分|ふん|ぶん|ぷん)*)(?!\/|\-))', message)
    if len(time) > 0:
        time_split = re.split(r'(-|~|から|->|〜|>)', time[0][0])
        time = [[time_split[0]], [time_split[-1]]]
        time += re.findall(r'(今|今から|いま|いまから|現在|現在に|げんざい)', message)
    return time


def room_regex(message):
    # patch first: NOTE: có thể cần comment lại 2 dòng này trước khi implement chức năng vùng.
    message = re.sub(r"18階|18f", "18F", message)
    message = re.sub(r"13階|13f", "13F", message)

    tokenizer = jp_tokenizer(message)

    for i in range(len(tokenizer)):
        # match official names first
        if(tokenizer[i] == "booth" or tokenizer[i] == "ブース"):
            word = tokenizer[i] + tokenizer[i+1]
        else:
            word = tokenizer[i]

        for room, proper_name in PROPER_NAMES.items():
            if proper_name == word:
                return room

        for room_vn, room_jp in ROOM_IDS_JP.items():
            if room_jp == word:
                return room_vn

        if word in ROOM_IDS:
            if 'fizz' in message:
                return 'fizz'
            elif 'buzz' in message:
                return 'buzz'
            return word

        if word == '13' and tokenizer[i + 1] == 'F':
            return '13F'
        if word == '18' and tokenizer[i + 1] == 'F':
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
        r'(?i)((毎|隔)((二|2))?(週|月|日)(の)?((月|火|水|木|金|土)*(曜日)?))', message)
    repeat += re.findall(
        r'(?i)((二|2)(週|月|日)((間))?((ごとに|に))?((毎|一回|1回))?)', message)
    repeat += re.findall(r'(?i)((month|(bi)?week|dyi)ly)', message)
    repeat += re.findall(r'(?i)(every\s?(two|2)?\s?(month|week|day))', message)
    recurring = ["定期", "固定", "繰り返す"]
    for regex in recurring:
        repeat += re.findall(r'(?i)(' + regex + ')', message)

    if len(repeat) == 0:
        return None, None, None
    repeat_str = repeat[0][0]
    days = re.findall(r'(?i)((月|火|水|木|金|土)*(曜日))', repeat_str)

    date_start = re.search('((' + '|'.join(date_regexes) + ')' + r'(?i)((から|〜|・|ー|->|-)+)' + ')', message) or \
                 re.search(r'(?i)(開始日は|開始日：|開始日:)(' + '|'.join(date_regexes) + ')', message)

    if date_start is None:
        date_start = None
    else:
        date_start = normalize_date(date_start.group(2))[0]

        #Processing if days in regex_repeat
        if len(days) > 0:
            repeat_str = "毎週"
            start = parse(date_start, dayfirst=False)
            monday = start + timedelta(days= -start.weekday())
            day_delta = 0

            for key in day_abs:
                if key in days[0][0]:
                    day_delta += day_abs[key]
                    break

            date_start = monday + timedelta(days=day_delta, weeks=0)
            if(start > date_start):
                date_start += timedelta(weeks=1)

            date_start = date_start.strftime("%Y-%m-%d")


    date_end = re.search('((' + '|'.join(date_regexes) + ')' + r'(?i)((まで)+)' + ')', message) or \
               re.search(r'(?i)(終了日は|終了日：|終了日:|完了日：|完了日:)(' + '|'.join(date_regexes) + ')', message) or \
               re.search(r'(?i)(から|〜|・|ー|->|-)(' + '|'.join(date_regexes) + ')', message)

    if date_end is None:
        date_end = None
    else:
        date_end = normalize_date(date_end.group(2))[0]

    if '週' in repeat_str or 'week' in repeat_str:
        repeat = 'W'
    if '月' in repeat_str or 'month' in repeat_str:
        repeat = 'M'
    if '日' in repeat_str or 'dai' in repeat_str or 'day' in repeat_str:
        repeat = 'D'
    if '2' in repeat_str or '隔' in repeat_str in repeat_str:
        repeat += '-2'
    if repeat_str in recurring:
        repeat = 'W'
    return date_start, date_end, repeat


def subject_regex(message):
    update_word = ['変更', '変', '入換', '変換', '繰り返', '手直', '更新']
    replace_word = ['を', 'に', 'へ', 'は', 'です', 'だ']

    #Check message for update intent
    update = 0
    for word in update_word:
        if word in message:
            update = 1
            break

    message = message.split('。')
    subject = []

    for line in message:
        if update == 1:
            regex = re.findall(
                r'(?i)(タイトル|内容|会議名|ないよう|title|かいぎめい|題名|だいめ)\s*(\：|は|:|を)*\s*(.+)*(を|に|が|へ)?(変更|変|入換|変換|繰り返|手直|更新)', line)
        else:
            regex = re.findall(
                r'(?i)(タイトル|内容|会議名|ないよう|title|題名|だいめ)\s*(\：|は|:|を)*\s*(.+)*(|です|だ|。)', line)
        if len(regex) > 0:
            subject += regex

    if len(subject) > 0:
        title = ''
        for t in subject:
            if t[0].lower() in ['プロジェクト', 'project']:
                title += '「' + t[2] + '」'
        for t in subject:
            if t[0].lower() in ['タイトル', 'title', '会議名', 'かいぎめい' '題名', 'だいめ']:
                title += t[2] + ' '
        for t in subject:
            if t[0].lower() in ['ないよう', '内容']:
                title += t[2] + ' '
        #normalize title
        title = title.strip()
        for re_word in replace_word:
            title = title.replace(re_word, "")

        if title != '':
            return title
    return None


def correct_sentence(sentence):
    sentence = re.sub(r'booth(\s)*', "booth", sentence)
    sentence = sentence.translate(str.maketrans('\n', ' ', ";,!%.。、"))

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
    monday = now + timedelta(days= -now.weekday())
    date = date.replace("の", "")
    date_only = ""

    if '午後' in date or 'ごご' in date:
        apm = 'pm'
        for i in range(len(date)):
            if(date[i] == '日'):
                break
        date_only = date[:i+1]
        date = date_only
    elif '午前' in date or '朝' in date or 'ごぜん' in date or 'あさ' in date:
        apm = 'am'
        for i in range(len(date)):
            if(date[i] == '日'):
                break
        date_only = date[:i+1]
        date = date_only
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

    #if no pattern
    pattern = [r'(?i)((だれも|誰も|誰か|誰)+\s*(を|は|が|に)?\s*(招待しな|誘わな|招かな|勧誘しな|招待しません|誘いません|招きません|勧誘しません))',
               r'(?i)((ゲスト|ゲストリスト)+\s*(を|は|が|に)?\s*(削除|キャンセル|取り消す))']

    if re.findall('(' + '|'.join(pattern) + ')', message):
        return [' ']

    pattern = r'''((?:[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*|"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|\[(?:(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9]))\.){3}(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9])|[a-z0-9-]*[a-z0-9]:(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)\]))'''
    return [x[0] for x in re.findall(pattern, message)]


def processing_nlu(message):
    # print(message)
    # get emails before fixing message
    #convert to half-width character
    message = jaconv.z2h(message, digit=True, kana=False, ascii=True)

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
                if(date_start != repeat_start):
                    date_start = repeat_start
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
                                 'attendees'])\
                            if x is not None]
    return extracted


if __name__ == '__main__':
    import pprint
    while True:
        pprint.pprint(processing_nlu(input("Text to test => ")))
