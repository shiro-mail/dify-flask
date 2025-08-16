onDOMReady(() => {
    const uploadForm = document.getElementById('uploadForm');
    const fileInput = document.getElementById('fileInput');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const resultArea = document.getElementById('resultArea');
    const errorArea = document.getElementById('errorArea');
    const resultContent = document.getElementById('resultContent');
    const errorContent = document.getElementById('errorContent');
    const fileProgressArea = document.getElementById('fileProgressArea');
    const fileProgressList = document.getElementById('fileProgressList');
    const retryButtonArea = document.getElementById('retryButtonArea');
    const retryFailedBtn = document.getElementById('retryFailedBtn');
    
    let currentSessionId = null;
    
    function getCurrentSessionId() {
        return currentSessionId;
    }
    
    const fileUploadArea = document.querySelector('.file-upload-area');
    if (fileUploadArea && fileInput) {
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
                }
            }
        });
    } else {
        console.error('File upload area or file input not found');
    }
    
    if (!uploadForm || !fileInput || !analyzeBtn) {
        console.error('Required form elements not found');
        return;
    }
    
    const useSequential = document.getElementById('useSequential');
    if (useSequential) {
        useSequential.addEventListener('change', () => {
            if (fileInput.files.length > 0) {
                displayFileList(fileInput.files);
            }
        });
    }
    
    fileInput.addEventListener('change', (e) => {
        const files = e.target.files;
        if (files.length > 0) {
            let validFiles = 0;
            let totalSize = 0;
            
            for (let i = 0; i < files.length; i++) {
                const file = files[i];
                if (!isValidPNGFile(file)) {
                    continue;
                }
                
                if (file.size > 16 * 1024 * 1024) {
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
            
            displayFileList(files);
        }
    });
    
    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const files = fileInput.files;
        if (files.length === 0) {
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
            
            const useSequential = document.getElementById('useSequential');
            if (useSequential && useSequential.checked) {
                await startSequentialProcessing(validFiles);
            } else {
                const response = await fetch('/api/dify/analyze-multiple', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (response.ok && result.success) {
                    displayResult(result.results);
                } else {
                    const errorMessage = result.error || '分析に失敗しました';
                    displayError(errorMessage);
                }
                setButtonLoading(analyzeBtn, false);
            }
        } catch (error) {
            const errorMessage = '分析中にエラーが発生しました';
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
                    html += formatResultData(item.result);
                    html += `</div>`;
                });
                resultContent.innerHTML = html;
            } else if (typeof results === 'object') {
                resultContent.innerHTML = formatResultData(results);
            } else {
                resultContent.textContent = results;
            }
        }
        showElement(resultArea);
        hideElement(errorArea);
    }
    
    function formatResultData(result) {
        if (result && result.extracted_data) {
            return `<pre class="result-content">${formatJSON(result.extracted_data)}</pre>`;
        } else if (result && result.text) {
            const textContent = result.text;
            if (textContent.includes('```json')) {
                const jsonMatch = textContent.match(/```json\s*\n(.*?)\n```/s);
                if (jsonMatch) {
                    try {
                        const parsedData = JSON.parse(jsonMatch[1]);
                        return `<pre class="result-content">${formatJSON(parsedData)}</pre>`;
                    } catch (e) {
                        console.warn('Failed to parse JSON from markdown:', e);
                    }
                }
            }
            return `<pre class="result-content">${textContent}</pre>`;
        } else {
            return `<pre class="result-content">${formatJSON(result)}</pre>`;
        }
    }
    
    function displayError(error) {
        if (errorContent) {
            errorContent.textContent = error;
        }
        showElement(errorArea);
        hideElement(resultArea);
    }
    
    
    async function startSequentialProcessing(validFiles) {
        const formData = new FormData();
        for (let i = 0; i < validFiles.length; i++) {
            formData.append('files', validFiles[i]);
        }
        
        try {
            const response = await fetch('/api/dify/analyze-sequential', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            if (response.ok && result.success) {
                startPollingForResults(result.session_id, result.total_files);
            } else {
                const errorMessage = result.error || '処理開始に失敗しました';
                displayError(errorMessage);
                setButtonLoading(analyzeBtn, false);
            }
        } catch (error) {
            const errorMessage = '処理開始中にエラーが発生しました';
            displayError(errorMessage);
            console.error('Sequential processing error:', error);
            setButtonLoading(analyzeBtn, false);
        }
    }
    
    function startPollingForResults(sessionId, totalFiles) {
        currentSessionId = sessionId;
        let lastResultCount = 0;
        let allResults = [];
        
        const pollInterval = setInterval(async () => {
            try {
                const response = await fetch(`/api/dify/session/${sessionId}/status?last_result_count=${lastResultCount}`);
                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.error || 'Status check failed');
                }
                
                if (data.current_processing) {
                    updateCurrentProcessingStatus(data.current_processing);
                }
                
                if (data.new_results && data.new_results.length > 0) {
                    allResults = allResults.concat(data.new_results);
                    displaySequentialResults(allResults);
                    lastResultCount = data.total_results_count;
                }
                
                if (data.completed) {
                    clearInterval(pollInterval);
                    setButtonLoading(analyzeBtn, false);
                    
                    checkRetryButtonVisibility(allResults, true);
                    
                    if (data.errors && data.errors.length > 0) {
                        console.warn('Processing errors:', data.errors);
                    }
                    
                    if (!allResults.some(result => result.failed)) {
                        fetch(`/api/dify/session/${sessionId}/cleanup`, { method: 'DELETE' })
                            .catch(err => console.warn('Cleanup failed:', err));
                    }
                }
                
            } catch (error) {
                clearInterval(pollInterval);
                const errorMessage = 'ステータス確認中にエラーが発生しました';
                displayError(errorMessage);
                console.error('Polling error:', error);
                setButtonLoading(analyzeBtn, false);
            }
        }, 2000);
    }
    
    function displaySequentialResults(results) {
        if (resultContent) {
            let html = '';
            results.sort((a, b) => a.file_index - b.file_index);
            results.forEach((item, index) => {
                html += `<div class="mb-3">`;
                html += `<h6>ファイル ${item.file_index + 1}: ${item.filename}</h6>`;
                html += formatResultData(item.result);
                html += `</div>`;
            });
            resultContent.innerHTML = html;
        }
        showElement(resultArea);
        hideElement(errorArea);
        
        updateFileProgress(results);
        
        checkRetryButtonVisibility(results, false);
    }
    
    function displayFileList(files) {
        if (!fileProgressList || !fileProgressArea) return;
        
        const useSequential = document.getElementById('useSequential');
        if (!useSequential || !useSequential.checked) {
            hideElement(fileProgressArea);
            return;
        }
        
        let html = '';
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            if (isValidPNGFile(file) && file.size <= 16 * 1024 * 1024) {
                html += `<div class="file-progress-item" data-file-index="${i}">`;
                html += `<span class="file-name">${file.name}</span>`;
                html += `<span class="file-status">⏳</span>`;
                html += `</div>`;
            }
        }
        
        fileProgressList.innerHTML = html;
        showElement(fileProgressArea);
    }
    
    function updateFileProgress(results) {
        if (!fileProgressList) return;
        
        results.forEach(result => {
            const fileItem = fileProgressList.querySelector(`[data-file-index="${result.file_index}"]`);
            if (fileItem) {
                const statusElement = fileItem.querySelector('.file-status');
                if (statusElement) {
                    const elapsedText = result.elapsed_seconds ? ` (${result.elapsed_seconds}秒)` : '';
                    if (result.failed) {
                        statusElement.innerHTML = `❌${elapsedText}`;
                        statusElement.style.color = '#dc3545';
                        fileItem.classList.add('failed');
                        fileItem.classList.remove('completed', 'processing');
                    } else {
                        statusElement.innerHTML = `✅${elapsedText}`;
                        statusElement.style.color = '#28a745';
                        fileItem.classList.add('completed');
                        fileItem.classList.remove('failed', 'processing');
                    }
                }
            }
        });
    }
    
    function updateCurrentProcessingStatus(processingInfo) {
        if (!fileProgressList || !processingInfo) return;
        
        const fileItem = fileProgressList.querySelector(`[data-file-index="${processingInfo.file_index}"]`);
        if (fileItem) {
            const statusElement = fileItem.querySelector('.file-status');
            if (statusElement) {
                const attemptText = `${processingInfo.current_attempt}回目分析中`;
                statusElement.innerHTML = `🔄 ${attemptText}`;
                statusElement.style.color = '#007bff';
                fileItem.classList.add('processing');
                fileItem.classList.remove('completed', 'failed');
            }
        }
    }
    
    function checkRetryButtonVisibility(allResults, isCompleted) {
        if (!retryButtonArea || !retryFailedBtn) return;
        
        if (isCompleted && allResults.some(result => result.failed)) {
            showElement(retryButtonArea);
        } else {
            hideElement(retryButtonArea);
        }
    }
    
    async function handleRetryFailedClick(event) {
        event.preventDefault();
        const sessionId = getCurrentSessionId();
        
        if (!sessionId) {
            console.error('No active session for retry');
            return;
        }
        
        try {
            hideElement(retryButtonArea);
            
            const response = await fetch(`/api/dify/session/${sessionId}/retry-failed`, {
                method: 'POST'
            });
            
            const result = await response.json();
            
            if (!response.ok) {
                throw new Error(result.error || 'Batch retry failed');
            }
            
            console.log('Batch retry started successfully:', result.message);
            
            startPollingForResults(sessionId, 0);
            
        } catch (error) {
            console.error('Batch retry error:', error);
            showElement(retryButtonArea);
        }
    }
    
    if (retryFailedBtn) {
        retryFailedBtn.addEventListener('click', handleRetryFailedClick);
    }
});
