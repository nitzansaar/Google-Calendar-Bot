import datetime
import os.path
import re
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar"]

def preprocess_event_details(event_details):
    # Add a space between the time and phone number if they are stuck together
    event_details = re.sub(r'(\d+[apmAPM]+)(\d{10})', r'\1 \2', event_details)
    return event_details

def create_event(service, event_details):
    # Preprocess the event details
    event_details = preprocess_event_details(event_details)
    
    # Regex to match the event details format, allowing for flexible spacing
    event_pattern = re.compile(
        r'(\d+\.\d+\.\d+) Booked (\d+\.\d+\.\d+) (\d+[apmAPM]+)\s+'
        r'(\d+)\s+([^\t]+)\t+([^\t]+)\t+([^\t]+)\t+([A-Z]{2})\t+(\d+)\t+'
        r'([^\n]+)'
    )
    
    match = event_pattern.match(event_details)
    if not match:
        print("Invalid format. Please ensure the input matches the expected format.")
        return

    _, event_date, event_time, phone, name, address, city, state, zip_code, description = match.groups()

    # Parse the date and time
    try:
        event_datetime_str = f"{event_date} {event_time.upper()}"
        event_datetime = datetime.datetime.strptime(event_datetime_str, "%m.%d.%y %I%p")
    except ValueError:
        print("Invalid date/time format. Please check the input.")
        return

    # Start and end time of the event
    start_datetime = event_datetime.isoformat()
    end_datetime = (event_datetime + datetime.timedelta(minutes=60)).isoformat()

    event = {
        'summary': f"ros {phone} {name}",
        'location': f"{address}, {city}, {state} {zip_code}",
        'description': description,
        'start': {
            'dateTime': start_datetime,
            'timeZone': 'America/Los_Angeles',
        },
        'end': {
            'dateTime': end_datetime,
            'timeZone': 'America/Los_Angeles',
        },
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'popup', 'minutes': 10},
            ],
        },
    }

    event = service.events().insert(calendarId='primary', body=event).execute()
    print(f'Event created: {event.get("htmlLink")}')

def main():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        service = build("calendar", "v3", credentials=creds)

        # Get upcoming 10 events
        now = datetime.datetime.utcnow().isoformat() + "Z"
        print("Getting the upcoming 10 events")
        events_result = service.events().list(
            calendarId="primary", timeMin=now, maxResults=10, singleEvents=True, orderBy="startTime"
        ).execute()
        events = events_result.get("items", [])

        if not events:
            print("No upcoming events found.")
        else:
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                print(start, event["summary"])

        # Prompt user to input event details
        print("\nEnter the event details as copied from WhatsApp:")
        event_details = input().strip()

        # Split the event details into individual events
        event_blocks = re.split(r'(\d+\.\d+\.\d+ Booked)', event_details)
        if len(event_blocks) > 1:
            event_blocks = [''.join(event_blocks[i:i+2]) for i in range(1, len(event_blocks), 2)]

        # Create events for each block
        for block in event_blocks:
            create_event(service, block.strip())

    except HttpError as error:
        print(f"An error occurred: {error}")

if __name__ == "__main__":
    main()