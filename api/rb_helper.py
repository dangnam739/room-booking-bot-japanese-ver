import requests
from pprint import pprint
from typing import List, Dict, Optional
from json.decoder import JSONDecodeError
from api.exceptions import (
    AlreadyBookedException,
    InvalidParameterException,
    NotLoggedInException
)

ROOMBOOKING_URL = "https://rooms.sun-asterisk.vn/api/"
HEADCOUNT_URL = "http://10.0.1.190:8000/server/api"
TIMEOUT = 2

def attention(log):
    def wrapper(fn):
        def wrapped(*args, **kwargs):
            print(f'Note: {log} functionality.')
            return fn(*args, **kwargs)
        return wrapped
    return wrapper

@attention("Out-of-scope")
def detect_people_out(room: str) -> bool:
    """
    k hiểu lắm cơ mà quote Quân Lỗ:
    "khi bắt đầu cuộc họp mà người cuối cùng ra khỏi phòng thì sau 5p hay 10p
    gì đó không có người quay lại thì anh sẽ gọi vào cái api này để hủy phòng
    đấy đi"
    """
    url = ROOMBOOKING_URL + "detect-people-out"
    data = {'room': room}
    r = requests.post(url, json=data)

    return r.json()["message"] == "ok"

def get_headcount(room:str) -> int:
    '''
    Returns how many people are in the room right now.
    '''
    r = requests.get(HEADCOUNT_URL, timeout=TIMEOUT).json()["data"]
    r = [x["sensor_data"] for x in r if x["room"] == room.upper()][0]
    return r

def get_free(rooms:List[str]) -> List[str]:
    '''
    Returns all currently free rooms based on headcount.
    '''
    r = requests.get(HEADCOUNT_URL, timeout=TIMEOUT).json()["data"]
    upper_list = set(map(str.upper, rooms))
    ret = set()
    for entry in r:
        if entry["room"] in upper_list and entry["sensor_data"] == 0:
            ret.add(entry["room"].lower())
    return sorted(ret)

def booking_modify_add_book(
    creator: str or int,
    location: str,
    room: str,
    time_start: str,
    time_end: str,
    subject: str,
    repeat:str=None,
    repeat_end:str=None,
    capacity:str or int=None,
    attendees:List[str]=None
    ):
    """
    Parameters:
    ----------
    creator     : string or int
                    Chatwork ID of the creator
    location    : string
                    HN-KN, HCM, DN-HAGL
    room        : string
                    Room want to book
    time_*      : string
                    YYYY-MM-DD HH:MM:SS
    subject     : string
                    Event title
    repeat      : string, optional
                    Recurring event (Daily, Weekly, Monthly)
    repeat_end  : string, optional
                    Recurring end date
    capacity    : string, optional
                    Number of people will join the meeting
    attendees   : List[string], optional
                    Emails of invitees

    Returns:
    --------
    hangout     : hangout link
    gcal        : Google Calendar link
    invited     : list of invited people's emails

    Throws:
    ------
    PermissionError             : the account is not sufficiently privileged
    AlreadyBookedError          : booking an existing slot
    InvalidParameterException   : if params into API is bad
    """
    url = ROOMBOOKING_URL + 'booking-modify-add-book'
    data = {
        "data": {
            'subject': subject,
            'location': location,
            'time': {
                "start": time_start,
                "end"  : time_end
            },
            'creator': creator,
            'room': room
        }
    }
    if repeat is not None:
        data["data"]["repeat"] = repeat
        data["data"]["repeat_end"] = repeat_end
    if capacity is not None:
        data["data"]["capacity"] = capacity
    if attendees is not None:
        data["data"]["attendees"] = attendees

    '''
    upon success, it returns a JSON containing:
    room        : standard room name
    start       : time start
    end         : time end
    hangout     : hangout link
    link        : Google Calendar link
    invited     : list of invited people's emails
    subject     : subject of the meeting
    description : (will be blank since we don't send it)
    '''

    r = requests.post(url=url, json=data).json()
    if 'message' in r:
        if 'Permission denied!' in r['message']:
            raise PermissionError
        elif 'successfully' in r['message']:
            return r['data']['hangout'], r['data']['link'], r['data']['invited']
        elif 'This room is in another meeting' == r['message']:
            raise AlreadyBookedException
        elif 'Please use your Sun* Gsuite account to login' in r['message']:
            raise NotLoggedInException

    # handle more.
    raise InvalidParameterException

def booking_query_empty(
        location: str,
        time_start:str,
        time_end:str,
        rooms: Optional[List[str]]=None
    ) -> Dict[str, List[str]]:
    """
    Parameters:
    ----------
    location: HN-KN, HCM, DN-HAGL
    time_*  : YYYY-MM-DD HH:MM:SS

    Returns:
    -------
    Rooms with available timeslots.
    """
    url = ROOMBOOKING_URL + 'booking-query-empty'
    data = {
        "data": {
            'location': location,
            'time': {
                'start': time_start,
                'end'  : time_end
            }   
        }
    }
    response = requests.post(url, json=data).json()
    if 'message' in response:
        raise InvalidParameterException
    
    r = response['data']['rooms']
    if rooms is not None:
        for room in r:
            if room not in rooms:
                del r[room]
    return r

def booking_query_info(
        creator: str or int,
        room: str,
        start: str
    ) -> bool:
    """
    Check if the room is booked (and ready to be cancelled).

    Parameters:
    ----------
    creator : Chatwork ID
    room    : Room to be checked
    start   : YYYY-MM-DD HH:MM:SS

    Returns:
    -------
    Boolean, whether there exists a booking.

    Throws:
    ------
    PermissionError: the account is not in RBBot's friendlist
    """
    url = ROOMBOOKING_URL + 'booking-query-info'
    data = {
        'creator': creator,
        'room': room,
        'start': start
    }
    r = requests.post(url, json=data).json()

    # this means that the account is not in RBBot's friendlist
    if 'data' not in r:
        raise PermissionError

    return len(r['data']) > 0

@attention("Out-of-scope")
def booking_query_keeping_room(event_id:str):
    """
    Parameters:
    ----------
    event_id: string
                Event ID

    Returns:
    -------
    TBD
    """

    raise NotImplementedError
    # pylint: disable=unreachable
    url = ROOMBOOKING_URL + 'booking-query-keeping-room'
    data = {
        'data': {
            'event_id': event_id
        }
    }
    r = requests.post(url=url, json=data).json()

    return r

def booking_query_room_status(
        location:str,
        room:str,
        time_start:str,
        time_end:str
    ) -> bool:
    """
    Parameters:
    ----------
    location: HN-KN, HCM, DN-HAGL
    room    : Room to be checked
    time_*  : YYYY-MM-DD HH:MM:SS

    Returns:
    -------
    Whether the room is currently booked.
    """

    url = ROOMBOOKING_URL + 'booking-query-room-status'
    data = {
        'data': {
            'time': {
                'start': time_start,
                'end': time_end
            },
            "location": location,
            'room': room
        }
    }
    r = requests.post(url=url, json=data).json()
    if "data" not in r:
        raise InvalidParameterException
    return r["data"] == "This room is in another meeting"

def booking_query_room_schedule(
        location: str,
        time_start: str,
        time_end: str,
        room: str
    ) -> Dict[str, List[str]]:
    """
    Parameters:
    ----------
    location: HN-KN, HCM, DN-HAGL
    time_*  : YYYY-MM-DD HH:MM:SS
    room    : room to be booked

    Returns:
    -------
    Days with their free timeslots.
    """
    url = ROOMBOOKING_URL + 'booking-query-schedule-room'
    data = {
        'data': {
            'location': location,
            'time': {
                'start': time_start,
                'end'  : time_end
            },
            'room': room
        }
    }

    r = requests.post(url, json=data).json()["data"]

    return r

def booking_modify_cancel(
        creator: str or int,
        room: str,
        start: str,
        recurring: bool
    ) -> Optional[Dict]:
    """
    Parameters:
    ----------
    creator     : string or int
                    Chatwork ID
    room        : string
                    Room to be cancelled
    start       : string
                    Start time
    recurring   : bool
                    if the booking is to be deleted recurrently

    Returns:
    -------
    Nothing of value, ignore it. A JSON saying deleted.

    Throws:
    ------
    PermissionError: the account is not in RBBot's friendlist
    """
    url = ROOMBOOKING_URL + 'booking-modify-cancel'
    data = {
        'data': {
            'creator': creator,
            'room': room,
            'start': start,
            'recurring': recurring
        }
    }
    r = requests.post(url=url, json=data)

    # this means that the account is not in RBBot's friendlist
    if 'data' not in r.json():
        raise PermissionError

    return r.json()

def check_recurring_room(
        creator: str or int,
        location: str,
        start: str,
        end: str,
        repeat:str,
        repeat_start:str,
        repeat_end:str
    ) -> List[str]:
    """
    Parameters:
    ----------
    creator     : string or int
                    Chatwork ID of the creator
    location    : string
                    HN-KN, HCM, DN-HAGL
    start       : string
                    HH:MM:SS
    end         : string
                    HH:MM:SS
    repeat      : string, optional
                    Recurring event: [DWM](-2)?
    repeat_start: string, optional
                    Recurring end date                    
    repeat_end  : string, optional
                    Recurring end date

    Returns:
    --------
    list of available rooms

    Throws:
    ------
    PermissionError             : the account is not sufficiently privileged
    InvalidParameterException   : if params into API is bad
    """
    url = ROOMBOOKING_URL + 'check-recurring-room'
    data = {
        'data': {
            'creator': creator,
            'location': location,
            'start': start,
            'end': end,
            'repeat': repeat,
            'repeat_start': repeat_start,
            'repeat_end': repeat_end
        }
    }
    try:
        r = requests.post(url=url, json=data).json()
        if 'message' in r and "You didn't have permission" in r['message']:
            raise NotLoggedInException
        # because sometimes Google throws something back
        if 'data' not in r:
            raise InvalidParameterException
        return r['data']
    except JSONDecodeError:
        raise InvalidParameterException

@attention("Unneeded")
def bo_admins() -> List[str]:
    '''
    Return BO Admin Chatwork IDs.
    '''
    url = ROOMBOOKING_URL + 'bo-admins'
    r = requests.get(url)
    return r.json()['data']

if __name__ == '__main__':
    from requests.exceptions import ConnectTimeout
    try:
        print(check_recurring_room(
            "3948586",
            "HN-KN",
            "17:00:00",
            "17:30:00",
            "W",
            "2020-04-14",
            "2020-04-18"
        ))
    except ConnectTimeout:
        print('Timeout.')