import os
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from bs4 import BeautifulSoup
from email.mime.text import MIMEText

from core.config import TOKEN_FILE, CREDENTIALS_FILE

# If modifying these scopes, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/calendar'
]

class UnauthenticatedError(Exception):
    pass

def get_google_credentials():
    """Returns valid credentials or None."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if creds and creds.valid:
        return creds
        
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Save the refreshed credentials
            with open(TOKEN_FILE, "w") as token:
                token.write(creds.to_json())
            return creds
        except Exception:
            pass
            
    return None

def get_auth_url(redirect_uri):
    """Generates the OAuth2 authorization URL."""
    if not os.path.exists(CREDENTIALS_FILE):
         # Create a dummy credentials file to prevent crash and show Google error
         dummy_creds = {
             "installed": {
                 "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
                 "project_id": "YOUR_PROJECT_ID",
                 "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                 "token_uri": "https://oauth2.googleapis.com/token",
                 "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                 "client_secret": "YOUR_CLIENT_SECRET",
                 "redirect_uris": [redirect_uri]
             }
         }
         os.makedirs(os.path.dirname(CREDENTIALS_FILE), exist_ok=True)
         import json
         with open(CREDENTIALS_FILE, 'w') as f:
             json.dump(dummy_creds, f, indent=4)

    flow = InstalledAppFlow.from_client_secrets_file(
        CREDENTIALS_FILE, SCOPES, redirect_uri=redirect_uri
    )
    # Using access_type='offline' is crucial for receiving a refresh token
    auth_url, _ = flow.authorization_url(access_type='offline', prompt='consent', include_granted_scopes='true')
    print(f"DEBUG: Auth URL: {auth_url}")
    return auth_url

def finish_auth(code, redirect_uri):
    """Exchanges the auth code for credentials."""
    flow = InstalledAppFlow.from_client_secrets_file(
        CREDENTIALS_FILE, SCOPES, redirect_uri=redirect_uri
    )
    flow.fetch_token(code=code)
    creds = flow.credentials
    
    with open(TOKEN_FILE, "w") as token:
        token.write(creds.to_json())
        
    return creds

def get_service(api, version):
    """Returns an authorized service instance or raises UnauthenticatedError."""
    creds = get_google_credentials()
    if not creds:
        raise UnauthenticatedError("User is not authenticated.")
    return build(api, version, credentials=creds)

def get_gmail_service():
    """Returns an authorized Gmail API service instance."""
    return get_service('gmail', 'v1')

def get_drive_service():
    """Returns an authorized Drive API service instance."""
    return get_service('drive', 'v3')

def get_calendar_service():
    """Returns an authorized Calendar API service instance."""
    return get_service('calendar', 'v3')

# --- Helper Functions ---

def list_messages(query=None, limit=5):
    """Lists messages from the user's mailbox.
    
    Args:
        query: String query to filter messages (e.g., 'subject:insurance').
        limit: Max number of messages to return.
    """
    print(f"DEBUG: list_messages called with query='{query}', limit={limit} (type: {type(limit)})")
    try:
        service = get_gmail_service()
        
        results = service.users().messages().list(userId="me", q=query, maxResults=limit).execute()
        messages = results.get("messages", [])
        
        email_summaries = []
        if not messages:
            return []

        for msg in messages:
            # Get full details for snippet and headers
            full_msg = service.users().messages().get(userId="me", id=msg['id'], format='metadata', metadataHeaders=['From', 'Subject', 'Date']).execute()
            
            headers = full_msg.get("payload", {}).get("headers", [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), '(Unknown Sender)')
            
            email_summaries.append({
                "id": msg['id'],
                "snippet": full_msg.get("snippet", ""),
                "subject": subject,
                "sender": sender
            })
            
        return email_summaries

    except UnauthenticatedError:
        raise
    except Exception as e:
        print(f"An error occurred: {e}")
        return []

def get_message(message_id):
    """Get the full content of a message."""
    try:
        service = get_gmail_service()
        message = service.users().messages().get(userId="me", id=message_id, format='full').execute()
        
        payload = message.get('payload', {})
        headers = payload.get("headers", [])
        
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
        sender = next((h['value'] for h in headers if h['name'] == 'From'), '(Unknown Sender)')
        date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
        
        # Decode body
        parts = payload.get('parts')
        body_text = ""
        body_html = None
        
        # Helper to recursively extract parts
        def parse_parts(parts):
            text = ""
            html = None
            for part in parts:
                mime_type = part.get('mimeType')
                body = part.get('body', {})
                data = body.get('data')
                
                if part.get('parts'):
                    # Recursive call
                    nested_text, nested_html = parse_parts(part.get('parts'))
                    text += nested_text
                    if nested_html and not html:
                        html = nested_html
                
                if mime_type == 'text/plain' and data:
                    text += base64.urlsafe_b64decode(data).decode('utf-8')
                elif mime_type == 'text/html' and data:
                    html = base64.urlsafe_b64decode(data).decode('utf-8')
            return text, html

        if parts:
            body_text, body_html = parse_parts(parts)
        else:
            # Single part message
            data = payload.get('body', {}).get('data', '')
            if data:
                body_text = base64.urlsafe_b64decode(data).decode('utf-8')
        
        # If no text found but html exists, use BS to strip tags for text body
        if not body_text and body_html:
             soup = BeautifulSoup(body_html, 'html.parser')
             body_text = soup.get_text()

        text = body_text if body_text else "(No body content found)"

        return {
            "id": message['id'],
            "subject": subject,
            "sender": sender,
            "date": date,
            "body": text,
            "html_body": body_html
        }

    except UnauthenticatedError:
        raise
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

def send_email(to, subject, body, cc=None, bcc=None):
    """Sends an email message.

    Args:
        to: Recipient email address.
        subject: Email subject.
        body: Email body text.
        cc: Optional CC recipient(s).
        bcc: Optional BCC recipient(s).
    """
    try:
        service = get_gmail_service()
        
        message = MIMEText(body)
        message['to'] = to
        if cc:
            message['Cc'] = cc
        if bcc:
            message['Bcc'] = bcc
        message['subject'] = subject
        
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        body = {'raw': raw}

        message = service.users().messages().send(userId="me", body=body).execute()
        print(f"DEBUG: Message Sent. Id: {message['id']}")
        return message
    except UnauthenticatedError:
        raise
    except Exception as e:
        print(f"An error occurred sending email: {e}")
        return None
