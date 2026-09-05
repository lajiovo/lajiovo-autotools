async function fetchData() {
    try {
        const response = await fetch('/clipboard');
        const data = await response.json();
        if (data.status === 'ok') {
            document.getElementById('textClipboard').value = data.text || '';
            renderGallery(data.images || []);
        }
    } catch (err) {
        showToast('获取数据失败: ' + err, 'error');
    }
}

function renderGallery(images) {
    const gallery = document.getElementById('imageGallery');
    if (images.length === 0) {
        gallery.innerHTML = '<div class="loading">暂无图片缓存</div>';
        return;
    }

    gallery.innerHTML = images.map(img => `
        <div class="image-item">
            <img src="/clipboard/file/${img}" alt="${img}" onclick="window.open('/clipboard/file/${img}')">
            <div class="image-actions">
                <button class="btn-icon" onclick="copyUrl('/clipboard/file/${img}')">🔗 链接</button>
                <button class="btn-icon del" onclick="deleteFile('${img}')">🗑️ 删除</button>
            </div>
        </div>
    `).join('');
}

async function saveText() {
    const text = document.getElementById('textClipboard').value;
    try {
        const response = await fetch('/clipboard', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
        const data = await response.json();
        if (data.status === 'ok') {
            showToast('文本保存成功');
        } else {
            showToast('保存失败: ' + data.message);
        }
    } catch (err) {
        showToast('网络请求失败');
    }
}

function copyText() {
    const text = document.getElementById('textClipboard').value;
    navigator.clipboard.writeText(text).then(() => {
        showToast('已复制到系统剪切板');
    }).catch(err => {
        showToast('复制失败');
    });
}

function copyUrl(url) {
    const fullUrl = window.location.origin + url;
    navigator.clipboard.writeText(fullUrl).then(() => {
        showToast('图片链接已复制');
    });
}

async function deleteFile(filename) {
    if (!confirm('确定要删除这张图片吗？')) return;
    try {
        const response = await fetch('/clipboard', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'delete', filename })
        });
        const data = await response.json();
        if (data.status === 'ok') {
            showToast('文件已删除');
            renderGallery(data.images);
        }
    } catch (err) {
        showToast('删除失败');
    }
}

// 图片上传处理
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');

uploadArea.onclick = () => fileInput.click();

uploadArea.ondragover = (e) => {
    e.preventDefault();
    uploadArea.style.borderColor = 'var(--primary)';
};

uploadArea.ondragleave = () => {
    uploadArea.style.borderColor = 'var(--card-border)';
};

uploadArea.ondrop = (e) => {
    e.preventDefault();
    uploadArea.style.borderColor = 'var(--card-border)';
    const files = e.dataTransfer.files;
    if (files.length > 0) handleUpload(files[0]);
};

fileInput.onchange = (e) => {
    if (e.target.files.length > 0) handleUpload(e.target.files[0]);
};

async function handleUpload(file) {
    const status = document.getElementById('uploadStatus');
    status.innerText = '正在上传: ' + file.name;
    
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/clipboard', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        if (data.status === 'ok') {
            showToast('上传成功');
            status.innerText = '';
            renderGallery(data.images);
        } else {
            status.innerText = '上传失败: ' + data.message;
        }
    } catch (err) {
        status.innerText = '网络错误';
    }
}

function showToast(msg) {
    const toast = document.getElementById('toast');
    toast.innerText = msg;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 2000);
}

// 初始化加载
document.addEventListener('DOMContentLoaded', fetchData);
