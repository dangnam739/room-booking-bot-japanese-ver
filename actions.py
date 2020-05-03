# This files contains your custom actions which can be used to run
# custom Python code.
#
# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/core/actions/#custom-actions/

from abc import ABC
from typing import Any, Text, Dict, List, Union, Optional
import re
from datetime import datetime, timedelta
from rasa_sdk import Action, Tracker
from rasa_sdk.events import (
    EventType,
    AllSlotsReset,
    Restarted,
    SlotSet,
    UserUtteranceReverted,
    FollowupAction
)
from rasa_sdk.interfaces import ActionExecutionRejection
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.forms import FormAction, REQUESTED_SLOT
from pha_helper import ROOM_IDS
from requests.exceptions import ConnectTimeout
from rb_helper import (
    AlreadyBookedException,
    InvalidParameterException,
    NotLoggedInException,
    get_free,
    get_headcount,
    booking_modify_cancel,
    booking_modify_add_book,
    booking_query_room_status,
    booking_query_room_schedule,
    booking_query_empty,
    check_recurring_room
)
from email.utils import parseaddr
from constants import tz, PROPER_NAMES, ROOM_GROUPS
from dateutil.parser import parse, ParserError
from pprint import pprint


SLOT_NAMES = {
  'attendees': 'ゲストリスト',
  'capacity': '人数',
  'datetime_': '時間',
  'datetime_1': '開始時間',
  'repeat': '繰り返し頻度',
  'repeat_end': '終了日',
  'repeat_start': '開始日',
  'room_id': '会議室',
  'subject': 'タイトル',
}

class CancellableForm(FormAction, ABC):
    '''
    base class form with cancel ability and data validation.
    should/will never be initialized by itself; rather extend it.
    '''

    def name(self):
        return 'abstract form'

    @staticmethod
    def datetime_format(datetime_):
        d_f, d_t = map(parse, datetime_.split('->'))
        day_start = d_f.strftime('%Y年%m月%d日')
        day_end = d_t.strftime('%Y年%m月%d日')
        time_start = d_f.strftime('%H:%M')
        time_end = d_t.strftime('%H:%M')
        if day_start == day_end:
            return f'{day_start}・{time_start}〜{time_end}'
        else:
            return f'{day_start}・{time_start}〜{day_end}・{time_end}'

    @staticmethod
    def repeat_format(repeat_str:str) -> str:
        '''
        input: D/W/M(-2)
        '''
        if '-2' in repeat_str:
            ret = '毎2'
        else:
            ret = '毎'
        if 'D' in repeat_str:
            ret += '日'
        elif 'W' in repeat_str:
            ret += '週'
        elif 'M' in repeat_str:
            ret += '月'
        else:
            ret = 'ERROR'
        return ret

    def slot_mappings(self) -> Dict[Text, Union[Dict, List[Dict]]]:
        """A dictionary to map required slots to
            - an extracted entity
            - intent: value pairs
            - a whole message
            or a list of them, where a first match will be picked"""

        return {
            "subject": [self.from_entity("subject"), self.from_text()],
            "capacity": self.from_entity("capacity"),
            "repeat": self.from_entity("repeat"),
            "room_id": self.from_entity("room_id"),
            "datetime_": self.from_entity("datetime_"),
            "repeat_start": self.from_entity("repeat_start"),
            "repeat_end": [
                    self.from_entity("repeat_end"),
                    self.from_entity("datetime_"),
                    self.from_entity("datetime_1")
            ],
            "datetime_1": self.from_entity("datetime_1"),
            "confirm_booking": [
                    self.from_intent("true", intent=["affirmative", "thanks"]),
                    self.from_intent("false", intent="negative"),
                    # self.from_intent("false", not_intent="affirmative")
            ],
            "confirm_cancel": [
                    self.from_intent("true", intent=["affirmative", "thanks"]),
                    self.from_intent("false", intent="negative"),
                    # self.from_intent("false", not_intent="affirmative")
            ],
            "confirm_booking_repeat": [
                    self.from_intent("true", intent=["affirmative", "thanks"]),
                    self.from_intent("false", intent="negative"),
                    # self.from_intent("false", not_intent="affirmative")
            ],
            "attendees": [
                    self.from_intent(' ', intent='negative'),
                    self.from_entity("attendees")
            ]
        }

    async def validate(self,
                       dispatcher: CollectingDispatcher,
                       tracker: Tracker,
                       domain: Dict[Text, Any],
                       ) -> List[EventType]:
        """Extract and validate value of requested slot.

        If nothing was extracted reject execution of the form action.
        Subclass this method to add custom validation and rejection logic
        """

        # extract other slots that were not requested
        # but set by corresponding entity or trigger intent mapping
        slot_values = self.extract_other_slots(dispatcher, tracker, domain)

        # extract requested slot
        slot_to_fill = tracker.get_slot(REQUESTED_SLOT)

        if slot_to_fill:

            # custom code to cancel out
            latest_intent = tracker.latest_message.get("intent", {})
            # hard thresholding
            if latest_intent.get("name") == 'cancelling' \
                    and float(latest_intent.get('confidence', 0)) > .9:

                dispatcher.utter_message(template="utter_abort", **tracker.slots)
                ret = [AllSlotsReset()] + self.deactivate()
                return ret

            updated = []
            # Only update when you're certain.
            if not (latest_intent.get("name") == 'update_existing_slot' \
                    and float(latest_intent.get('confidence', 0)) > .6):
                for key in slot_values.copy():
                    if tracker.get_slot(key):
                        slot_values.pop(key)
                    else:
                        updated.append(SLOT_NAMES[key])

            if len(updated) > 0:
                dispatcher.utter_message("次の情報を更新しました： \n" +
                    '\n'.join(updated) + ".")

            slot_values.update(self.extract_requested_slot(dispatcher, tracker, domain))

            if not slot_values:
                # reject to execute the form action
                # if some slot was requested but nothing was extracted
                # it will allow other policies to predict another action

                dispatcher.utter_message(template="utter_fallback")
                if 'datetime_' in slot_to_fill:
                    dispatcher.utter_message(template=f"utter_reenter_{slot_to_fill}")
                return [UserUtteranceReverted()]

                # raise ActionExecutionRejection(
                #     self.name(),
                #     f"Failed to extract slot {slot_to_fill} with action {self.name()}",
                # )
        return await self.validate_slots(slot_values, dispatcher, tracker, domain)

    def request_next_slot(self, dispatcher: CollectingDispatcher,
                          tracker: Tracker,
                          domain: Dict[Text, Any]) -> Optional[List[Dict]]:
        """Request the next slot and utter template if needed,
            else return None"""

        for slot in self.required_slots(tracker):
            if self._should_request_slot(tracker, slot):
                if slot[:15] == 'confirm_booking':
                    room_id = tracker.get_slot("room_id")
                    if room_id in PROPER_NAMES:
                        room_format = PROPER_NAMES[room_id]
                    else:
                        if room_id[0] == '1':
                            room_format = room_id[:2] + '階'
                        else:
                            room_format = room_id.capitalize() + '区'
                        room_format += ' (' + ', '.join(map(str.capitalize, ROOM_GROUPS[room_id])) + ')'

                    subject = tracker.get_slot("subject")
                    capacity = tracker.get_slot("capacity")
                    emails = tracker.get_slot("attendees")
                    datetime_ = self.__class__.datetime_format(
                        tracker.get_slot("datetime_")
                    )

                    if slot == 'confirm_booking_repeat':
                        subject = tracker.get_slot("subject")
                        repeat = tracker.get_slot("repeat")
                        repeat_end = tracker.get_slot("repeat_end")

                        time_start, time_end = map(
                            lambda x: x.split()[1],
                            tracker.get_slot("datetime_").split(' -> ')
                        )

                        repeat_start = tracker.get_slot(  "datetime_").split(' -> ')[0].split()[0]
                        repeat_start_2 = tracker.get_slot("repeat_start")
                        if repeat_start_2 is not None:
                            repeat_start = max(repeat_start, repeat_start_2)
                        try:
                            suggestions = check_recurring_room(
                                tracker.sender_id ,
                                'HN-KN',
                                time_start,
                                time_end,
                                repeat,
                                repeat_start,
                                repeat_end
                            )
                        except NotLoggedInException:
                            dispatcher.utter_message(template="utter_not_logged_in")
                            return [AllSlotsReset()]

                        if 'freespace' in suggestions:
                            suggestions.remove('freespace')
                        if room_id not in suggestions:
                            if len(suggestions) == 0:
                                dispatcher.utter_message(
                                    "要件を満たす屋はありません。 " +
                                    "上記の要求を保存しました。再試行したいですか。"
                                )
                                return self.deactivate()
                            # if it's salvageable
                            ret = tracker.get_slot('room_id').capitalize() + '室' + \
                                'ただ今、要求による要約すことができません。' + \
                                '室のおすすめは:[info]' + \
                                ('\n- ').join(['']+suggestions).capitalize() + \
                                "[/info]\n"
                            dispatcher.utter_message(ret)
                            return [SlotSet("room_id", None), SlotSet(REQUESTED_SLOT, 'room_id')]

                        # if the room is ok to be booked
                        repeat = self.__class__.repeat_format(repeat)
                        repeat_end = datetime.strptime(repeat_end, "%Y-%m-%d").strftime("%Y年%m月%d日")
                        repeat_start = datetime.strptime(repeat_start, "%Y-%m-%d").strftime("%Y年%m月%d日")

                    dispatcher.utter_message(
                        "下記の予約情報をご確認ください:\n[info]\n" + \
                        f"- タイトル: {subject}\n" + \
                        f"- 会議室: {room_format}\n" + \
                        (f"- 時間: {repeat}、{time_start}〜{time_end}" +
                         "\n" + "  " * 10 + f"{repeat_start}〜{repeat_end}"
                            if 'repeat' in slot else f"- 時間: {datetime_}") + \

                        (f"\n- 人数: {capacity}" if capacity is not None
                            else '') + \

                        (('\n' + ' '*10 + '+ ').join(["\n- ゲストリスト:"] + emails.split(',')) \
                            if emails != '' else '') + \
                        "\n[/info]\n上記の情報で予約を完了するに、「OK」とご返事ください。"
                    )
                elif slot == 'confirm_cancel':
                    room_id = tracker.get_slot('room_id')
                    datetime_1 = tracker.get_slot("datetime_1").split()
                    date_ = '-'.join(datetime_1[0].split('-')[::-1])
                    if tracker.get_slot("repeat") is None:
                        dt_format = f"{date_}・{datetime_1[1]}"
                    else:
                        dt_format = f"{date_}から{datetime_1[1]}に"
                    dispatcher.utter_message("キャンセルの要求をご確認ください: \n[info]\n" + f"- 会議室: {room_id}\n" + f"- 時間: {dt_format}")
                else:
                    dispatcher.utter_message(template=f"utter_ask_{slot}", **tracker.slots)
                return [SlotSet(REQUESTED_SLOT, slot)]

    def validate_datetime_(
            self,
            value: Text,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
        ) -> Dict[Text, Any]:

        try:
            d1, d2 = value.split(' -> ')
            parse(d1)
            parse(d2)
            valid = True
        except ParserError:
            valid = False

        if valid:
            return {"datetime_": value}
        else:
            dispatcher.utter_message(template="utter_invalid_datetime")
            return {"datetime_": None}

    def validate_datetime_1(
            self,
            value: Text,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
        ) -> Dict[Text, Any]:

        try:
            parse(value)
            valid = True
        except ParserError:
            valid = False

        if not valid:
            dispatcher.utter_message(template="utter_invalid_datetime")
            return {"datetime_1": None}
        else:
            return {"datetime_1": value}

    def validate_repeat_end(
            self,
            value: Text,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
        ) -> Dict[Text, Any]:

        value = value[:10]
        try:
            parse(value)
            valid = True
        except ParserError:
            valid = False

        if not valid:
            dispatcher.utter_message(template="utter_invalid_datetime")
            return {"repeat_end": None}
        else:
            return {"repeat_end": value}

    def validate_repeat(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:

        if value == '_':
            return {"repeat": None}
        else:
            return {"repeat": value}

    def validate_attendees(
            self,
            value: Text,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
        ) -> Dict[Text, Any]:

        def is_valid_email(email):
            parsed = parseaddr(email)[1]
            # because fuck localhost DNS.
            return '@' in parsed and '.' in parsed

        value = value.strip()
        if value == '' or not all(map(is_valid_email, re.split(r'\s*,\s*', value))):
            dispatcher.utter_message(template="utter_invalid_attendees")
            return {"attendees": ''}
        else:
            return {"attendees": value}

class BookingModifyCancelForm(CancellableForm):
    '''
    form to cancel a room booking.
    '''

    def name(self):
        """Unique identifier of the form"""
        return "booking_modify_cancel_form"

    @staticmethod
    def required_slots(tracker: Tracker) -> List[Text]:
        """A list of required slots that the form has to fill.

        Use `tracker` to request different list of slots
        depending on the state of the dialogue
        """
        if 'repeat' in [e['entity'] for e in tracker.latest_message['entities']] \
                or tracker.get_slot('repeat') is not None:
            return ['room_id', 'datetime_1', 'repeat', 'confirm_cancel']

        return ['room_id', 'datetime_1', 'confirm_cancel']

    # override, do not validate
    def validate_repeat(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:

        return {"repeat_end": value}

    def submit(self,
               dispatcher: CollectingDispatcher,
               tracker: Tracker,
               domain: Dict[Text, Any]) -> List[Dict]:
        """Define what the form has to do
            after all required slots are filled"""

        confirm = tracker.get_slot('confirm_cancel')
        if confirm == 'false':
            dispatcher.utter_message(template='utter_abort')
        else:
            try:
                booking_modify_cancel(
                    tracker.sender_id ,
                    tracker.get_slot("room_id"),
                    tracker.get_slot("datetime_1"),
                    tracker.get_slot('repeat') is not None
                )
                dispatcher.utter_message(template="utter_cancel_success")
            except PermissionError:
                dispatcher.utter_message(template="utter_add_friend")

        return [AllSlotsReset()]

class BookingModifyAddForm(CancellableForm):
    '''
    form to create a room booking.
    '''

    def name(self):
        """Unique identifier of the form"""
        return "booking_modify_add_form"

    @staticmethod
    def required_slots(tracker: Tracker) -> List[Text]:
        """A list of required slots that the form has to fill.

        Use `tracker` to request different list of slots
        depending on the state of the dialogue
        """

        if 'repeat' not in [x['entity'] for x in tracker.latest_message['entities']] \
                and tracker.get_slot('repeat') is None:
            return ['room_id', 'datetime_', 'subject', 'attendees','confirm_booking']

        if 'repeat_start' not in [x['entity'] for x in tracker.latest_message['entities']] \
                and tracker.get_slot('repeat_start') is None:
            return ['room_id', 'datetime_', 'subject', 'repeat',
                'repeat_end', 'attendees', 'confirm_booking_repeat']

        return ['room_id', 'datetime_', 'subject', 'repeat', 'repeat_start',
            'repeat_end', 'attendees', 'confirm_booking_repeat']

    def submit(self,
               dispatcher: CollectingDispatcher,
               tracker: Tracker,
               domain: Dict[Text, Any]) -> List[Dict]:
        """Define what the form has to do
            after all required slots are filled"""

        self.repeat = tracker.get_slot('repeat') is not None
        confirm = tracker.get_slot('confirm_booking' + ('_repeat' if self.repeat else ''))
        if confirm == 'false':
            dispatcher.utter_message(template='utter_abort')
        else:
            room_id = tracker.get_slot("room_id")
            subject = tracker.get_slot("subject")
            datetime_ = tracker.get_slot("datetime_")
            d_f, d_t = datetime_.split(" -> ")
            datetime_ = self.__class__.datetime_format(datetime_)
            emails = tracker.get_slot("attendees")

            if room_id in ROOM_GROUPS:
                room_ids = ROOM_GROUPS[room_id]
            else:
                room_ids = [room_id]
            success = False
            booked = 0
            for room_id in room_ids:
                try:
                    hangout, gcal, _ = booking_modify_add_book(
                        tracker.sender_id ,
                        "HN-KN",
                        room_id,
                        d_f, d_t,
                        subject,
                        tracker.get_slot('repeat') if self.repeat else None,
                        tracker.get_slot('repeat_end') if self.repeat else None,
                        tracker.get_slot('repeat_start') if self.repeat else None,
                        tracker.get_slot('capacity'),
                        [] if len(emails) == 0 else emails.split(',')
                    )
                    success = True
                except PermissionError:
                    dispatcher.utter_message(template="utter_insufficient_privilege")
                except AlreadyBookedException:
                    booked += 1
                    continue
                except InvalidParameterException:
                    dispatcher.utter_message(template="utter_invalid_parameters")
                except NotLoggedInException:
                    dispatcher.utter_message(template="utter_not_logged_in")
                break

            if booked == len(room_ids):
                if booked == 1:
                    dispatcher.utter_message(template="utter_already_booked")
                else:
                    dispatcher.utter_message(template="utter_already_booked_all")

            if success:
                if self.repeat:
                    repeat = self.__class__.repeat_format(tracker.get_slot('repeat'))
                dispatcher.utter_message("予約が完了しました。\n[info]" + \
                    f"- タイトル: {subject}\n" + \
                    f"- 会議室: {PROPER_NAMES[room_id]}\n" + \
                    ((f"- 時間: {datetime_.split(' ')[1]}〜{datetime_.split(' ')[4]}\n" +
                      " " * 10 + f"{repeat}、{tracker.get_slot('repeat_start')}〜{tracker.get_slot('repeat_end')}\n")
                    if self.repeat
                    else
                        f"- 時間: {datetime_}\n") +
                    f"- Google Calendar: {gcal}\n" + \
                    f"- Google Hangout: {hangout}" + \
                    (('\n' + ' '*10 + '+ ').join(["\n- ゲストリスト:"] + emails.split(',')) \
                            if emails != '' else '') + \
                    "[/info]"
                )

        return [AllSlotsReset()]

class BookingQueryEmpty(CancellableForm):
    '''
    10. Chức năng hỏi lịch trống:
            "Từ 1h-2h ngày 1/1 có phòng nào trống không?"
    '''

    def name(self):
        """Unique identifier of the form"""
        return "booking_query_empty_form"

    @staticmethod
    def required_slots(tracker: Tracker) -> List[Text]:
        """A list of required slots that the form has to fill.

        Use `tracker` to request different list of slots
        depending on the state of the dialogue
        """
        if 'room_id' not in [x['entity'] for x in tracker.latest_message['entities']] \
                and tracker.get_slot('room_id') is None:
            return ['datetime_']
        return ['room_id', 'datetime_']

    def submit(self,
               dispatcher: CollectingDispatcher,
               tracker: Tracker,
               domain: Dict[Text, Any]) -> List[Dict]:
        """Define what the form has to do
            after all required slots are filled"""

        datetime_ = tracker.get_slot("datetime_")
        d_f, d_t = datetime_.split(' -> ')
        datetime_ = self.__class__.datetime_format(datetime_)
        r = booking_query_empty("HN-KN", d_f, d_t)

        room_id = tracker.get_slot("room_id")
        if room_id is None:
            region_format = ''
        elif room_id[0] == '1':
            region_format = f' {room_id[:2]}階に'
        else:
            region_format = f' {room_id.capitalize()}区に'

        if len(r) == 0:
            dispatcher.utter_message(template="utter_no_free_room_slot", **tracker.slots)
        else:
            count = 0
            ret = f"{datetime_.capitalize()}、{region_format}空室リストは下記となります。\n[info]"
            for k, v in r.items():
                if (room_id is None and k in PROPER_NAMES) or \
                        (room_id in ROOM_GROUPS and k in ROOM_GROUPS[room_id]) \
                        or (room_id in PROPER_NAMES and room_id == k):
                    ret += PROPER_NAMES[k] + ":\n"
                    for timeslot in v:
                        ret += " " * 10 + "+ " + timeslot + "\n"
                    count += 1
            if count == 0:
                dispatcher.utter_message(template="utter_no_free_room_slot", **tracker.slots)
            else:
                ret = ret.strip() + "[/info]"
                dispatcher.utter_message(ret)

        return []

class BookingQueryRoomSchedule(CancellableForm):
    '''
    11. Chức năng hỏi lịch phòng cụ thể:
            "Lịch sử dụng phòng Bangkok ngày mai?"
    '''

    def name(self):
        """Unique identifier of the form"""
        return "booking_query_room_schedule_form"

    @staticmethod
    def required_slots(tracker: Tracker) -> List[Text]:
        """A list of required slots that the form has to fill.

        Use `tracker` to request different list of slots
        depending on the state of the dialogue
        """
        if 'repeat' not in [x['entity'] for x in tracker.latest_message['entities']] \
                and tracker.get_slot('repeat') is None:
            return ['room_id', 'datetime_']

        if 'repeat_start' not in [x['entity'] for x in tracker.latest_message['entities']] \
                and tracker.get_slot('repeat_start') is None:
            return ['datetime_', 'repeat', 'repeat_end']

        return ['datetime_', 'repeat', 'repeat_start', 'repeat_end']

    def submit(self,
               dispatcher: CollectingDispatcher,
               tracker: Tracker,
               domain: Dict[Text, Any]) -> List[Dict]:
        """Define what the form has to do
            after all required slots are filled"""

        room_id = tracker.get_slot("room_id")
        datetime_ = tracker.get_slot("datetime_")
        d_f, d_t = datetime_.split(' -> ')
        datetime_ = self.__class__.datetime_format(datetime_)

        if tracker.get_slot('repeat'):
            time_start, time_end = map(
                lambda x: x.split()[1],
                tracker.get_slot("datetime_").split(' -> ')
            )
            repeat_start = tracker.get_slot(
                "datetime_").split(' -> ')[0].split()[0]
            repeat_start_2 = tracker.get_slot("repeat_start")
            if repeat_start_2 is not None:
                repeat_start = max(repeat_start, repeat_start_2)
            try:
                available_rooms = check_recurring_room(
                    tracker.sender_id ,
                    'HN-KN',
                    time_start,
                    time_end,
                    tracker.get_slot('repeat'),
                    tracker.get_slot('repeat_start'),
                    tracker.get_slot('repeat_end')
                )
            except NotLoggedInException:
                dispatcher.utter_message(template="utter_not_logged_in")
                return [AllSlotsReset()]
            msg = "その時間に空室は:[info]" + \
                ('\n' + " " * 10 + "+ ").join(['']+available_rooms) + "[/info]"
            dispatcher.utter_message(text=msg)
            return []

        r = booking_query_room_schedule("HN-KN", d_f, d_t, room_id)
        if len(r) == 0:
            dispatcher.utter_message(template="utter_no_free_slot", **tracker.slots)
        else:
            ret = f"{datetime_}に、{PROPER_NAMES[room_id]}室は次の時間に空いているそうです。\n[info]"
            for k, v in r.items():
                ret += k + ":\n"
                for timeslot in v:
                    ret += " " * 10 + "+ " + \
                        ' -> '.join(timeslot.split(" ")[1].split('-')) + \
                        "\n"
            ret = ret.strip() + "[/info]"
            dispatcher.utter_message(ret)

        return []

class BookingQueryRoomStatus(CancellableForm):
    '''
    12. Chức năng hỏi trạng thái phòng:
            "Phòng Bangkok có ai sử dụng không?"
    '''

    def name(self):
        """Unique identifier of the form"""
        return "booking_query_room_status_form"

    @staticmethod
    def required_slots(tracker: Tracker) -> List[Text]:
        """A list of required slots that the form has to fill.

        Use `tracker` to request different list of slots
        depending on the state of the dialogue
        """
        return ['room_id']

    def submit(self,
               dispatcher: CollectingDispatcher,
               tracker: Tracker,
               domain: Dict[Text, Any]) -> List[Dict]:
        """Define what the form has to do
            after all required slots are filled"""

        room_id = tracker.get_slot('room_id')

        # won't support, deal with it.
        if room_id in ROOM_GROUPS:
            dispatcher.utter_message(template="utter_status_group_error")
            return []

        now = datetime.now(tz)
        then = now + timedelta(seconds=1)
        # assume error won't be thrown based on NLU design
        booked = booking_query_room_status(
            "HN-KN", room_id,
            now.strftime("%Y年%m月%d日・%H:%M:%S"),
            then.strftime("%Y年%m月%d日・%H:%M:%S")
        )
        try:
            occupied = get_headcount(room_id)
        except ConnectTimeout:
            occupied = None

        if occupied is None or occupied < 0:
            if not booked:
                dispatcher.utter_message(template="utter_status_available_none", **tracker.slots)
            else:
                dispatcher.utter_message(template="utter_status_booked_none", **tracker.slots)

        elif not booked and occupied == 0:
            message = f"ただ今、{room_id}は誰も予約されていませんが、誰も使用されていません。"
            dispatcher.utter_message(text=message, **tracker.slots)

        elif not booked and occupied > 0:
            message = f"{room_id}室は誰も予約されていませんが、" \
                    + f"{occupied}人に使用されています。"
            dispatcher.utter_message(text=message, **tracker.slots)

        elif booked and occupied == 0:
            message = f"ただ今、{room_id}室は誰かに予約されましたが、誰も " \
                    + f"使用されていません。"
            dispatcher.utter_message(text=message, **tracker.slots)

        elif booked and occupied > 0:
            message = f"ただ今、{room_id}室は誰かに予約されました、" \
                    + f"{occupied}人に利用されています。"
            dispatcher.utter_message(text=message, **tracker.slots)

        return []

class BookingQueryEmptyNow(Action):
    """
    13. Hỏi phòng trống hiện tại:
            "Hiện tại có phòng nào trống không?"
    """
    def name(self):
        """Unique identifier of the form"""
        return "action_booking_query_empty_now"

    def run(self,
               dispatcher: CollectingDispatcher,
               tracker: Tracker,
               domain: Dict[Text, Any]) -> List[Dict]:
        """Define what the form has to do
            after all required slots are filled"""

        room_id = [d['value'] \
            for d in tracker.latest_message.get("entities") \
            if d['entity'] == 'room_id']
        if len(room_id) == 0:
            room_id = None
        else:
            room_id = room_id[0]

        try:
            if room_id in ROOM_GROUPS:
                free = get_free(ROOM_GROUPS[room_id])
            else:
                free = get_free(ROOM_IDS)
        except ConnectTimeout:
            free = None

        if free is None:
            dispatcher.utter_message(template="utter_headcount_unreachable", **tracker.slots)
        elif len(free) == 0:
            dispatcher.utter_message(template="utter_no_free_room", **tracker.slots)
        else:
            if room_id not in ROOM_GROUPS['18F'] and room_id != '18F':
                region = '' if room_id not in ROOM_GROUPS else "区" + room_id
                dispatcher.utter_message(
                    f'現在、{region}に空室は下記となります。\n[info]' + \
                    "\n   + " + \
                    "\n   + ".join(free) + "[/info]"
                )
            else:
                dispatcher.utter_message(template='utter_headcount_18f')

        return []

class FallbackRevert(Action):
    '''
    default fallback action.
    '''
    def name(self):
        return "fallback_revert"

    def run(self,
               dispatcher: CollectingDispatcher,
               tracker: Tracker,
               domain: Dict[Text, Any]) -> List[Dict]:
        """Define what the form has to do
            after all required slots are filled"""

        dispatcher.utter_message(template="utter_fallback", **tracker.slots)
        return [UserUtteranceReverted()]

class SupportedFeatures(Action):
    '''
    yell out what it supports.
    '''
    def name(self):
        return "action_supported_features"

    def run(self,
               dispatcher: CollectingDispatcher,
               tracker: Tracker,
               domain: Dict[Text, Any]) -> List[Dict]:
        """Define what the form has to do
            after all required slots are filled"""

        ret = "できる機能は:[info]"
        ret += "\n+ ルームの予約機能:\n"
        ret += ' '*10 + '来週の金曜日の午前10時から午後11時30分までCebu室を予約してください。\n'
        ret += ' '*10 + '毎週予約をお願いします。\n'
        ret += '+ 空のカレンダーを要求する機能：\n'
        ret += ' '*10 + '明日9時から10時は空いていルームがありますか。\n'
        ret += '+ ルームのスケジュールを求める機能：\n'
        ret += ' '*10 + '明日バンコクを利用するには\n'
        ret += '+ 現在にルームの状況を聞く機能：\n'
        ret += ' '*10 + '今は誰かVientianeを使っていますか。\n'
        ret += ' '*10 + 'Dili室には何人いますか？\n'
        ret += '+ 今に空いているルームのリストを求める機能：\n'
        ret += ' '*10 + '今空いているルームはありますか？\n'
        ret += '+ 予約したルームのキャンセル機能：\n'
        ret += ' '*10 + '今日10:00のVientianeルームをキャンセルしてください。'
        ret += '[/info]'

        dispatcher.utter_message(ret)
        return []
