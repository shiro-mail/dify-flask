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
        const file = e.target.files[0];
        if (file) {
            if (!isValidPNGFile(file)) {
                showMessage('PNGファイルのみ対応しています', 'error');
                fileInput.value = '';
                return;
            }
            
            if (file.size > 16 * 1024 * 1024) {
                showMessage('ファイルサイズは16MB以下にしてください', 'error');
                fileInput.value = '';
                return;
            }
            
            showMessage(`ファイル選択: ${file.name} (${formatFileSize(file.size)})`, 'success');
        }
    });
    
    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const file = fileInput.files[0];
        if (!file) {
            showMessage('PNGファイルを選択してください', 'error');
            return;
        }
        
        if (!isValidPNGFile(file)) {
            showMessage('PNGファイルのみ対応しています', 'error');
            return;
        }
        
        hideElement(resultArea);
        hideElement(errorArea);
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            setButtonLoading(analyzeBtn, true);
            showMessage('画像をDifyで分析中...', 'info');
            
            const response = await fetch('/api/dify/analyze', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            if (response.ok && result.success) {
                showMessage('分析が完了しました！', 'success');
                displayResult(result.result);
            } else {
                const errorMessage = result.error || '分析に失敗しました';
                showMessage(errorMessage, 'error');
                displayError(errorMessage);
            }
        } catch (error) {
            const errorMessage = '分析中にエラーが発生しました';
            showMessage(errorMessage, 'error');
            displayError(errorMessage);
            console.error('Analysis error:', error);
        } finally {
            setButtonLoading(analyzeBtn, false);
        }
    });
    
    function displayResult(result) {
        if (resultContent) {
            if (typeof result === 'object') {
                resultContent.innerHTML = `<pre>${formatJSON(result)}</pre>`;
            } else {
                resultContent.textContent = result;
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
                const file = files[0];
                if (isValidPNGFile(file)) {
                    fileInput.files = files;
                    const event = new Event('change', { bubbles: true });
                    fileInput.dispatchEvent(event);
                } else {
                    showMessage('PNGファイルのみ対応しています', 'error');
                }
            }
        });
    }
});
