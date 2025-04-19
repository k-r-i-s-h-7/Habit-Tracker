from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from flask import Flask
import sqlite3
app = Flask(__name__)
from flask import request, jsonify
SCOPES = ['https://www.googleapis.com/auth/calendar',
          'https://www.googleapis.com/auth/gmail.modify',
          'https://www.googleapis.com/auth/presentations',
          'https://www.googleapis.com/auth/gmail.readonly']

# ---------------------------------------     Basic functions for calendar  -------------------------------------

def generate_rrule(weekdays, repeat_until=None):
    day_map = {
        "Monday": "MO",
        "Tuesday": "TU",
        "Wednesday": "WE",
        "Thursday": "TH",
        "Friday": "FR",
        "Saturday": "SA",
        "Sunday": "SU"
    }
    byday = [day_map[day] for day in weekdays if day in day_map]

    if len(byday) == 7 or len(byday) == 0:
        rule = "RRULE:FREQ=DAILY"
    else:
        rule = f"RRULE:FREQ=WEEKLY;BYDAY={','.join(byday)}"

    if repeat_until:
        rule += f";UNTIL={repeat_until.strftime('%Y%m%dT%H%M%SZ')}"

    return rule

from datetime import datetime



def schedule_daily_habit(summary, start_time, end_time, attendees_emails=[], repeat_until=None, days =[]):# Schedules daily habits for user into calendar
    # Authenticate
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=8080)
    service = build('calendar', 'v3', credentials=creds)

    # Recurrence rule: DAILY
    
    recurrence_rule = generate_rrule(days, repeat_until)
    if repeat_until:
        recurrence_rule += f";UNTIL={repeat_until.strftime('%Y%m%dT%H%M%SZ')}"

    event = {
        'summary': summary,
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'popup', 'minutes':0 },
                
            ]
        },
        'start': {'dateTime': start_time.isoformat(), 'timeZone': 'UTC'},
        'end': {'dateTime': end_time.isoformat(), 'timeZone': 'UTC'},
        'attendees': [{'email': email} for email in attendees_emails],
        'recurrence': [recurrence_rule],
    }

    created_event = service.events().insert(
        calendarId='primary',
        body=event
    ).execute()

    return created_event.get('htmlLink', 'Recurring event created, but no link returned.')

def create_google_event(summary, start_time, end_time): # Schedules tasks for the user
    # Authenticate
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)

    creds = flow.run_local_server(port=8080)
    service = build('calendar', 'v3', credentials=creds)
    
    event = {
        'summary': summary,
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'popup', 'minutes':0 },
                
            ]
        },
        'start': {'dateTime': start_time.isoformat(), 'timeZone': 'UTC'},
        'end': {'dateTime': end_time.isoformat(), 'timeZone': 'UTC'},
    }

    created_event = service.events().insert(
        calendarId='primary',
        body=event,
        conferenceDataVersion=1
    ).execute()

    return created_event.get('htmlLink', 'No event created.')

def reschedule_event(event_name, new_start_time, new_end_time):
    # Authenticate
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=8080)
    service = build('calendar', 'v3', credentials=creds)
    
    # Search for the event by name (no ordering if singleEvents is False)
    events_result = service.events().list(
        calendarId='primary',
        q=event_name,
        singleEvents=False,  # This includes recurring master events
        maxResults=10
    ).execute()
    
    events = events_result.get('items', [])
    
    if not events:
        return f"No events found with name: {event_name}"
    
    # Get the first matching event
    event = events[0]
    event_id = event['id']
    
    # Update the start and end time
    event['start']['dateTime'] = new_start_time.isoformat()
    event['end']['dateTime'] = new_end_time.isoformat()
    event['start']['timeZone'] = 'UTC'
    event['end']['timeZone'] = 'UTC'

    # Update the event
    updated_event = service.events().update(
        calendarId='primary',
        eventId=event_id,
        body=event
    ).execute()
    
    return updated_event.get('htmlLink', 'Event rescheduled, but no link returned.')

def list_events_for_day():
    target_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) #today
    # Authenticate
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=8080)
    service = build('calendar', 'v3', credentials=creds)

    # Define start and end of the day in UTC
    start_of_day = datetime.combine(target_date, datetime.min.time()).isoformat() + 'Z'
    end_of_day = datetime.combine(target_date, datetime.max.time()).isoformat() + 'Z'

    # Get events
    events_result = service.events().list(
        calendarId='primary',
        timeMin=start_of_day,
        timeMax=end_of_day,
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])

    clean_events = []
    for event in events:
        event_type = 'habit' if 'recurringEventId' in event or 'recurrence' in event else 'task'
        clean_events.append({
            'summary': event.get('summary', 'No Title'),
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 10},
                    {'method': 'email', 'minutes': 30}
                ]
            },
            'start': event['start'].get('dateTime', event['start'].get('date')),
            'end': event['end'].get('dateTime', event['end'].get('date')),
            'event_type': event_type
        })

    return clean_events

3 # ---------------------------------------     SQL Working  -------------------------------------
def insert_habit(cursor, desc, priority, preferences, habit_type, time, remarks):
    cursor.execute("""
        INSERT INTO Habits (Desc, Priority, Prefernces, Type, Time, Remarks)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (desc, priority, preferences, habit_type, time, remarks))

    return cursor.lastrowid  # Returns the new Habit ID

def insert_habit_days(cursor, habit_id, days_list):
    day_tuples = [(habit_id, day) for day in days_list]
    cursor.executemany("INSERT INTO HabitDays (HabitID, Day) VALUES (?, ?)", day_tuples)

def insert_habit_progress(cursor, habit_id, completed_days, total_days):
    cursor.execute("""
        INSERT INTO HabitTimes (HabitID, No_of_days_Completed, Total_no_of_days)
        VALUES (?, ?, ?)
    """, (habit_id, completed_days, total_days))
def update_habit(cursor, habit_id, desc=None, priority=None, preferences=None, habit_type=None, time=None, remarks=None):
    fields = []
    values = []

    if desc:
        fields.append("Desc = ?")
        values.append(desc)
    if priority:
        fields.append("Priority = ?")
        values.append(priority)
    if preferences:
        fields.append("Prefernces = ?")
        values.append(preferences)
    if habit_type:
        fields.append("Type = ?")
        values.append(habit_type)
    if time:
        fields.append("Time = ?")
        values.append(time)
    if remarks:
        fields.append("Remarks = ?")
        values.append(remarks)

    values.append(habit_id)

    if fields:
        query = f"UPDATE Habits SET {', '.join(fields)} WHERE ID = ?"
        cursor.execute(query, values)

def update_habit_days(cursor, habit_id, new_days):
    # Delete existing days
    cursor.execute("DELETE FROM HabitDays WHERE HabitID = ?", (habit_id,))
    # Insert new days
    insert_habit_days(cursor, habit_id, new_days)


@app.route('/schedule_habit', methods=['POST'])
def schedule_habit():
    data = request.json
    summary = data['summary']
    start_time = datetime.fromisoformat(data['start_time'])
    end_time = datetime.fromisoformat(data['end_time'])
    attendees_emails = data.get('attendees_emails', [])
    repeat_until = data.get('repeat_until', None)
    days = data.get('days', [])

    if repeat_until:
        repeat_until = datetime.fromisoformat(repeat_until)

    link = schedule_daily_habit(summary, start_time, end_time, attendees_emails, repeat_until, days)

@app.route('/reschedule_habit', methods=['POST'])
def reschedule_habit():
    data = request.json
    event_name = data['event_name']
    new_start_time = datetime.fromisoformat(data['new_start_time'])
    new_end_time = datetime.fromisoformat(data['new_end_time'])

    link = reschedule_event(event_name, new_start_time, new_end_time)


@app.route('/list_events', methods=['GET'])
def list_events():
    events = list_events_for_day()
    return jsonify(events)




