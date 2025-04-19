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

from langchain.memory import ConversationBufferMemory
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain.chains import ConversationChain
from langchain.prompts import ChatPromptTemplate

from langchain_groq import ChatGroq
from dotenv import load_dotenv
import os
load_dotenv()

os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")
llm = ChatGroq(model="deepseek-r1-distill-llama-70b",temperature=0)

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

def update_habit_progress(cursor, habit_id, completed_days=None, total_days=None):
    fields = []
    values = []

    if completed_days is not None:
        fields.append("No_of_days_Completed = ?")
        values.append(completed_days)
    if total_days is not None:
        fields.append("Total_no_of_days = ?")
        values.append(total_days)

    values.append(habit_id)

    if fields:
        query = f"UPDATE HabitTimes SET {', '.join(fields)} WHERE HabitID = ?"
        cursor.execute(query, values)

def update_habit_days(cursor, habit_id, new_days):
    # Delete existing days
    cursor.execute("DELETE FROM HabitDays WHERE HabitID = ?", (habit_id,))
    # Insert new days
    insert_habit_days(cursor, habit_id, new_days)

# 
prompt_Remarker = ChatPromptTemplate.from_messages([
    ("system", """You are an AI assistant that helps generate a single, polished remark for a habit by combining older feedback with new observations. Your goal is to merge both remarks into a clear, meaningful sentence or paragraph. Avoid repeating information and make the result sound natural and coherent.
     Just directly give the remark without any additional explanation or context. The remark should be consice and to the point. and in 20 words or less"""),
    ("user", "Previous remarks: {Remarks}"),
    ("user", "New Remark: {text}"),
])
chain_remarker = prompt_Remarker | llm

def Remarker(text, HabitID): # Updates remarks for a habit in HabitTimes table, Note, habit already has a remark
    connection = sqlite3.connect("student.db")
    cursor = connection.cursor()
    cursor.execute("SELECT Remarks FROM Habits WHERE ID = ?", (HabitID,))
    row = cursor.fetchone()
    if row:
        Remarks = row[0]
    else :
        Remarks = " "
    raw_remark = chain_remarker.invoke({"text": text, "Remarks": Remarks})
    remark_content = raw_remark.content
    print("Remark Content:", remark_content)
    # Slice the content after </think>
    if "</think>" in remark_content:
        sliced_remark = remark_content.split("</think>", 1)[1].strip()
    else:
        sliced_remark = remark_content.strip()  # Fallback if </think> not found

    cursor.execute("UPDATE Habits SET Remarks = ? WHERE ID = ?", (sliced_remark, HabitID))
    connection.commit()
    cursor.execute("SELECT * FROM Habits")
    rows = cursor.fetchall()
    for row in rows:
        print(row)
    connection.close()

def get_habits():
    connection = sqlite3.connect("student.db")
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM Habits")
    rows = cursor.fetchall()
    connection.close()
    return rows

def get_habit_by_id(habit_id):
    connection = sqlite3.connect("student.db")
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM Habits WHERE ID = ?", (habit_id,))
    row = cursor.fetchone()
    connection.close()
    return row

def habit_no_of_days(habit_id):
    connection = sqlite3.connect("student.db")
    cursor = connection.cursor()
    cursor.execute("SELECT No_of_days_Completed, Total_no_of_days FROM HabitTimes WHERE HabitID = ?", (habit_id,))
    row = cursor.fetchone()
    connection.close()
    return row


# ---------------------------------------     Profiling  -------------------------------------

user_data = {
    "How do you usually prefer to spend your free time?": [
        "Engaging in creative activities",
        "Socializing with friends/family",
        "Learning something new"
    ],
    "What’s your ideal work style?": "I thrive in a structured environment with clear deadlines and schedules.",
    "Which of the following statements best describes your approach to tasks?": "I prefer starting with small, manageable tasks and gradually build up to bigger ones.",
    "What motivates you the most to stick to a goal or habit?": "Internal satisfaction and personal growth",
    "What kind of work or tasks do you find most draining or challenging?": "Repetitive or monotonous tasks",
    "How would you describe your decision-making process?": "I take my time and analyze all possible options before deciding.",
    "Which of the following is most important to you right now?": "Career progression and success"
}

prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a Profile generator AI.
        You are provided with a question answer session of a user and you need to generate a profile for the user based on the session.
        The profile should include the following information:Likes, Dislikes, Hobbies, Interests, and any other relevant information.""",
    ),
    ("user", "{input}"),
])
chain = prompt | llm
def generate_profile(user_data):
    response = chain.invoke({"input": user_data})

    with open('user_profile.txt', 'w') as f:
        f.write(response.content)

    sliced_remark = response.content.split("</think>", 1)[1].strip()
    return sliced_remark

# ---------------------------------------     cHATBOT    -------------------------------------

memory = ConversationBufferMemory(return_messages=True)

# Prompt to summarize SQL results
sql_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an assistant that summarizes SQL query results to help the user improve their habits. Focus on identifying habits that need attention and explain how the user can improve their consistency. SQL input is in the form: HabitID, Description, Priority, Preferences, Type, Time, Remarks"),
    ("human", "{input}")
])

# General Personal Assistant prompt
general_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a Personal Assistant that helps the user improve on himself, by giving him advice on how to be more productive, more organized, and more efficient. 
You are friendly, patient, and insightful. You understand the user's context and provide actionable, thoughtful suggestions.

Start by analyzing their current habits based on tracked data and guide them step by step toward improvement.
"""),
    ("human", "{input}")
])

# SQL Retriever Function
def retrieve_low_completion_habits():
    conn = sqlite3.connect('student.db')
    cursor = conn.cursor()

    query = """
    SELECT H.* FROM Habits H
    JOIN HabitTimes HT ON H.ID = HT.HabitID
    WHERE HT.No_of_days_Completed < HT.Total_no_of_days * 3 / 4;
    """
    cursor.execute(query)
    results = cursor.fetchall()
    conn.close()
    return results

# SQL Summary Chain
def get_sql_summary_with_context(sql_results):
    input_text = f"Summarize these habit records and give suggestions: {sql_results}"
    chain = sql_prompt | llm
    summary = chain.invoke({"input": input_text})
    memory.save_context({"input": input_text}, {"output": summary.content})
    return summary.content

# General Personal Assistant Chain
def get_general_advice(user_input):
    chain = general_prompt | llm
    response = chain.invoke({"input": user_input})
    memory.save_context({"input": user_input}, {"output": response.content})
    return response.content

# Flask endpoint
count= 0
@app.route("/habit-summary", methods=["GET", "POST"])
def habit_summary():
    global count
    try:
        # Step 1: Retrieve low-completion habits from database
        habits = retrieve_low_completion_habits()

        # Step 2: Generate SQL-based summary
        if count==0:
            sql_summary = get_sql_summary_with_context(habits)
            count=count+1

        # Step 3: Optional: Get user query from request
        user_input = request.json.get("user_input") if request.is_json else None
        advice = get_general_advice(user_input) if user_input else None

        return jsonify({
            "habit_summary": sql_summary,
            "assistant_advice": advice
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------------------------------     Flask App  -------------------------------------

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

@app.route('/profiler', methods=['POST'])
def profiler():
    data = request.json
    user_data = data['user_data']
    profile = generate_profile(user_data)
    return jsonify({"profile": profile})

@app.route('/get_habits', methods=['POST'])
def get_habits_route():
    habits = get_habits()
    return jsonify(habits)

@app.route('/get_habit_by_id', methods=['POST'])
def get_habit_by_id_route():
    data = request.json
    habit_id = data['habit_id']
    habit = get_habit_by_id(habit_id)
    return jsonify(habit)

@app.route('/insert_habit', methods=['POST'])
def insert_habit_route():
    data = request.json
    desc = data['desc']
    priority = data['priority']
    preferences = data['preferences']
    habit_type = data['habit_type']
    time = data['time']
    remarks = data['remarks']

    connection = sqlite3.connect("student.db")
    cursor = connection.cursor()
    habit_id = insert_habit(cursor, desc, priority, preferences, habit_type, time, remarks)
    connection.commit()
    connection.close()


    return jsonify({"habit_id": habit_id})

@app.route('/update_habit', methods=['POST'])
def update_habit_route():
    data = request.json
    habit_id = data['habit_id']
    desc = data.get('desc')
    priority = data.get('priority')
    preferences = data.get('preferences')
    habit_type = data.get('habit_type')
    time = data.get('time')
    remarks = data.get('remarks')

    connection = sqlite3.connect("student.db")
    cursor = connection.cursor()
    update_habit(cursor, habit_id, desc, priority, preferences, habit_type, time, remarks)
    connection.commit()
    connection.close()
    
    return jsonify({"status": "Habit updated successfully"})

@app.route('/update_habit_progress', methods=['POST'])
def update_habit_progress_route():
    data = request.json
    habit_id = data['habit_id']
    completed_days = data.get('completed_days')
    total_days = data.get('total_days')

    connection = sqlite3.connect("student.db")
    cursor = connection.cursor()
    update_habit_progress(cursor, habit_id, completed_days, total_days)
    connection.commit()
    connection.close()

    return jsonify({"status": "Habit progress updated successfully"})

@app.route('/update_habit_days', methods=['POST'])
def update_habit_days_route():
    data = request.json
    habit_id = data['habit_id']
    new_days = data['new_days']

    connection = sqlite3.connect("student.db")
    cursor = connection.cursor()
    update_habit_days(cursor, habit_id, new_days)
    connection.commit()
    connection.close()

    return jsonify({"status": "Habit days updated successfully"})

@app.route('/habit_no_of_days', methods=['POST'])
def habit_no_of_days_route():
    data = request.json
    habit_id = data['habit_id']
    days = habit_no_of_days(habit_id)
    return jsonify(days)

@app.route('/remark', methods=['POST'])
def remark_route():
    data = request.json
    text = data['text']
    habit_id = data['habit_id']
    Remarker(text, habit_id)
    return jsonify({"status": "Remark updated successfully"})

