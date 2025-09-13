// OKX跟单交易系统前端配置文件
window.APP_CONFIG = {
    // API配置
    api: {
        baseUrl: '/api/v1', // 默认端口，根据您的main.py实际端口调整
        timeout: 30000, // 30秒超时
        retryCount: 3,  // 重试次数
        retryDelay: 1000 // 重试延迟（毫秒）
    },

    // 应用配置
    app: {
        name: 'OKX跟单交易系统',
        version: '1.0.0',
        language: 'zh-CN',
        timezone: 'Asia/Shanghai',
        refreshInterval: 30000, // 数据刷新间隔（毫秒）
        pageSize: 10, // 默认分页大小
        maxPageSize: 100 // 最大分页大小
    },

    // 主题配置
    theme: {
        primaryColor: '#0d6efd',
        secondaryColor: '#6c757d',
        successColor: '#198754',
        warningColor: '#ffc107',
        dangerColor: '#dc3545',
        infoColor: '#0dcaf0',
        lightColor: '#f8f9fa',
        darkColor: '#212529',
        borderRadius: '0.5rem',
        boxShadow: '0 0.125rem 0.25rem rgba(0, 0, 0, 0.075)',
        transition: 'all 0.15s ease-in-out'
    },

    // 图表配置
    charts: {
        tradesChart: {
            height: 300,
            colors: ['#0d6efd', '#198754', '#ffc107', '#dc3545'],
            animation: true,
            responsive: true
        },
        strategyChart: {
            height: 300,
            colors: ['#0d6efd', '#198754', '#ffc107', '#6c757d'],
            animation: true,
            responsive: true
        }
    },

    // 表格配置
    tables: {
        defaultPageSize: 10,
        pageSizeOptions: [10, 20, 50, 100],
        sortable: true,
        searchable: true,
        filterable: true,
        exportable: true
    },

    // 通知配置
    notifications: {
        toast: {
            duration: 5000, // 显示时长（毫秒）
            position: 'bottom-right',
            animation: true
        },
        alert: {
            autoHide: true,
            hideDelay: 10000 // 自动隐藏延迟（毫秒）
        }
    },

    // 安全配置
    security: {
        enableAuth: false, // 是否启用身份验证
        sessionTimeout: 3600000, // 会话超时时间（毫秒）
        maxLoginAttempts: 5, // 最大登录尝试次数
        lockoutDuration: 300000 // 锁定持续时间（毫秒）
    },

    // 开发配置
    development: {
        debug: true, // 是否启用调试模式
        logLevel: 'info', // 日志级别：debug, info, warn, error
        mockData: false, // 是否使用模拟数据
        apiMockDelay: 500 // API模拟延迟（毫秒）
    },

    // 功能开关
    features: {
        realTimeUpdates: true, // 实时更新
        dataExport: true, // 数据导出
        bulkOperations: true, // 批量操作
        advancedSearch: true, // 高级搜索
        dataVisualization: true, // 数据可视化
        systemMonitoring: true, // 系统监控
        riskControl: true, // 风控管理
        notificationCenter: true // 通知中心
    },

    // 本地化配置
    localization: {
        defaultLanguage: 'zh-CN',
        supportedLanguages: ['zh-CN', 'en-US'],
        dateFormat: 'YYYY-MM-DD',
        timeFormat: 'HH:mm:ss',
        numberFormat: {
            decimal: '.',
            thousands: ',',
            precision: 2
        }
    },

    // 性能配置
    performance: {
        lazyLoading: true, // 懒加载
        virtualScrolling: false, // 虚拟滚动
        dataCaching: true, // 数据缓存
        cacheExpiry: 300000, // 缓存过期时间（毫秒）
        maxCacheSize: 100 // 最大缓存条目数
    }
};

// 环境检测和配置覆盖
(function() {
    // 检测环境
    const hostname = window.location.hostname;
    const port = window.location.port;
    
    // 开发环境配置
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
        if (port === '8080' || port === '8081') {
            // 本地开发环境
            window.APP_CONFIG.api.baseUrl = 'http://localhost:5000/api/v1';
            window.APP_CONFIG.development.debug = true;
            window.APP_CONFIG.development.mockData = false;
        }
    }
    
    // 生产环境配置
    if (hostname !== 'localhost' && hostname !== '127.0.0.1') {
        window.APP_CONFIG.api.baseUrl = `https://${hostname}/api/v1`;
        window.APP_CONFIG.development.debug = false;
        window.APP_CONFIG.development.mockData = false;
        window.APP_CONFIG.security.enableAuth = true;
    }
    
    // 从URL参数覆盖配置
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('api')) {
        window.APP_CONFIG.api.baseUrl = urlParams.get('api');
    }
    if (urlParams.has('debug')) {
        window.APP_CONFIG.development.debug = urlParams.get('debug') === 'true';
    }
    if (urlParams.has('mock')) {
        window.APP_CONFIG.development.mockData = urlParams.get('mock') === 'true';
    }
    
    // 从localStorage恢复用户偏好设置
    try {
        const userPrefs = JSON.parse(localStorage.getItem('userPreferences') || '{}');
        if (userPrefs.theme) {
            Object.assign(window.APP_CONFIG.theme, userPrefs.theme);
        }
        if (userPrefs.language) {
            window.APP_CONFIG.localization.defaultLanguage = userPrefs.language;
        }
    } catch (e) {
        console.warn('无法恢复用户偏好设置:', e);
    }
    
    // 应用主题配置到CSS变量
    function applyThemeConfig() {
        const root = document.documentElement;
        Object.entries(window.APP_CONFIG.theme).forEach(([key, value]) => {
            if (key !== 'borderRadius' && key !== 'boxShadow' && key !== 'transition') {
                root.style.setProperty(`--${key.replace(/([A-Z])/g, '-$1').toLowerCase()}`, value);
            }
        });
    }
    
    // 页面加载完成后应用主题
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', applyThemeConfig);
    } else {
        applyThemeConfig();
    }
})();

// 配置验证
(function() {
    const requiredConfigs = [
        'api.baseUrl',
        'app.name',
        'theme.primaryColor'
    ];
    
    function validateConfig() {
        const errors = [];
        requiredConfigs.forEach(path => {
            const value = path.split('.').reduce((obj, key) => obj && obj[key], window.APP_CONFIG);
            if (value === undefined || value === null || value === '') {
                errors.push(`缺少必需配置: ${path}`);
            }
        });
        
        if (errors.length > 0) {
            console.error('配置验证失败:', errors);
            if (window.APP_CONFIG.development.debug) {
                alert('配置验证失败: ' + errors.join(', '));
            }
        }
    }
    
    // 延迟验证，确保所有配置都已加载
    setTimeout(validateConfig, 100);
})(); 