import json
import os

def convert_firebase_to_env():
    """
    Convert firebase-service-account.json to proper environment variable format
    """
    
    # Check if the service account file exists
    service_account_path = './firebase-service-account.json'
    
    if not os.path.exists(service_account_path):
        print(f"❌ File not found: {service_account_path}")
        print("Please make sure firebase-service-account.json is in the same directory as this script")
        return
    
    try:
        # Read the JSON file
        with open(service_account_path, 'r') as file:
            service_account_data = json.load(file)
        
        # Convert to a single line JSON string
        # This handles escaping newlines and quotes automatically
        json_string = json.dumps(service_account_data, separators=(',', ':'))
        
        # Create the environment variable line
        env_line = f"FIREBASE_SERVICE_ACCOUNT_JSON={json_string}"
        
        # Save to .env file
        with open('.env', 'w') as env_file:
            env_file.write(env_line + '\n')
        
        print("✅ Successfully converted Firebase service account to .env format")
        print(f"�� Created/updated: .env")
        print("\n📋 Copy this line to your Render environment variable:")
        print("=" * 80)
        print(env_line)
        print("=" * 80)
        
        # Also show the first 100 characters to verify format
        print(f"\n�� Preview (first 100 chars): {env_line[:100]}...")
        
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in service account file: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    convert_firebase_to_env()
