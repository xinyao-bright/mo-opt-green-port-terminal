let currentSolutions = [];
let activeSolutionId = null;
let currentPortConfig = null;

function alertMsg(text, isError = false) {
    const alertBox = document.createElement('div');
    alertBox.className = 'alert app-toast ' + (isError ? 'alert-danger' : 'alert-success');
    alertBox.setAttribute('role', isError ? 'alert' : 'status');
    alertBox.textContent = text;
    document.body.appendChild(alertBox);
    setTimeout(() => alertBox.remove(), 5000);
}

let shipPool = [];
let resultsSnapshot = {};
function resetResults() {
    currentSolutions = [];
    activeSolutionId = null;
    for (const [id, html] of Object.entries(resultsSnapshot)) document.getElementById(id).innerHTML = html;
    document.getElementById('metricsCard').style.display = 'none';
    document.getElementById('exportResultBtn').disabled = true;
}
function renderShipPool() {
    const box = document.getElementById('shipBox');
    const query = document.getElementById('shipSearch').value.trim().toLocaleLowerCase();
    const ships = shipPool.filter(s => String(s.name).toLocaleLowerCase().includes(query));
    document.getElementById('shipCountBadge').textContent = shipPool.length + ' 艘';
    document.getElementById('workspaceStatus').textContent = shipPool.length ? '调度就绪 · ' + shipPool.length + ' 艘船舶' : '等待船舶数据';
    if (!ships.length) {
        box.innerHTML = '<div class="empty-state compact-empty"><span class="empty-icon"><i class="bi bi-box-seam"></i></span><strong>' + (query ? '未找到匹配船舶' : '船舶池为空') + '</strong><p>' + (query ? '尝试其他名称或清除搜索条件' : '导入数据，开始规划本次调度') + '</p></div>';
        return;
    }
    box.innerHTML = ships.map(s => `<div class="ship-mini-card"><span class="ship-mini-icon"><i class="bi bi-box-seam"></i></span><div class="ship-mini-info"><strong class="ship-mini-name" title="${escapeHTML(s.name)}">${escapeHTML(s.name)}</strong><div class="ship-mini-meta">${escapeHTML(s.teu)} TEU <span>·</span> ${escapeHTML(s.length)} m</div></div><div class="ship-mini-arrival"><small>ETA</small>${escapeHTML(s.arrivalTime)}</div></div>`).join('');
}
async function refreshShipPool() {
    try {
        const res = await fetch('/api/ships');
        if (!res.ok || res.redirected) throw new Error('船舶数据加载失败，请重新登录或刷新页面');
        const data = await res.json();
        if (JSON.stringify(data) !== JSON.stringify(shipPool) && currentSolutions.length) resetResults();
        shipPool = data;
        renderShipPool();
    } catch (e) {
        document.getElementById('shipBox').innerHTML = '<div class="empty-state compact-empty"><strong>船舶加载失败</strong><p>请检查连接后刷新页面重试</p></div>';
        document.getElementById('workspaceStatus').textContent = '数据连接异常';
        alertMsg(e.message, true);
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
        const columns = (parsedRows[0] || []).map((column, index) => column || (index === 0 ? 'name' : 'column_' + (index + 1)));
        if (!columns.length) throw new Error('未读取到 CSV 表头，请检查文件格式');
        const rows = parsedRows.slice(1).filter(row => row.some(v => v !== ''));
        if (rows.some(row => row.length !== columns.length)) throw new Error('CSV 数据行与表头列数不一致，请检查文件格式');
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
        await refreshShipPool();
        bootstrap.Modal.getOrCreateInstance(document.getElementById('manualInputModal')).hide();
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
        await refreshShipPool();
        bootstrap.Modal.getOrCreateInstance(document.getElementById('importEditorModal')).hide();
        document.getElementById('csvFile').value = '';
        updateSelectedFileInfo();
    } catch (err) { alertMsg(err.message, true); }
}

async function uploadCSV() { await openFileImportModal(); }

async function clearPool() {
    if (!shipPool.length) { alertMsg('船舶池已为空'); return; }
    if (!confirm('确定清空当前待调度船舶？已保存的历史方案仍会保留。')) return;
    try {
        const res = await fetch('/api/ships/clear', { method: 'POST' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || '清空失败');
        alertMsg(data.message);
        await refreshShipPool();
    } catch (error) { alertMsg(error.message, true); }
}

async function loadBerthConfigOverview() {
    try {
        const res = await fetch('/api/port-config');
        if (!res.ok || res.redirected) throw new Error('配置加载失败');
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
        document.getElementById('configStatus').textContent = '配置加载失败';
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
    if (!shipPool.length) { alertMsg('请先导入至少一艘船舶，再开始调度', true); return; }
    const popInput = document.getElementById('popSize');
    const iterInput = document.getElementById('maxIter');
    if (!popInput.reportValidity() || !iterInput.reportValidity()) return;
    const payload = {
        w_co2: Number(document.getElementById('wCo2').value),
        w_time: Number(document.getElementById('wTime').value),
        w_cost: Number(document.getElementById('wCost').value),
        pop_size: Number(popInput.value),
        max_iter: Number(iterInput.value),
        objectiveParameters: {
            gridEmissionFactor: Number(document.getElementById('gridFactor').value),
            electricityPrice: Number(document.getElementById('electricityPrice').value),
            qcCoordinationCost: Number(document.getElementById('coordinationCost').value),
            serviceAuxRatio: Number(document.getElementById('serviceAuxRatio').value)
        }
    };
    if (!payload.pop_size || !payload.max_iter) { alertMsg('请填写种群数量与迭代次数', true); return; }
    if (payload.w_co2 + payload.w_time + payload.w_cost <= 0) { alertMsg('请至少为一个优化目标设置大于 0 的权重', true); return; }
    if (['gridFactor','electricityPrice','coordinationCost','serviceAuxRatio'].some(id => !document.getElementById(id).reportValidity())) return;
    const runBtn = document.getElementById('runBtn');
    const progressDiv = document.getElementById('runProgress');
    const progressBar = document.getElementById('runProgressBar');
    const progressText = document.getElementById('runProgressText');
    runBtn.disabled = true;
    runBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> 正在生成方案';
    progressDiv.style.display = '';
    progressBar.style.width = '15%';
    progressText.textContent = '正在计算，请稍候（此进度为估算）';
    document.getElementById('workspaceStatus').textContent = '正在优化调度方案';
    const startTime = Date.now();
    const progressInterval = setInterval(() => {
        const elapsed = Math.round((Date.now() - startTime) / 1000);
        progressBar.style.width = Math.min(90, 15 + 60 * (1 - Math.exp(-elapsed / 20))) + '%';
        progressText.textContent = '已计算 ' + elapsed + ' 秒 · 正在搜索更优方案';
    }, 700);
    let succeeded = false;
    try {
        const res = await fetch('/api/schedule', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (res.redirected) throw new Error('登录已过期，请重新登录');
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || '调度计算失败');
        currentSolutions = data.solutions || [];
        currentPortConfig = data.portConfig || null;
        renderParetoGrid();
        const recommended = currentSolutions.find(s => s.isRecommended) || currentSolutions[0];
        if (recommended) mountSolution(recommended.id);
        succeeded = true;
        alertMsg(data.info || '调度方案已生成');
        document.getElementById('workspaceStatus').textContent = '已生成 ' + currentSolutions.length + ' 个调度方案';
    } catch (err) {
        alertMsg(err.message, true);
        document.getElementById('workspaceStatus').textContent = '调度未完成 · 可重试';
    } finally {
        clearInterval(progressInterval);
        progressBar.style.width = succeeded ? '100%' : '0%';
        progressText.textContent = succeeded ? '计算完成，已选择推荐方案' : '本次计算未完成，请检查提示后重试';
        runBtn.disabled = false;
        runBtn.innerHTML = '<i class="bi bi-play-fill"></i> 开始智能调度';
    }
}

// ============================================================
// Pareto方案网格渲染
// ============================================================
function renderParetoGrid() {
    const row = document.getElementById('paretoRow');
    document.getElementById('paretoCountBadge').textContent = currentSolutions.length + ' 个方案';
    if (!currentSolutions.length) { row.innerHTML = '<div class="solution-empty">未找到可用方案，请检查船舶与泊位配置。</div>'; return; }
    row.innerHTML = currentSolutions.map(s => `<button type="button" class="pareto-card ${s.isRecommended ? 'recommended' : ''}" id="pcard-${s.id}" onclick="mountSolution(${s.id})" aria-pressed="false"><div class="pareto-card-title">方案 ${String(s.id + 1).padStart(2,'0')}${s.isRecommended ? '<span class="recommend-tag">推荐</span>' : ''}<span class="solution-radio"></span></div><div class="pareto-card-metrics"><div class="pareto-metric-row"><span class="pareto-metric-label">碳排放</span><span class="pareto-metric-value co2">${s.co2.toLocaleString(undefined,{maximumFractionDigits:1})} kg</span></div><div class="pareto-metric-row"><span class="pareto-metric-label">在港时间</span><span class="pareto-metric-value">${s.stayTime.toFixed(2)} h</span></div><div class="pareto-metric-row"><span class="pareto-metric-label">调度成本</span><span class="pareto-metric-value">¥ ${s.cost.toLocaleString(undefined,{maximumFractionDigits:0})}</span></div></div></button>`).join('');
}

// ============================================================
// 装载方案
// ============================================================
function mountSolution(id) {
    activeSolutionId = id;
    document.querySelectorAll('.pareto-card').forEach(c => { c.classList.remove('active'); c.setAttribute('aria-pressed','false'); });
    const card = document.getElementById(`pcard-${id}`);
    if (card) { card.classList.add('active'); card.setAttribute('aria-pressed','true'); }

    const sol = currentSolutions.find(s => s.id === id);
    if (!sol) return;

    const setMetric = (id, value, unit) => {
        const element = document.getElementById(id);
        const large = Math.abs(value) >= 10000;
        const display = (large ? value / 10000 : value).toLocaleString('zh-CN', {maximumFractionDigits:2});
        element.innerHTML = display + ' <span>' + (large ? '万 ' : '') + unit + '</span>';
        element.title = value.toLocaleString('zh-CN', {maximumFractionDigits:2}) + ' ' + unit;
        element.setAttribute('aria-label', element.title);
    };
    setMetric('kpiCo2', sol.co2, 'kg');
    setMetric('kpiTime', sol.stayTime, '小时');
    setMetric('kpiCost', sol.cost, '元');
    document.getElementById('activeSolTag').textContent = '当前方案 ' + String(id + 1).padStart(2,'0') + (sol.isRecommended ? ' · 推荐' : '');

    document.getElementById('exportResultBtn').disabled = false;
    const breakdown = sol.objectiveBreakdown || {};
    const number = value => Number(value || 0).toLocaleString('zh-CN', {maximumFractionDigits: 2});
    document.getElementById('objectiveExplanation').style.display = '';
    document.getElementById('objectiveExplanationBody').innerHTML = `<p>碳排放 = 等待辅机 <strong>${number(breakdown.waitingCarbon)}</strong> + 作业辅机 <strong>${number(breakdown.serviceCarbon)}</strong> + 岸桥用电间接排放 <strong>${number(breakdown.electricityCarbon)}</strong> kg CO₂。</p><p>成本 = 货物等待 <strong>${number(breakdown.waitingCost)}</strong> + 岸桥运行 <strong>${number(breakdown.qcOperatingCost)}</strong> + 电费 <strong>${number(breakdown.electricityCost)}</strong> + 多机协同 <strong>${number(breakdown.coordinationCost)}</strong> 元。</p><p class="settings-caption">推荐依据：三目标在本次候选集内归一化后，计算加权理想点距离（越小越优），当前得分 ${number(sol.recommendation?.score)}。仅返回通过约束校验的方案。核算边界为辅机与岸桥，非全港碳盘查；演示单价需校准。</p>`;
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
    if (!assignments || !assignments.length) { container.innerHTML = '<div class="empty-state">暂无泊位分配</div>'; return; }
    const berthMap = new Map();
    assignments.forEach(a => { const key = a.berthName || 'B' + a.berthIndex; if (!berthMap.has(key)) berthMap.set(key, []); berthMap.get(key).push(a); });
    const berths = [...berthMap.keys()].sort((a,b) => a.localeCompare(b, undefined, { numeric:true }));
    const minTime = Math.floor(Math.min(...assignments.map(a => a.startHours)));
    const maxTime = Math.ceil(Math.max(...assignments.map(a => a.endHours)));
    const timeSpan = Math.max(1, maxTime - minTime);
    const colors = Array.from({length:8}, (_, index) => 'var(--gantt-color-' + (index + 1) + ')');
    let html = '<div class="gantt-chart"><div class="gantt-header"><div class="gantt-berth-label">泊位 / 时间</div><div class="gantt-timeline">';
    for (let i = 0; i <= 5; i++) {
        const time = minTime + timeSpan * i / 5;
        const minutes = Math.round(time * 60);
        const hour = Math.floor(minutes / 60);
        const label = (hour >= 24 ? '+' + Math.floor(hour / 24) + 'd ' : '') + String(hour % 24).padStart(2,'0') + ':' + String(minutes % 60).padStart(2,'0');
        html += '<span style="left:' + i * 20 + '%">' + label + '</span>';
    }
    html += '</div></div>';
    berths.forEach(name => {
        html += '<div class="gantt-row"><div class="gantt-row-label" title="' + escapeHTML(name) + '">' + escapeHTML(name) + '</div><div class="gantt-row-track">';
        berthMap.get(name).forEach(a => {
            const left = (a.startHours - minTime) / timeSpan * 100;
            const width = (a.endHours - a.startHours) / timeSpan * 100;
            const tooltip = a.shipName + '\n靠泊：' + a.startTimeStr + '\n离泊：' + a.endTimeStr + '\n岸桥：QC' + a.qcStart + '–QC' + a.qcEnd + '\n等待：' + a.waitTimeMin + ' 分钟';
            html += '<div class="gantt-bar" tabindex="0" aria-label="' + escapeHTML(tooltip) + '" title="' + escapeHTML(tooltip) + '" style="left:' + left + '%;width:' + Math.max(width,0.4) + '%;background:' + colors[assignments.indexOf(a) % colors.length] + '"><span class="bar-label">' + escapeHTML(a.shipName) + '</span><span class="bar-time">' + escapeHTML(a.startTimeStr) + ' – ' + escapeHTML(a.endTimeStr) + '</span></div>';
        });
        html += '</div></div>';
    });
    container.innerHTML = html + '</div>';
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
            <td class="ship-name-cell">${escapeHTML(a.shipName)}</td>
            <td>${a.teu}</td>
            <td>${a.length} m</td>
            <td><span class="berth-badge">${escapeHTML(a.berthName)}</span></td>
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
    ['paretoRow','paretoCountBadge','kpiCo2','kpiTime','kpiCost','activeSolTag','ganttContainer','tableBody'].forEach(id => { resultsSnapshot[id] = document.getElementById(id).innerHTML; });
    document.getElementById('shipSearch').addEventListener('input', renderShipPool);
    refreshShipPool();
    loadBerthConfigOverview();
});

function exportCurrentSolution() {
    const sol = currentSolutions.find(s => s.id === activeSolutionId);
    if (!sol) return;
    const columns = ['船舶名称','货量(TEU)','船长(m)','泊位','岸桥数量','岸桥起始','岸桥结束','靠泊时间','离泊时间','等待(min)','作业(min)','碳排放(kg)'];
    const safeCell = value => {
        const text = String(value ?? '');
        return escapeCSVCell(/^[=+@\-]/.test(text) ? "'" + text : text);
    };
    const rows = sol.assignments.map(a => [a.shipName,a.teu,a.length,a.berthName,a.qcCount,a.qcStart,a.qcEnd,a.startTimeStr,a.endTimeStr,a.waitTimeMin,a.workTimeMin,a.shipCo2]);
    const csv = '\uFEFF' + [columns,...rows].map(row => row.map(safeCell).join(',')).join('\r\n');
    const url = URL.createObjectURL(new Blob([csv], {type:'text/csv;charset=utf-8;'}));
    const link = document.createElement('a');
    link.href = url; link.download = 'EcoPort_调度方案_' + (sol.id + 1) + '.csv';
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    alertMsg('已导出当前方案的执行明细');
}
