import sqlite3
from datetime import datetime
import requests
import time

# Vapi API base URL and token
VAPI_BASE_URL = "https://api.vapi.ai"
API_TOKEN = "db57c803-6613-4b4c-869a-23308510aeed"
headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

# Constants for waiting
MAX_WAIT_TIME = 600  # 10 minutes
CHECK_INTERVAL = 110  # 10 seconds

# Function to wait for the call to complete and return call data
def wait_for_call_completion(call_id):
    start_time = time.time()
    while True:
        if time.time() - start_time > MAX_WAIT_TIME:
            print("Timeout waiting for call to complete")
            return None
        response = requests.get(f"{VAPI_BASE_URL}/call/{call_id}", headers=headers)
        if response.status_code == 200:
            call_data = response.json()
            if call_data.get('status') == 'ended':
                return call_data
            else:
                print(f"Call status: {call_data.get('status')}")
        else:
            print(f"Error checking call status: {response.status_code}")
        time.sleep(CHECK_INTERVAL)

# Function to retrieve call details using call ID (used only for failed calls)
def retrieve_call_details(call_id):
    try:
        response = requests.get(f"{VAPI_BASE_URL}/call/{call_id}", headers=headers)
        response.raise_for_status()
        call_data = response.json()
        analysis = call_data.get('analysis', {})
        summary = analysis.get('summary', 'No summary available')
        structured_data = analysis.get('structuredData', {})
        
        extracted_name = structured_data.get('Full name', '')
        extracted_email = structured_data.get('Email account', '')
        extracted_phone = str(structured_data.get('Phone number', ''))  # Convert to string
        extracted_address = structured_data.get('Full address', '')
        extracted_dob = structured_data.get('Date of birth', '')
        extracted_zip_code = ''  # Could parse from address if needed
        transcript = call_data.get('transcript', '')
        
        return summary, extracted_name, extracted_email, extracted_phone, extracted_address, extracted_zip_code, extracted_dob, transcript
    except requests.exceptions.RequestException as e:
        print(f"Error retrieving call details: {str(e)}")
        return "Error retrieving summary", "", "", "", "", "", "", ""

# Function to initiate a call and handle analysis retrieval
def initiate_call(agent_assistant_id, agent_phone_number_id, persona_phone_number, agent_name, persona_name):
    call_name = f"call_{agent_name}_&_{persona_name}"
    print(f"DEBUG: Initiating call - Agent Assistant ID: {agent_assistant_id}, "
          f"Agent Phone Number ID: {agent_phone_number_id}, "
          f"Persona Phone Number: {persona_phone_number}, "
          f"Call Name: {call_name}")
    try:
        response = requests.post(
            "https://api.vapi.ai/call",
            headers=headers,
            json={
                "assistantId": agent_assistant_id,
                "name": call_name,
                "phoneNumberId": agent_phone_number_id,
                "customer": {
                    "number": persona_phone_number
                }
            }
        )
        response.raise_for_status()
        call_data = response.json()
        call_id = call_data['id']
        print(f"Success: Initiated call with ID {call_id}")
        
        # Wait for the call to complete
        call_data = wait_for_call_completion(call_id)
        if call_data is None:
            return call_id, "Timeout", "", "", "", "", "", "", "Timeout", ""
        
        # Extract transcript
        transcript = call_data.get('transcript', '')
        
        # Check successEvaluation
        analysis = call_data.get('analysis', {})
        success_evaluation = analysis.get('successEvaluation', 'Unknown')
        
        if success_evaluation == "Fail":
            # For failed calls, retrieve details using call ID
            summary, extracted_name, extracted_email, extracted_phone, extracted_address, extracted_zip_code, extracted_dob, transcript = retrieve_call_details(call_id)
        else:
            # For successful calls, extract data directly from response
            summary = analysis.get('summary', 'No summary available')
            structured_data = analysis.get('structuredData', {})
            extracted_name = structured_data.get('Full name', '')
            extracted_email = structured_data.get('Email account', '')
            extracted_phone = str(structured_data.get('Phone number', ''))  # Convert to string
            extracted_address = structured_data.get('Full address', '')
            extracted_dob = structured_data.get('Date of birth', '')
            extracted_zip_code = ''  # Could parse from address if needed
        
        return call_id, summary, extracted_name, extracted_email, extracted_phone, extracted_address, extracted_zip_code, extracted_dob, success_evaluation, transcript
    except requests.exceptions.RequestException as e:
        print(f"Error initiating call: {str(e)}")
        return None, "Error", "", "", "", "", "", "", "Error", ""

# Function to log the call in the database
def log_call(persona_id, persona_name, agent_id, agent_name, call_id, summary, extracted_name, extracted_email, extracted_phone, extracted_address, extracted_zip_code, extracted_dob, success_evaluation, transcript):
    conn = sqlite3.connect('simulations.db')
    c = conn.cursor()
    
    # Check if transcript column exists, add it if not
    c.execute("PRAGMA table_info(logs)")
    columns = [col[1] for col in c.fetchall()]
    if 'transcript' not in columns:
        c.execute("ALTER TABLE logs ADD COLUMN transcript TEXT")
    
    # Insert the log entry
    c.execute('''INSERT INTO logs (
        persona_id, persona_name, agent_id, agent_name, call_id, call_timestamp, 
        extracted_name, extracted_email, extracted_phone_number, extracted_full_address, 
        extracted_zip_code, extracted_date_of_birth, call_summary, success_evaluation, transcript
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
        persona_id,
        persona_name,
        agent_id,
        agent_name,
        call_id,
        datetime.now().isoformat(),
        extracted_name,
        extracted_email,
        extracted_phone,
        extracted_address,
        extracted_zip_code,
        extracted_dob,
        summary,
        success_evaluation,
        transcript
    ))
    conn.commit()
    conn.close()
    print(f"Logged call with ID {call_id} for persona {persona_id} and agent {agent_id}, Success Evaluation: {success_evaluation}")

# Function to initiate a call between persona and agent
def make_call_between_persona_and_agent(persona_id, agent_id):
    # Connect to the database
    conn = sqlite3.connect('simulations.db')
    c = conn.cursor()
    
    # Retrieve persona details
    c.execute("SELECT name, phone_number FROM personas WHERE id = ?", (persona_id,))
    persona_data = c.fetchone()
    
    # Retrieve agent details
    c.execute("SELECT vapi_assistant_id, name, outbound_phone_number FROM agents WHERE id = ?", (agent_id,))
    agent_data = c.fetchone()
    
    conn.close()
    if persona_data and agent_data:
        persona_name, persona_phone_number = persona_data
        agent_assistant_id, agent_name, agent_phone_number_id = agent_data
        
        if not all([persona_phone_number, agent_assistant_id, agent_phone_number_id]):
            print("Missing required data for call initiation")
            return
        
        # Initiate call and get results
        result = initiate_call(agent_assistant_id, agent_phone_number_id, persona_phone_number, agent_name, persona_name)
        call_id, summary, extracted_name, extracted_email, extracted_phone, extracted_address, extracted_zip_code, extracted_dob, success_evaluation, transcript = result
        
        if call_id:  # Log the call if we have a call ID
            log_call(persona_id, persona_name, agent_id, agent_name, call_id, summary, extracted_name, extracted_email, extracted_phone, extracted_address, extracted_zip_code, extracted_dob, success_evaluation, transcript)
        else:
            print("Failed to initiate call")
    else:
        print("Persona or agent not found in database")

# Example usage
if __name__ == "__main__":
    # Replace with actual IDs from your database
    persona_id = 2
    agent_id = 2
    make_call_between_persona_and_agent(persona_id, agent_id)