const ThemeManager = {
    currentTheme: 'light',
    storageKey: 'port-schedule-theme',

    init() {
        const savedTheme = localStorage.getItem(this.storageKey) || 'light';
        this.setTheme(savedTheme, false);
        this.bindEvents();
    },

    setTheme(themeName, saveToStorage = true) {
        if (!['light','dark',  'blue'].includes(themeName)) {
            themeName = 'light';
        }

        document.documentElement.setAttribute('data-theme', themeName);
        this.currentTheme = themeName;

        if (saveToStorage) {
            localStorage.setItem(this.storageKey, themeName);
        }

        const themeSelector = document.getElementById('themeSelector');
        if (themeSelector && themeSelector.value !== themeName) {
            themeSelector.value = themeName;
        }

        this.updateChartColors();

        window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme: themeName } }));
    },

    bindEvents() {
        const themeSelector = document.getElementById('themeSelector');
        if (themeSelector) {
            themeSelector.addEventListener('change', (e) => {
                this.setTheme(e.target.value);
            });
        }
    },

    getThemeColors() {
        const root = document.documentElement;
        const style = getComputedStyle(root);

        return {
            bgMain: style.getPropertyValue('--bg-main').trim(),
            bgCard: style.getPropertyValue('--bg-card').trim(),
            textPrimary: style.getPropertyValue('--text-primary').trim(),
            textSecondary: style.getPropertyValue('--text-secondary').trim(),
            colorPrimary: style.getPropertyValue('--color-primary').trim(),
            colorSuccess: style.getPropertyValue('--color-success').trim(),
            colorWarning: style.getPropertyValue('--color-warning').trim(),
            colorDanger: style.getPropertyValue('--color-danger').trim(),
            chartColor1: style.getPropertyValue('--chart-color-1').trim(),
            chartColor2: style.getPropertyValue('--chart-color-2').trim(),
            chartColor3: style.getPropertyValue('--chart-color-3').trim(),
            chartColor4: style.getPropertyValue('--chart-color-4').trim(),
            chartColor5: style.getPropertyValue('--chart-color-5').trim(),
            chartGrid: style.getPropertyValue('--chart-grid').trim(),
        };
    },

    updateChartColors() {
        if (typeof Chart !== 'undefined') {
            const colors = this.getThemeColors();
            Chart.defaults.color = colors.textSecondary;
            Chart.defaults.borderColor = colors.chartGrid;
        }
    }
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => ThemeManager.init());
} else {
    ThemeManager.init();
}
