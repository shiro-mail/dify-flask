from flask import Flask, render_template, request, jsonify, Response
import sqlite3
import os
import json
import time
from datetime import datetime
import requests
import re
import uuid
from io import BytesIO
from werkzeug.utils import secure_filename
from threading import Lock
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# データベースの初期化
def init_database():
    conn = sqlite3.connect('inventory_data.db')
    cursor = conn.cursor()
    
    # 基本情報テーブルの作成
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS basic_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ページ TEXT,
            出荷日 TEXT,
            受注番号 TEXT,
            納入先番号 TEXT,
            担当者 TEXT,
            税抜合計 TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# アプリケーション起動時にデータベースを初期化
init_database()

processing_sessions = {}
session_lock = Lock()

DIFY_API_BASE_URL = os.getenv("DIFY_API_BASE_URL", "https://api.dify.ai")
DIFY_API_KEY = os.getenv("DIFY_API_KEY")
DIFY_WORKFLOW_ID = os.getenv("DIFY_WORKFLOW_ID")

if not DIFY_API_KEY or not DIFY_WORKFLOW_ID:
    print("Warning: DIFY_API_KEY and DIFY_WORKFLOW_ID environment variables must be set")
    print("Please copy .env.example to .env and update with your actual values")

@app.route('/')
def index():
    return render_template('upload.html')

@app.route('/upload')
def upload_page():
    return render_template('upload.html')

@app.route('/data')
def data_page():
    return render_template('data.html')

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
                'created_at': time.time(),
                'current_processing': None,
                'original_files': valid_files
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

def is_valid_json_response(result_data):
    """Check if the result contains valid JSON data"""
    if not result_data:
        return False
    
    if 'extracted_data' in result_data:
        extracted = result_data['extracted_data']
        if isinstance(extracted, (dict, list)) and extracted:
            return True
    
    if 'text' in result_data:
        text_content = result_data['text']
        if isinstance(text_content, str):
            if '```json' in text_content:
                json_match = re.search(r'```json\s*\n(.*?)\n```', text_content, re.DOTALL)
                if json_match:
                    try:
                        json.loads(json_match.group(1))
                        return True
                    except:
                        pass
            
            text_content = text_content.strip()
            if text_content.startswith('[{') and text_content.endswith('}]'):
                try:
                    json.loads(text_content)
                    return True
                except:
                    pass
    
    return False

def send_to_dify_with_progress(file_obj, filename, session_id, file_index, max_retries=3):
    """Send file to Dify API with progress tracking and retry logic"""
    
    try:
        print(f"DEBUG: Starting Dify API call for {filename}")
        
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
            timeout=30
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
        
    except requests.exceptions.Timeout:
        print(f"DEBUG: Upload timeout error for {filename}")
        return {'error': 'Dify APIアップロードのタイムアウトが発生しました'}
    except requests.exceptions.RequestException as e:
        print(f"DEBUG: Upload request error for {filename}: {str(e)}")
        return {'error': f'Dify APIアップロード接続エラー: {str(e)}'}
    except Exception as e:
        print(f"DEBUG: Upload general error for {filename}: {str(e)}")
        return {'error': f'ファイルアップロード中にエラーが発生しました: {str(e)}'}
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"DEBUG: Workflow execution attempt {attempt}/{max_retries} for {filename}")
            
            with session_lock:
                if session_id in processing_sessions:
                    processing_sessions[session_id]['current_processing']['current_attempt'] = attempt
            
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
            
            print(f"DEBUG: Executing workflow with payload: {json.dumps(workflow_payload, indent=2)}")
            workflow_response = requests.post(
                f"{DIFY_API_BASE_URL}/v1/workflows/run",
                headers={
                    'Authorization': f'Bearer {DIFY_API_KEY}',
                    'Content-Type': 'application/json'
                },
                json=workflow_payload,
                timeout=(30, 300)
            )
            
            print(f"DEBUG: Workflow response status: {workflow_response.status_code}")
            if workflow_response.status_code != 200:
                print(f"DEBUG: Workflow response content: {workflow_response.text}")
                if attempt == max_retries:
                    return {'error': f'Difyワークフロー実行エラー: {workflow_response.status_code} (最大{max_retries}回試行後)'}
                else:
                    print(f"DEBUG: Retrying workflow execution for {filename} (attempt {attempt + 1})")
                    time.sleep(2)  # Wait 2 seconds before retry
                    continue
            
            workflow_result = workflow_response.json()
            print(f"DEBUG: Workflow result: {workflow_result}")
            
            if 'data' in workflow_result and 'outputs' in workflow_result['data']:
                result_data = workflow_result['data']['outputs']
                print(f"DEBUG: Extracted result data: {result_data}")
                
                if is_valid_json_response(result_data):
                    print(f"DEBUG: Valid JSON response received for {filename} on attempt {attempt}")
                    return result_data
                else:
                    print(f"DEBUG: Invalid JSON response for {filename} on attempt {attempt}")
                    if attempt == max_retries:
                        return {'error': f'有効なJSONデータが取得できませんでした (最大{max_retries}回試行後)'}
                    else:
                        print(f"DEBUG: Retrying for valid JSON response for {filename} (attempt {attempt + 1})")
                        time.sleep(2)  # Wait 2 seconds before retry
                        continue
            else:
                print(f"DEBUG: No outputs found in workflow result for {filename} on attempt {attempt}")
                if attempt == max_retries:
                    return {'error': f'Difyワークフローの実行に失敗しました (最大{max_retries}回試行後)'}
                else:
                    print(f"DEBUG: Retrying workflow execution for {filename} (attempt {attempt + 1})")
                    time.sleep(2)  # Wait 2 seconds before retry
                    continue
                    
        except requests.exceptions.Timeout:
            print(f"DEBUG: Workflow timeout error for {filename} on attempt {attempt}")
            if attempt == max_retries:
                return {'error': f'Dify APIワークフローのタイムアウトが発生しました (最大{max_retries}回試行後)'}
            else:
                print(f"DEBUG: Retrying after timeout for {filename} (attempt {attempt + 1})")
                time.sleep(2)
                continue
        except requests.exceptions.RequestException as e:
            print(f"DEBUG: Workflow request error for {filename} on attempt {attempt}: {str(e)}")
            if attempt == max_retries:
                return {'error': f'Dify APIワークフロー接続エラー: {str(e)} (最大{max_retries}回試行後)'}
            else:
                print(f"DEBUG: Retrying after request error for {filename} (attempt {attempt + 1})")
                time.sleep(2)
                continue
        except Exception as e:
            print(f"DEBUG: Workflow general error for {filename} on attempt {attempt}: {str(e)}")
            if attempt == max_retries:
                return {'error': f'ワークフロー実行中にエラーが発生しました: {str(e)} (最大{max_retries}回試行後)'}
            else:
                print(f"DEBUG: Retrying after general error for {filename} (attempt {attempt + 1})")
                time.sleep(2)
                continue
    
    return {'error': f'予期しないエラーが発生しました (最大{max_retries}回試行後)'}

def send_to_dify(file_obj, filename):
    """Send file to Dify API using two-step process: upload then workflow execution"""
    try:
        print(f"DEBUG: Starting Dify API call for {filename}")
        
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
            timeout=30
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
        
        print(f"DEBUG: Executing workflow with payload: {json.dumps(workflow_payload, indent=2)}")
        workflow_response = requests.post(
            f"{DIFY_API_BASE_URL}/v1/workflows/run",
            headers={
                'Authorization': f'Bearer {DIFY_API_KEY}',
                'Content-Type': 'application/json'
            },
            json=workflow_payload,
            timeout=(30, 300)
        )
        
        print(f"DEBUG: Workflow response status: {workflow_response.status_code}")
        if workflow_response.status_code != 200:
            print(f"DEBUG: Workflow response content: {workflow_response.text}")
            return {'error': f'Difyワークフロー実行エラー: {workflow_response.status_code}'}
        
        workflow_result = workflow_response.json()
        print(f"DEBUG: Workflow result: {workflow_result}")
        
        if 'data' in workflow_result and 'outputs' in workflow_result['data']:
            result_data = workflow_result['data']['outputs']
            print(f"DEBUG: Extracted result data: {result_data}")
            return result_data
        else:
            print(f"DEBUG: No outputs found in workflow result")
            return {'error': 'Difyワークフローの実行に失敗しました'}
            
    except requests.exceptions.Timeout:
        print(f"DEBUG: Timeout error for {filename}")
        return {'error': 'Dify APIのタイムアウトが発生しました'}
    except requests.exceptions.RequestException as e:
        print(f"DEBUG: Request error for {filename}: {str(e)}")
        return {'error': f'Dify API接続エラー: {str(e)}'}
    except Exception as e:
        print(f"DEBUG: General error for {filename}: {str(e)}")
        return {'error': f'データ取得中にエラーが発生しました: {str(e)}'}

def process_files_sequential(valid_files, session_id):
    """Process files one by one in background thread"""
    print(f"DEBUG: Starting sequential processing for session {session_id}")
    
    for i, file_info in enumerate(valid_files):
        try:
            filename = file_info['filename']
            file_data = file_info['file_data']
            
            print(f"DEBUG: Processing file {i+1}/{len(valid_files)}: {filename}")
            
            with session_lock:
                if session_id in processing_sessions:
                    processing_sessions[session_id]['current_processing'] = {
                        'file_index': i,
                        'filename': filename,
                        'started_at': time.time(),
                        'current_attempt': 0
                    }
            
            from io import BytesIO
            file_obj = BytesIO(file_data)
            
            result = send_to_dify_with_progress(file_obj, filename, session_id, i)
            
            with session_lock:
                if session_id in processing_sessions:
                    session = processing_sessions[session_id]
                    
                    elapsed_time = time.time() - session['current_processing']['started_at']
                    session['current_processing'] = None
                    
                    if 'error' in result:
                        session['errors'].append(f'{filename}: {result["error"]}')
                        session['results'].append({
                            'filename': filename,
                            'file_index': i,
                            'result': result,
                            'failed': True,
                            'completed_at': time.time(),
                            'elapsed_seconds': round(elapsed_time, 1)
                        })
                    else:
                        session['results'].append({
                            'filename': filename,
                            'file_index': i,
                            'result': result,
                            'failed': False,
                            'completed_at': time.time(),
                            'elapsed_seconds': round(elapsed_time, 1)
                        })
                    
                    session['processed_files'] += 1
                    print(f"DEBUG: Completed {session['processed_files']}/{session['total_files']} files")
                    
        except Exception as e:
            print(f"DEBUG: Error processing {filename}: {str(e)}")
            with session_lock:
                if session_id in processing_sessions:
                    elapsed_time = time.time() - processing_sessions[session_id]['current_processing']['started_at']
                    processing_sessions[session_id]['current_processing'] = None
                    processing_sessions[session_id]['errors'].append(f'{filename}: {str(e)}')
                    processing_sessions[session_id]['results'].append({
                        'filename': filename,
                        'file_index': i,
                        'result': {'error': str(e)},
                        'failed': True,
                        'completed_at': time.time(),
                        'elapsed_seconds': round(elapsed_time, 1)
                    })
                    processing_sessions[session_id]['processed_files'] += 1
    
    with session_lock:
        if session_id in processing_sessions:
            processing_sessions[session_id]['status'] = 'completed'
            processing_sessions[session_id]['current_processing'] = None
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
            
            current_processing = session.get('current_processing')
            current_processing_info = None
            
            if current_processing:
                elapsed_time = time.time() - current_processing['started_at']
                current_processing_info = {
                    'file_index': current_processing['file_index'],
                    'filename': current_processing['filename'],
                    'current_attempt': current_processing['current_attempt'],
                    'elapsed_seconds': round(elapsed_time, 1)
                }
            
            return jsonify({
                'session_id': session_id,
                'status': session['status'],
                'processed_files': session['processed_files'],
                'total_files': session['total_files'],
                'progress_percentage': round((session['processed_files'] / session['total_files']) * 100, 1),
                'new_results': new_results,
                'total_results_count': len(session['results']),
                'errors': session['errors'],
                'completed': session['status'] == 'completed',
                'current_processing': current_processing_info
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

@app.route('/api/dify/session/<session_id>/retry/<int:file_index>', methods=['POST'])
def retry_file(session_id, file_index):
    """Retry processing for a specific failed file"""
    try:
        with session_lock:
            if session_id not in processing_sessions:
                return jsonify({'error': 'Session not found'}), 404
            
            session = processing_sessions[session_id]
            
            if file_index >= len(session.get('original_files', [])):
                return jsonify({'error': 'File index out of range'}), 400
            
            failed_result = None
            for result in session['results']:
                if result['file_index'] == file_index and result['failed']:
                    failed_result = result
                    break
            
            if not failed_result:
                return jsonify({'error': 'File not found or not failed'}), 400
            
            original_file = session['original_files'][file_index]
            filename = original_file['filename']
            file_data = original_file['file_data']
            
            session['results'] = [r for r in session['results'] if not (r['file_index'] == file_index and r['failed'])]
            
            session['current_processing'] = {
                'file_index': file_index,
                'filename': filename,
                'started_at': time.time(),
                'current_attempt': 0
            }
        
        import threading
        from io import BytesIO
        
        def retry_file_processing():
            file_obj = BytesIO(file_data)
            result = send_to_dify_with_progress(file_obj, filename, session_id, file_index)
            
            with session_lock:
                if session_id in processing_sessions:
                    session = processing_sessions[session_id]
                    elapsed_time = time.time() - session['current_processing']['started_at']
                    session['current_processing'] = None
                    
                    if 'error' in result:
                        session['errors'].append(f'{filename}: {result["error"]}')
                        session['results'].append({
                            'filename': filename,
                            'file_index': file_index,
                            'result': result,
                            'failed': True,
                            'completed_at': time.time(),
                            'elapsed_seconds': round(elapsed_time, 1)
                        })
                    else:
                        session['results'].append({
                            'filename': filename,
                            'file_index': file_index,
                            'result': result,
                            'failed': False,
                            'completed_at': time.time(),
                            'elapsed_seconds': round(elapsed_time, 1)
                        })
        
        thread = threading.Thread(target=retry_file_processing)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'message': f'Retry started for {filename}'
        })
        
    except Exception as e:
        return jsonify({'error': f'Retry error: {str(e)}'}), 500

@app.route('/api/dify/session/<session_id>/retry-failed', methods=['POST'])
def retry_failed_files(session_id):
    """Retry processing for all failed files in a session"""
    try:
        with session_lock:
            if session_id not in processing_sessions:
                return jsonify({'error': 'Session not found'}), 404
            
            session = processing_sessions[session_id]
            
            failed_files = []
            for result in session['results']:
                if result['failed']:
                    failed_files.append({
                        'file_index': result['file_index'],
                        'filename': result['filename']
                    })
            
            if not failed_files:
                return jsonify({'error': 'No failed files to retry'}), 400
            
            session['results'] = [r for r in session['results'] if not r['failed']]
            
            session['status'] = 'processing'
            session['processed_files'] = len([r for r in session['results'] if not r['failed']])
        
        import threading
        from io import BytesIO
        
        def retry_failed_processing():
            for failed_file in failed_files:
                file_index = failed_file['file_index']
                filename = failed_file['filename']
                
                with session_lock:
                    if session_id in processing_sessions:
                        session = processing_sessions[session_id]
                        original_file = session['original_files'][file_index]
                        file_data = original_file['file_data']
                        
                        session['current_processing'] = {
                            'file_index': file_index,
                            'filename': filename,
                            'started_at': time.time(),
                            'current_attempt': 0
                        }
                
                file_obj = BytesIO(file_data)
                result = send_to_dify_with_progress(file_obj, filename, session_id, file_index)
                
                with session_lock:
                    if session_id in processing_sessions:
                        session = processing_sessions[session_id]
                        elapsed_time = time.time() - session['current_processing']['started_at']
                        session['current_processing'] = None
                        
                        if 'error' in result:
                            session['errors'].append(f'{filename}: {result["error"]}')
                            session['results'].append({
                                'filename': filename,
                                'file_index': file_index,
                                'result': result,
                                'failed': True,
                                'completed_at': time.time(),
                                'elapsed_seconds': round(elapsed_time, 1)
                            })
                        else:
                            session['results'].append({
                                'filename': filename,
                                'file_index': file_index,
                                'result': result,
                                'failed': False,
                                'completed_at': time.time(),
                                'elapsed_seconds': round(elapsed_time, 1)
                            })
                        
                        session['processed_files'] += 1
            
            with session_lock:
                if session_id in processing_sessions:
                    processing_sessions[session_id]['status'] = 'completed'
        
        thread = threading.Thread(target=retry_failed_processing)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'message': f'Retry started for {len(failed_files)} failed files'
        })
        
    except Exception as e:
        return jsonify({'error': f'Batch retry error: {str(e)}'}), 500

# 分析結果を保存するためのグローバル変数
analysis_results = []

@app.route('/api/analysis/results', methods=['GET'])
def get_analysis_results():
    """分析結果の一覧を取得"""
    try:
        conn = sqlite3.connect('inventory_data.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT ページ, 出荷日, 受注番号, 納入先番号, 担当者, 税抜合計 FROM basic_info ORDER BY created_at DESC')
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            results.append({
                'ページ': row[0],
                '出荷日': row[1],
                '受注番号': row[2],
                '納入先番号': row[3],
                '担当者': row[4],
                '税抜合計': row[5]
            })
        
        conn.close()
        
        return jsonify({
            'success': True,
            'results': results
        })
    except Exception as e:
        return jsonify({'error': f'データ取得エラー: {str(e)}'}), 500

@app.route('/api/analysis/results', methods=['POST'])
def save_analysis_results():
    """分析結果を保存"""
    try:
        data = request.get_json()
        if not data or 'results' not in data:
            return jsonify({'error': 'Invalid data format'}), 400
        
        # SQLiteデータベースに保存
        conn = sqlite3.connect('inventory_data.db')
        cursor = conn.cursor()
        
        # 既存データをクリア
        cursor.execute('DELETE FROM basic_info')
        
        # 新しいデータを挿入
        for item in data['results']:
            cursor.execute('''
                INSERT INTO basic_info (ページ, 出荷日, 受注番号, 納入先番号, 担当者, 税抜合計)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                item.get('ページ', ''),
                item.get('出荷日', ''),
                item.get('受注番号', ''),
                item.get('納入先番号', ''),
                item.get('担当者', ''),
                item.get('税抜合計', '')
            ))
        
        conn.commit()
        conn.close()
        
        # グローバル変数も更新
        global analysis_results
        analysis_results = data['results']
        
        return jsonify({
            'success': True,
            'message': f'{len(data["results"])}件の分析結果をSQLiteデータベースに保存しました'
        })
    except Exception as e:
        return jsonify({'error': f'保存エラー: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
