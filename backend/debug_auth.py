from google_auth_oauthlib.flow import InstalledAppFlow
import os

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/drive'
]

def test_auth_url():
    if not os.path.exists("credentials.json"):
        print("credentials.json not found")
        return

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            "credentials.json", SCOPES, redirect_uri="http://localhost:3000/auth/callback"
        )
        auth_url, _ = flow.authorization_url(access_type='offline', prompt='consent')
        print(f"Generated URL: {auth_url}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_auth_url()
