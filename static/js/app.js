
function onDOMReady(callback) {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', callback);
    } else {
        callback();
    }
}

function showMessage(message, type = 'info') {
    const alertClass = type === 'error' ? 'alert-danger' : 
                      type === 'success' ? 'alert-success' : 'alert-info';
    
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert ${alertClass} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const container = document.querySelector('.container');
    if (container) {
        container.insertBefore(alertDiv, container.firstChild);
        
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, 5000);
    }
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function isValidPNGFile(file) {
    return file && file.type === 'image/png';
}

function setButtonLoading(button, loading = true) {
    const btnText = button.querySelector('#btnText');
    const btnSpinner = button.querySelector('#btnSpinner');
    
    if (loading) {
        button.disabled = true;
        if (btnText) btnText.textContent = '分析中...';
        if (btnSpinner) btnSpinner.classList.remove('d-none');
    } else {
        button.disabled = false;
        if (btnText) btnText.textContent = '分析開始';
        if (btnSpinner) btnSpinner.classList.add('d-none');
    }
}

function formatJSON(obj) {
    return JSON.stringify(obj, null, 2);
}

function showElement(element) {
    if (element) element.classList.remove('d-none');
}

function hideElement(element) {
    if (element) element.classList.add('d-none');
}
