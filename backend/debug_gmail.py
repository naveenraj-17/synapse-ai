from google_service import get_gmail_service

def debug_gmail():
    print("Attempting to authenticate...")
    try:
        service = get_gmail_service()
        print("Authentication successful!")
        
        print("Attempting to list messages...")
        results = service.users().messages().list(userId="me", maxResults=5).execute()
        
        print(f"Raw results keys: {results.keys()}")
        
        messages = results.get("messages", [])
        print(f"Number of messages found: {len(messages)}")
        
        if len(messages) == 0:
            print("No messages returned by API. This means either the inbox is empty or the API is filtering them.")
        
        for msg in messages:
            print(f"Found message ID: {msg['id']}")
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_gmail()
