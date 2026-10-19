let configs = [];
let selectedConfigId = null;
let isNewMode = false;
let configBusy = false;

const configText = (key, fallback) => typeof i18n !== 'undefined' ? i18n.t(key, fallback) : fallback;

function configNotice(message, type = 'success') {
    const notice = document.getElementById('configNotice');
    notice.textContent = message;
    notice.className = `alert alert-${type}`;
}

async function configRequest(url, options = {}) {
    const response = await fetch(url, options);
    const result = await response.json();
    if (!response.ok || result.success === false) throw new Error(result.error || '操作未完成，请稍后重试。');
    return result;
}

async function loadConfigs(preferredId = selectedConfigId) {
    try {
        const result = await configRequest('/api/port-config');
        if (!Array.isArray(result)) throw new Error('配置数据格式异常，请刷新重试。');
        configs = result;
        renderConfigList();
        const selection = configs.find(c => String(c.id) === String(preferredId)) || configs.find(c => c.isActive) || configs[0];
        if (selection) selectConfig(selection.id);
        else createNewConfig(false);
    } catch (error) {
        document.getElementById('configListContainer').innerHTML = '<div class="page-empty"><i class="bi bi-wifi-off"></i><h3>配置加载失败</h3><p>请检查连接后重新加载。</p><button class="btn btn-sm btn-outline-primary" onclick="loadConfigs()">重新加载</button></div>';
        document.getElementById('activeConfigName').textContent = '暂时无法读取配置';
        configNotice(error.message || '网络连接异常，请重试。', 'danger');
    }
}

function renderConfigList() {
    const container = document.getElementById('configListContainer');
    container.replaceChildren();
    document.getElementById('configCount').textContent = configs.length;
    const active = configs.find(config => config.isActive);
    document.getElementById('activeConfigName').textContent = active ? active.name : '未启用自定义配置';
    document.getElementById('activeBerthCount').textContent = active ? active.totalBerths : '—';
    document.getElementById('activeQcCount').textContent = active ? active.totalQcs : '—';
    if (!configs.length) {
        container.innerHTML = '<div class="page-empty"><i class="bi bi-folder-plus"></i><h3>创建第一个港口配置</h3><p>在右侧填写资源参数并保存。</p></div>';
        return;
    }
    configs.forEach(config => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `config-item ${selectedConfigId === config.id ? 'selected' : ''}`;
        button.setAttribute('aria-pressed', selectedConfigId === config.id ? 'true' : 'false');
        const title = document.createElement('div');
        title.className = 'config-item-title';
        const name = document.createElement('strong');
        name.textContent = config.name;
        title.append(name);
        if (config.isActive) {
            const badge = document.createElement('span');
            badge.className = 'status-pill is-active';
            badge.textContent = '使用中';
            title.append(badge);
        }
        const meta = document.createElement('div');
        meta.className = 'config-item-meta';
        const berths = document.createElement('span');
        berths.textContent = `${config.totalBerths} 个泊位`;
        const cranes = document.createElement('span');
        cranes.textContent = `${config.totalQcs} 台岸桥`;
        meta.append(berths, cranes);
        const created = document.createElement('span');
        created.className = 'config-item-date';
        const date = new Date(config.createdAt);
        created.textContent = Number.isNaN(date.getTime()) ? '已保存配置' : `创建于 ${date.toLocaleDateString('zh-CN')}`;
        button.append(title, meta, created);
        button.addEventListener('click', () => selectConfig(config.id));
        container.append(button);
    });
}

function updateEditorState(config = null) {
    document.getElementById('editorTitle').textContent = config ? config.name : '新建港口配置';
    const status = document.getElementById('editorStatus');
    status.textContent = config ? (config.isActive ? '当前使用中' : '已保存') : '待保存';
    status.className = `status-pill ${config?.isActive ? 'is-active' : ''}`;
    document.getElementById('activateConfigButton').disabled = !config || config.isActive || configBusy;
    document.getElementById('deleteConfigButton').disabled = !config || config.isActive || configBusy;
    document.getElementById('deleteConfigButton').title = config?.isActive ? '正在使用的配置不能删除，请先启用其他配置' : '删除配置';
    document.getElementById('saveConfigButton').disabled = configBusy;
}

function selectConfig(configId) {
    const config = configs.find(c => String(c.id) === String(configId));
    if (!config) return;
    selectedConfigId = config.id;
    isNewMode = false;
    document.getElementById('configId').value = config.id;
    document.getElementById('configName').value = config.name;
    document.getElementById('totalBerths').value = config.totalBerths;
    document.getElementById('totalQCs').value = config.totalQcs;
    document.getElementById('qcEfficiency').value = config.qcEfficiency;
    document.getElementById('maxQcPerVessel').value = config.maxQcPerVessel ?? 3;
    document.getElementById('safetyInterval').value = config.safetyInterval ?? 0.167;
    const existing = Array.isArray(config.berthConfig) ? config.berthConfig : [];
    renderBerthTable(Array.from({length: Math.max(1, Number(config.totalBerths) || 1)}, (_, index) => existing[index] || {name: `B${String(index + 1).padStart(2, '0')}`, length: 300}));
    renderConfigList();
    updateEditorState(config);
}

function makeBerthRow(berth, index) {
    const row = document.createElement('div');
    row.className = 'berth-row';
    const name = document.createElement('input');
    name.type = 'text';
    name.className = 'form-control';
    name.value = berth.name || `B${String(berth.id || index + 1).padStart(2, '0')}`;
    name.placeholder = '泊位名称';
    name.setAttribute('aria-label', `第 ${index + 1} 个泊位名称`);
    name.dataset.berthId = index;
    name.required = true;
    const length = document.createElement('input');
    length.type = 'number';
    length.className = 'form-control';
    length.value = berth.length ?? 300;
    length.min = '0.1';
    length.step = 'any';
    length.placeholder = '长度（米）';
    length.setAttribute('aria-label', `第 ${index + 1} 个泊位长度（米）`);
    length.dataset.berthLength = index;
    length.required = true;
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'btn btn-sm btn-outline-danger';
    remove.title = '删除此泊位';
    remove.setAttribute('aria-label', `删除第 ${index + 1} 个泊位`);
    remove.innerHTML = '<i class="bi bi-trash3" aria-hidden="true"></i>';
    remove.addEventListener('click', () => removeBerthRow(Array.from(row.parentElement.children).indexOf(row)));
    row.append(name, length, remove);
    return row;
}

function renderBerthTable(berths) {
    const table = document.getElementById('berthTable');
    table.replaceChildren(...berths.map(makeBerthRow));
    document.getElementById('totalBerths').value = berths.length;
}

function getBerthConfigFromForm() {
    return Array.from(document.querySelectorAll('#berthTable .berth-row')).map((row, index) => ({
        id: index + 1,
        name: row.querySelector('[data-berth-id]').value.trim(),
        length: Number(row.querySelector('[data-berth-length]').value)
    }));
}

function addBerthRow() {
    const rows = getBerthConfigFromForm();
    const names = new Set(rows.map(row => row.name));
    let next = rows.length + 1;
    while (names.has(`B${String(next).padStart(2, '0')}`)) next++;
    rows.push({name: `B${String(next).padStart(2, '0')}`, length: 300});
    renderBerthTable(rows);
    const table = document.getElementById('berthTable');
    table.scrollTop = table.scrollHeight;
    table.lastElementChild.querySelector('input').focus();
}

function removeBerthRow(index) {
    const rows = getBerthConfigFromForm();
    if (rows.length <= 1) return configNotice('至少需要保留一个泊位。', 'warning');
    rows.splice(index, 1);
    renderBerthTable(rows);
}

function handleTotalBerthsChange() {
    const input = document.getElementById('totalBerths');
    if (!input.checkValidity()) return;
    const count = Number(input.value);
    if (!Number.isInteger(count) || count < 1) return;
    const existing = getBerthConfigFromForm();
    renderBerthTable(Array.from({length: count}, (_, index) => existing[index] || {name: `B${String(index + 1).padStart(2, '0')}`, length: 300}));
}

function createNewConfig(focus = true) {
    isNewMode = true;
    selectedConfigId = null;
    document.getElementById('configForm').reset();
    document.getElementById('configId').value = '';
    document.getElementById('configName').value = '';
    document.getElementById('totalQCs').value = 30;
    renderBerthTable(Array.from({length: 17}, (_, index) => ({name: `B${String(index + 1).padStart(2, '0')}`, length: index < 10 ? 300 : 200})));
    renderConfigList();
    updateEditorState();
    if (focus) document.getElementById('configName').focus();
}

function resetForm() {
    const config = configs.find(item => item.id === selectedConfigId) || configs.find(item => item.isActive) || configs[0];
    if (config) selectConfig(config.id);
    else createNewConfig(false);
    document.getElementById('configNotice').classList.add('d-none');
}

async function saveConfig(event) {
    event.preventDefault();
    if (configBusy) return;
    const form = document.getElementById('configForm');
    if (!form.reportValidity()) return;
    const configId = document.getElementById('configId').value;
    const configData = {
        name: document.getElementById('configName').value.trim(),
        totalBerths: Number(document.getElementById('totalBerths').value),
        totalQcs: Number(document.getElementById('totalQCs').value),
        qcEfficiency: Number(document.getElementById('qcEfficiency').value),
        maxQcPerVessel: Number(document.getElementById('maxQcPerVessel').value),
        safetyInterval: Number(document.getElementById('safetyInterval').value),
        berthConfig: getBerthConfigFromForm()
    };
    if (!configData.name) return configNotice('请填写配置名称。', 'warning');
    if (configData.maxQcPerVessel > configData.totalQcs) return configNotice('单船最大岸桥数不能超过岸桥总数。', 'warning');
    if (configData.berthConfig.some(berth => !berth.name || !Number.isFinite(berth.length) || berth.length <= 0)) return configNotice('请为每个泊位填写名称和有效长度。', 'warning');
    configBusy = true;
    updateEditorState(configs.find(config => config.id === selectedConfigId));
    try {
        const result = await configRequest(configId ? `/api/port-config/${encodeURIComponent(configId)}` : '/api/port-config', {
            method: configId ? 'PUT' : 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(configData)
        });
        configNotice(configText('messages.saveSuccess', '配置已保存。'));
        await loadConfigs(result.id || configId);
    } catch (error) {
        configNotice(error.message || '保存失败，请稍后重试。', 'danger');
    } finally {
        configBusy = false;
        updateEditorState(configs.find(config => config.id === selectedConfigId));
    }
}

async function activateCurrentConfig() {
    const configId = document.getElementById('configId').value;
    if (!configId || configBusy) return;
    configBusy = true;
    updateEditorState(configs.find(config => config.id === selectedConfigId));
    try {
        await configRequest(`/api/port-config/${encodeURIComponent(configId)}/activate`, {method: 'POST'});
        configNotice('配置已启用，下一次调度将使用这些港口资源。');
        await loadConfigs(configId);
    } catch (error) {
        configNotice(error.message || '启用失败，请稍后重试。', 'danger');
    } finally {
        configBusy = false;
        updateEditorState(configs.find(config => config.id === selectedConfigId));
    }
}

async function deleteCurrentConfig() {
    const configId = document.getElementById('configId').value;
    if (!configId || configBusy || !confirm(configText('messages.confirmDelete', '确定删除此配置吗？此操作无法撤销。'))) return;
    configBusy = true;
    updateEditorState(configs.find(config => config.id === selectedConfigId));
    try {
        await configRequest(`/api/port-config/${encodeURIComponent(configId)}`, {method: 'DELETE'});
        configNotice(configText('messages.deleteSuccess', '配置已删除。'));
        selectedConfigId = null;
        await loadConfigs();
    } catch (error) {
        configNotice(error.message || '删除失败，请稍后重试。', 'danger');
    } finally {
        configBusy = false;
        updateEditorState(configs.find(config => config.id === selectedConfigId));
    }
}

window.addEventListener('DOMContentLoaded', () => {
    document.getElementById('configForm').addEventListener('submit', saveConfig);
    document.getElementById('totalBerths').addEventListener('change', handleTotalBerthsChange);
    loadConfigs();
});
