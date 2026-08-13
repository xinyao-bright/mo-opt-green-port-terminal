const i18n = {
    locale: 'zh-CN',
    messages: {},
    storageKey: 'port-schedule-locale',

    async init() {
        const savedLocale = localStorage.getItem(this.storageKey) || 'zh-CN';
        await this.load(savedLocale);
        this.bindEvents();
    },

    async load(locale) {
        if (!['zh-CN', 'en'].includes(locale)) {
            locale = 'zh-CN';
        }

        try {
            const response = await fetch(`/static/i18n/${locale}.json`);
            if (!response.ok) throw new Error('Failed to load translations');

            this.messages = await response.json();
            this.locale = locale;
            localStorage.setItem(this.storageKey, locale);

            this.updateDOM();
            this.updatePageTitle();

            const langSelector = document.getElementById('langSelector');
            if (langSelector && langSelector.value !== locale) {
                langSelector.value = locale;
            }

            document.documentElement.setAttribute('lang', locale === 'zh-CN' ? 'zh-CN' : 'en');

            window.dispatchEvent(new CustomEvent('localeChanged', { detail: { locale } }));
        } catch (error) {
            console.error('Failed to load translations:', error);
        }
    },

    t(key, fallback = null) {
        const keys = key.split('.');
        let value = this.messages;

        for (const k of keys) {
            if (value && typeof value === 'object' && k in value) {
                value = value[k];
            } else {
                return fallback || key;
            }
        }

        return typeof value === 'string' ? value : (fallback || key);
    },

    updateDOM() {
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.dataset.i18n;
            const text = this.t(key);

            if (el.tagName === 'INPUT' && (el.type === 'button' || el.type === 'submit')) {
                el.value = text;
            } else if (el.hasAttribute('placeholder')) {
                el.placeholder = text;
            } else {
                el.textContent = text;
            }
        });

        document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
            const key = el.dataset.i18nPlaceholder;
            el.placeholder = this.t(key);
        });

        document.querySelectorAll('[data-i18n-title]').forEach(el => {
            const key = el.dataset.i18nTitle;
            el.title = this.t(key);
        });
    },

    updatePageTitle() {
        const titleKey = document.querySelector('[data-page-title]')?.dataset.pageTitle;
        if (titleKey) {
            document.title = this.t(titleKey);
        }
    },

    bindEvents() {
        const langSelector = document.getElementById('langSelector');
        if (langSelector) {
            langSelector.addEventListener('change', (e) => {
                this.load(e.target.value);
            });
        }
    },

    formatNumber(number, decimals = 2) {
        return new Intl.NumberFormat(this.locale, {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals
        }).format(number);
    },

    formatDate(date, options = {}) {
        const defaultOptions = {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        };
        return new Intl.DateTimeFormat(this.locale, { ...defaultOptions, ...options }).format(date);
    }
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => i18n.init());
} else {
    i18n.init();
}
