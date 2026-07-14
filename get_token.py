import os
from google_auth_oauthlib.flow import Flow
from dotenv import load_dotenv

# تحديد المسار بدقة لتجنب انهيار المكتبة
current_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(current_dir, '.env'))

CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    print("❌ Error: YOUTUBE_CLIENT_ID or YOUTUBE_CLIENT_SECRET not found in .env file!")
    exit(1)

flow = Flow.from_client_config(
    client_config={
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    },
    scopes=["https://www.googleapis.com/auth/youtube.upload"],
    redirect_uri="http://localhost:8000/api/youtube/callback"
)

auth_url, _ = flow.authorization_url(
    access_type="offline",
    prompt="select_account consent",
    include_granted_scopes="true"
)

print("\n🔗 Open this link in your browser:\n")
print(auth_url)
print("\nAfter approving, copy the full URL from the browser address bar.")

code = input("\nEnter the verification CODE (the part after ?code=): ").strip()

# لو قمت بلصق الرابط كاملاً بالخطأ، السكريبت سيستخرج الكود ذكياً
if "code=" in code:
    code = code.split("code=")[1].split("&")[0]

flow.fetch_token(code=code)
creds = flow.credentials

print("\n✅ Token generated successfully!")
print(f"\nAdd this line to your .env file:\n")
print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}\n")


