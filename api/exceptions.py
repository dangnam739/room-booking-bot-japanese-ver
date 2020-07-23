class AlreadyBookedException(Exception):
    '''
    placeholder to throw when booking a booked room.
    '''
    pass

class InvalidParameterException(Exception):
    '''
    placeholder to throw when a RB API call has bad fields.
    '''
    pass

class NotLoggedInException(Exception):
    '''
    placeholder to throw when account has not registered on
    Sun* Gsuite account.
    '''
    pass
