/**
 * HyperFind — Frontend Controller
 * EventBus + Panel Switching + Upload + Repository + Search
 */

// ═══════════════════════════════════════════════════════════
// EventBus
// ═══════════════════════════════════════════════════════════

class EventBus {
    constructor() {
        this._listeners = {};
    }

    on(event, callback) {
        if (!this._listeners[event]) this._listeners[event] = [];
        this._listeners[event].push(callback);
    }

    emit(event, data) {
        const cbs = this._listeners[event];
        if (cbs) cbs.forEach(cb => cb(data));
    }

    off(event, callback) {
        const cbs = this._listeners[event];
        if (cbs) {
            this._listeners[event] = cbs.filter(cb => cb !== callback);
        }
    }
}

window._eventBus = new EventBus();

// ═══════════════════════════════════════════════════════════
// Backend Event Bridge
// ═══════════════════════════════════════════════════════════

window.onBackendEvent = function(payload) {
    try {
        const { event, data } = typeof payload === 'string' ? JSON.parse(payload) : payload;
        window._eventBus.emit(event, data);
    } catch (e) {
        console.error('[BackendEvent] parse error:', e);
    }
};

// ═══════════════════════════════════════════════════════════
// Toast Notifications
// ═══════════════════════════════════════════════════════════

function showToast(message, type) {
    type = type || 'info';
    const area = document.getElementById('toastArea');
    const toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.textContent = message;
    area.appendChild(toast);
    setTimeout(function() {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(function() { toast.remove(); }, 300);
    }, 3000);
}

// ═══════════════════════════════════════════════════════════
// Modal Confirmation
// ═══════════════════════════════════════════════════════════

let _modalResolve = null;

function showModal(title, body, confirmText) {
    return new Promise(function(resolve) {
        document.getElementById('modalTitle').textContent = title;
        document.getElementById('modalBody').textContent = body;
        document.getElementById('modalConfirm').textContent = confirmText || '确认';
        document.getElementById('modalOverlay').classList.add('visible');
        _modalResolve = resolve;
    });
}

function hideModal(confirmed) {
    document.getElementById('modalOverlay').classList.remove('visible');
    if (_modalResolve) {
        _modalResolve(!!confirmed);
        _modalResolve = null;
    }
}

document.getElementById('modalConfirm').addEventListener('click', function() { hideModal(true); });
document.getElementById('modalCancel').addEventListener('click', function() { hideModal(false); });
document.getElementById('modalOverlay').addEventListener('click', function(e) {
    if (e.target === this) hideModal(false);
});

// ═══════════════════════════════════════════════════════════
// Tab Switching
// ═══════════════════════════════════════════════════════════

document.getElementById('mainTabs').addEventListener('click', function(e) {
    const tab = e.target.closest('.tab');
    if (!tab) return;
    const tabName = tab.dataset.tab;
    switchTab(tabName);
});

function switchTab(name) {
    // Update tab buttons
    document.querySelectorAll('.tab').forEach(function(t) {
        t.classList.toggle('active', t.dataset.tab === name);
    });

    // Show/hide panels
    document.getElementById('panelUpload').classList.toggle('panel-hidden', name !== 'upload');
    document.getElementById('panelRepository').classList.toggle('panel-hidden', name === 'upload' || name === 'search');
    document.getElementById('panelSearch').classList.toggle('panel-hidden', name !== 'search');

    window._eventBus.emit('tab:switched', { tab: name });
}

// ═══════════════════════════════════════════════════════════
// Sidebar — File Type Tree
// ═══════════════════════════════════════════════════════════

const TYPE_CONFIG = [
    { key: 'excel',       icon: '📊', label: 'Excel' },
    { key: 'word',        icon: '📝', label: 'Word' },
    { key: 'pdf',         icon: '📄', label: 'PDF' },
    { key: 'powerpoint',  icon: '📽',  label: 'PowerPoint' },
    { key: 'html',        icon: '🌐', label: 'HTML' },
    { key: 'markdown',    icon: '📑', label: 'Markdown' },
];

let _currentFileType = null;  // currently selected type in sidebar

async function loadSidebar() {
    try {
        const repo = await window.pywebview.api.get_file_repository();
        const byType = repo.by_type || {};
        const total = repo.total || 0;

        const nav = document.getElementById('sidebarNav');
        nav.innerHTML = '';

        if (total === 0) {
            nav.innerHTML = '<div class="sidebar-empty">暂无文件</div>';
        } else {
            TYPE_CONFIG.forEach(function(tc) {
                const count = byType[tc.key] || 0;
                const div = document.createElement('div');
                div.className = 'type-item' + (count === 0 ? ' empty-type' : '');
                div.dataset.type = tc.key;
                div.innerHTML = '<span class="type-icon">' + tc.icon + '</span>' +
                    '<span class="type-name">' + tc.label + '</span>' +
                    '<span class="type-count">' + count + '</span>';
                div.addEventListener('click', function() {
                    selectFileType(tc.key);
                });
                nav.appendChild(div);
            });
        }

        document.getElementById('sidebarTotal').textContent = '总计: ' + total + ' 文件';
        document.getElementById('btnClearAll').disabled = (total === 0);
    } catch (e) {
        console.error('[Sidebar] load error:', e);
    }
}

function selectFileType(fileType) {
    _currentFileType = fileType;

    // Highlight sidebar
    document.querySelectorAll('.type-item').forEach(function(item) {
        item.classList.toggle('active', item.dataset.type === fileType);
    });

    // Switch to repository panel view
    switchTab('repository');
    loadFileList(fileType);
}

async function loadFileList(fileType) {
    try {
        const files = await window.pywebview.api.get_files_by_type(fileType);
        const tc = TYPE_CONFIG.find(function(t) { return t.key === fileType; });
        document.getElementById('repoTitle').textContent = (tc ? tc.icon : '') + ' ' + (tc ? tc.label : fileType) + ' (' + files.length + ')';

        const list = document.getElementById('repoList');
        const empty = document.getElementById('repoEmpty');

        if (files.length === 0) {
            list.innerHTML = '';
            empty.style.display = 'block';
            return;
        }

        empty.style.display = 'none';
        list.innerHTML = files.map(function(f) {
            return '<div class="file-card">' +
                '<div class="file-card-info">' +
                    '<div class="file-card-name">' + escapeHtml(f.file_name) + '</div>' +
                    '<div class="file-card-meta">' +
                        '<span>' + linkMethodLabel(f.link_method) + '</span>' +
                        '<span>' + formatSize(f.file_size) + '</span>' +
                        '<span>' + (f.chunk_count || 0) + ' 块</span>' +
                        '<span>上传于 ' + formatDate(f.uploaded_at) + '</span>' +
                    '</div>' +
                    '<div class="file-card-path" title="' + escapeHtml(f.original_path) + '">' +
                        escapeHtml(f.original_path) +
                    '</div>' +
                '</div>' +
                '<div class="file-card-actions">' +
                    '<button class="btn-delete" data-file-id="' + f.file_id + '" data-file-name="' + escapeHtml(f.file_name) + '">🗑</button>' +
                '</div>' +
            '</div>';
        }).join('');

        // Bind delete buttons
        list.querySelectorAll('.btn-delete').forEach(function(btn) {
            btn.addEventListener('click', async function() {
                const fileId = btn.dataset.fileId;
                const fileName = btn.dataset.fileName;
                const confirmed = await showModal('确认删除', '将删除 "' + fileName + '" 及其全部索引数据，此操作不可撤销。');
                if (confirmed) {
                    try {
                        await window.pywebview.api.delete_file(fileId);
                        showToast('已删除: ' + fileName, 'success');
                        await refreshAllPanels();
                    } catch (e) {
                        showToast('删除失败: ' + e, 'error');
                    }
                }
            });
        });
    } catch (e) {
        console.error('[Repo] load error:', e);
    }
}

// ═══════════════════════════════════════════════════════════
// Panel 1: Upload Center
// ═══════════════════════════════════════════════════════════

const dropzone = document.getElementById('dropzone');

// Click to select files
dropzone.addEventListener('click', async function() {
    await selectAndUpload();
});

// Drag & drop
dropzone.addEventListener('dragover', function(e) {
    e.preventDefault();
    dropzone.classList.add('drag-over');
});

dropzone.addEventListener('dragleave', function(e) {
    e.preventDefault();
    dropzone.classList.remove('drag-over');
});

dropzone.addEventListener('drop', async function(e) {
    e.preventDefault();
    dropzone.classList.remove('drag-over');

    const paths = [];

    // macOS Finder: text/uri-list
    const uriList = e.dataTransfer.getData('text/uri-list');
    if (uriList) {
        uriList.split('\n').forEach(function(line) {
            const trimmed = line.trim();
            if (!trimmed) return;
            try {
                const url = new URL(trimmed);
                if (url.protocol === 'file:') {
                    paths.push(decodeURIComponent(url.pathname));
                }
            } catch (_) {}
        });
    }

    // Windows/Linux: file.path
    if (paths.length === 0 && e.dataTransfer.files) {
        for (let i = 0; i < e.dataTransfer.files.length; i++) {
            const f = e.dataTransfer.files[i];
            if (f.path) {
                paths.push(f.path);
            } else {
                paths.push('__lookup__:' + f.name);
            }
        }
    }

    if (paths.length > 0) {
        await doUpload(paths);
    }
});

document.getElementById('btnSelectFiles').addEventListener('click', selectAndUpload);
document.getElementById('btnClearDone').addEventListener('click', clearCompletedProgress);

async function selectAndUpload() {
    try {
        const files = await window.pywebview.api.select_files();
        if (files && files.length > 0) {
            await doUpload(files);
        }
    } catch (e) {
        console.error('[Upload] select error:', e);
        showToast('选择文件失败', 'error');
    }
}

async function doUpload(paths) {
    // Clear old progress bars
    clearAllProgress();

    console.log('[Upload] uploading ' + paths.length + ' files');

    try {
        const result = await window.pywebview.api.upload_files(paths);
        console.log('[Upload] result:', result);

        if (result.task_ids) {
            // Non-blocking: poll for progress
            pollUploadTasks();
        } else if (result.results) {
            // Blocking: results directly returned
            result.results.forEach(function(r, i) {
                updateFileProgress({
                    index: i,
                    file_name: r.file_name || paths[i].split('/').pop(),
                    status: r.success ? '✅ 已完成' : '❌ 失败',
                    progress: r.success ? 1.0 : 0,
                    link_method: r.link_method,
                    chunk_count: r.chunk_count,
                    error: r.error,
                });
            });
            await refreshAllPanels();
        }
    } catch (e) {
        console.error('[Upload] error:', e);
        showToast('上传失败: ' + e, 'error');
    }
}

function pollUploadTasks() {
    const interval = setInterval(async function() {
        try {
            const tasks = await window.pywebview.api.get_upload_tasks();
            if (!tasks || tasks.length === 0) {
                clearInterval(interval);
                return;
            }

            let allDone = true;
            tasks.forEach(function(t) {
                updateFileProgress({
                    index: t.index,
                    file_name: t.file_name,
                    status: statusLabel(t.status),
                    progress: t.progress,
                });
                if (t.status !== 'done' && t.status !== 'error') {
                    allDone = false;
                }
            });

            if (allDone) {
                clearInterval(interval);
                await refreshAllPanels();
            }
        } catch (e) {
            clearInterval(interval);
        }
    }, 500);
}

function updateFileProgress(data) {
    const grid = document.getElementById('progressGrid');
    const idx = data.index !== undefined ? data.index : 0;
    let row = document.getElementById('progress-' + idx);

    if (!row) {
        row = document.createElement('div');
        row.id = 'progress-' + idx;
        row.className = 'progress-row';
        row.innerHTML =
            '<div class="progress-row-header">' +
                '<span class="progress-row-name">📄 <span class="row-filename">' + escapeHtml(data.file_name) + '</span></span>' +
                '<span class="progress-row-status"></span>' +
            '</div>' +
            '<div class="progress-bar"><div class="progress-bar-fill"></div></div>' +
            '<div class="progress-row-meta" style="font-size:11px;color:var(--text-tertiary);margin-top:2px"></div>';
        grid.appendChild(row);
    }

    const pct = Math.round((data.progress || 0) * 100);
    row.querySelector('.row-filename').textContent = data.file_name;
    row.querySelector('.progress-row-status').textContent = data.status;

    const fill = row.querySelector('.progress-bar-fill');
    fill.style.width = pct + '%';

    // Map status to CSS class
    const statusClass = statusToClass(data.status);
    fill.className = 'progress-bar-fill ' + statusClass;

    if (data.status === '✅ 已完成' || data.status === 'done') {
        row.classList.add('completed');
    }
    if (data.status === '❌ 失败' || data.status === 'error') {
        row.classList.add('error');
        const meta = row.querySelector('.progress-row-meta');
        if (meta && data.error) meta.textContent = '错误: ' + data.error;
    }

    // Link/chunk info
    if (data.link_method || data.chunk_count) {
        const meta = row.querySelector('.progress-row-meta');
        if (meta) {
            let info = [];
            if (data.link_method) info.push(linkMethodLabel(data.link_method));
            if (data.chunk_count) info.push(data.chunk_count + ' 个文本块');
            meta.textContent = info.join(' · ');
        }
    }
}

function clearAllProgress() {
    document.getElementById('progressGrid').innerHTML = '';
}

function clearCompletedProgress() {
    const grid = document.getElementById('progressGrid');
    grid.querySelectorAll('.progress-row.completed').forEach(function(r) { r.remove(); });
}

// ═══════════════════════════════════════════════════════════
// Panel 3: Smart Search
// ═══════════════════════════════════════════════════════════

let _searchResults = [];  // current search results for export

document.getElementById('btnSearch').addEventListener('click', doSearch);
document.getElementById('searchInput').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') doSearch();
});
document.getElementById('btnClearSearch').addEventListener('click', clearSearch);
document.getElementById('btnExport').addEventListener('click', exportMatchedFiles);
document.getElementById('btnOpenFolder').addEventListener('click', openMatchedFolder);

// Threshold slider
document.getElementById('filterThreshold').addEventListener('input', function() {
    const labels = ['低', '中', '高'];
    const val = parseInt(this.value);
    document.getElementById('thresholdLabel').textContent = labels[val - 1] || '中';
});

async function doSearch() {
    const query = document.getElementById('searchInput').value.trim();
    if (!query) return;

    const fileType = document.getElementById('filterType').value;
    const mode = document.getElementById('filterMode').value;
    const threshold = parseInt(document.getElementById('filterThreshold').value);

    document.getElementById('searchResults').innerHTML =
        '<div style="text-align:center;padding:48px;color:var(--text-tertiary)">🔍 搜索中...</div>';
    document.getElementById('searchSummary').textContent = '';
    document.getElementById('exportBar').innerHTML = '';

    try {
        const result = await window.pywebview.api.search(query, fileType, mode, threshold);
        _searchResults = result.results || [];
        renderSearchResults(result);
    } catch (e) {
        console.error('[Search] error:', e);
        document.getElementById('searchResults').innerHTML =
            '<div style="text-align:center;padding:48px;color:var(--danger)">搜索出错: ' + e + '</div>';
    }
}

function renderSearchResults(result) {
    const totalFiles = result.total_files || 0;
    const totalHits = result.total_hits || 0;
    const time = result.search_time_ms || 0;

    document.getElementById('searchSummary').textContent =
        '找到 ' + totalFiles + ' 个文件，共 ' + totalHits + ' 处匹配 (用时 ' + time + 'ms)';

    const container = document.getElementById('searchResults');

    if (totalFiles === 0) {
        container.innerHTML = '<div style="text-align:center;padding:48px;color:var(--text-tertiary)">未找到匹配结果</div>';
        document.getElementById('exportBar').innerHTML = '';
        return;
    }

    const results = result.results || [];
    container.innerHTML = results.map(function(file) {
        const snippetsHtml = (file.snippets || []).map(function(s) {
            // 后端已做 <mark> 高亮，直接渲染
            return '<div class="result-snippet">' + s.content + '</div>';
        }).join('');

        return '<div class="result-card">' +
            '<div class="result-card-header">' +
                '<span class="result-card-title">' +
                    (getFileIcon(file.file_type) || '📄') + ' ' + escapeHtml(file.file_name) +
                '</span>' +
                '<span class="result-card-badge">匹配: ' + (file.match_count || 0) + ' 处</span>' +
            '</div>' +
            '<div class="result-snippets">' + snippetsHtml + '</div>' +
            '<div class="result-card-actions">' +
                '<button class="btn-secondary btn-sm btn-open-file" data-path="' + escapeHtml(file.file_path || file.original_path) + '">打开文件</button>' +
            '</div>' +
        '</div>';
    }).join('');

    // Bind open file buttons
    container.querySelectorAll('.btn-open-file').forEach(function(btn) {
        btn.addEventListener('click', async function() {
            try {
                await window.pywebview.api.open_file(btn.dataset.path);
                showToast('已打开文件', 'success');
            } catch (e) {
                showToast('打开失败: ' + e, 'error');
            }
        });
    });

    // Export bar
    var exportBar = document.getElementById('exportBar');
    exportBar.style.display = 'flex';
    exportBar.innerHTML =
        '<span class="export-info">✅ 已选择 ' + totalFiles + ' 个文件</span>' +
        '<div style="display:flex;gap:8px">' +
            '<button class="btn-primary btn-sm" id="btnExportAction">📋 复制所有匹配文件到...</button>' +
            '<button class="btn-secondary btn-sm" id="btnOpenFolderAction">📂 打开所在文件夹</button>' +
        '</div>';

    document.getElementById('btnExportAction').addEventListener('click', exportMatchedFiles);
    document.getElementById('btnOpenFolderAction').addEventListener('click', openMatchedFolder);
}

async function exportMatchedFiles() {
    if (!_searchResults || _searchResults.length === 0) {
        showToast('没有匹配的文件可导出', 'info');
        return;
    }
    try {
        const fileIds = _searchResults.map(function(r) { return r.file_id; });
        const result = await window.pywebview.api.export_matched_files(fileIds);
        if (result.success) {
            showToast('已复制 ' + result.copied_count + ' 个文件到 ' + result.target_dir, 'success');
        }
    } catch (e) {
        showToast('导出失败: ' + e, 'error');
    }
}

async function openMatchedFolder() {
    if (!_searchResults || _searchResults.length === 0) return;
    const firstPath = _searchResults[0].file_path || _searchResults[0].original_path;
    if (firstPath) {
        try {
            await window.pywebview.api.open_file(firstPath);
        } catch (e) {
            showToast('打开失败', 'error');
        }
    }
}

function clearSearch() {
    document.getElementById('searchInput').value = '';
    document.getElementById('searchResults').innerHTML = '';
    document.getElementById('searchSummary').textContent = '';
    var exportBar = document.getElementById('exportBar');
    exportBar.innerHTML = '';
    exportBar.style.display = 'none';
    _searchResults = [];
}

// ═══════════════════════════════════════════════════════════
// Status Bar
// ═══════════════════════════════════════════════════════════

async function updateStatusBar() {
    try {
        const stats = await window.pywebview.api.get_app_status();
        document.getElementById('statusTotal').textContent =
            '📊 仓库共有 ' + (stats.total_files || 0) + ' 个文件';

        const lm = stats.link_counts || {};
        document.getElementById('statusLinks').textContent =
            '📦 硬链接: ' + (lm.hardlink || 0) +
            ' · 软链接: ' + (lm.symlink || 0) +
            ' · 克隆: ' + (lm.clonefile || 0) +
            ' · 复制: ' + (lm.copy || 0);

        document.getElementById('statusIndexed').textContent =
            '上次索引: ' + (stats.last_indexed ? formatRelativeTime(stats.last_indexed) : '--');
    } catch (e) {
        console.error('[StatusBar] update error:', e);
    }
}

// ═══════════════════════════════════════════════════════════
// Global Refresh
// ═══════════════════════════════════════════════════════════

async function refreshAllPanels() {
    await loadSidebar();
    await updateStatusBar();
}

// ═══════════════════════════════════════════════════════════
// Utility Functions
// ═══════════════════════════════════════════════════════════

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function formatSize(bytes) {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let size = bytes;
    while (size >= 1024 && i < units.length - 1) {
        size /= 1024;
        i++;
    }
    return size.toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
}

function formatDate(dateStr) {
    if (!dateStr) return '--';
    try {
        const d = new Date(dateStr);
        return d.getFullYear() + '-' +
            String(d.getMonth() + 1).padStart(2, '0') + '-' +
            String(d.getDate()).padStart(2, '0');
    } catch (_) {
        return dateStr;
    }
}

function formatRelativeTime(dateStr) {
    if (!dateStr) return '--';
    try {
        const now = Date.now();
        const then = new Date(dateStr).getTime();
        const diff = Math.floor((now - then) / 1000);
        if (diff < 60) return '刚刚';
        if (diff < 3600) return Math.floor(diff / 60) + '分钟前';
        if (diff < 86400) return Math.floor(diff / 3600) + '小时前';
        return Math.floor(diff / 86400) + '天前';
    } catch (_) {
        return dateStr;
    }
}

function linkMethodLabel(method) {
    const labels = {
        'hardlink': '🔗 硬链接',
        'symlink': '🔗 软链接',
        'clonefile': '🍎 APFS 克隆',
        'chunked_copy': '📋 分块复制',
        'copy': '📋 普通复制',
    };
    return labels[method] || method || '--';
}

function statusLabel(status) {
    const labels = {
        'waiting': '排队中…',
        'linking': '链接中…',
        'parsing': '解析中…',
        'chunking': '切片中…',
        'embedding': '嵌入中…',
        'indexing': '索引中…',
        'saving': '存储中…',
        'done': '✅ 已完成',
        'error': '❌ 失败',
    };
    return labels[status] || status;
}

function statusToClass(status) {
    const map = {
        '排队中…': 'waiting', 'waiting': 'waiting',
        '链接中…': 'linking', 'linking': 'linking',
        '解析中…': 'parsing', 'parsing': 'parsing',
        '切片中…': 'chunking', 'chunking': 'chunking',
        '嵌入中…': 'embedding', 'embedding': 'embedding',
        '索引中…': 'indexing', 'indexing': 'indexing',
        '存储中…': 'saving', 'saving': 'saving',
        '✅ 已完成': 'done', 'done': 'done',
        '❌ 失败': 'error', 'error': 'error',
    };
    return map[status] || 'waiting';
}

function getFileIcon(fileType) {
    const icons = {
        'excel': '📊',
        'word': '📝',
        'pdf': '📄',
        'powerpoint': '📽',
        'html': '🌐',
        'markdown': '📑',
    };
    return icons[fileType] || '📄';
}

function highlightText(text, query) {
    if (!text || !query) return escapeHtml(text);
    const escaped = escapeHtml(text);
    const queryWords = query.split(/\s+/).filter(function(w) { return w.length > 0; });
    let result = escaped;
    queryWords.forEach(function(word) {
        const escapedWord = escapeHtml(word);
        const regex = new RegExp('(' + escapedWord.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
        result = result.replace(regex, '<mark>$1</mark>');
    });
    return result;
}

// ═══════════════════════════════════════════════════════════
// Event Bindings — Internal Events
// ═══════════════════════════════════════════════════════════

window._eventBus.on('file:uploaded', refreshAllPanels);
window._eventBus.on('file:deleted', refreshAllPanels);
window._eventBus.on('files:cleared', refreshAllPanels);

// Backend push events — progress & errors
window._eventBus.on('file:progress', function(data) {
    updateFileProgress({
        index: data.index,
        file_name: data.file_name,
        status: statusLabel(data.status),
        progress: data.progress,
        link_method: data.link_method,
        chunk_count: data.chunk_count,
        error: data.error,
    });
});
window._eventBus.on('upload:complete', refreshAllPanels);
window._eventBus.on('upload:error', refreshAllPanels);
window._eventBus.on('app:error', function(data) {
    showToast('应用错误: ' + (data.message || '未知错误'), 'error');
    console.error('[App Error]', data);
});

// ═══════════════════════════════════════════════════════════
// Init — wait for pywebview
// ═══════════════════════════════════════════════════════════

async function initApp() {
    console.log('[HyperFind] Initializing...');

    // Listen for backend ready event
    window._eventBus.on('app:ready', async function() {
        console.log('[HyperFind] Backend ready');
        document.getElementById('loadingOverlay').classList.add('hidden');
        await refreshAllPanels();
    });

    // Backend init progress
    window._eventBus.on('app:init', function(data) {
        document.getElementById('loadingStatus').textContent = data.status || '';
    });

    // If already ready (pywebview loaded before init)
    if (window.pywebview && window.pywebview.api) {
        await refreshAllPanels();
    }

    // Sidebar clear all button
    document.getElementById('btnClearAll').addEventListener('click', async function() {
        const confirmed = await showModal(
            '清空全部索引',
            '此操作将删除所有文件索引和链接，不可撤销。确定继续吗？',
            '确认清空'
        );
        if (confirmed) {
            try {
                await window.pywebview.api.clear_all_files();
                showToast('已清空全部索引', 'info');
                await refreshAllPanels();
            } catch (e) {
                showToast('清空失败: ' + e, 'error');
            }
        }
    });

    console.log('[HyperFind] Init complete');
}

// Wait for pywebview to be ready
window.addEventListener('pywebviewready', initApp);

// Fallback: if pywebview is already ready
if (window.pywebview && window.pywebview.api) {
    initApp();
}
