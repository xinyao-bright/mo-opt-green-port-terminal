let historyData = [];
let historyLoaded = false;
let historyRequestId = 0;
let detailRequestId = 0;
const deletingHistoryIds = new Set();

function escapeHistory(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
}

function historyNumber(value, digits = 2) {
    if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return '—';
    return Number(value).toLocaleString(typeof i18n !== 'undefined' ? i18n.locale : 'zh-CN', {minimumFractionDigits: digits, maximumFractionDigits: digits});
}

function historyDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleString(typeof i18n !== 'undefined' ? i18n.locale : 'zh-CN', {year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'});
}

function historyNotice(message, type = 'danger') {
    const notice = document.getElementById('historyNotice');
    notice.textContent = message;
    notice.className = `alert alert-${type} mx-4`;
}

function historyExportUrl(historyId, solutionId) {
    const url = `/api/history/${encodeURIComponent(historyId)}/export`;
    return solutionId === undefined ? url : `${url}?solution=${encodeURIComponent(solutionId)}`;
}

function validHistoryDates() {
    const start = document.getElementById('filterStartDate').value;
    const end = document.getElementById('filterEndDate').value;
    if (start && end && start > end) {
        historyNotice('开始日期不能晚于结束日期，请调整日期范围。', 'warning');
        return false;
    }
    return true;
}

async function loadHistory() {
    if (!validHistoryDates()) return;
    const requestId = ++historyRequestId;
    document.getElementById('historyNotice').classList.add('d-none');
    document.getElementById('historyList').innerHTML = '<div class="page-empty"><div class="spinner-border spinner-border-sm" role="status"></div><p>正在加载调度记录…</p></div>';
    try {
        const response = await fetch('/api/history');
        if (!response.ok) throw new Error('暂时无法读取调度记录，请稍后重试。');
        const result = await response.json();
        if (!Array.isArray(result)) throw new Error('调度记录数据格式异常，请重新加载。');
        if (requestId !== historyRequestId) return;
        historyData = result;
        historyLoaded = true;
        document.getElementById('historyCount').textContent = historyNumber(result.length, 0);
        document.getElementById('historyShipCount').textContent = historyNumber(result.reduce((sum, item) => sum + (item.shipsData?.length || 0), 0), 0);
        document.getElementById('historySolutionCount').textContent = historyNumber(result.reduce((sum, item) => sum + (item.solutions?.length || 0), 0), 0);
        renderHistory();
    } catch (error) {
        if (requestId !== historyRequestId) return;
        document.getElementById('historyResultLabel').textContent = '读取失败';
        document.getElementById('historyList').innerHTML = '<div class="page-empty"><i class="bi bi-wifi-off"></i><h3>暂时无法加载记录</h3><p>检查网络连接后，再试一次。</p><button class="btn btn-outline-primary btn-sm" onclick="loadHistory()">重新加载</button></div>';
        historyNotice(error.message || '网络连接异常，请重新加载。');
    }
}

function historyMetrics(solution) {
    return `<div class="history-metrics">
        <div class="history-metric"><span class="history-metric-label"><i class="bi bi-cloud"></i>CO₂ 排放</span><strong>${historyNumber(solution.co2)}</strong><small>kg</small></div>
        <div class="history-metric"><span class="history-metric-label"><i class="bi bi-clock"></i>在港停留时间</span><strong>${historyNumber(solution.stayTime)}</strong><small>小时</small></div>
        <div class="history-metric"><span class="history-metric-label"><i class="bi bi-wallet2"></i>联合调度成本</span><strong>${historyNumber(solution.cost)}</strong><small>元</small></div>
    </div>`;
}

function renderHistory() {
    if (!validHistoryDates()) return;
    const startValue = document.getElementById('filterStartDate').value;
    const endValue = document.getElementById('filterEndDate').value;
    const start = startValue ? new Date(`${startValue}T00:00:00`) : null;
    const end = endValue ? new Date(`${endValue}T23:59:59.999`) : null;
    const filtered = historyData.filter(item => {
        const date = new Date(item.createdAt);
        return (!start || date >= start) && (!end || date <= end);
    });
    const container = document.getElementById('historyList');
    document.getElementById('historyResultLabel').textContent = start || end ? `筛选到 ${filtered.length} 条记录，共 ${historyData.length} 条` : `共 ${historyData.length} 条历史记录`;
    if (!filtered.length) {
        container.innerHTML = historyData.length
            ? '<div class="page-empty"><i class="bi bi-calendar2-range"></i><h3>该日期范围内暂无记录</h3><p>试着扩大日期范围，或查看全部调度记录。</p><button class="btn btn-sm btn-outline-primary" onclick="resetFilters()">查看全部记录</button></div>'
            : '<div class="page-empty"><i class="bi bi-clock-history"></i><h3>第一份调度记录，即将从这里开始</h3><p>完成一次智能调度后，方案和关键指标会自动保存在这里。</p><a class="btn btn-primary" href="/">前往调度工作台 <i class="bi bi-arrow-right"></i></a></div>';
        return;
    }
    container.innerHTML = filtered.map(item => {
        const solutions = Array.isArray(item.solutions) ? item.solutions : [];
        const best = solutions.find(solution => solution.isRecommended) || solutions[0];
        const weights = item.weights || {};
        return `<article class="history-item">
            <div class="history-item-top">
                <div class="history-record-title"><div class="history-record-icon"><i class="bi bi-file-earmark-bar-graph"></i></div><div><h3>调度记录 #${escapeHistory(item.id)}</h3><p>${escapeHistory(historyDate(item.createdAt))} · ${item.shipsData?.length || 0} 艘船舶 · ${solutions.length} 个方案</p></div></div>
                <span class="history-config-tag"><i class="bi bi-bounding-box"></i> ${escapeHistory(item.configName || '默认配置')}</span>
            </div>
            <p class="text-muted small">${best?.objectiveModel === 'physical-v2' ? '目标核算 physical-v2 · 含电网因子与成本拆解' : '历史口径 legacy-v1 · 指标请勿与新版直接比较'}</p>
            ${best ? historyMetrics(best) : '<p class="text-muted small">该记录没有可用的方案指标。</p>'}
            <div class="history-item-footer">
                <div class="history-weights">${best ? '推荐方案 · ' : ''}决策权重：碳排放 ${historyNumber(weights.w_co2)} / 时间 ${historyNumber(weights.w_time)} / 成本 ${historyNumber(weights.w_cost)}</div>
                <div class="history-actions">
                    <button class="btn btn-sm btn-outline-primary" data-view-history="${escapeHistory(item.id)}"><i class="bi bi-eye"></i> 查看详情</button>
                    ${best ? `<a href="${historyExportUrl(item.id)}" class="btn btn-sm btn-light"><i class="bi bi-download"></i> 导出推荐方案</a>` : ''}
                    <button class="btn btn-sm btn-outline-danger" data-delete-history="${escapeHistory(item.id)}" title="删除这条调度记录" aria-label="删除调度记录 ${escapeHistory(item.id)}"><i class="bi bi-trash3"></i></button>
                </div>
            </div>
            ${solutions.length > 1 ? `<details class="pareto-disclosure"><summary>展开全部 ${solutions.length} 个 Pareto 方案对比</summary><div class="table-responsive"><table class="table table-sm"><thead><tr><th>方案</th><th>CO₂ 排放（kg）</th><th>在港停留（h）</th><th>调度成本（元）</th><th>导出</th></tr></thead><tbody>${solutions.map((solution, index) => `<tr><td>#${index + 1} ${solution.isRecommended ? '<span class="status-pill is-active ms-2">推荐</span>' : ''}</td><td>${historyNumber(solution.co2)}</td><td>${historyNumber(solution.stayTime)}</td><td>${historyNumber(solution.cost)}</td><td><a href="${historyExportUrl(item.id, solution.id)}" class="btn btn-sm btn-light" title="导出方案 ${index + 1}" aria-label="导出方案 ${index + 1}"><i class="bi bi-download"></i></a></td></tr>`).join('')}</tbody></table></div></details>` : ''}
        </article>`;
    }).join('');
    container.querySelectorAll('[data-view-history]').forEach(button => button.addEventListener('click', () => viewDetail(button.dataset.viewHistory)));
    container.querySelectorAll('[data-delete-history]').forEach(button => button.addEventListener('click', () => deleteHistory(button.dataset.deleteHistory)));
}

async function viewDetail(historyId) {
    const requestId = ++detailRequestId;
    const content = document.getElementById('detailContent');
    content.innerHTML = '<div class="page-empty"><div class="spinner-border spinner-border-sm" role="status"></div><p>正在读取调度详情…</p></div>';
    bootstrap.Modal.getOrCreateInstance(document.getElementById('detailModal')).show();
    try {
        const response = await fetch(`/api/history/${encodeURIComponent(historyId)}`);
        if (!response.ok) throw new Error('详情加载失败，请关闭后重试。');
        const data = await response.json();
        if (requestId !== detailRequestId) return;
        const solutions = Array.isArray(data.solutions) ? data.solutions : [];
        const ships = Array.isArray(data.shipsData) ? data.shipsData : [];
        content.innerHTML = `<div class="detail-summary"><span>调度记录 #${escapeHistory(data.id)} · ${escapeHistory(historyDate(data.createdAt))}</span><span>${escapeHistory(data.configName || '默认配置')}</span></div>
            <h6 class="detail-section-heading">参与调度的船舶 <span class="count-pill ms-2">${ships.length}</span></h6>
            <div class="table-responsive"><table class="table table-sm"><thead><tr><th>船舶名称</th><th>船舶长度（m）</th><th>货量（TEU）</th><th>预计到港</th></tr></thead><tbody>${ships.length ? ships.map(ship => `<tr><td>${escapeHistory(ship.name)}</td><td>${historyNumber(ship.length, 1)}</td><td>${historyNumber(ship.teu, 0)}</td><td>${escapeHistory(ship.arrivalTime ?? '—')}</td></tr>`).join('') : '<tr><td colspan="4" class="text-center text-muted py-4">暂无船舶数据</td></tr>'}</tbody></table></div>
            <h6 class="detail-section-heading">Pareto 方案 <span class="count-pill ms-2">${solutions.length}</span></h6>
            <div class="detail-solutions">${solutions.map((solution, index) => `<div class="detail-solution ${solution.isRecommended ? 'is-recommended' : ''}"><div class="detail-solution-title"><h6>方案 ${String(index + 1).padStart(2, '0')}</h6>${solution.isRecommended ? '<span class="status-pill is-active">推荐方案</span>' : ''}</div><dl><dt>CO₂ 排放</dt><dd>${historyNumber(solution.co2)} kg</dd><dt>在港停留</dt><dd>${historyNumber(solution.stayTime)} h</dd><dt>调度成本</dt><dd>${historyNumber(solution.cost)} 元</dd></dl><a href="${historyExportUrl(historyId, solution.id)}" class="btn btn-sm btn-outline-primary w-100"><i class="bi bi-download"></i> 下载 Excel 方案</a></div>`).join('')}</div>
            ${solutions.length ? '' : '<p class="text-muted small">该记录暂无可用方案。</p>'}`;
    } catch (error) {
        if (requestId !== detailRequestId) return;
        content.innerHTML = `<div class="page-empty"><i class="bi bi-exclamation-circle"></i><h3>暂时无法读取详情</h3><p>${escapeHistory(error.message || '请稍后重试。')}</p></div>`;
    }
}

async function deleteHistory(historyId) {
    if (deletingHistoryIds.has(String(historyId))) return;
    if (!confirm('确定删除这条调度记录吗？记录及其方案将无法恢复。')) return;
    deletingHistoryIds.add(String(historyId));
    try {
        const response = await fetch(`/api/history/${encodeURIComponent(historyId)}`, {method: 'DELETE'});
        const result = await response.json();
        if (!response.ok || !result.success) throw new Error(result.error || '删除失败，请稍后重试。');
        await loadHistory();
        historyNotice('调度记录已删除。', 'success');
    } catch (error) {
        historyNotice(error.message || '网络连接异常，请稍后重试。');
    } finally {
        deletingHistoryIds.delete(String(historyId));
    }
}

function resetFilters() {
    document.getElementById('filterStartDate').value = '';
    document.getElementById('filterEndDate').value = '';
    loadHistory();
}

window.addEventListener('DOMContentLoaded', () => {
    document.getElementById('historyFilterForm').addEventListener('submit', event => {
        event.preventDefault();
        loadHistory();
    });
    loadHistory();
});
window.addEventListener('localeChanged', () => { if (historyLoaded) renderHistory(); });
