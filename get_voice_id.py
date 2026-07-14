import os
import requests
from dotenv import load_dotenv


load_dotenv()


API_KEY = os.getenv("ELEVENLABS_API_KEY")


if not API_KEY:
    print("Error: ELEVENLABS_API_KEY variable not found in .env file")
else:
    url = "https://api.elevenlabs.io/v1/voices"
    headers = {"xi-api-key": API_KEY}

    
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        voices = response.json().get('voices', [])
        if voices:
            
            ready_voice_id = voices[0]['voice_id']
            print(f"Use this ready ID directly in your code: {ready_voice_id}")
        else:
            print("No voices available in your account, please activate at least one voice from the website.")
    else:
        print(f"Connection error: {response.status_code}")
        print(f"Error details: {response.text}")