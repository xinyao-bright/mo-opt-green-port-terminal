let configs = [];
let selectedConfigId = null;
let isNewMode = false;

async function loadConfigs() {
    try {
        const response = await fetch('/api/port-config');
        if (!response.ok) throw new Error('Failed to load configs');

        configs = await response.json();
        renderConfigList();

        if (configs.length > 0) {
            selectConfig(configs[0].id);
        }
    } catch (error) {
        console.error('Error loading configs:', error);
        alert(i18n.t('messages.networkError'));
    }
}

function renderConfigList() {
    const container = document.getElementById('configListContainer');
    if (configs.length === 0) {
        container.innerHTML = `<p class="text-muted" data-i18n="common.noData">暂无数据</p>`;
        i18n.updateDOM();
        return;
    }

    container.innerHTML = configs.map(config => `
        <div class="config-item ${config.isActive ? 'active' : ''} ${selectedConfigId === config.id ? 'selected' : ''}"
             onclick="selectConfig(${config.id})">
            <div class="d-flex justify-content-between align-items-center">
                <strong>${config.name}</strong>
                ${config.isActive ? `<span class="badge badge-active" data-i18n="portConfig.active">激活</span>` : ''}
            </div>
            <div class="text-muted small mt-1">
                <span data-i18n="portConfig.totalBerths">泊位</span>: ${config.totalBerths} |
                <span data-i18n="portConfig.totalQCs">岸桥</span>: ${config.totalQcs}
            </div>
            <div class="text-muted small">
                ${new Date(config.createdAt).toLocaleDateString()}
            </div>
        </div>
    `).join('');

    i18n.updateDOM();
}

function selectConfig(configId) {
    selectedConfigId = configId;
    const config = configs.find(c => c.id === configId);

    if (!config) return;

    document.getElementById('configId').value = config.id;
    document.getElementById('configName').value = config.name;
    document.getElementById('totalBerths').value = config.totalBerths;
    document.getElementById('totalQCs').value = config.totalQcs;
    document.getElementById('qcEfficiency').value = config.qcEfficiency;

    renderBerthTable(config.berthConfig);
    renderConfigList();
}

function renderBerthTable(berthConfig) {
    const table = document.getElementById('berthTable');

    if (!berthConfig || berthConfig.length === 0) {
        table.innerHTML = '<p class="text-muted" data-i18n="common.noData">暂无数据</p>';
        i18n.updateDOM();
        return;
    }

    table.innerHTML = berthConfig.map((berth, index) => `
        <div class="berth-row">
            <input type="text" class="form-control" placeholder="${i18n.t('portConfig.berthId')}"
                   value="${berth.name || berth.id}" data-berth-id="${index}">
            <input type="number" class="form-control" placeholder="${i18n.t('portConfig.berthLength')}"
                   value="${berth.length}" min="1" data-berth-length="${index}">
            <button type="button" class="btn btn-sm btn-outline-danger" onclick="removeBerthRow(${index})">
                <i class="bi bi-trash"></i>
            </button>
        </div>
    `).join('');
}

function addBerthRow() {
    const table = document.getElementById('berthTable');
    const currentRows = table.querySelectorAll('.berth-row').length;

    const newRow = document.createElement('div');
    newRow.className = 'berth-row';
    newRow.innerHTML = `
        <input type="text" class="form-control" placeholder="${i18n.t('portConfig.berthId')}"
               value="B${String(currentRows + 1).padStart(2, '0')}" data-berth-id="${currentRows}">
        <input type="number" class="form-control" placeholder="${i18n.t('portConfig.berthLength')}"
               value="300" min="1" data-berth-length="${currentRows}">
        <button type="button" class="btn btn-sm btn-outline-danger" onclick="removeBerthRow(${currentRows})">
            <i class="bi bi-trash"></i>
        </button>
    `;
    table.appendChild(newRow);
}

function removeBerthRow(index) {
    const table = document.getElementById('berthTable');
    const rows = table.querySelectorAll('.berth-row');
    if (rows.length > 1) {
        rows[index].remove();
    } else {
        alert('至少需要保留一个泊位');
    }
}

function getBerthConfigFromForm() {
    const table = document.getElementById('berthTable');
    const rows = table.querySelectorAll('.berth-row');

    return Array.from(rows).map((row, index) => {
        const nameInput = row.querySelector(`[data-berth-id="${index}"]`);
        const lengthInput = row.querySelector(`[data-berth-length="${index}"]`);

        return {
            id: index + 1,
            name: nameInput ? nameInput.value : `B${String(index + 1).padStart(2, '0')}`,
            length: lengthInput ? parseFloat(lengthInput.value) : 300
        };
    });
}

function createNewConfig() {
    resetForm();
    document.getElementById('configName').value = '新配置 ' + new Date().toLocaleTimeString();
    document.getElementById('totalBerths').value = 17;
    document.getElementById('totalQCs').value = 30;

    const berthConfig = Array.from({length: 17}, (_, i) => ({
        id: i + 1,
        name: `B${String(i + 1).padStart(2, '0')}`,
        length: i < 10 ? 300 : 200
    }));

    renderBerthTable(berthConfig);
}

function resetForm() {
    document.getElementById('configForm').reset();
    document.getElementById('configId').value = '';
    selectedConfigId = null;
    document.getElementById('berthTable').innerHTML = '';
    renderConfigList();
}

document.getElementById('configForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const configId = document.getElementById('configId').value;
    const configData = {
        name: document.getElementById('configName').value,
        totalBerths: parseInt(document.getElementById('totalBerths').value),
        totalQcs: parseInt(document.getElementById('totalQCs').value),
        qcEfficiency: parseFloat(document.getElementById('qcEfficiency').value),
        maxQcPerVessel: parseInt(document.getElementById('maxQcPerVessel').value),
        safetyInterval: parseFloat(document.getElementById('safetyInterval').value),
        berthConfig: getBerthConfigFromForm()
    };

    const url = configId ? `/api/port-config/${configId}` : '/api/port-config';
    const method = configId ? 'PUT' : 'POST';

    try {
        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(configData)
        });

        const result = await response.json();

        if (result.success) {
            alert(i18n.t('messages.saveSuccess'));
            const savedId = configId || result.id;
            await loadConfigs();
            if (savedId) selectConfig(parseInt(savedId));
        } else {
            alert(result.error || i18n.t('messages.saveError'));
        }
    } catch (error) {
        console.error('Error saving config:', error);
        alert(i18n.t('messages.networkError'));
    }
});

async function activateCurrentConfig() {
    const configId = document.getElementById('configId').value;
    if (!configId) {
        alert('请先选择一个配置');
        return;
    }

    try {
        const response = await fetch(`/api/port-config/${configId}/activate`, {
            method: 'POST'
        });

        const result = await response.json();

        if (result.success) {
            alert(i18n.t('messages.activateSuccess'));
            await loadConfigs();
        } else {
            alert(result.error || i18n.t('messages.activateError'));
        }
    } catch (error) {
        console.error('Error activating config:', error);
        alert(i18n.t('messages.networkError'));
    }
}


function handleTotalBerthsChange() {
    const num = parseInt(document.getElementById('totalBerths').value) || 0;
    if (num <= 0) return;
    const berthList = Array.from({ length: num }, (_, i) => ({
        id: i + 1,
        name: `B${String(i + 1).padStart(2, '0')}`,
        length: 300
    }));
    renderBerthTable(berthList);
}

async function deleteCurrentConfig() {
    const configId = document.getElementById('configId').value;
    if (!configId) {
        alert('请先选择一个配置');
        return;
    }

    if (!confirm(i18n.t('messages.confirmDelete'))) {
        return;
    }

    try {
        const response = await fetch(`/api/port-config/${configId}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (result.success) {
            alert(i18n.t('messages.deleteSuccess'));
            resetForm();
            await loadConfigs();
        } else {
            alert(result.error || i18n.t('messages.deleteError'));
        }
    } catch (error) {
        console.error('Error deleting config:', error);
        alert(i18n.t('messages.networkError'));
    }
}

window.addEventListener('DOMContentLoaded', () => {
    loadConfigs();
    const totalBerthsInput = document.getElementById('totalBerths');
    totalBerthsInput.addEventListener('input', handleTotalBerthsChange);
});
