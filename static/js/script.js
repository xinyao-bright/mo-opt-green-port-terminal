let currentSolutions = [];
let activeSolutionId = null;
let currentPortConfig = null;

function alertMsg(text, isError = false) {
    const alertBox = document.createElement('div');
    alertBox.className = `alert ${isError ? 'alert-danger' : 'alert-success'} position-fixed`;
    alertBox.style.cssText = 'top: 25px; right: 25px; z-index: 99999; font-size:0.85rem; box-shadow:0 4px 12px rgba(0,0,0,0.3); max-width: 400px;';
    alertBox.innerText = text;
    document.body.appendChild(alertBox);
    setTimeout(() => alertBox.remove(), 3500);
}

async function refreshShipPool() {
    try {
        const res = await fetch('/api/ships');
        const data = await res.json();
        const box = document.getElementById('shipBox');
        if (!data.length) {
            box.innerHTML = `<div class="text-center py-4 text-muted fs-7" data-i18n="common.noData">${i18n ? i18n.t('common.noData') : '暂无数据'}</div>`;
            return;
        }
        box.innerHTML = data.map(s => `
            <div class="ship-mini-card">
                <div class="d-flex justify-content-between text-sm fw-bold"><span>${s.name}</span><span class="text-primary">${s.length}m</span></div>
                <div class="d-flex justify-content-between text-xs text-muted mt-1"><span>${i18n ? i18n.t('columns.volume_of_goods') : '货量'}: ${s.teu} TEU</span><span>ETA: ${s.arrivalTime}</span></div>
            </div>
        `).join('');
    } catch (e) {
        console.error(e);
    }
}

function parseCSVText(text) {
    const rows = [];
    let row = [];
    let cell = '';
    let inQuotes = false;
    for (let i = 0; i < text.length; i++) {
        const char = text[i];
        const nextChar = text[i + 1];
        if (char === '"' && inQuotes && nextChar === '"') { cell += '"'; i++; }
        else if (char === '"') { inQuotes = !inQuotes; }
        else if (char === ',' && !inQuotes) { row.push(cell.trim()); cell = ''; }
        else if ((char === '\n' || char === '\r') && !inQuotes) {
            if (char === '\r' && nextChar === '\n') i++;
            row.push(cell.trim());
            if (row.some(v => v !== '')) rows.push(row);
            row = []; cell = '';
        } else { cell += char; }
    }
    row.push(cell.trim());
    if (row.some(v => v !== '')) rows.push(row);
    return rows;
}

function escapeCSVCell(value) {
    const text = String(value ?? '');
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function escapeHTML(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

const DEFAULT_SHIP_COLUMNS = ['name', 'length', 'teu', 'arrivalTime'];
const DEFAULT_SHIP_SAMPLE = ['船舶A', '280', '4200', '2026-07-07 08:00'];

function formatFileSize(bytes) {
    if (!Number.isFinite(bytes)) return '--';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function updateSelectedFileInfo() {
    const file = document.getElementById('csvFile')?.files?.[0];
    const label = document.getElementById('selectedFileInfo');
    if (!label) return;
    if (!file) {
        label.innerHTML = `<i class="bi bi-info-circle me-1"></i>${i18n ? i18n.t('shipPool.uploadCSV') : '尚未选择 CSV 文件'}`;
        return;
    }
    label.innerHTML = `<i class="bi bi-filetype-csv me-1"></i>${escapeHTML(file.name)} · ${formatFileSize(file.size)}`;
}

function getImportEditorRows() {
    return Array.from(document.querySelectorAll('#importEditorTable tbody tr')).map(row =>
        Array.from(row.querySelectorAll('input')).map(input => input.value.trim())
    );
}

function addImportEditorRow(defaultValues = []) {
    const tbody = document.querySelector('#importEditorTable tbody');
    const columns = JSON.parse(document.getElementById('importEditorColumns').value || '[]');
    const row = document.createElement('tr');
    row.innerHTML = columns.map((column, index) => `
        <td><input type="text" class="form-control form-control-sm manual-cell-input"
                   placeholder="${escapeHTML(column)}" value="${escapeHTML(defaultValues[index] || '')}"></td>
    `).join('') + `
        <td class="text-center">
            <button type="button" class="btn btn-sm btn-outline-danger" onclick="deleteImportEditorRow(this)"><i class="bi bi-trash3"></i></button>
        </td>`;
    tbody.appendChild(row);
}

function deleteImportEditorRow(button) {
    const tbody = document.querySelector('#importEditorTable tbody');
    if (tbody.children.length <= 1) {
        Array.from(tbody.querySelectorAll('input')).forEach(input => input.value = '');
        alertMsg('至少保留一行，可直接清空该行内容', true);
        return;
    }
    button.closest('tr').remove();
}

function ensureImportEditorModal() {
    let modal = document.getElementById('importEditorModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.id = 'importEditorModal';
        modal.tabIndex = -1;
        modal.innerHTML = `
            <div class="modal-dialog modal-xl modal-dialog-centered modal-dialog-scrollable">
                <div class="modal-content manual-modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title"><i class="bi bi-database-up me-2"></i>船舶数据导入确认</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        <input type="hidden" id="importEditorColumns" value="[]">
                        <input type="hidden" id="importEditorMode" value="file">
                        <div class="manual-input-hint mb-3">请在弹窗内确认已选择文件的信息和表格内容。导入前可以直接修改单元格，也可以新增或删除行。</div>
                        <div class="import-file-summary mb-3" id="importFileSummary"></div>
                        <div class="table-responsive manual-table-wrap">
                            <table class="table table-dark table-bordered align-middle text-center fs-7" id="importEditorTable">
                                <thead></thead><tbody></tbody>
                            </table>
                        </div>
                    </div>
                    <div class="modal-footer d-flex justify-content-between flex-wrap gap-2">
                        <div class="d-flex gap-2">
                            <button type="button" class="btn btn-sm btn-outline-cyan" onclick="addImportEditorRow()"><i class="bi bi-plus-lg"></i> 新增一行</button>
                            <button type="button" class="btn btn-sm btn-outline-warning" onclick="clearImportEditorRows()"><i class="bi bi-eraser"></i> 清空表格</button>
                        </div>
                        <div>
                            <button type="button" class="btn btn-sm btn-outline-light me-2" data-bs-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-sm btn-cyan fw-bold text-dark" onclick="submitImportEditorCSV()"><i class="bi bi-upload"></i> 导入</button>
                        </div>
                    </div>
                </div>
            </div>`;
        document.body.appendChild(modal);
    }
    return bootstrap.Modal.getOrCreateInstance(modal);
}

function renderImportEditor({ columns, rows, file = null, mode = 'file' }) {
    ensureImportEditorModal();
    const safeColumns = columns.length ? columns : DEFAULT_SHIP_COLUMNS;
    document.getElementById('importEditorColumns').value = JSON.stringify(safeColumns);
    document.getElementById('importEditorMode').value = mode;
    const summary = document.getElementById('importFileSummary');
    if (file) {
        summary.innerHTML = `<div class="row g-2">
            <div class="col-md-4"><span class="summary-label">文件名</span><strong>${escapeHTML(file.name)}</strong></div>
            <div class="col-md-2"><span class="summary-label">大小</span><strong>${formatFileSize(file.size)}</strong></div>
            <div class="col-md-2"><span class="summary-label">列数</span><strong>${safeColumns.length}</strong></div>
            <div class="col-md-2"><span class="summary-label">数据行</span><strong>${rows.length}</strong></div>
            <div class="col-md-2"><span class="summary-label">模式</span><strong>文件导入</strong></div>
        </div>`;
    } else {
        summary.innerHTML = `<div class="row g-2">
            <div class="col-md-4"><span class="summary-label">文件来源</span><strong>手动输入</strong></div>
            <div class="col-md-2"><span class="summary-label">列数</span><strong>${safeColumns.length}</strong></div>
            <div class="col-md-2"><span class="summary-label">数据行</span><strong>${rows.length}</strong></div>
            <div class="col-md-4"><span class="summary-label">说明</span><strong>将生成临时 CSV 后导入</strong></div>
        </div>`;
    }
    document.querySelector('#importEditorTable thead').innerHTML = `<tr>${safeColumns.map(c => `<th>${escapeHTML(c)}</th>`).join('')}<th style="width:76px;">操作</th></tr>`;
    const tbody = document.querySelector('#importEditorTable tbody');
    tbody.innerHTML = '';
    const visibleRows = rows.length ? rows : [new Array(safeColumns.length).fill('')];
    visibleRows.forEach(row => addImportEditorRow(row));
}

function clearImportEditorRows() {
    const columns = JSON.parse(document.getElementById('importEditorColumns').value || '[]');
    const tbody = document.querySelector('#importEditorTable tbody');
    tbody.innerHTML = '';
    addImportEditorRow(new Array(columns.length).fill(''));
}

async function openFileImportModal() {
    const fileInput = document.getElementById('csvFile');
    const file = fileInput.files[0];
    if (!file) { alertMsg('请先选择一个 CSV 文件', true); return; }
    try {
        const text = await file.text();
        const parsedRows = parseCSVText(text.replace(/^﻿/, ''));
        const columns = parsedRows[0]?.filter(Boolean) || [];
        if (!columns.length) throw new Error('未读取到 CSV 表头，请检查文件格式');
        const rows = parsedRows.slice(1).filter(row => row.some(v => v !== ''));
        renderImportEditor({ columns, rows, file, mode: 'file' });
        ensureImportEditorModal().show();
    } catch (err) { alertMsg(err.message || 'CSV 文件解析失败', true); }
}

async function openManualInputModal() {
    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('manualInputModal'));
    modal.show();
}

function addManualShipRow() {
    const tbody = document.getElementById('manualShipTableBody');
    const row = document.createElement('tr');
    row.innerHTML = `
        <td><input type="text" class="form-control form-control-sm" placeholder="船舶名称" value=""></td>
        <td><input type="number" class="form-control form-control-sm" placeholder="船长" value="" min="1"></td>
        <td><input type="number" class="form-control form-control-sm" placeholder="货量" value="" min="0"></td>
        <td><input type="text" class="form-control form-control-sm" placeholder="HH:MM" value=""></td>
        <td><input type="number" class="form-control form-control-sm" placeholder="0.22" value="0.22" step="0.001"></td>
        <td><button type="button" class="btn btn-sm btn-outline-danger" onclick="removeManualShipRow(this)"><i class="bi bi-trash3"></i></button></td>
    `;
    tbody.appendChild(row);
}

function removeManualShipRow(button) {
    const tbody = document.getElementById('manualShipTableBody');
    if (tbody.children.length > 1) {
        button.closest('tr').remove();
    } else {
        alertMsg('至少保留一行数据', true);
    }
}

async function submitManualShips() {
    const tbody = document.getElementById('manualShipTableBody');
    const rows = Array.from(tbody.querySelectorAll('tr'));

    const data = rows.map(row => {
        const inputs = row.querySelectorAll('input');
        return {
            name: inputs[0].value.trim(),
            length: parseFloat(inputs[1].value) || 0,
            teu: parseFloat(inputs[2].value) || 0,
            arrivalTime: inputs[3].value.trim(),
            auxFuelCons: parseFloat(inputs[4].value) || 0.22
        };
    }).filter(d => d.name && d.length > 0 && d.teu > 0);

    if (data.length === 0) {
        alertMsg('请至少输入一条完整的船舶数据（名称、船长、货量都必填）', true);
        return;
    }

    const columns = ['name', 'length', 'teu', 'arrivalTime', 'auxFuelCons'];
    const csvRows = [columns, ...data.map(d => [d.name, d.length, d.teu, d.arrivalTime, d.auxFuelCons])];
    const csvText = csvRows.map(row => row.map(escapeCSVCell).join(',')).join('\n');

    const file = new File([csvText], 'manual_ships.csv', { type: 'text/csv;charset=utf-8' });
    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('/api/ships/import', { method: 'POST', body: formData });
        const result = await res.json();
        if (!res.ok) throw new Error(result.error || '导入失败');
        alertMsg(result.message || '船舶数据已成功导入');
        bootstrap.Modal.getOrCreateInstance(document.getElementById('manualInputModal')).hide();
        refreshShipPool();
    } catch (err) {
        alertMsg(err.message, true);
    }
}

async function submitImportEditorCSV() {
    const columns = JSON.parse(document.getElementById('importEditorColumns').value || '[]');
    const rows = getImportEditorRows().filter(row => row.some(v => v !== ''));
    if (!columns.length) { alertMsg('缺少 CSV 表头，无法导入', true); return; }
    if (!rows.length) { alertMsg('请至少保留一行有效船舶数据', true); return; }
    const invalidIndex = rows.findIndex(row => row.length !== columns.length);
    if (invalidIndex !== -1) { alertMsg(`第 ${invalidIndex + 1} 行列数与表头不一致`, true); return; }
    const csvText = [columns, ...rows].map(row => row.map(escapeCSVCell).join(',')).join('\n');
    const mode = document.getElementById('importEditorMode').value || 'file';
    const filename = mode === 'manual' ? 'manual_ship_data.csv' : 'edited_ship_data.csv';
    const file = new File([csvText], filename, { type: 'text/csv;charset=utf-8' });
    const formData = new FormData();
    formData.append('file', file);
    try {
        const res = await fetch('/api/ships/import', { method: 'POST', body: formData });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || '数据导入失败');
        alertMsg(data.message || '船舶数据已导入');
        bootstrap.Modal.getOrCreateInstance(document.getElementById('importEditorModal')).hide();
        document.getElementById('csvFile').value = '';
        updateSelectedFileInfo();
        refreshShipPool();
    } catch (err) { alertMsg(err.message, true); }
}

async function uploadCSV() { await openFileImportModal(); }

async function clearPool() {
    const res = await fetch('/api/ships/clear', { method: 'POST' });
    const data = await res.json();
    alertMsg(data.message);
    refreshShipPool();
}

async function loadBerthConfigOverview() {
    try {
        const res = await fetch('/api/port-config');
        if (!res.ok) return;
        const configs = await res.json();
        const activeConfig = configs.find(c => c.isActive);

        if (activeConfig) {
            document.getElementById('configTotalBerths').textContent = activeConfig.totalBerths;
            document.getElementById('configTotalQcs').textContent = activeConfig.totalQcs;
            document.getElementById('configQcEff').textContent = activeConfig.qcEfficiency + ' TEU/h';
            document.getElementById('configStatus').textContent = activeConfig.name;
        } else {
            document.getElementById('configTotalBerths').textContent = '10';
            document.getElementById('configTotalQcs').textContent = '15';
            document.getElementById('configQcEff').textContent = '48 TEU/h';
            document.getElementById('configStatus').textContent = '默认配置';
        }
    } catch (e) {
        console.error('Failed to load berth config:', e);
    }
}

// ============================================================
// 智能推荐参数
// ============================================================
async function recommendParams() {
    try {
        const res = await fetch('/api/ships');
        const ships = await res.json();
        const shipCount = ships.length;

        if (shipCount === 0) {
            alertMsg('请先导入船舶数据再获取推荐参数', true);
            return;
        }

        const configRes = await fetch('/api/port-config');
        const configs = await configRes.json();
        const activeConfig = configs.find(c => c.isActive);
        const totalBerths = activeConfig ? activeConfig.totalBerths : 10;

        let popSize, maxIter;
        if (shipCount <= 5) {
            popSize = 40;
            maxIter = 100;
        } else if (shipCount <= 10) {
            popSize = 60;
            maxIter = 150;
        } else if (shipCount <= 20) {
            popSize = 80;
            maxIter = 200;
        } else if (shipCount <= 40) {
            popSize = 100;
            maxIter = 300;
        } else {
            popSize = 120;
            maxIter = 400;
        }

        if (totalBerths > 15) {
            popSize = Math.round(popSize * 1.3);
            maxIter = Math.round(maxIter * 1.2);
        }

        document.getElementById('popSize').value = popSize;
        document.getElementById('maxIter').value = maxIter;

        const estTime = estimateTime(popSize, maxIter, shipCount);
        const info = document.getElementById('paramRecommendInfo');
        info.style.display = '';
        info.innerHTML = `<i class="bi bi-lightbulb me-1"></i>已根据 <strong>${shipCount}</strong> 艘船 / <strong>${totalBerths}</strong> 泊位推荐参数，预计耗时 <strong>${estTime}</strong>`;
    } catch (e) {
        alertMsg('获取推荐参数失败', true);
    }
}

function estimateTime(popSize, maxIter, shipCount) {
    const baseMs = 0.15 * popSize * maxIter * Math.max(1, shipCount);
    const seconds = Math.max(10, Math.round(baseMs / 200));
    if (seconds < 60) return `${seconds} 秒`;
    const min = Math.floor(seconds / 60);
    const sec = seconds % 60;
    return sec > 0 ? `${min} 分 ${sec} 秒` : `${min} 分钟`;
}

// ============================================================
// NSGA-II 调度运行
// ============================================================
async function executeNSGA() {
    const runBtn = document.getElementById('runBtn');
    runBtn.disabled = true;
    runBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> 进化演算中...';

    const popSize = parseInt(document.getElementById('popSize').value) || 60;
    const maxIter = parseInt(document.getElementById('maxIter').value) || 200;

    const payload = {
        w_co2: parseFloat(document.getElementById('wCo2').value),
        w_time: parseFloat(document.getElementById('wTime').value),
        w_cost: parseFloat(document.getElementById('wCost').value),
        pop_size: popSize,
        max_iter: maxIter
    };

    const progressDiv = document.getElementById('runProgress');
    const progressBar = document.getElementById('runProgressBar');
    const progressText = document.getElementById('runProgressText');
    progressDiv.style.display = '';

    let shipCount = 1;
    try {
        const shipRes = await fetch('/api/ships');
        const shipData = await shipRes.json();
        shipCount = shipData.length || 1;
    } catch (e) {}

    const estMs =0.15 * popSize * maxIter * Math.max(1, shipCount);
    const estSeconds = Math.max(3, Math.round(estMs / 200));
    const estLabel = estimateTime(popSize, maxIter, shipCount);
    progressText.textContent = `预计耗时 ${estLabel}，请稍候...`;

    const startTime = Date.now();
    const progressInterval = setInterval(() => {
        const elapsed = (Date.now() - startTime) / 1000;
        const pct = Math.min(95, (elapsed / estSeconds) * 100);
        progressBar.style.width = pct + '%';
        const remaining = Math.max(0, estSeconds - Math.round(elapsed));
        if (remaining > 0) {
            progressText.textContent = `演算进行中... 预计剩余 ${remaining} 秒`;
        } else {
            progressText.textContent = '即将完成，正在整理结果...';
        }
    }, 500);

    try {
        const res = await fetch('/api/schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error);

        currentSolutions = data.solutions;
        currentPortConfig = data.portConfig || null;
        alertMsg(data.info);

        renderParetoGrid();
        const recommended = currentSolutions.find(s => s.isRecommended) || currentSolutions[0];
        if (recommended) mountSolution(recommended.id);
    } catch (err) {
        alertMsg(err.message, true);
    } finally {
        clearInterval(progressInterval);
        progressBar.style.width = '100%';
        progressText.textContent = '计算完成';
        setTimeout(() => { progressDiv.style.display = 'none'; progressBar.style.width = '0%'; }, 2000);
        runBtn.disabled = false;
        runBtn.innerHTML = '<i class="bi bi-lightning-charge-fill"></i> <span data-i18n="schedule.runAlgorithm">启动多目标寻优演化</span>';
    }
}

// ============================================================
// Pareto方案网格渲染
// ============================================================
function renderParetoGrid() {
    const row = document.getElementById('paretoRow');
    const badge = document.getElementById('paretoCountBadge');
    if (!currentSolutions.length) {
        row.innerHTML = '<div class="text-muted text-center w-100 py-4">未检索到边界非支配解</div>';
        badge.textContent = '0 个方案';
        return;
    }
    badge.textContent = `${currentSolutions.length} 个方案`;

    row.innerHTML = currentSolutions.map(s => `
        <div class="pareto-card ${s.isRecommended ? 'recommended' : ''}" id="pcard-${s.id}" onclick="mountSolution(${s.id})">
            <div class="pareto-card-title">策略 #${s.id + 1}</div>
            <div class="pareto-card-metrics">
                <div class="pareto-metric-row">
                    <span class="pareto-metric-label">CO₂排放</span>
                    <span class="pareto-metric-value co2">${s.co2.toFixed(1)} kg</span>
                </div>
                <div class="pareto-metric-row">
                    <span class="pareto-metric-label">在港停留</span>
                    <span class="pareto-metric-value time">${s.stayTime.toFixed(2)} h</span>
                </div>
                <div class="pareto-metric-row">
                    <span class="pareto-metric-label">调度成本</span>
                    <span class="pareto-metric-value cost">¥${s.cost.toFixed(0)}</span>
                </div>
            </div>
        </div>
    `).join('');
}

// ============================================================
// 装载方案
// ============================================================
function mountSolution(id) {
    activeSolutionId = id;
    document.querySelectorAll('.pareto-card').forEach(c => c.classList.remove('active'));
    const card = document.getElementById(`pcard-${id}`);
    if (card) card.classList.add('active');

    const sol = currentSolutions.find(s => s.id === id);
    if (!sol) return;

    document.getElementById('kpiCo2').innerHTML = `${sol.co2.toLocaleString()} <span class="fs-6">kg</span>`;
    document.getElementById('kpiTime').innerHTML = `${sol.stayTime.toFixed(2)} <span class="fs-6">小时</span>`;
    document.getElementById('kpiCost').innerHTML = `¥${sol.cost.toLocaleString()} <span class="fs-6">元</span>`;
    document.getElementById('activeSolTag').innerText = `当前: 策略 #${id + 1}${sol.isRecommended ? ' (推荐)' : ''}`;

    renderMetrics(sol);
    renderGantt(sol.assignments);
    renderDetailTable(sol.assignments);
}

// ============================================================
// 方案运营指标
// ============================================================
function renderMetrics(sol) {
    const card = document.getElementById('metricsCard');
    const row = document.getElementById('metricsRow');
    const m = sol.metrics || {};
    card.style.display = '';

    const items = [
        { label: '船舶数', value: m.shipCount || sol.assignments.length },
        { label: '启用泊位', value: m.berthsUsed || '-' },
        { label: '平均等待', value: `${m.avgWaitMin || 0} min` },
        { label: '最长等待', value: `${m.maxWaitMin || 0} min` },
        { label: '平均在港', value: `${m.avgStayHours || '-'} h` },
        { label: '完工时刻', value: `${m.makespanHours || '-'} h` },
    ];

    row.innerHTML = items.map(it => `
        <div class="col-lg-2 col-md-4 col-6">
            <div class="metric-mini">
                <div class="metric-mini-label">${it.label}</div>
                <div class="metric-mini-value">${it.value}</div>
            </div>
        </div>
    `).join('');
}

// ============================================================
// 甘特图渲染
// ============================================================
function renderGantt(assignments) {
    const container = document.getElementById('ganttContainer');
    if (!assignments || !assignments.length) {
        container.innerHTML = '<div class="text-muted text-center py-4">无分配数据</div>';
        return;
    }

    const berthMap = {};
    assignments.forEach(a => {
        const key = a.berthName || `B${String(a.berthIndex).padStart(2, '0')}`;
        if (!berthMap[key]) berthMap[key] = [];
        berthMap[key].push(a);
    });

    const berths = Object.keys(berthMap).sort((a, b) => {
        const na = parseInt(a.replace(/\D/g, '')) || 0;
        const nb = parseInt(b.replace(/\D/g, '')) || 0;
        return na - nb;
    });

    const allStarts = assignments.map(a => a.startHours);
    const allEnds = assignments.map(a => a.endHours);
    const minTime = Math.floor(Math.min(...allStarts));
    const maxTime = Math.ceil(Math.max(...allEnds)) + 0.5;
    const timeSpan = maxTime - minTime || 1;

    const COLORS = [
        '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
        '#06b6d4', '#ec4899', '#14b8a6', '#f97316', '#6366f1',
        '#84cc16', '#a855f7', '#22d3ee', '#fb923c', '#4ade80'
    ];

    const timeLabels = [];
    for (let t = minTime; t <= maxTime; t++) {
        timeLabels.push(`${String(t % 24).padStart(2, '0')}:00`);
    }

    let html = '<div class="gantt-chart">';

    // header
    html += '<div class="gantt-header">';
    html += '<div class="gantt-berth-label">泊位</div>';
    html += '<div class="gantt-timeline">';
    timeLabels.forEach(t => { html += `<span>${t}</span>`; });
    html += '</div></div>';

    // rows
    berths.forEach(berthName => {
        const ships = berthMap[berthName];
        html += '<div class="gantt-row">';
        html += `<div class="gantt-row-label">${berthName}</div>`;
        html += '<div class="gantt-row-track">';

        ships.forEach(a => {
            const left = ((a.startHours - minTime) / timeSpan) * 100;
            const width = ((a.endHours - a.startHours) / timeSpan) * 100;
            const colorIdx = (assignments.indexOf(a)) % COLORS.length;
            const bg = COLORS[colorIdx];

            html += `<div class="gantt-bar" style="left:${left}%;width:${Math.max(width, 2)}%;background:${bg};"
                          title="${a.shipName}\n靠泊: ${a.startTimeStr}\n离泊: ${a.endTimeStr}\n岸桥: QC${String(a.qcStart).padStart(2,'0')}-QC${String(a.qcEnd).padStart(2,'0')}\n等待: ${a.waitTimeMin}分钟">
                        <span class="bar-label">${a.shipName}</span>
                        <span class="bar-time">${a.startTimeStr}-${a.endTimeStr}</span>
                    </div>`;
        });

        html += '</div></div>';
    });

    html += '</div>';
    container.innerHTML = html;
}

// ============================================================
// 详细表格
// ============================================================
function renderDetailTable(assignments) {
    const tbody = document.getElementById('tableBody');
    if (!assignments || !assignments.length) {
        tbody.innerHTML = '<tr><td colspan="11" class="py-4 text-muted">无分配数据</td></tr>';
        return;
    }

    tbody.innerHTML = assignments.map(a => {
        const waitClass = a.waitTimeMin === 0 ? 'wait-zero' : (a.waitTimeMin > 30 ? 'wait-high' : '');
        return `
        <tr>
            <td class="ship-name-cell">${a.shipName}</td>
            <td>${a.teu}</td>
            <td>${a.length} m</td>
            <td><span class="berth-badge">${a.berthName}</span></td>
            <td><strong>${a.qcCount}</strong> 台</td>
            <td class="qc-badge">QC${String(a.qcStart).padStart(2,'0')} ~ QC${String(a.qcEnd).padStart(2,'0')}</td>
            <td>${a.startTimeStr}</td>
            <td>${a.endTimeStr}</td>
            <td class="${waitClass}">${a.waitTimeMin} min</td>
            <td>${a.workTimeMin} min</td>
            <td>${(a.shipCo2 || 0).toFixed(1)} kg</td>
        </tr>`;
    }).join('');
}

// ============================================================
// 页面初始化
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    refreshShipPool();
    loadBerthConfigOverview();
});
