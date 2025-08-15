from flask import Flask, render_template, request, jsonify, Response
import requests
import os
import uuid
import time
import json
from werkzeug.utils import secure_filename
from threading import Lock

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

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

@app.route('/api/dify/analyze-iterator', methods=['POST'])
def analyze_images_iterator():
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
            valid_files.append({'file': file, 'filename': filename})
        
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
        
        for i, file_info in enumerate(valid_files):
            try:
                file_info['file'].seek(0)
                send_to_dify_iterator(file_info['file'], file_info['filename'], session_id, i)
            except Exception as e:
                with session_lock:
                    processing_sessions[session_id]['errors'].append(f"{file_info['filename']}: {str(e)}")
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'total_files': len(valid_files),
            'message': 'ファイル処理を開始しました'
        })
        
    except Exception as e:
        return jsonify({'error': f'エラーが発生しました: {str(e)}'}), 500

def send_to_dify(file_obj, filename):
    """Send file to Dify API using two-step process: upload then workflow execution"""
    try:
        upload_files = {
            'file': (filename, file_obj, 'image/png')
        }
        upload_data = {
            'user': 'dify-flask-app'
        }
        
        upload_response = requests.post(
            f"{DIFY_API_BASE_URL}/v1/files/upload",
            headers={'Authorization': f'Bearer {DIFY_API_KEY}'},
            files=upload_files,
            data=upload_data,
            timeout=30
        )
        
        if upload_response.status_code != 201:
            return {'error': f'Difyファイルアップロードエラー: {upload_response.status_code}'}
        
        upload_result = upload_response.json()
        file_id = upload_result.get('id')
        
        if not file_id:
            return {'error': 'ファイルアップロードからIDを取得できませんでした'}
        
        workflow_payload = {
            "inputs": {
                "input_file": [{
                    "type": "image",
                    "transfer_method": "local_file", 
                    "upload_file_id": file_id
                }]
            },
            "response_mode": "blocking",
            "user": "dify-flask-app"
        }
        
        workflow_response = requests.post(
            f"{DIFY_API_BASE_URL}/v1/workflows/run",
            headers={
                'Authorization': f'Bearer {DIFY_API_KEY}',
                'Content-Type': 'application/json'
            },
            json=workflow_payload,
            timeout=60
        )
        
        if workflow_response.status_code != 200:
            return {'error': f'Difyワークフロー実行エラー: {workflow_response.status_code}'}
        
        workflow_result = workflow_response.json()
        
        if 'data' in workflow_result and 'outputs' in workflow_result['data']:
            return workflow_result['data']['outputs']
        else:
            return {'error': 'Difyワークフローの実行に失敗しました'}
            
    except requests.exceptions.Timeout:
        return {'error': 'Dify APIのタイムアウトが発生しました'}
    except requests.exceptions.RequestException as e:
        return {'error': f'Dify API接続エラー: {str(e)}'}
    except Exception as e:
        return {'error': f'データ取得中にエラーが発生しました: {str(e)}'}

def send_to_dify_iterator(file_obj, filename, session_id, file_index):
    """Send file to Dify API using iterator workflow (non-blocking)"""
    try:
        upload_files = {
            'file': (filename, file_obj, 'image/png')
        }
        upload_data = {
            'user': 'dify-flask-app'
        }
        
        upload_response = requests.post(
            f"{DIFY_API_BASE_URL}/v1/files/upload",
            headers={'Authorization': f'Bearer {DIFY_API_KEY}'},
            files=upload_files,
            data=upload_data,
            timeout=30
        )
        
        if upload_response.status_code != 201:
            raise Exception(f'Difyファイルアップロードエラー: {upload_response.status_code}')
        
        upload_result = upload_response.json()
        file_id = upload_result.get('id')
        
        if not file_id:
            raise Exception('ファイルアップロードからIDを取得できませんでした')
        
        workflow_payload = {
            "inputs": {
                "input_file": [{
                    "type": "image",
                    "transfer_method": "local_file", 
                    "upload_file_id": file_id
                }]
            },
            "response_mode": "streaming",
            "user": "dify-flask-app",
            "metadata": {
                "session_id": session_id,
                "filename": filename,
                "file_index": file_index
            }
        }
        
        workflow_response = requests.post(
            f"{DIFY_API_BASE_URL}/v1/workflows/run",
            headers={
                'Authorization': f'Bearer {DIFY_API_KEY}',
                'Content-Type': 'application/json'
            },
            json=workflow_payload,
            timeout=10
        )
        
        if workflow_response.status_code != 200:
            raise Exception(f'Difyワークフロー実行エラー: {workflow_response.status_code}')
        
        
    except Exception as e:
        with session_lock:
            if session_id in processing_sessions:
                processing_sessions[session_id]['errors'].append(f'{filename}: {str(e)}')

@app.route('/api/webhook/result', methods=['POST'])
def webhook_result():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data received'}), 400
        
        session_id = data.get('session_id')
        filename = data.get('filename')
        file_index = data.get('file_index')
        result = data.get('result')
        
        if not session_id or session_id not in processing_sessions:
            return jsonify({'error': 'Invalid session'}), 400
        
        with session_lock:
            session = processing_sessions[session_id]
            session['results'].append({
                'filename': filename,
                'file_index': file_index,
                'result': result
            })
            session['processed_files'] += 1
            
            if session['processed_files'] >= session['total_files']:
                session['status'] = 'completed'
        
        return jsonify({'success': True, 'message': 'Result received'})
        
    except Exception as e:
        return jsonify({'error': f'Webhook error: {str(e)}'}), 500

@app.route('/api/sse/session/<session_id>')
def sse_session_updates(session_id):
    def generate():
        while True:
            if session_id not in processing_sessions:
                yield f"data: {json.dumps({'error': 'Session not found'})}\n\n"
                break
            
            with session_lock:
                session = processing_sessions[session_id]
                data = {
                    'session_id': session_id,
                    'status': session['status'],
                    'processed_files': session['processed_files'],
                    'total_files': session['total_files'],
                    'results': session['results'],
                    'errors': session['errors']
                }
            
            yield f"data: {json.dumps(data)}\n\n"
            
            if session['status'] == 'completed':
                break
            
            time.sleep(1)
    
    return Response(generate(), mimetype='text/plain')

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
