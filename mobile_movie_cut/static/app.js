// HADO Match Extractor - Client-side logic

let currentJobId = null;
let uploadXHR = null;
let eventSource = null;
let elapsedTimer = null;
let startTime = null;
let wakeLock = null;
let selectedGame = 'hado';

// --- Game Selection ---

function selectGame(type) {
    selectedGame = type;
    document.getElementById('btn-hado').classList.toggle('selected', type === 'hado');
    document.getElementById('btn-hadoworld').classList.toggle('selected', type === 'hadoworld');
}

// --- File Selection & Upload ---

// btn-select click: use pywebview native picker if available, else trigger file input
document.getElementById('btn-select').addEventListener('click', function() {
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.pick_file().then(function(fileInfo) {
            if (!fileInfo) return;
            document.getElementById('file-name').textContent = fileInfo.name;
            document.getElementById('file-size').textContent = formatSize(fileInfo.size);
            document.getElementById('file-info').style.display = 'flex';
            uploadFromPath(fileInfo);
        }).catch(function(err) {
            showError('ファイル選択エラー: ' + (err || ''));
        });
    } else {
        document.getElementById('file-input').click();
    }
});

function uploadFromPath(fileInfo) {
    document.getElementById('btn-select').style.display = 'none';
    document.getElementById('upload-progress').style.display = 'block';
    document.querySelector('.hint').style.display = 'none';
    document.getElementById('upload-bar').style.width = '50%';
    document.getElementById('upload-detail').textContent = '準備中...';
    document.getElementById('btn-cancel-upload').style.display = 'none';

    fetch('/upload_path', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: fileInfo.path }),
    })
        .then(function(resp) {
            if (!resp.ok) return resp.json().then(function(d) { throw new Error(d.detail); });
            return resp.json();
        })
        .then(function(data) {
            currentJobId = data.job_id;
            startProcessing(data.job_id, fileInfo.name);
        })
        .catch(function(err) {
            showError(err.message || 'ファイルの読み込みに失敗しました');
        });
}

function handleFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;
    // Detach listeners to prevent double-fire
    var el = document.getElementById('file-input');
    el.removeEventListener('change', handleFileSelect);
    el.removeEventListener('input', handleFileSelect);

    // Show file info
    document.getElementById('file-name').textContent = file.name;
    document.getElementById('file-size').textContent = formatSize(file.size);
    document.getElementById('file-info').style.display = 'flex';

    // Start upload immediately
    uploadFile(file);
}

document.getElementById('file-input').addEventListener('change', handleFileSelect);
document.getElementById('file-input').addEventListener('input', handleFileSelect);

function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    // Show upload UI
    document.getElementById('btn-select').style.display = 'none';
    document.getElementById('upload-progress').style.display = 'block';
    document.querySelector('.hint').style.display = 'none';

    uploadXHR = new XMLHttpRequest();

    uploadXHR.upload.addEventListener('progress', function(e) {
        if (e.lengthComputable) {
            const pct = Math.round((e.loaded / e.total) * 100);
            document.getElementById('upload-bar').style.width = pct + '%';
            document.getElementById('upload-detail').textContent =
                pct + '%  (' + formatSize(e.loaded) + ' / ' + formatSize(e.total) + ')';
        }
    });

    uploadXHR.addEventListener('load', function() {
        if (uploadXHR.status === 200) {
            const data = JSON.parse(uploadXHR.responseText);
            currentJobId = data.job_id;
            startProcessing(data.job_id, file.name);
        } else {
            showError('アップロードに失敗しました');
        }
    });

    uploadXHR.addEventListener('error', function() {
        showError('ネットワークエラーが発生しました');
    });

    uploadXHR.addEventListener('abort', function() {
        resetUI();
    });

    uploadXHR.open('POST', '/upload');
    uploadXHR.send(formData);
}

function cancelUpload() {
    if (uploadXHR) {
        uploadXHR.abort();
        uploadXHR = null;
    }
}

// --- Processing ---

function startProcessing(jobId, filename) {
    showSection('section-processing');
    document.getElementById('processing-filename').textContent = filename;

    // Start elapsed timer
    startTime = Date.now();
    elapsedTimer = setInterval(updateElapsed, 1000);

    // Acquire wake lock
    acquireWakeLock();

    // Start processing on server
    fetch('/process/' + jobId, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game_type: selectedGame })
    })
        .then(function(resp) {
            if (!resp.ok) {
                return resp.json().then(function(data) {
                    throw new Error(data.detail || 'Processing failed');
                });
            }
            return resp.json();
        })
        .then(function() {
            // Connect SSE for progress
            connectSSE(jobId);
        })
        .catch(function(err) {
            showError(err.message);
        });
}

function connectSSE(jobId) {
    eventSource = new EventSource('/progress/' + jobId);

    eventSource.addEventListener('progress', function(e) {
        const data = JSON.parse(e.data);
        updateProgress(data);
    });

    eventSource.addEventListener('completed', function(e) {
        const data = JSON.parse(e.data);
        eventSource.close();
        eventSource = null;
        clearInterval(elapsedTimer);
        showResults(data);
    });

    eventSource.addEventListener('error', function(e) {
        // Check if it's an SSE error event with data
        if (e.data) {
            const data = JSON.parse(e.data);
            eventSource.close();
            eventSource = null;
            clearInterval(elapsedTimer);
            releaseWakeLock();
            showError(data.error || 'エラーが発生しました');
        }
        // Otherwise it's a connection error - EventSource will auto-reconnect
    });
}

function updateProgress(data) {
    document.getElementById('processing-stage').textContent = data.stage + '...';
    document.getElementById('processing-bar').style.width = data.pct + '%';
    document.getElementById('processing-pct').textContent = Math.round(data.pct) + '%';
    document.getElementById('processing-detail').textContent = data.message;

    // Add to log
    addLog(data.message);
}

function updateElapsed() {
    if (!startTime) return;
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const min = Math.floor(elapsed / 60);
    const sec = elapsed % 60;
    document.getElementById('elapsed-time').textContent =
        min + ':' + (sec < 10 ? '0' : '') + sec;
}

function addLog(message) {
    const logArea = document.getElementById('log-area');
    const line = document.createElement('div');
    line.className = 'log-line';
    line.textContent = '> ' + message;
    logArea.appendChild(line);
    logArea.scrollTop = logArea.scrollHeight;
}

// --- Results ---

function showResults(data) {
    releaseWakeLock();
    showSection('section-results');

    const clips = data.clips;
    const totalDuration = clips.reduce(function(sum, c) { return sum + c.duration; }, 0);

    document.getElementById('result-summary').textContent =
        clips.length + '試合を抽出しました';
    document.getElementById('result-total-duration').textContent =
        '合計: ' + formatDuration(totalDuration);

    // Build clips list
    const listEl = document.getElementById('clips-list');
    listEl.innerHTML = '';

    clips.forEach(function(clip) {
        const card = document.createElement('div');
        card.className = 'clip-card';

        var methodLabels = { 'score detected': 'スコア検出', 'win detected': 'WIN検出', 'fallback': 'フォールバック' };
        const method = methodLabels[clip.detection_method] || clip.detection_method;

        card.innerHTML =
            '<div class="clip-info">' +
                '<span class="clip-title">試合 ' + clip.match + '</span>' +
                '<span class="clip-time">' +
                    formatTimestamp(clip.start) + ' - ' + formatTimestamp(clip.end) +
                    ' (' + formatDuration(clip.duration) + ')' +
                '</span>' +
                '<span class="clip-method">[' + method + ']</span>' +
            '</div>' +
            '<button class="btn btn-download" onclick="downloadClip(\'' +
                data.job_id + '\', \'match_' + String(clip.match).padStart(2, '0') + '.mp4\')">' +
                'ダウンロード' +
            '</button>';

        listEl.appendChild(card);
    });

    // Store job_id for combined download
    document.getElementById('btn-download-combined').dataset.jobId = data.job_id;
}

function downloadClip(jobId, filename) {
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.download_file(jobId, filename).then(function(result) {
            if (result && result.error) {
                showError('ダウンロードエラー: ' + result.error);
            }
            // null = user cancelled, that's OK
        }).catch(function(err) {
            showError('ダウンロードエラー: ' + (err || ''));
        });
    } else {
        // Fallback for plain browser
        var a = document.createElement('a');
        a.href = '/download/' + jobId + '/' + filename;
        a.download = filename;
        a.click();
    }
}

function downloadCombined() {
    const btn = document.getElementById('btn-download-combined');
    const jobId = btn.dataset.jobId;
    downloadClip(jobId, 'all_matches_combined.mp4');
}

// --- Error handling ---

function showError(message) {
    releaseWakeLock();
    clearInterval(elapsedTimer);
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    document.getElementById('error-message').textContent = message;
    showSection('section-error');
}

// --- UI helpers ---

function showSection(id) {
    var sections = document.querySelectorAll('.section');
    for (var i = 0; i < sections.length; i++) {
        sections[i].classList.remove('active');
    }
    document.getElementById(id).classList.add('active');
}

function resetUI() {
    currentJobId = null;
    uploadXHR = null;
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    clearInterval(elapsedTimer);
    startTime = null;
    releaseWakeLock();

    // Reset file input and re-attach listeners
    var fi = document.getElementById('file-input');
    fi.value = '';
    fi.removeEventListener('change', handleFileSelect);
    fi.removeEventListener('input', handleFileSelect);
    fi.addEventListener('change', handleFileSelect);
    fi.addEventListener('input', handleFileSelect);
    document.getElementById('file-info').style.display = 'none';
    document.getElementById('btn-select').style.display = 'block';
    document.getElementById('upload-progress').style.display = 'none';
    document.querySelector('.hint').style.display = 'block';
    document.getElementById('upload-bar').style.width = '0%';
    document.getElementById('upload-detail').textContent = '0%';

    // Reset processing
    document.getElementById('processing-bar').style.width = '0%';
    document.getElementById('processing-pct').textContent = '0%';
    document.getElementById('processing-stage').textContent = '準備中...';
    document.getElementById('processing-detail').textContent = '';
    document.getElementById('elapsed-time').textContent = '0:00';
    document.getElementById('log-area').innerHTML = '';

    // Reset game selector
    selectedGame = 'hado';
    document.getElementById('btn-hado').classList.add('selected');
    document.getElementById('btn-hadoworld').classList.remove('selected');

    showSection('section-upload');
}

// --- Wake Lock ---

async function acquireWakeLock() {
    if ('wakeLock' in navigator) {
        try {
            wakeLock = await navigator.wakeLock.request('screen');
        } catch (e) {
            // Wake lock not available or denied
        }
    }
}

function releaseWakeLock() {
    if (wakeLock) {
        wakeLock.release();
        wakeLock = null;
    }
}

// --- Formatting ---

function formatSize(bytes) {
    if (bytes >= 1073741824) {
        return (bytes / 1073741824).toFixed(2) + ' GB';
    } else if (bytes >= 1048576) {
        return (bytes / 1048576).toFixed(1) + ' MB';
    } else {
        return (bytes / 1024).toFixed(0) + ' KB';
    }
}

function formatDuration(seconds) {
    seconds = Math.round(seconds);
    var m = Math.floor(seconds / 60);
    var s = seconds % 60;
    return m + '分' + (s < 10 ? '0' : '') + s + '秒';
}

function formatTimestamp(seconds) {
    var m = Math.floor(seconds / 60);
    var s = Math.floor(seconds % 60);
    return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
}
