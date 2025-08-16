from flask import Flask, render_template, request, jsonify, Response
import requests
import os
import uuid
import time
import json
from io import BytesIO
from werkzeug.utils import secure_filename
from threading import Lock
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

processing_sessions = {}
session_lock = Lock()

DIFY_API_BASE_URL = os.getenv("DIFY_API_BASE_URL", "https://api.dify.ai")
DIFY_API_KEY = os.getenv("DIFY_API_KEY")
DIFY_WORKFLOW_ID = os.getenv("DIFY_WORKFLOW_ID")
DIFY_UPLOAD_TIMEOUT = int(os.getenv("DIFY_UPLOAD_TIMEOUT", "90"))
DIFY_WORKFLOW_TIMEOUT = int(os.getenv("DIFY_WORKFLOW_TIMEOUT", "180"))
DIFY_MAX_RETRIES = int(os.getenv("DIFY_MAX_RETRIES", "2"))

if not DIFY_API_KEY or not DIFY_WORKFLOW_ID:
    print("Warning: DIFY_API_KEY and DIFY_WORKFLOW_ID environment variables must be set")
    print("Please copy .env.example to .env and update with your actual values")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload')
def upload_page():
    return render_template('upload.html')

@app.route('/api/dify/analyze', methods=['POST'])
def analyze_image():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'ファイルが選択されていません'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'ファイルが選択されていません'}), 400
        
        if file and file.filename.lower().endswith('.png'):
            filename = secure_filename(file.filename)
            
            file.seek(0)
            dify_response = send_to_dify(file, filename)
            
            if 'error' in dify_response:
                return jsonify({'error': dify_response['error']}), 500
            
            return jsonify({
                'success': True,
                'result': dify_response,
                'filename': filename
            })
        else:
            return jsonify({'error': 'PNGファイルのみ対応しています'}), 400
            
    except Exception as e:
        return jsonify({'error': f'エラーが発生しました: {str(e)}'}), 500

@app.route('/api/dify/analyze-multiple', methods=['POST'])
def analyze_multiple_images():
    try:
        files = request.files.getlist('files')
        if not files or len(files) == 0:
            return jsonify({'error': 'ファイルが選択されていません'}), 400
        
        results = []
        errors = []
        
        for file in files:
            if file.filename == '':
                continue
                
            if not file.filename.lower().endswith('.png'):
                errors.append(f'{file.filename}: PNGファイルのみ対応しています')
                continue
            
            filename = secure_filename(file.filename)
            
            try:
                file.seek(0)
                dify_response = send_to_dify(file, filename)
                
                if 'error' in dify_response:
                    errors.append(f'{filename}: {dify_response["error"]}')
                else:
                    results.append({
                        'filename': filename,
                        'result': dify_response
                    })
            except Exception as e:
                errors.append(f'{filename}: {str(e)}')
        
        if len(results) == 0:
            return jsonify({
                'error': '有効な分析結果がありません',
                'errors': errors
            }), 500
        
        response_data = {
            'success': True,
            'results': results,
            'processed_count': len(results),
            'total_count': len(files)
        }
        
        if errors:
            response_data['errors'] = errors
            
        return jsonify(response_data)
            
    except Exception as e:
        return jsonify({'error': f'エラーが発生しました: {str(e)}'}), 500

@app.route('/api/dify/analyze-sequential', methods=['POST'])
def analyze_images_sequential():
    try:
        files = request.files.getlist('files')
        if not files or len(files) == 0:
            return jsonify({'error': 'ファイルが選択されていません'}), 400
        
        session_id = str(uuid.uuid4())
        
        valid_files = []
        errors = []
        
        for file in files:
            if file.filename == '':
                continue
                
            if not file.filename.lower().endswith('.png'):
                errors.append(f'{file.filename}: PNGファイルのみ対応しています')
                continue
            
            filename = secure_filename(file.filename)
            file.seek(0)
            file_data = file.read()
            valid_files.append({'file_data': file_data, 'filename': filename})
        
        if len(valid_files) == 0:
            return jsonify({
                'error': '有効なPNGファイルがありません',
                'errors': errors
            }), 400
        
        with session_lock:
            processing_sessions[session_id] = {
                'total_files': len(valid_files),
                'processed_files': 0,
                'results': [],
                'errors': errors,
                'status': 'processing',
                'created_at': time.time()
            }
        
        import threading
        thread = threading.Thread(
            target=process_files_sequential, 
            args=(valid_files, session_id)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'total_files': len(valid_files),
            'message': 'ファイル処理を開始しました'
        })
        
    except Exception as e:
        return jsonify({'error': f'エラーが発生しました: {str(e)}'}), 500

def send_to_dify(file_obj, filename, max_retries=None):
    """Send file to Dify API using two-step process: upload then workflow execution"""
    if max_retries is None:
        max_retries = DIFY_MAX_RETRIES
        
    for attempt in range(max_retries + 1):
        try:
            print(f"DEBUG: Starting Dify API call for {filename} (attempt {attempt + 1}/{max_retries + 1})")
            
            upload_files = {
                'file': (filename, file_obj, 'image/png')
            }
            upload_data = {
                'user': 'dify-flask-app'
            }
            
            print(f"DEBUG: Uploading file to Dify...")
            upload_response = requests.post(
                f"{DIFY_API_BASE_URL}/v1/files/upload",
                headers={'Authorization': f'Bearer {DIFY_API_KEY}'},
                files=upload_files,
                data=upload_data,
                timeout=DIFY_UPLOAD_TIMEOUT
            )
            
            print(f"DEBUG: Upload response status: {upload_response.status_code}")
            if upload_response.status_code != 201:
                print(f"DEBUG: Upload response content: {upload_response.text}")
                return {'error': f'Difyファイルアップロードエラー: {upload_response.status_code}'}
            
            upload_result = upload_response.json()
            file_id = upload_result.get('id')
            print(f"DEBUG: File uploaded with ID: {file_id}")
            
            if not file_id:
                return {'error': 'ファイルアップロードからIDを取得できませんでした'}
            
            workflow_payload = {
                "inputs": {
                    "input_file": {
                        "type": "image",
                        "transfer_method": "local_file", 
                        "upload_file_id": file_id
                    }
                },
                "response_mode": "blocking",
                "user": "dify-flask-app"
            }
            
            print(f"DEBUG: Executing workflow for file: {filename}")
            print(f"DEBUG: Executing workflow with payload: {json.dumps(workflow_payload, indent=2)}")
            workflow_response = requests.post(
                f"{DIFY_API_BASE_URL}/v1/workflows/run",
                headers={
                    'Authorization': f'Bearer {DIFY_API_KEY}',
                    'Content-Type': 'application/json'
                },
                json=workflow_payload,
                timeout=(30, DIFY_WORKFLOW_TIMEOUT)  # (connection_timeout, read_timeout)
            )
            
            print(f"DEBUG: Workflow response status: {workflow_response.status_code}")
            if workflow_response.status_code == 504:
                print(f"DEBUG: Gateway timeout (504) - API server overloaded")
                if attempt < max_retries:
                    print(f"DEBUG: Retrying {filename} due to 504 timeout in {10 + attempt * 5} seconds...")
                    time.sleep(10 + attempt * 5)  # Exponential backoff for 504 errors
                    file_obj.seek(0)
                    continue
                else:
                    return {'error': f'Dify APIサーバーがタイムアウトしました (504エラー、最大{max_retries + 1}回試行)'}
            elif workflow_response.status_code != 200:
                print(f"DEBUG: Workflow response content: {workflow_response.text}")
                return {'error': f'Difyワークフロー実行エラー: {workflow_response.status_code}'}
            
            workflow_result = workflow_response.json()
            print(f"DEBUG: Workflow result: {workflow_result}")
            
            if 'data' in workflow_result and 'outputs' in workflow_result['data']:
                result_data = workflow_result['data']['outputs']
                print(f"DEBUG: Extracted result data: {result_data}")
                
                processed_data = process_dify_response(result_data)
                return processed_data
            else:
                print(f"DEBUG: No outputs found in workflow result")
                return {'error': 'Difyワークフローの実行に失敗しました'}
                
        except requests.exceptions.Timeout:
            print(f"DEBUG: Timeout error for {filename} (attempt {attempt + 1}/{max_retries + 1})")
            if attempt < max_retries:
                print(f"DEBUG: Retrying {filename} in 5 seconds...")
                time.sleep(5)
                file_obj.seek(0)
                continue
            else:
                return {'error': f'Dify APIのタイムアウトが発生しました (最大{max_retries + 1}回試行)'}
        except requests.exceptions.RequestException as e:
            print(f"DEBUG: Request error for {filename}: {str(e)}")
            return {'error': f'Dify API接続エラー: {str(e)}'}
        except Exception as e:
            print(f"DEBUG: General error for {filename}: {str(e)}")
            return {'error': f'データ取得中にエラーが発生しました: {str(e)}'}

def is_valid_json_response(response_data):
    """Check if Dify response contains structured data vs plain text error"""
    if not response_data:
        return False
    
    if isinstance(response_data, dict) and 'extracted_data' in response_data:
        return True
    
    if 'text' not in response_data:
        return isinstance(response_data, dict) and len(response_data) > 0
    
    text_content = response_data['text'].strip()
    
    if not text_content:
        return False
    
    error_indicators = [
        'error',
        'failed',
        'timeout',
        'unable to',
        'cannot',
        'invalid',
        'not found',
        'access denied'
    ]
    
    if len(text_content) < 100:
        text_lower = text_content.lower()
        if any(indicator in text_lower for indicator in error_indicators):
            return False
    
    # Check for structured data indicators
    structured_indicators = [
        '[{',  # JSON array start
        '```json',  # Markdown JSON block
        '```',  # Any markdown code block
        '"',  # JSON string indicators
        '{',  # JSON object start
    ]
    
    if any(indicator in text_content for indicator in structured_indicators):
        return True
    
    if len(text_content) > 200:
        return True
    
    return False

def process_dify_response(result_data):
    """Process Dify API response and extract structured data from various formats"""
    print(f"DEBUG: Processing Dify response: {result_data}")
    
    if isinstance(result_data, dict) and 'text' not in result_data:
        print("DEBUG: Response is already structured, returning as-is")
        return result_data
    
    text_content = ""
    if isinstance(result_data, dict) and 'text' in result_data:
        text_content = result_data['text']
    elif isinstance(result_data, str):
        text_content = result_data
    else:
        print(f"DEBUG: Unexpected response format: {type(result_data)}")
        return result_data
    
    print(f"DEBUG: Extracted text content: {text_content[:200]}...")
    
    import re
    
    json_pattern1 = r'```json\s*\n(.*?)\n```'
    match1 = re.search(json_pattern1, text_content, re.DOTALL)
    
    json_pattern2 = r'```\s*\n(.*?)\n```'
    match2 = re.search(json_pattern2, text_content, re.DOTALL)
    
    json_text = None
    if match1:
        json_text = match1.group(1).strip()
        print("DEBUG: Found JSON in markdown code block (with json specifier)")
    elif match2:
        json_text = match2.group(1).strip()
        print("DEBUG: Found JSON in markdown code block (without specifier)")
    else:
        json_text = text_content.strip()
        print("DEBUG: Attempting to parse entire text as JSON")
    
    if json_text:
        try:
            import json
            parsed_data = json.loads(json_text)
            print(f"DEBUG: Successfully parsed JSON data: {type(parsed_data)}")
            return {'extracted_data': parsed_data, 'raw_text': text_content}
        except json.JSONDecodeError as e:
            print(f"DEBUG: JSON parsing failed: {e}")
    
    print("DEBUG: Returning original text content as fallback")
    return {'text': text_content, 'parsing_note': 'Could not extract structured data'}

def process_files_sequential(valid_files, session_id):
    """Process files one by one in background thread"""
    print(f"DEBUG: Starting sequential processing for session {session_id}")
    
    for i, file_info in enumerate(valid_files):
        filename = file_info['filename']
        file_data = file_info['file_data']
        
        print(f"DEBUG: Processing file {i+1}/{len(valid_files)}: {filename}")
        
        if i > 0:
            delay = 2  # 2 second delay between files
            print(f"DEBUG: Waiting {delay} seconds before processing next file...")
            time.sleep(delay)
        
        max_file_retries = 3
        result = None
        success = False
        
        for attempt in range(max_file_retries):
            try:
                from io import BytesIO
                file_obj = BytesIO(file_data)
                
                print(f"DEBUG: Attempt {attempt + 1}/{max_file_retries} for {filename}")
                result = send_to_dify(file_obj, filename)
                
                if 'error' in result:
                    print(f"DEBUG: API error on attempt {attempt + 1}: {result['error']}")
                    if attempt < max_file_retries - 1:
                        time.sleep(2 * (attempt + 1))  # Exponential backoff: 2s, 4s, 6s
                        continue
                    else:
                        break  # Max retries reached, use this error result
                
                if not is_valid_json_response(result):
                    print(f"DEBUG: Invalid JSON format on attempt {attempt + 1} for {filename}")
                    if attempt < max_file_retries - 1:
                        time.sleep(2 * (attempt + 1))  # Exponential backoff
                        result = {'error': f'Invalid response format (attempt {attempt + 1})'}
                        continue
                    else:
                        result = {'error': f'Invalid response format after {max_file_retries} attempts'}
                        break
                
                print(f"DEBUG: Valid JSON response received for {filename} on attempt {attempt + 1}")
                success = True
                break
                
            except Exception as e:
                print(f"DEBUG: Exception on attempt {attempt + 1} for {filename}: {str(e)}")
                if attempt < max_file_retries - 1:
                    time.sleep(2 * (attempt + 1))  # Exponential backoff
                    result = {'error': f'Processing exception (attempt {attempt + 1}): {str(e)}'}
                    continue
                else:
                    result = {'error': f'Processing failed after {max_file_retries} attempts: {str(e)}'}
                    break
        
        with session_lock:
            if session_id in processing_sessions:
                session = processing_sessions[session_id]
                
                if 'error' in result or not success:
                    error_msg = f'{filename}: {result.get("error", "Unknown error")}'
                    session['errors'].append(error_msg)
                    session['results'].append({
                        'filename': filename,
                        'file_index': i,
                        'result': {'error': result.get('error', 'Processing failed')},
                        'failed': True,
                        'completed_at': time.time()
                    })
                    print(f"DEBUG: File processing failed - {error_msg}")
                else:
                    processed_result = process_dify_response(result)
                    session['results'].append({
                        'filename': filename,
                        'file_index': i,
                        'result': processed_result,
                        'failed': False,
                        'completed_at': time.time()
                    })
                    print(f"DEBUG: File processing success - {filename}")
                
                session['processed_files'] += 1
                session['last_activity'] = time.time()
                print(f"DEBUG: Completed {session['processed_files']}/{session['total_files']} files")
    
    with session_lock:
        if session_id in processing_sessions:
            processing_sessions[session_id]['status'] = 'completed'
            print(f"DEBUG: Session {session_id} completed")

@app.route('/api/dify/session/<session_id>/status')
def get_session_status(session_id):
    """Get current status and results for a processing session"""
    try:
        if session_id not in processing_sessions:
            return jsonify({'error': 'Session not found'}), 404
        
        with session_lock:
            session = processing_sessions[session_id]
            
            last_check = request.args.get('last_result_count', 0, type=int)
            new_results = session['results'][last_check:]
            
            return jsonify({
                'session_id': session_id,
                'status': session['status'],
                'processed_files': session['processed_files'],
                'total_files': session['total_files'],
                'progress_percentage': round((session['processed_files'] / session['total_files']) * 100, 1),
                'new_results': new_results,
                'total_results_count': len(session['results']),
                'errors': session['errors'],
                'completed': session['status'] == 'completed'
            })
            
    except Exception as e:
        return jsonify({'error': f'Status check error: {str(e)}'}), 500

@app.route('/api/dify/session/<session_id>/cleanup', methods=['DELETE'])
def cleanup_session(session_id):
    """Clean up completed session data"""
    try:
        with session_lock:
            if session_id in processing_sessions:
                del processing_sessions[session_id]
                return jsonify({'success': True, 'message': 'Session cleaned up'})
            else:
                return jsonify({'error': 'Session not found'}), 404
                
    except Exception as e:
        return jsonify({'error': f'Cleanup error: {str(e)}'}), 500

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
