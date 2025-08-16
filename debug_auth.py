import os
from dotenv import load_dotenv
import requests

print("=== Debugging Dify API Authentication ===")

load_dotenv()

api_key = os.getenv('DIFY_API_KEY')
api_base = os.getenv('DIFY_API_BASE_URL', 'https://api.dify.ai')
workflow_id = os.getenv('DIFY_WORKFLOW_ID')

print(f"API Base URL: {api_base}")
print(f"API Key length: {len(api_key) if api_key else 0}")
print(f"API Key starts with: {api_key[:10] if api_key else 'None'}...")
print(f"API Key type: {type(api_key)}")
print(f"Workflow ID: {workflow_id}")

if api_key:
    print("\\n=== Testing API Key Validity ===")
    try:
        test_url = f"{api_base}/v1/workflows/run"
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        test_payload = {
            "inputs": {},
            "response_mode": "blocking",
            "user": "test-user"
        }
        response = requests.post(test_url, headers=headers, json=test_payload, timeout=10)
        print(f"Test API call status: {response.status_code}")
        print(f"Test API call response: {response.text[:200]}...")
        if response.status_code == 401:
            print("❌ API KEY IS INVALID OR EXPIRED!")
        elif response.status_code == 400:
            print("✅ API key is valid (400 = bad request, but authenticated)")
        elif response.status_code == 200:
            print("✅ API key is valid and request succeeded")
        else:
            print(f"⚠️  Unexpected status code: {response.status_code}")
    except Exception as e:
        print(f"❌ Error testing API key: {str(e)}")
else:
    print("❌ No API key found!")

print("\\n=== Environment File Check ===")
env_file_path = ".env"
if os.path.exists(env_file_path):
    print("✅ .env file exists")
    with open(env_file_path, 'r') as f:
        content = f.read()
        print(f".env file content length: {len(content)} characters")
        if 'DIFY_API_KEY=' in content:
            print("✅ DIFY_API_KEY found in .env file")
        else:
            print("❌ DIFY_API_KEY not found in .env file")
else:
    print("❌ .env file does not exist")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Files in current directory: {os.listdir('.')}")
