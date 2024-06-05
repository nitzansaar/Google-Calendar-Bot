import datetime
import os
import re
import openai
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Set up OpenAI API key
openai.api_key = os.getenv('OPENAI_API_KEY')

def parse_event_details_with_openai(event_details):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that extracts structured event details from text."},
                {"role": "user", "content": f"Extract the following details from this text: {event_details}\n"
                                            "Provide the extracted details in the following format:\n"
                                            "Event Date: <event_date>\n"
                                            "Event Time: <event_time>\n"
                                            "Phone: <phone>\n"
                                            "Name: <name>\n"
                                            "Address: <address>\n"
                                            "City: <city>\n"
                                            "State: <state>\n"
                                            "Zip Code: <zip_code>\n"
                                            "Description: <description>\n"
                                            "Example:\n"
                                            "Event Date: 6.4.24\n"
                                            "Event Time: 1pm\n"
                                            "Phone: 15104144644\n"
                                            "Name: John Hornung\n"
                                            "Address: 2835 Buena Vista Way\n"
                                            "City: Berkeley\n"
                                            "State: CA\n"
                                            "Zip Code: 94708\n"
                                            "Description: Renovation project to install or replace an asphalt shingle roof."}
            ]
        )
        
        result = response['choices'][0]['message']['content'].strip()
        # Split by lines and map to the corresponding variables
        details = {}
        for line in result.split('\n'):
            if ': ' in line:
                key, value = line.split(': ', 1)
                details[key] = value
        return details
    except openai.error.RateLimitError:
        print("Rate limit exceeded. Please wait and try again later.")
        return {}
    except openai.error.InvalidRequestError as e:
        print(f"Invalid request error: {e}")
        return {}

def normalize_time_format(time_str):
    # Ensure the time format is consistent (e.g., "530pm" -> "5:30pm")
    time_str = time_str.lower().replace('.', ':')
    if len(time_str) == 4 and time_str[-2:] in ['am', 'pm']:
        time_str = time_str[:-2] + ':00' + time_str[-2:]
    if len(time_str) == 5 and time_str[-2:] in ['am', 'pm']:
        time_str = time_str[:-2] + 'm'
    if len(time_str) == 6 and time_str[-2:] in ['am', 'pm'] and ':' not in time_str:
        time_str = time_str[:1] + ':' + time_str[1:]
    if len(time_str) == 7 and time_str[-2:] in ['am', 'pm'] and ':' not in time_str:
        time_str = time_str[:2] + ':' + time_str[2:]
    return time_str

def create_event(service, parsed_details):
    required_fields = ["Event Date", "Event Time", "Phone", "Name", "Address", "City", "State", "Zip Code", "Description"]
    if not all(field in parsed_details for field in required_fields):
        print("Failed to parse event details correctly. Parsed details:", parsed_details)
        return
    
    event_date = parsed_details["Event Date"]
    event_time = normalize_time_format(parsed_details["Event Time"])
    phone = parsed_details["Phone"]
    name = parsed_details["Name"]
    address = parsed_details["Address"]
    city = parsed_details["City"]
    state = parsed_details["State"]
    zip_code = parsed_details["Zip Code"]
    description = parsed_details["Description"]

    # Parse the date and time
    try:
        event_datetime_str = f"{event_date} {event_time.upper()}"
        event_datetime = datetime.datetime.strptime(event_datetime_str, "%m.%d.%y %I:%M%p")
    except ValueError:
        try:
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

    try:
        event = service.events().insert(calendarId='primary', body=event).execute()
        print(f'Event created: {event.get("htmlLink")}')
    except HttpError as error:
        print(f"An error occurred: {error}")

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

        # Prompt user to input event details
        print("\nEnter the event details as copied from WhatsApp:")
        event_details = input().strip()

        # Split the event details into individual events
        event_blocks = re.split(r'(\d+\.\d+\.\d+ Booked)', event_details)
        if len(event_blocks) > 1:
            event_blocks = [''.join(event_blocks[i:i+2]) for i in range(1, len(event_blocks), 2)]

        # Create events for each block
        for block in event_blocks:
            parsed_details = parse_event_details_with_openai(block.strip())
            if parsed_details:
                create_event(service, parsed_details)

    except HttpError as error:
        print(f"An error occurred: {error}")

if __name__ == "__main__":
    main()
