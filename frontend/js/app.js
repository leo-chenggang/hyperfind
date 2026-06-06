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
        if (cbs) cbs.forEach(function(cb) { cb(data); });
    }
}

window._eventBus = new EventBus();

// ═══════════════════════════════════════════════════════════
// Backend Event Bridge
// ═══════════════════════════════════════════════════════════

window.onBackendEvent = function(payload) {
    try {
        var parsed = typeof payload === 'string' ? JSON.parse(payload) : payload;
        window._eventBus.emit(parsed.event, parsed.data);
    } catch (e) {
        console.error('[BackendEvent] parse error:', e);
    }
};

// ═══════════════════════════════════════════════════════════
// Utility Functions
// ═══════════════════════════════════════════════════════════

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function formatSize(bytes) {
    if (!bytes) return '0 B';
    var units = ['B', 'KB', 'MB', 'GB'];
    var i = 0;
    var size = bytes;
    while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
    return size.toFixed(i === 0 ? 0 : 1) + ' ' + units[i];
}

function formatDate(dateStr) {
    if (!dateStr) return '--';
    try {
        var d = new Date(dateStr);
        return d.getFullYear() + '-' +
            String(d.getMonth() + 1).padStart(2, '0') + '-' +
            String(d.getDate()).padStart(2, '0');
    } catch (e) { return dateStr; }
}

function linkMethodLabel(method) {
    var map = { hardlink: '硬链接', symlink: '软链接', clonefile: 'APFS 克隆', chunked_copy: '分块复制', copy: '复制' };
    return map[method] || method || '--';
}

var STATUS_LABELS = {
    waiting:   '排队中',
    hashing:   '哈希中',
    linking:   '链接中',
    parsing:   '解析中',
    chunking:  '切片中',
    embedding: '嵌入中',
    saving:    '存储中',
    indexing:  '索引中',
    done:      '已完成',
    error:     '失败',
    skipped:   '已跳过',
};

// ═══════════════════════════════════════════════════════════
// Toast Notifications
// ═══════════════════════════════════════════════════════════

function showToast(message, type) {
    type = type || 'info';
    var area = document.getElementById('toastArea');
    var toast = document.createElement('div');
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

var _modalResolve = null;

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
    var tab = e.target.closest('.tab');
    if (!tab) return;
    switchTab(tab.dataset.tab);
});

function switchTab(name) {
    document.querySelectorAll('.tab').forEach(function(t) {
        t.classList.toggle('active', t.dataset.tab === name);
    });
    document.getElementById('panelUpload').classList.toggle('panel-hidden', name !== 'upload');
    document.getElementById('panelRepository').classList.toggle('panel-hidden', name === 'upload' || name === 'search');
    document.getElementById('panelSearch').classList.toggle('panel-hidden', name !== 'search');
    window._eventBus.emit('tab:switched', { tab: name });
}

// ═══════════════════════════════════════════════════════════
// Sidebar — File Type Tree
// ═══════════════════════════════════════════════════════════

var TYPE_CONFIG = [
    { key: 'excel',      icon: '\uD83D\uDCCA', label: 'Excel' },
    { key: 'word',       icon: '\uD83D\uDCDD', label: 'Word' },
    { key: 'pdf',        icon: '\uD83D\uDCC4', label: 'PDF' },
    { key: 'powerpoint', icon: '\uD83D\uDCFD', label: 'PowerPoint' },
    { key: 'html',       icon: '\uD83C\uDF10', label: 'HTML' },
    { key: 'markdown',   icon: '\uD83D\uDCD1', label: 'Markdown' },
];

var _currentFileType = null;

async function loadSidebar() {
    try {
        var repo = await window.pywebview.api.get_file_repository();
        var byType = repo.by_type || {};
        var total = repo.total || 0;
        var nav = document.getElementById('sidebarNav');
        nav.innerHTML = '';

        if (total === 0) {
            nav.innerHTML = '<div class="sidebar-empty">暂无文件</div>';
        } else {
            TYPE_CONFIG.forEach(function(tc) {
                var count = byType[tc.key] || 0;
                var div = document.createElement('div');
                div.className = 'type-item' + (count === 0 ? ' empty-type' : '');
                div.dataset.type = tc.key;
                div.innerHTML = '<span class="type-icon">' + tc.icon + '</span>' +
                    '<span class="type-name">' + tc.label + '</span>' +
                    '<span class="type-count">' + count + '</span>';
                div.addEventListener('click', function() { selectFileType(tc.key); });
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
    document.querySelectorAll('.type-item').forEach(function(item) {
        item.classList.toggle('active', item.dataset.type === fileType);
    });
    switchTab('repository');
    loadFileList(fileType);
}

async function loadFileList(fileType) {
    try {
        var files = await window.pywebview.api.get_files_by_type(fileType);
        var tc = TYPE_CONFIG.find(function(t) { return t.key === fileType; });
        document.getElementById('repoTitle').textContent = (tc ? tc.icon + ' ' + tc.label : fileType) + ' (' + files.length + ')';

        var list = document.getElementById('repoList');
        var empty = document.getElementById('repoEmpty');

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

        list.querySelectorAll('.btn-delete').forEach(function(btn) {
            btn.addEventListener('click', async function() {
                var fileId = btn.dataset.fileId;
                var fileName = btn.dataset.fileName;
                var confirmed = await showModal('确认删除', '将删除 "' + fileName + '" 及其全部索引数据，此操作不可撤销。');
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

var dropzone = document.getElementById('dropzone');

dropzone.addEventListener('click', async function() { await selectAndUpload(); });

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
    var paths = [];

    var uriList = e.dataTransfer.getData('text/uri-list');
    if (uriList) {
        uriList.split('\n').forEach(function(line) {
            var t = line.trim();
            if (!t || t.startsWith('#')) return;
            try {
                var url = new URL(t);
                if (url.protocol === 'file:') paths.push(decodeURIComponent(url.pathname));
            } catch (_) {}
        });
    }

    if (paths.length === 0 && e.dataTransfer.files) {
        for (var i = 0; i < e.dataTransfer.files.length; i++) {
            var f = e.dataTransfer.files[i];
            if (f.path) { paths.push(f.path); }
            else { paths.push('__lookup__:' + f.name); }
        }
    }

    if (paths.length > 0) await doUpload(paths);
});

document.getElementById('btnSelectFiles').addEventListener('click', selectAndUpload);
document.getElementById('btnClearDone').addEventListener('click', clearCompletedProgress);

async function selectAndUpload() {
    try {
        var files = await window.pywebview.api.select_files();
        if (files && files.length > 0) await doUpload(files);
    } catch (e) {
        console.error('[Upload] select error:', e);
        showToast('选择文件失败', 'error');
    }
}

async function doUpload(paths) {
    clearAllProgress();
    try {
        var result = await window.pywebview.api.upload_files(paths);
        if (result.task_ids && result.task_ids.length > 0) {
            pollUploadTasks();
        } else if (result.results) {
            result.results.forEach(function(r, i) {
                updateFileProgress({
                    index: i,
                    file_name: r.file_name || paths[i].split('/').pop(),
                    status: r.success ? 'done' : 'error',
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
    var interval = setInterval(async function() {
        try {
            var tasks = await window.pywebview.api.get_upload_tasks();
            if (!tasks || tasks.length === 0) { clearInterval(interval); return; }
            var allDone = true;
            tasks.forEach(function(t) {
                updateFileProgress({
                    index: t.index,
                    file_name: t.file_name,
                    status: t.status || 'waiting',
                    progress: t.progress || 0,
                });
                if (t.status !== 'done' && t.status !== 'error') allDone = false;
            });
            if (allDone) { clearInterval(interval); await refreshAllPanels(); }
        } catch (e) { clearInterval(interval); }
    }, 500);
}

function updateFileProgress(data) {
    var grid = document.getElementById('progressGrid');
    var idx = data.index !== undefined ? data.index : 0;
    var row = document.getElementById('progress-' + idx);

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

    var pct = Math.round((data.progress || 0) * 100);
    row.querySelector('.progress-bar-fill').style.width = pct + '%';

    var statusEl = row.querySelector('.progress-row-status');
    var statusText = STATUS_LABELS[data.status] || data.status || '处理中';
    statusEl.textContent = statusText;
    statusEl.className = 'progress-row-status ' + (data.status === 'done' ? 'done' : data.status === 'error' ? 'error' : 'processing');

    if (data.status === 'done' || data.status === 'skipped') {
        row.classList.add('completed');
    }

    var meta = row.querySelector('.progress-row-meta');
    var parts = [];
    if (data.link_method) parts.push(linkMethodLabel(data.link_method));
    if (data.chunk_count !== undefined) parts.push(data.chunk_count + ' 个文本块');
    if (data.error) parts.push(data.error);
    meta.textContent = parts.join(' · ');
}

function clearAllProgress() {
    document.getElementById('progressGrid').innerHTML = '';
}

function clearCompletedProgress() {
    var grid = document.getElementById('progressGrid');
    grid.querySelectorAll('.progress-row.completed').forEach(function(r) { r.remove(); });
}

// ═══════════════════════════════════════════════════════════
// Panel 3: Search Center
// ═══════════════════════════════════════════════════════════

var _searchMatchedFiles = [];

document.getElementById('btnSearch').addEventListener('click', doSearch);
document.getElementById('searchInput').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') doSearch();
});

document.getElementById('btnClearSearch').addEventListener('click', function() {
    document.getElementById('searchInput').value = '';
    document.getElementById('searchResults').innerHTML = '';
    document.getElementById('searchSummary').textContent = '';
    document.getElementById('exportBar').style.display = 'none';
    _searchMatchedFiles = [];
});

document.getElementById('btnExport').addEventListener('click', async function() {
    if (_searchMatchedFiles.length === 0) return;
    try {
        var result = await window.pywebview.api.export_matched_files(_searchMatchedFiles);
        if (result.success) {
            showToast('已复制 ' + result.copied_count + ' 个文件到 ' + result.target_dir, 'success');
        } else {
            showToast(result.error || '导出失败', 'error');
        }
    } catch (e) { showToast('导出失败: ' + e, 'error'); }
});

document.getElementById('btnOpenFolder').addEventListener('click', async function() {
    if (_searchMatchedFiles.length === 0) return;
    try {
        var files = await window.pywebview.api.get_files_by_type('all');
        var firstMatch = _searchMatchedFiles[0];
        var file = null;
        for (var i = 0; i < files.length; i++) {
            if (files[i].file_id === firstMatch) { file = files[i]; break; }
        }
        if (!file && _searchMatchedFiles.length > 0) {
            try {
                var allFiles = await Promise.all(_searchMatchedFiles.map(function(fid) {
                    return window.pywebview.api.get_files_by_type('word');
                }));
            } catch (_) {}
        }
        if (file) {
            window.pywebview.api.open_file(file.original_path);
        }
    } catch (e) { console.error('[Export] error:', e); }
});

document.getElementById('filterThreshold').addEventListener('input', function() {
    var labels = { '1': '宽松', '2': '中', '3': '严格' };
    document.getElementById('thresholdLabel').textContent = labels[this.value] || '中';
});

async function doSearch() {
    var query = document.getElementById('searchInput').value.trim();
    if (!query) { showToast('请输入搜索内容', 'info'); return; }

    var fileType = document.getElementById('filterType').value;
    var mode = document.getElementById('filterMode').value;
    var threshold = parseInt(document.getElementById('filterThreshold').value) || 2;

    document.getElementById('searchSummary').textContent = '搜索中...';
    document.getElementById('searchResults').innerHTML = '';
    document.getElementById('exportBar').style.display = 'none';
    _searchMatchedFiles = [];

    try {
        var result = await window.pywebview.api.search(query, fileType, mode, threshold);
        document.getElementById('searchSummary').textContent = '找到 ' + result.total_files + ' 个文件，共 ' + result.total_hits + ' 处匹配 (' + result.search_time_ms + 'ms)';
        renderSearchResults(result.results);
        _searchMatchedFiles = result.results.map(function(r) { return r.file_id; });
    } catch (e) {
        console.error('[Search] error:', e);
        document.getElementById('searchSummary').textContent = '搜索出错';
        showToast('搜索失败: ' + e, 'error');
    }
}

function renderSearchResults(results) {
    var container = document.getElementById('searchResults');
    if (!results || results.length === 0) {
        container.innerHTML = '<div style="padding:32px;text-align:center;color:var(--text-tertiary);">无匹配结果</div>';
        document.getElementById('exportBar').style.display = 'none';
        return;
    }

    container.innerHTML = results.map(function(r) {
        var snippetsHtml = r.snippets.map(function(s) {
            return '<div class="result-card-snippet">' + s.content + '</div>';
        }).join('');

        return '<div class="result-card">' +
            '<div class="result-card-header">' +
                '<span class="result-card-name">' + escapeHtml(r.file_name) + '</span>' +
                '<span class="result-card-badge">匹配: ' + r.match_count + ' 处</span>' +
            '</div>' +
            '<div class="result-card-snippets">' + snippetsHtml + '</div>' +
            '<div class="result-card-actions">' +
                '<button class="btn-open-file" onclick="openFileByPath(\'' + escapeHtml(r.file_path).replace(/'/g, "\\'") + '\')">打开文件</button>' +
            '</div>' +
        '</div>';
    }).join('');

    document.getElementById('exportBar').style.display = 'flex';
    document.getElementById('exportInfo').textContent = '已选择 ' + results.length + ' 个文件';
}

function openFileByPath(filePath) {
    window.pywebview.api.open_file(filePath).catch(function(e) {
        showToast('无法打开文件: ' + e, 'error');
    });
}

// ═══════════════════════════════════════════════════════════
// Global Panel Refresh
// ═══════════════════════════════════════════════════════════

async function refreshAllPanels() {
    await loadSidebar();
    await updateStatusbar();
    if (_currentFileType) await loadFileList(_currentFileType);
}

async function updateStatusbar() {
    try {
        var status = await window.pywebview.api.get_app_status();
        document.getElementById('statusTotal').innerHTML = '📊 仓库共有 ' + status.total_files + ' 个文件';
        var lc = status.link_counts || {};
        document.getElementById('statusLinks').innerHTML = '📦 硬链接: ' + (lc.hardlink || 0) +
            ' · 软链接: ' + (lc.symlink || 0) +
            ' · 克隆: ' + (lc.clonefile || 0) +
            ' · 复制: ' + (lc.copy || 0);
        document.getElementById('statusIndexed').textContent = '上次索引: ' +
            (status.last_indexed ? formatDate(status.last_indexed) : '--');
    } catch (e) {
        console.error('[Statusbar] error:', e);
    }
}

// ═══════════════════════════════════════════════════════════
// Event Listeners — Backend Events + Clear All
// ═══════════════════════════════════════════════════════════

window._eventBus.on('file:uploaded', async function() { await refreshAllPanels(); });
window._eventBus.on('file:deleted', async function() { await refreshAllPanels(); });
window._eventBus.on('files:cleared', async function() { await refreshAllPanels(); });

window._eventBus.on('file:progress', function(data) {
    updateFileProgress(data);
});

window._eventBus.on('app:init', function(data) {
    var statusEl = document.getElementById('loadingStatus');
    if (statusEl) statusEl.textContent = data.status || '加载中...';
});

window._eventBus.on('app:ready', function() {
    var overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.classList.add('fade-out');
        setTimeout(function() { overlay.style.display = 'none'; }, 400);
    }
    refreshAllPanels();
});

// 引擎在后台线程初始化完成后发送 app:ready → 隐藏 loading overlay
// 注意：不在 DOMContentLoaded 中隐藏 — 引擎可能还未就绪
document.addEventListener('DOMContentLoaded', function() {
    loadSidebar();
    updateStatusbar();
});

document.getElementById('btnClearAll').addEventListener('click', async function() {
    var confirmed = await showModal('清空全部索引', '此操作将删除所有文件索引和仓库链接，原始文件不受影响。此操作不可撤销。', '确认清空');
    if (!confirmed) return;
    try {
        var result = await window.pywebview.api.clear_all_files();
        showToast('已清空 ' + result.deleted_count + ' 个文件的索引', 'success');
        _currentFileType = null;
        switchTab('upload');
        await refreshAllPanels();
    } catch (e) {
        showToast('清空失败: ' + e, 'error');
    }
});

