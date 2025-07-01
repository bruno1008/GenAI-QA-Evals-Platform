import requests
import json
import sqlite3
from datetime import datetime

# Vapi API base URL
VAPI_BASE_URL = "https://api.vapi.ai"

# API token (replace with your real token)
API_TOKEN = "db57c803-6613-4b4c-869a-23308510aeed"

# Headers for authentication
headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

# Provider and model configurations
provider_configs = {
    "openai": [
        {"model": "gpt-4", "description": "Advanced reasoning"},
        
    ],
}

# Voice configurations
voice_configs = {
    "11labs": [
        {"Voice": "bIHbv24MWmeRgasZH58o", "model": "eleven_flash_v2_5"},
    ]
}

# Transcriber configurations
transcriber_configs = {
    "deepgram": [
        {"model": "nova-2", "language": "en-US"},
    ]
}

# Read the persona prompt template from a file
with open('persona_prompt.txt', 'r') as file:
    persona_system_prompt = file.read().strip()

# Define personas without predefined phone numbers
personas = [
    {"name": "John Doe", "date_of_birth": "1990-01-01", "full_address": "123 Main St, Anytown", "zip_code": "12345", "email": "john@example.com", "phone_number": None, "AreaCode": "351"},
]

# Flatten model configurations for cycling
model_list = []
for provider, models in provider_configs.items():
    for model in models:
        model_list.append({'provider': provider, 'model': model['model']})

# Function to format date of birth
def format_date_of_birth(dob):
    date_obj = datetime.strptime(dob, "%Y-%m-%d")
    day = date_obj.day
    month = date_obj.strftime("%B")
    year = "-".join(list(str(date_obj.year)))
    return f"{day} of {month} of {year}"

# Ensure 'phone_number' column exists in 'personas' table
conn = sqlite3.connect('simulations.db')
c = conn.cursor()
c.execute("PRAGMA table_info(personas)")
columns = [col[1] for col in c.fetchall()]
if 'phone_number' not in columns:
    c.execute("ALTER TABLE personas ADD COLUMN phone_number TEXT")
conn.commit()
conn.close()

# Function to create a persona and associate a phone number
def create_persona_assistant(persona, model_config, voice_config, transcriber_config, assistant_name):
    # 1. Create the phone number without associating an assistant initially
    try:
        phone_response = requests.post(
            f"{VAPI_BASE_URL}/phone-number",
            headers=headers,
            json={
                "provider": "vapi",
                "assistantId": None,
                "numberDesiredAreaCode": persona['AreaCode'],
                "name": persona['name']
            }
        )
        phone_response.raise_for_status()
        phone_data = phone_response.json()
        print("Phone number creation response:", phone_data)
        
        # Extract phone number ID and actual phone number from the response
        phone_number_id = phone_data['id']
        phone_number = phone_data['number']  # Adjust if the key is different (e.g., 'phoneNumber')
        
    except requests.exceptions.RequestException as e:
        print(f"Error creating phone number for {persona['name']}: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status code: {e.response.status_code}")
            print(f"Response body: {e.response.text}")
        return None

    # 2. Format the system prompt with the actual phone number
    formatted_dob = format_date_of_birth(persona['date_of_birth'])
    persona_system_prompt_formatted = persona_system_prompt.format(
        name=persona['name'],
        phone_number=phone_number,  # Using the actual phone number
        email=persona['email'],
        full_address=persona['full_address'],
        zip_code=persona['zip_code'],
        formatted_dob=formatted_dob
    )
    
    print(f"System Prompt for {persona['name']}:\n{persona_system_prompt_formatted}\n{'-'*50}\n")
    
    # 3. Configure and create the assistant
    assistant_config = {
        "name": assistant_name,
        "model": {
            "provider": model_config['provider'],
            "model": model_config["model"],
            "messages": [
                {
                    "role": "system",
                    "content": persona_system_prompt_formatted
                }
            ],
            "temperature": 0.1,
            "maxTokens": 250
        },
        "voice": {
            "provider": "11labs",
            "voiceId": voice_config["Voice"],
            "model": voice_config["model"],
            "speed": 0.9,
            "stability": 0.8,
            "similarityBoost": 0.9,
            "useSpeakerBoost": True,
            "inputPunctuationBoundaries": ["，", ".", "!", "?", ";", ":"]
        },
        "transcriber": {
            "provider": "deepgram",
            "model": transcriber_config["model"],
            "language": transcriber_config["language"]
        },
        "firstMessageMode":"assistant-waits-for-user",
        "endCallMessage": "Thank you for calling and helping me complete my application. Goodbye!",
        "endCallFunctionEnabled": True,
        "backgroundDenoisingEnabled": True,
        "silenceTimeoutSeconds": 110,
        "serverMessages": ["end-of-call-report"],
        "startSpeakingPlan": {
            "waitSeconds": 1.2,
            "smartEndpointingPlan": {
                "provider": "vapi"
            }
        },
        "stopSpeakingPlan": {
            "numWords": 1,
            "voiceSeconds": 0.1,
            "backoffSeconds": 1
        }
    }
    
    try:
        assistant_response = requests.post(
            f"{VAPI_BASE_URL}/assistant",
            headers=headers,
            data=json.dumps(assistant_config)
        )
        assistant_response.raise_for_status()
        assistant_data = assistant_response.json()
        vapi_assistant_id = assistant_data['id']
    except requests.exceptions.RequestException as e:
        print(f"Error creating assistant for {persona['name']}: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status code: {e.response.status_code}")
            print(f"Response body: {e.response.text}")
        return None

    # 4. Associate the phone number with the assistant
    try:
        update_response = requests.patch(
            f"{VAPI_BASE_URL}/phone-number/{phone_number_id}",
            headers=headers,
            json={"assistantId": vapi_assistant_id}
        )
        update_response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error updating phone number {phone_number_id} with assistant ID {vapi_assistant_id}: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status code: {e.response.status_code}")
            print(f"Response body: {e.response.text}")
        return None

    # 5. Insert the persona into the database with both phone number ID and actual number
    try:
        conn = sqlite3.connect('simulations.db')
        c = conn.cursor()
        c.execute('''INSERT INTO personas (
            name, outbound_phone_number, phone_number, date_of_birth, full_address, zip_code, email,
            model_provider, model, voice_provider, voice, voice_model, transcriber_provider, transcriber_model, vapi_assistant_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
            persona['name'],
            phone_number_id,  # Store the phone number ID
            phone_number,     # Store the actual phone number
            persona['date_of_birth'],
            persona['full_address'],
            persona['zip_code'],
            persona['email'],
            model_config['provider'],
            model_config['model'],
            '11labs',
            voice_config['Voice'],
            voice_config['model'],
            'deepgram',
            transcriber_config['model'],
            vapi_assistant_id
        ))
        conn.commit()
        conn.close()
        
        print(f"Success: Persona '{assistant_name}' created and saved with ID {vapi_assistant_id}, phone number ID {phone_number_id}, and phone number {phone_number}")
        return assistant_data
    except sqlite3.Error as e:
        print(f"Database error: {str(e)}")
        return None

# Create personas with cyclic configurations
for i, persona in enumerate(personas):
    model_config = model_list[i % len(model_list)]
    voice_config = voice_configs["11labs"][i % len(voice_configs["11labs"])]
    transcriber_config = transcriber_configs["deepgram"][i % len(transcriber_configs["deepgram"])]
    assistant_name = persona['name'].replace(" ", "_")
    create_persona_assistant(persona, model_config, voice_config, transcriber_config, assistant_name)