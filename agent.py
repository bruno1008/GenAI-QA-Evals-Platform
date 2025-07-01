import requests
import json
import sqlite3

# Vapi API base URL
VAPI_BASE_URL = "https://api.vapi.ai"

# API token (replace with your actual token)
API_TOKEN = "db57c803-6613-4b4c-869a-23308510aeed"

# Headers for authentication
headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

# Define providers and their models
provider_configs = {
    "openai": [
        #{"model": "gpt-4", "description": "Advanced reasoning"},
        {"model": "gpt-4-turbo", "description": "High-performance turbo"}
    ],
    #"anthropic": [
       #{"model": "claude-2", "description": "Safe and interpretable"},
       # {"model": "claude-3-sonnet", "description": "Balanced performance"}
    #],
    #"google": [
        #{"model": "gemini-pro", "description": "General-purpose"},
        #{"model": "gemini-ultra", "description": "Advanced reasoning"}
    #]
}

# Define voice configurations
voice_configs = {
    "11labs": [
        {"Voice": "bIHbv24MWmeRgasZH58o", "model": "eleven_flash_v2_5"},
        #{"Voice": "Will", "model": "ElevenLabs-turbo-v2_5"}    
        ]
}

# Define transcriber configurations
transcriber_configs = {
    "deepgram": [
        {"model": "nova-2", "language": "en-US"},
        #{"model": "nova-3", "language": "es-US"}
    ]
}

# Read system prompt for agents from file
with open('agent_prompt.txt', 'r') as file:
    agent_system_prompt = file.read().strip()

# Initialize the database
def init_db():
    conn = sqlite3.connect('simulations.db')
    c = conn.cursor()
    # Create agents table with initial columns
    c.execute('''CREATE TABLE IF NOT EXISTS agents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        model_provider TEXT,
        model TEXT,
        voice_provider TEXT,
        voice TEXT,
        voice_model TEXT,
        transcriber_provider TEXT,
        transcriber_model TEXT,
        vapi_assistant_id TEXT
    )''')
    # Add new columns if they don't exist
    c.execute("PRAGMA table_info(agents)")
    columns = [col[1] for col in c.fetchall()]
    if 'outbound_phone_number' not in columns:
        c.execute("ALTER TABLE agents ADD COLUMN outbound_phone_number TEXT")
    if 'phone_number' not in columns:
        c.execute("ALTER TABLE agents ADD COLUMN phone_number TEXT")
    # Create other tables
    c.execute('''CREATE TABLE IF NOT EXISTS personas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        outbound_phone_number TEXT,
        date_of_birth TEXT,
        full_address TEXT,
        zip_code TEXT,
        email TEXT,
        model_provider TEXT,
        model TEXT,
        voice_provider TEXT,
        voice TEXT,
        voice_model TEXT,
        transcriber_provider TEXT,
        transcriber_model TEXT,
        vapi_assistant_id TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        persona_id INTEGER,
        persona_name TEXT,
        agent_id INTEGER,
        agent_name TEXT,
        call_id TEXT,
        call_timestamp TEXT,
        extracted_name TEXT,
        extracted_email TEXT,
        extracted_phone_number TEXT,
        extracted_full_address TEXT,
        extracted_zip_code TEXT,
        extracted_date_of_birth TEXT,
        call_summary TEXT
    )''')
    conn.commit()
    conn.close()

# Function to create an agent assistant with a phone number
def create_agent_assistant(provider, model_config, voice_config, transcriber_config, assistant_name, area_code="351"):
    # Step 1: Create the phone number
    try:
        phone_response = requests.post(
            f"{VAPI_BASE_URL}/phone-number",
            headers=headers,
            json={
                "provider": "vapi",
                "assistantId": None,
                "numberDesiredAreaCode": area_code,
                "name": assistant_name
            }
        )
        phone_response.raise_for_status()
        phone_data = phone_response.json()
        phone_number_id = phone_data['id']
        phone_number = phone_data['number']  # Adjust key if API response differs
        print(f"Created phone number for {assistant_name}: ID={phone_number_id}, Number={phone_number}")
    except requests.exceptions.RequestException as e:
        print(f"Error creating phone number for {assistant_name}: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status code: {e.response.status_code}")
            print(f"Response body: {e.response.text}")
        return None

    # Step 2: Create the assistant
    assistant_config = {
        "name": assistant_name,
        "model": {
            "provider": provider,
            "model": model_config["model"],
            "messages": [
                {
                    "role": "system",
                    "content": agent_system_prompt
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
            "language": transcriber_config["language"],
            "confidenceThreshold": 0.4
        },
        "firstMessage": "Hello, this is Alex from SwordHealth. I'm calling to help you complete your application. Is now a good time to collect this information?",
        "firstMessageMode":"assistant-speaks-first",
        "voicemailMessage": "Hello, this is Alex from SwordHealth. I'm calling to collect some information for your application. Please call us back at your convenience so we can complete this process for you.",
        "endCallMessage": "Thank you!",
        "endCallFunctionEnabled": True,
        "backgroundDenoisingEnabled": True,
        "silenceTimeoutSeconds": 110,
        "serverMessages": ["end-of-call-report"],
        "analysisPlan": {
            "summaryPlan": {
                "messages": [
                    {
                        "content": "You are an AI assistant that summarizes the call transcript. Your summary should be concise and cover the main points discussed during the call.",
                        "role": "system"
                    }
                ],
                "enabled": True,
            },
            "structuredDataPlan": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "Full name": {"description": "This function must extract the full name of the client.", "type": "string"},
                        "Full address": {"description": "This function must extract the full address of the client by merging the street address, state and zip code provided.", "type": "string"},
                        "Phone number": {"description": "This function must extract the full phone number of the client.", "type": "number"},
                        "Date of birth": {"description": "This function must extract the date of birth of the client.", "type": "string"},
                        "Email account": {"description": "This function must extract the email account of the client.", "type": "string"}
                    },
                    "required": ["Full name", "Full address", "Phone number", "Date of birth", "Email account"]
                },
                "messages": [
                    {
                        "content": "Your will be given a transcript call and a system prompt for you to handle. You need to extract some information from the client, such as:\n\nFull name;\nPhone number;\nEmail account;\nFull address (Street address, State , ZipCode);\nDate of birth (in month-day-year format);\n\nBy using the respective functions.\n\nJson Schema:\n{{schema}}\n\nOnly respond with the JSON.",
                        "role": "system"
                    },
                    {
                        "content": "Here is the transcript:\n\n{{transcript}}\n\n. Here is the ended reason of the call:\n\n{{endedReason}}\n\n",
                        "role": "user"
                    }
                ]
            }
        },
        "startSpeakingPlan": {
            "waitSeconds": 0.9,
            "smartEndpointingPlan": {
                "provider": "vapi"
            }
        },
        "stopSpeakingPlan": {
            "numWords": 1,
            "voiceSeconds": 0.2,
            "backoffSeconds": 2
        }
    }
    
    try:
        response = requests.post(
            f"{VAPI_BASE_URL}/assistant",
            headers=headers,
            data=json.dumps(assistant_config)
        )
        response.raise_for_status()
        assistant_data = response.json()
        vapi_assistant_id = assistant_data['id']
    except requests.exceptions.RequestException as e:
        print(f"Error creating assistant {assistant_name}: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status code: {e.response.status_code}")
            print(f"Response body: {e.response.text}")
        return None

    # Step 3: Associate the phone number with the assistant
    try:
        update_response = requests.patch(
            f"{VAPI_BASE_URL}/phone-number/{phone_number_id}",
            headers=headers,
            json={"assistantId": vapi_assistant_id}
        )
        update_response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error associating phone number with assistant {assistant_name}: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status code: {e.response.status_code}")
            print(f"Response body: {e.response.text}")
        return None

    # Step 4: Insert into database
    try:
        conn = sqlite3.connect('simulations.db')
        c = conn.cursor()
        c.execute('''INSERT INTO agents (
            name, model_provider, model, voice_provider, voice, voice_model, transcriber_provider, transcriber_model, vapi_assistant_id, outbound_phone_number, phone_number
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
            assistant_name,
            provider,
            model_config['model'],
            '11labs',
            voice_config['Voice'],
            voice_config['model'],
            'deepgram',
            transcriber_config['model'],
            vapi_assistant_id,
            phone_number_id,
            phone_number
        ))
        conn.commit()
        conn.close()
        print(f"Success: Created and saved '{assistant_name}' with ID {vapi_assistant_id} and phone number {phone_number}")
        return assistant_data
    except sqlite3.Error as e:
        print(f"Database error for {assistant_name}: {str(e)}")
        return None

# Initialize the database
init_db()

# Create agents with different configurations
assistant_count = 1
for provider, models in provider_configs.items():
    for model_config in models:
        for voice_config in voice_configs["11labs"]:
            for transcriber_config in transcriber_configs["deepgram"]:
                assistant_name = "BrunoV0"
                # Optional: Uncomment for unique names
                # assistant_name = f"Agent-{assistant_count}-{provider}-{model_config['model']}-{voice_config['model']}-{transcriber_config['model']}"
                create_agent_assistant(provider, model_config, voice_config, transcriber_config, assistant_name)
                assistant_count += 1