## greetings
* greeting
    - utter_greeting

## thanks
* thanks
	- utter_welcome

## affirmative
* affirmative
	- utter_welcome

## update_existing_slot
* update_existing_slot
  - utter_no_current_request

## negative
* negative
  - utter_no_current_request

## cancelling
* cancelling
  - utter_no_current_request
  
## booking_modify_cancel
* booking_modify_cancel
  - booking_modify_cancel_form

## booking_query_empty_now
* booking_query_empty_now
  - action_booking_query_empty_now
  
## booking_query_empty
* booking_query_empty
  - booking_query_empty_form

## booking_modify_add
* booking_modify_add
  - booking_modify_add_form

## booking_query_room_schedule
* booking_query_room_schedule
  - booking_query_room_schedule_form
  
## booking_query_room_status
* booking_query_room_status
  - booking_query_room_status_form

## Hỏi phòng trống -> Đặt phòng
* booking_query_empty
  - booking_query_empty_form
* booking_modify_add
  - booking_modify_add_form

## Hỏi trạng thái phòng -> Đặt phòng
* booking_query_room_status
  - booking_query_room_status_form
* booking_modify_add
  - booking_modify_add_form

## Hỏi lịch phòng -> Đặt phòng
* booking_query_room_schedule
  - booking_query_room_schedule_form
* booking_modify_add
  - booking_modify_add_form

## Hỏi chức năng
* ask_supported_features
  - action_supported_features