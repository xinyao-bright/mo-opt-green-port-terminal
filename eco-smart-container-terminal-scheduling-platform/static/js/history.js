let historyData = [];

async function loadHistory() {
    try {
        const response = await fetch('/api/history');
        if (!response.ok) throw new Error('Failed to load history');

        historyData = await response.json();
        renderHistory();
    } catch (error) {
        console.error('Error loading history:', error);
        document.getElementById('historyList').innerHTML = `
            <div class="alert alert-danger">${i18n.t('messages.networkError')}</div>
        `;
    }
}

function renderHistory() {
    const container = document.getElementById('historyList');

    if (historyData.length === 0) {
        container.innerHTML = `
            <div class="text-center text-muted py-5">
                <i class="bi bi-inbox" style="font-size: 48px;"></i>
                <p class="mt-3" data-i18n="common.noData">暂无数据</p>
            </div>
        `;
        i18n.updateDOM();
        return;
    }

    container.innerHTML = historyData.map(item => {
        const date = new Date(item.createdAt);
        const solutions = item.solutions || [];
        const bestSolution = solutions.find(s => s.isRecommended) || solutions[0];
        const weights = item.weights || {};

        return `
            <div class="history-item">
                <div class="history-meta">
                    <div class="meta-item">
                        <span class="meta-label" data-i18n="history.timestamp">时间</span>
                        <span class="meta-value">${i18n.formatDate(date)}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label" data-i18n="history.shipCount">船舶数量</span>
                        <span class="meta-value">${item.shipsData?.length || 0}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label" data-i18n="history.config">配置</span>
                        <span class="meta-value">${item.configName || '默认配置'}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label" data-i18n="schedule.solutions">方案数</span>
                        <span class="meta-value">${solutions.length}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">决策权重</span>
                        <span class="meta-value" style="font-size: 13px;">
                            CO₂: ${weights.w_co2 ?? '-'} / 时间: ${weights.w_time ?? '-'} / 成本: ${weights.w_cost ?? '-'}
                        </span>
                    </div>
                </div>

                ${bestSolution ? `
                <div class="objectives-section mb-3">
                    <div class="objectives-title">推荐方案目标函数表现</div>
                    <div class="kpi-badges">
                        <div class="kpi-badge kpi-co2">
                            <i class="bi bi-cloud"></i>
                            CO₂排放: ${i18n.formatNumber(bestSolution.co2, 2)} kg
                        </div>
                        <div class="kpi-badge kpi-time">
                            <i class="bi bi-clock"></i>
                            在港停留: ${i18n.formatNumber(bestSolution.stayTime, 2)} h
                        </div>
                        <div class="kpi-badge kpi-cost">
                            <i class="bi bi-currency-dollar"></i>
                            调度成本: ${i18n.formatNumber(bestSolution.cost, 2)} 元
                        </div>
                    </div>
                </div>

                ${solutions.length > 1 ? `
                <div class="pareto-overview mb-3">
                    <div class="objectives-title">全部Pareto方案对比</div>
                    <div class="pareto-mini-table">
                        <table class="table table-sm table-bordered mb-0">
                            <thead>
                                <tr>
                                    <th>方案</th>
                                    <th>CO₂排放 (kg)</th>
                                    <th>在港停留 (h)</th>
                                    <th>调度成本 (元)</th>
                                    <th>操作</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${solutions.map((sol, idx) => `
                                    <tr class="${sol.isRecommended ? 'table-success' : ''}">
                                        <td>
                                            #${idx + 1}
                                            ${sol.isRecommended ? '<span class="badge bg-success ms-1">推荐</span>' : ''}
                                        </td>
                                        <td>${i18n.formatNumber(sol.co2, 2)}</td>
                                        <td>${i18n.formatNumber(sol.stayTime, 2)}</td>
                                        <td>${i18n.formatNumber(sol.cost, 2)}</td>
                                        <td>
                                            <a href="/api/history/${item.id}/export?solution=${sol.id}"
                                               class="btn btn-sm btn-outline-success" title="下载该方案Excel">
                                                <i class="bi bi-file-earmark-excel"></i>
                                            </a>
                                        </td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
                ` : ''}
                ` : ''}

                <div class="history-actions mt-3">
                    <button class="btn btn-sm btn-primary" onclick="viewDetail(${item.id})">
                        <i class="bi bi-eye"></i>
                        <span data-i18n="history.viewDetail">查看详情</span>
                    </button>
                    <a href="/api/history/${item.id}/export" class="btn btn-sm btn-success">
                        <i class="bi bi-file-earmark-excel"></i>
                        <span>下载推荐方案Excel</span>
                    </a>
                    <button class="btn btn-sm btn-danger" onclick="deleteHistory(${item.id})">
                        <i class="bi bi-trash"></i>
                        <span data-i18n="history.delete">删除</span>
                    </button>
                </div>
            </div>
        `;
    }).join('');

    i18n.updateDOM();
}

async function viewDetail(historyId) {
    try {
        const response = await fetch(`/api/history/${historyId}`);
        if (!response.ok) throw new Error('Failed to load detail');

        const data = await response.json();
        const solutions = data.solutions || [];

        const detailHTML = `
            <div class="mb-4">
                <h6>船舶列表</h6>
                <table class="table table-sm">
                    <thead>
                        <tr>
                            <th data-i18n="columns.ship_name">船舶</th>
                            <th data-i18n="columns.length_of_ship">长度</th>
                            <th data-i18n="columns.volume_of_goods">货量</th>
                            <th data-i18n="columns.time_of_reachport">到港时间</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${(data.shipsData || []).map(ship => `
                            <tr>
                                <td>${ship.name}</td>
                                <td>${ship.length} ${i18n.t('units.meter')}</td>
                                <td>${ship.teu} ${i18n.t('units.teu')}</td>
                                <td>${ship.arrivalTime}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>

            <div>
                <h6>Pareto方案 (共${solutions.length}个)</h6>
                <div class="row">
                    ${solutions.map((sol, idx) => `
                        <div class="col-md-4 mb-3">
                            <div class="card ${sol.isRecommended ? 'border-success' : ''}">
                                <div class="card-body">
                                    ${sol.isRecommended ? '<span class="badge bg-success mb-2">推荐</span>' : ''}
                                    <h6>方案 ${idx + 1}</h6>
                                    <p class="mb-1 small">CO₂: ${i18n.formatNumber(sol.co2, 2)} kg</p>
                                    <p class="mb-1 small">在港停留: ${i18n.formatNumber(sol.stayTime, 2)} h</p>
                                    <p class="mb-1 small">调度成本: ${i18n.formatNumber(sol.cost, 2)} 元</p>
                                    <hr class="my-2">
                                    <a href="/api/history/${historyId}/export?solution=${sol.id}"
                                       class="btn btn-sm btn-outline-success w-100">
                                        <i class="bi bi-download"></i> 下载Excel
                                    </a>
                                </div>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;

        document.getElementById('detailContent').innerHTML = detailHTML;
        i18n.updateDOM();

        const modal = new bootstrap.Modal(document.getElementById('detailModal'));
        modal.show();
    } catch (error) {
        console.error('Error viewing detail:', error);
        alert(i18n.t('messages.networkError'));
    }
}

async function deleteHistory(historyId) {
    if (!confirm(i18n.t('messages.confirmDelete'))) {
        return;
    }

    try {
        const response = await fetch(`/api/history/${historyId}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (result.success) {
            alert(i18n.t('messages.deleteSuccess'));
            loadHistory();
        } else {
            alert(result.error || i18n.t('messages.deleteError'));
        }
    } catch (error) {
        console.error('Error deleting history:', error);
        alert(i18n.t('messages.networkError'));
    }
}

function resetFilters() {
    document.getElementById('filterStartDate').value = '';
    document.getElementById('filterEndDate').value = '';
    loadHistory();
}

window.addEventListener('DOMContentLoaded', () => {
    loadHistory();
});
