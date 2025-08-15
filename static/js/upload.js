onDOMReady(() => {
    const uploadForm = document.getElementById('uploadForm');
    const fileInput = document.getElementById('fileInput');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const resultArea = document.getElementById('resultArea');
    const errorArea = document.getElementById('errorArea');
    const resultContent = document.getElementById('resultContent');
    const errorContent = document.getElementById('errorContent');
    
    if (!uploadForm || !fileInput || !analyzeBtn) {
        console.error('Required elements not found');
        return;
    }
    
    fileInput.addEventListener('change', (e) => {
        const files = e.target.files;
        if (files.length > 0) {
            let validFiles = 0;
            let totalSize = 0;
            
            for (let i = 0; i < files.length; i++) {
                const file = files[i];
                if (!isValidPNGFile(file)) {
                    showMessage(`${file.name} はPNGファイルではありません`, 'error');
                    continue;
                }
                
                if (file.size > 16 * 1024 * 1024) {
                    showMessage(`${file.name} のファイルサイズが16MBを超えています`, 'error');
                    continue;
                }
                
                validFiles++;
                totalSize += file.size;
            }
            
            if (validFiles === 0) {
                fileInput.value = '';
                return;
            }
            
            showMessage(`${validFiles}個のファイルを選択 (合計: ${formatFileSize(totalSize)})`, 'success');
        }
    });
    
    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const files = fileInput.files;
        if (files.length === 0) {
            showMessage('PNGファイルを選択してください', 'error');
            return;
        }
        
        const validFiles = [];
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            if (isValidPNGFile(file) && file.size <= 16 * 1024 * 1024) {
                validFiles.push(file);
            }
        }
        
        if (validFiles.length === 0) {
            showMessage('有効なPNGファイルがありません', 'error');
            return;
        }
        
        hideElement(resultArea);
        hideElement(errorArea);
        
        const formData = new FormData();
        for (let i = 0; i < validFiles.length; i++) {
            formData.append('files', validFiles[i]);
        }
        
        try {
            setButtonLoading(analyzeBtn, true);
            showMessage(`${validFiles.length}個の画像をDifyで分析中...`, 'info');
            
            const useIterator = document.getElementById('useIterator');
            if (useIterator && useIterator.checked) {
                await startIteratorProcessing(validFiles);
            } else {
                const response = await fetch('/api/dify/analyze-multiple', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (response.ok && result.success) {
                    showMessage('分析が完了しました！', 'success');
                    displayResult(result.results);
                } else {
                    const errorMessage = result.error || '分析に失敗しました';
                    showMessage(errorMessage, 'error');
                    displayError(errorMessage);
                }
                setButtonLoading(analyzeBtn, false);
            }
        } catch (error) {
            const errorMessage = '分析中にエラーが発生しました';
            showMessage(errorMessage, 'error');
            displayError(errorMessage);
            console.error('Analysis error:', error);
            setButtonLoading(analyzeBtn, false);
        }
    });
    
    function displayResult(results) {
        if (resultContent) {
            if (Array.isArray(results)) {
                let html = '';
                results.forEach((item, index) => {
                    html += `<div class="mb-3">`;
                    html += `<h6>ファイル ${index + 1}: ${item.filename}</h6>`;
                    html += `<pre class="result-content">${formatJSON(item.result)}</pre>`;
                    html += `</div>`;
                });
                resultContent.innerHTML = html;
            } else if (typeof results === 'object') {
                resultContent.innerHTML = `<pre class="result-content">${formatJSON(results)}</pre>`;
            } else {
                resultContent.textContent = results;
            }
        }
        showElement(resultArea);
        hideElement(errorArea);
    }
    
    function displayError(error) {
        if (errorContent) {
            errorContent.textContent = error;
        }
        showElement(errorArea);
        hideElement(resultArea);
    }
    
    const fileUploadArea = document.querySelector('.file-upload-area');
    if (fileUploadArea) {
        fileUploadArea.addEventListener('click', () => {
            fileInput.click();
        });
        
        fileUploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            fileUploadArea.classList.add('dragover');
        });
        
        fileUploadArea.addEventListener('dragleave', (e) => {
            e.preventDefault();
            fileUploadArea.classList.remove('dragover');
        });
        
        fileUploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            fileUploadArea.classList.remove('dragover');
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                const pngFiles = Array.from(files).filter(file => isValidPNGFile(file));
                
                if (pngFiles.length > 0) {
                    const dt = new DataTransfer();
                    pngFiles.forEach(file => dt.items.add(file));
                    fileInput.files = dt.files;
                    
                    const event = new Event('change', { bubbles: true });
                    fileInput.dispatchEvent(event);
                } else {
                    showMessage('PNGファイルのみ対応しています', 'error');
                }
            }
        });
    }
    
    async function startIteratorProcessing(validFiles) {
        const formData = new FormData();
        for (let i = 0; i < validFiles.length; i++) {
            formData.append('files', validFiles[i]);
        }
        
        try {
            const response = await fetch('/api/dify/analyze-iterator', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            if (response.ok && result.success) {
                showMessage(`${result.total_files}個のファイルの処理を開始しました`, 'info');
                startSSEConnection(result.session_id);
            } else {
                const errorMessage = result.error || '処理開始に失敗しました';
                showMessage(errorMessage, 'error');
                displayError(errorMessage);
                setButtonLoading(analyzeBtn, false);
            }
        } catch (error) {
            const errorMessage = '処理開始中にエラーが発生しました';
            showMessage(errorMessage, 'error');
            displayError(errorMessage);
            console.error('Iterator processing error:', error);
            setButtonLoading(analyzeBtn, false);
        }
    }
    
    function startSSEConnection(sessionId) {
        const eventSource = new EventSource(`/api/sse/session/${sessionId}`);
        
        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            
            if (data.error) {
                showMessage(data.error, 'error');
                displayError(data.error);
                eventSource.close();
                setButtonLoading(analyzeBtn, false);
                return;
            }
            
            showMessage(`処理中: ${data.processed_files}/${data.total_files} 完了`, 'info');
            
            if (data.results && data.results.length > 0) {
                displayIteratorResults(data.results);
            }
            
            if (data.status === 'completed') {
                showMessage('すべてのファイルの分析が完了しました！', 'success');
                eventSource.close();
                setButtonLoading(analyzeBtn, false);
            }
        };
        
        eventSource.onerror = function(event) {
            console.error('SSE error:', event);
            eventSource.close();
            setButtonLoading(analyzeBtn, false);
        };
    }
    
    function displayIteratorResults(results) {
        if (resultContent) {
            let html = '';
            results.forEach((item, index) => {
                html += `<div class="mb-3">`;
                html += `<h6>ファイル ${index + 1}: ${item.filename}</h6>`;
                html += `<pre class="result-content">${formatJSON(item.result)}</pre>`;
                html += `</div>`;
            });
            resultContent.innerHTML = html;
        }
        showElement(resultArea);
        hideElement(errorArea);
    }
});
