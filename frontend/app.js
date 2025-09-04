// OKX跟单交易系统前端应用
class OKXTradingApp {
    constructor() {
        this.apiBaseUrl = window.APP_CONFIG?.api?.baseUrl || 'http://localhost:5000/api/v1';
        this.currentPage = 'dashboard';
        this.currentTradesPage = 1;
        this.tradesSearchParams = {};
        
        // 系统日志分页
        this.systemLogsPage = 1;
        this.systemLogsPageSize = 10;
        this.systemLogsTotal = 0;
        
        // 自动刷新配置 - 完全后台运行，无需用户控制
        this.autoRefreshConfig = {
            enabled: true, // 始终启用
            intervals: {
                'trades': 10000,        // 交易记录：10秒
                'signal-trades': 15000, // 信号源交易：15秒
                'positions': 20000,     // 当前持仓：20秒
                'dashboard': 30000,     // 仪表盘：30秒
                'limit-follow': 15000,  // 限价跟单：15秒
                'strategy-trade': 20000, // 策略交易：20秒
                'kline': 1000         // K线图：1秒
            },
            timers: {},
            lastRefresh: {}
        };
        
        this.init();
    }

    // 格式化日期时间
    formatDateTime(dateTimeStr) {
        if (!dateTimeStr) return '-';
        
        try {
            const date = new Date(dateTimeStr);
            if (isNaN(date.getTime())) {
                return dateTimeStr; // 如果无法解析，直接返回原字符串
            }
            
            // 使用中文本地化格式，显示完整的年月日时分秒
            return date.toLocaleString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        } catch (error) {
            console.error('日期格式化错误:', error, dateTimeStr);
            return dateTimeStr; // 出错时返回原字符串
        }
    }

    init() {
        this.bindEvents();
        this.loadDashboardData();
        this.setupCharts();
        this.initKlineChart();
        
        this.initAutoRefresh(); // 初始化自动刷新
        this.startAutoRefresh('kline'); // 启动K线图自动刷新
    }

    bindEvents() {
        // 导航事件
        document.querySelectorAll('[data-page]').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                this.navigateToPage(e.target.dataset.page);
            });
        });

        // 刷新数据
        const refreshBtn = document.getElementById('refreshData');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.refreshCurrentPage();
            });
        }

        // 导出数据
        const exportBtn = document.getElementById('exportData');
        if (exportBtn) {
            exportBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.exportCurrentPageData();
            });
        }

        // 退出登录
        const logoutBtn = document.getElementById('logout');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.logout();
            });
        }

        // 客户搜索
        const customerSearchBtn = document.getElementById('customerSearchBtn');
        if (customerSearchBtn) {
            customerSearchBtn.addEventListener('click', () => {
                this.searchCustomers();
            });
        }

        // 客户筛选
        document.querySelectorAll('input[name="customerFilter"]').forEach(radio => {
            radio.addEventListener('change', () => {
                this.filterCustomers(radio.value);
            });
        });

        // 规则搜索
        const ruleSearchBtn = document.getElementById('ruleSearchBtn');
        if (ruleSearchBtn) {
            ruleSearchBtn.addEventListener('click', () => {
                this.searchRules();
            });
        }

        // 规则搜索回车事件
        const ruleSearch = document.getElementById('ruleSearch');
        if (ruleSearch) {
            ruleSearch.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.searchRules();
                }
            });
        }

        // 规则筛选
        document.querySelectorAll('input[name="ruleFilter"]').forEach(radio => {
            radio.addEventListener('change', () => {
                this.filterRules(radio.value);
            });
        });

        // 策略搜索
        const strategySearchBtn = document.getElementById('strategySearchBtn');
        if (strategySearchBtn) {
            strategySearchBtn.addEventListener('click', () => {
                this.searchStrategies();
            });
        }

        // 策略搜索回车事件
        const strategySearch = document.getElementById('strategySearch');
        if (strategySearch) {
            strategySearch.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.searchStrategies();
                }
            });
        }

        // 策略筛选
        document.querySelectorAll('input[name="strategyFilter"]').forEach(radio => {
            radio.addEventListener('change', () => {
                this.filterStrategies(radio.value);
            });
        });

        // 初始化限价跟单模块
        this.initLimitFollowModule();

        // 信号源搜索
        const signalSourceSearchBtn = document.getElementById('signalSourceSearchBtn');
        if (signalSourceSearchBtn) {
            signalSourceSearchBtn.addEventListener('click', () => {
                this.searchSignalSources();
            });
        }

        // 信号源搜索回车事件
        const signalSourceSearch = document.getElementById('signalSourceSearch');
        if (signalSourceSearch) {
            signalSourceSearch.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.searchSignalSources();
                }
            });
        }

        // 信号源筛选
        document.querySelectorAll('input[name="signalSourceFilter"]').forEach(radio => {
            radio.addEventListener('change', () => {
                this.filterSignalSources(radio.value);
            });
        });

        // 保存客户
        const saveCustomerBtn = document.getElementById('saveCustomerBtn');
        if (saveCustomerBtn) {
            saveCustomerBtn.addEventListener('click', () => {
                this.saveCustomer();
            });
        }

        // 客户模态框关闭事件
        const addCustomerModal = document.getElementById('addCustomerModal');
        if (addCustomerModal) {
            addCustomerModal.addEventListener('hidden.bs.modal', () => {
                this.clearCustomerForm();
                // 重置模态框标题
                document.querySelector('#addCustomerModal .modal-title').textContent = '添加新客户';
            });
        }

        // 持仓详情平仓按钮
        const closePositionBtn = document.getElementById('closePositionBtn');
        if (closePositionBtn) {
            closePositionBtn.addEventListener('click', () => {
                this.closeCurrentPosition();
            });
        }

        // 回车搜索
        const customerSearch = document.getElementById('customerSearch');
        if (customerSearch) {
            customerSearch.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.searchCustomers();
                }
            });
        }

        // 交易记录搜索表单事件绑定
        const tradesSearchForm = document.getElementById('tradesSearchForm');
        if (tradesSearchForm) {
            tradesSearchForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.searchTrades(e);
            });
        }

        // 交易记录搜索重置按钮
        const resetSearchBtn = document.getElementById('resetSearchBtn');
        if (resetSearchBtn) {
            resetSearchBtn.addEventListener('click', () => {
                this.resetTradesSearch();
            });
        }

        // 系统健康检查重新检查按钮
        const runHealthCheckBtn = document.getElementById('runHealthCheckBtn');
        if (runHealthCheckBtn) {
            runHealthCheckBtn.addEventListener('click', () => {
                this.loadSystemData();
            });
        }

        // 系统操作按钮
        const reloadRulesBtn = document.getElementById('reloadRulesBtn');
        if (reloadRulesBtn) {
            reloadRulesBtn.addEventListener('click', () => {
                this.reloadRules();
            });
        }

        const reloadCustomersBtn = document.getElementById('reloadCustomersBtn');
        if (reloadCustomersBtn) {
            reloadCustomersBtn.addEventListener('click', () => {
                this.reloadCustomers();
            });
        }

        const reloadSignalSourcesBtn = document.getElementById('reloadSignalSourcesBtn');
        if (reloadSignalSourcesBtn) {
            reloadSignalSourcesBtn.addEventListener('click', () => {
                this.reloadSignalSources();
            });
        }

        const reloadTradeServiceBtn = document.getElementById('reloadTradeServiceBtn');
        if (reloadTradeServiceBtn) {
            reloadTradeServiceBtn.addEventListener('click', () => {
                this.reloadTradeService();
            });
        }

        // 策略模态框事件
        const saveStrategyBtn = document.getElementById('saveStrategyBtn');
        if (saveStrategyBtn) {
            saveStrategyBtn.addEventListener('click', () => {
                this.saveStrategy();
            });
        }

        // 规则模态框事件
        const saveRuleBtn = document.getElementById('saveRuleBtn');
        if (saveRuleBtn) {
            saveRuleBtn.addEventListener('click', () => {
                this.saveRule();
            });
        }

        // 信号源模态框事件
        const saveSignalSourceBtn = document.getElementById('saveSignalSourceBtn');
        if (saveSignalSourceBtn) {
            saveSignalSourceBtn.addEventListener('click', () => {
                this.saveSignalSource();
            });

            // 信号源交易搜索表单事件
            const signalTradesSearchForm = document.getElementById('signalTradesSearchForm');
            if (signalTradesSearchForm) {
                signalTradesSearchForm.addEventListener('submit', (e) => {
                    e.preventDefault();
                    this.searchSignalTrades();
                });
            }

            // 信号源交易重置搜索按钮
            const resetSignalTradesSearchBtn = document.getElementById('resetSignalTradesSearchBtn');
            if (resetSignalTradesSearchBtn) {
                resetSignalTradesSearchBtn.addEventListener('click', () => {
                    this.resetSignalTradesSearch();
                });
            }
        }

        // 手动开仓保存按钮
        const saveManualPositionBtn = document.getElementById('saveManualPositionBtn');
        if (saveManualPositionBtn) {
            saveManualPositionBtn.addEventListener('click', () => {
                this.saveManualPosition();
            });
        }

        // 手动开仓模态框事件
        const manualOpenPositionModal = document.getElementById('manualOpenPositionModal');
        if (manualOpenPositionModal) {
            manualOpenPositionModal.addEventListener('hidden.bs.modal', () => {
                this.clearManualPositionForm();
            });
            // 添加显示事件，加载表单数据并初始化限价单功能
            manualOpenPositionModal.addEventListener('show.bs.modal', () => {
                this.loadManualPositionFormData();
                // 延迟初始化限价单功能，确保DOM元素已加载
                setTimeout(() => {
                    this.initLimitOrderFeatures();
                }, 100);
            });
        }
        
        // 撤单功能事件绑定
        const refreshOrdersBtn = document.getElementById('refreshOrdersBtn');
        if (refreshOrdersBtn) {
            refreshOrdersBtn.addEventListener('click', () => {
                this.refreshPendingOrders();
            });
        }
        
        const cancelAllOrdersBtn = document.getElementById('cancelAllOrdersBtn');
        if (cancelAllOrdersBtn) {
            cancelAllOrdersBtn.addEventListener('click', () => {
                this.cancelAllPendingOrders();
            });
        }
        
        // 当前持仓页面的撤单功能事件绑定
        const refreshPendingOrdersBtn = document.getElementById('refreshPendingOrdersBtn');
        if (refreshPendingOrdersBtn) {
            refreshPendingOrdersBtn.addEventListener('click', () => {
                this.loadPendingOrdersForPositions();
            });
        }
        
        const cancelAllPendingOrdersBtn = document.getElementById('cancelAllPendingOrdersBtn');
        if (cancelAllPendingOrdersBtn) {
            cancelAllPendingOrdersBtn.addEventListener('click', () => {
                this.cancelAllPendingOrdersForPositions();
            });
        }
        
        const cleanupDuplicatesBtn = document.getElementById('cleanupDuplicatesBtn');
        if (cleanupDuplicatesBtn) {
            cleanupDuplicatesBtn.addEventListener('click', () => {
                this.cleanupDuplicateOrders();
            });
        }
        
        const cleanupInvalidPositionsBtn = document.getElementById('cleanupInvalidPositionsBtn');
        if (cleanupInvalidPositionsBtn) {
            cleanupInvalidPositionsBtn.addEventListener('click', () => {
                this.cleanupInvalidPositions();
            });
        }
        
        const debugOrdersBtn = document.getElementById('debugOrdersBtn');
        if (debugOrdersBtn) {
            debugOrdersBtn.addEventListener('click', () => {
                this.debugAllOrders();
            });
        }

        // 账户类型选择事件
        const manualAccountTypeSelect = document.getElementById('manualAccountType');
        if (manualAccountTypeSelect) {
            manualAccountTypeSelect.addEventListener('change', () => {
                this.onManualAccountTypeChange();
            });
        }

        // 信号源模态框关闭事件
        const addSignalSourceModal = document.getElementById('addSignalSourceModal');
        if (addSignalSourceModal) {
            addSignalSourceModal.addEventListener('hidden.bs.modal', () => {
                this.clearSignalSourceForm();
            });
        }

        // 策略模态框关闭事件
        const addStrategyModal = document.getElementById('addStrategyModal');
        if (addStrategyModal) {
            addStrategyModal.addEventListener('hidden.bs.modal', () => {
                this.clearStrategyForm();
            });
            // 添加显示事件，加载信号源和客户选项
            addStrategyModal.addEventListener('show.bs.modal', () => {
                this.loadAccountsForStrategy('create');
            });
        }

        // 规则模态框关闭事件
        const addRuleModal = document.getElementById('addRuleModal');
        if (addRuleModal) {
            addRuleModal.addEventListener('hidden.bs.modal', () => {
                this.clearRuleForm();
            });
            // 添加显示事件，加载策略选项
            addRuleModal.addEventListener('show.bs.modal', () => {
                this.loadStrategiesOptions();
            });
        }

        // K线图相关事件
        const loadKlineBtn = document.getElementById('loadKlineBtn');
        if (loadKlineBtn) {
            loadKlineBtn.addEventListener('click', () => {
                this.loadKlineData();
            });
        }

        // K线图搜索回车事件
        const symbolSearch = document.getElementById('symbolSearch');
        if (symbolSearch) {
            symbolSearch.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.loadKlineData();
                }
            });
        }

        // 时间周期选择事件
        const timeframeSelect = document.getElementById('timeframeSelect');
        if (timeframeSelect) {
            timeframeSelect.addEventListener('change', () => {
                if (this.klineChart) {
                    this.loadKlineData();
                }
            });
        }

        // 系统日志分页事件
        const systemLogsPageSize = document.getElementById('systemLogsPageSize');
        if (systemLogsPageSize) {
            systemLogsPageSize.addEventListener('change', () => {
                this.systemLogsPageSize = parseInt(systemLogsPageSize.value);
                this.systemLogsPage = 1; // 重置到第一页
                this.loadSystemLogs();
            });
        }

        const refreshSystemLogsBtn = document.getElementById('refreshSystemLogsBtn');
        if (refreshSystemLogsBtn) {
            refreshSystemLogsBtn.addEventListener('click', () => {
                this.loadSystemLogs();
            });
        }

        const testSystemLogsPaginationBtn = document.getElementById('testSystemLogsPaginationBtn');
        if (testSystemLogsPaginationBtn) {
            testSystemLogsPaginationBtn.addEventListener('click', () => {
                this.testSystemLogsPagination();
            });
        }

        const systemLogsPrevBtn = document.getElementById('systemLogsPrevBtn');
        if (systemLogsPrevBtn) {
            systemLogsPrevBtn.addEventListener('click', (e) => {
                e.preventDefault();
                if (this.systemLogsPage > 1) {
                    this.systemLogsPage--;
                    this.loadSystemLogs();
                }
            });
        }

        const systemLogsNextBtn = document.getElementById('systemLogsNextBtn');
        if (systemLogsNextBtn) {
            systemLogsNextBtn.addEventListener('click', (e) => {
                e.preventDefault();
                const maxPage = Math.ceil(this.systemLogsTotal / this.systemLogsPageSize);
                if (this.systemLogsPage < maxPage) {
                    this.systemLogsPage++;
                    this.loadSystemLogs();
                }
            });
        }
    }

    // 动态加载信号源下拉选项
    async loadSignalSourcesOptions() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/signal_sources`);
            if (response.ok) {
                const data = await response.json();
                const signalSources = Array.isArray(data.data) ? data.data : (data.data?.sources || []);
                
                // 更新策略表单中的信号源下拉框
                const signalSourcesSelect = document.getElementById('signalSources');
                if (signalSourcesSelect) {
                    // 保留默认选项
                    signalSourcesSelect.innerHTML = '<option value="">请选择信号源</option>';
                    
                    // 添加信号源选项
                    signalSources.forEach(source => {
                        const option = document.createElement('option');
                        option.value = source.source_uid;
                        option.textContent = `${source.name} (${source.source_uid})`;
                        signalSourcesSelect.appendChild(option);
                    });
                }
            } else {
                console.error('加载信号源选项失败:', response.statusText);
            }
        } catch (error) {
            console.error('加载信号源选项失败:', error);
        }
    }

    // 动态加载策略下拉选项
    async loadStrategiesOptions() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/strategies`);
            if (response.ok) {
                const data = await response.json();
                const strategies = Array.isArray(data.data) ? data.data : (data.data?.strategies || []);
                
                // 更新规则表单中的策略下拉框
                const ruleStrategySelect = document.getElementById('ruleStrategy');
                if (ruleStrategySelect) {
                    // 保留默认选项
                    ruleStrategySelect.innerHTML = '<option value="">请选择策略</option>';
                    
                    // 添加策略选项
                    strategies.forEach(strategy => {
                        const option = document.createElement('option');
                        option.value = strategy.strategy_uid;
                        option.textContent = `${strategy.name} (${strategy.strategy_uid})`;
                        ruleStrategySelect.appendChild(option);
                    });
                }
            } else {
                console.error('加载策略选项失败:', response.statusText);
            }
        } catch (error) {
            console.error('加载策略选项失败:', error);
        }
    }

    // 页面导航
    navigateToPage(pageName) {

        
        // 停止当前页面的自动刷新
        if (this.currentPage) {
            this.stopAutoRefresh(this.currentPage);
        }
        
        // 如果当前是仪表盘页面，也要停止K线图的自动刷新
        if (this.currentPage === 'dashboard') {
            this.stopAutoRefresh('kline');
        }
        
        // 更新导航状态
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });
        
        const activeLink = document.querySelector(`[data-page="${pageName}"]`);
        if (activeLink) {
            activeLink.classList.add('active');
        }

        // 隐藏所有页面
        document.querySelectorAll('.page-content').forEach(page => {
            page.classList.remove('active');
        });

        // 显示目标页面
        const targetPage = document.getElementById(`${pageName}-page`);
        if (targetPage) {
            targetPage.classList.add('active');
        } else {
            console.warn('页面不存在:', pageName);
        }

        this.currentPage = pageName;
        this.loadPageData(pageName);
        
        // 启动新页面的自动刷新
        this.startAutoRefresh(pageName);
        
        // 如果是仪表盘页面，同时启动K线图的独立自动刷新
        if (pageName === 'dashboard') {
            this.startAutoRefresh('kline');
        }
    }

    // 加载页面数据
    loadPageData(pageName) {
        switch (pageName) {
            case 'dashboard':
                this.loadDashboardData();
                break;
            case 'customers':
                this.loadCustomersData();
                break;
            case 'signal-sources':
                this.loadSignalSourcesData();
                break;
            case 'strategies':
                this.loadStrategiesData();
                break;
            case 'rules':
                this.loadRulesData();
                break;
            case 'trades':
                this.loadTradesData();
                break;
            case 'signal-trades':
                this.loadSignalTradesData();
                break;
            case 'positions':
                this.loadPositionsData();
                break;
            case 'risk-control':
                this.loadRiskControlData();
                break;
            case 'limit-follow':
                this.loadLimitFollowData();
                break;
            case 'system':
                this.loadSystemData();
                break;
            case 'strategy-trade':
                this.loadStrategyTradeData();
                break;
            default:
                console.warn('未知页面:', pageName);
        }
    }

    // 加载仪表盘数据
    async loadDashboardData() {
        try {
            // 加载概览统计
            const statsResponse = await fetch(`${this.apiBaseUrl}/stats/overview`);
            if (statsResponse.ok) {
                const statsData = await statsResponse.json();
                this.updateDashboardStats(statsData.data);
            }

            // 加载最近活动
            const activitiesResponse = await fetch(`${this.apiBaseUrl}/activities/recent`);
            if (activitiesResponse.ok) {
                const activitiesData = await activitiesResponse.json();
                this.updateRecentActivities(activitiesData.data);
            }

            // 更新图表
            this.updateDashboardCharts();
            
        } catch (error) {
            console.error('加载仪表盘数据失败:', error);
            // 使用模拟数据
            this.updateDashboardStats({
                total_customers: 5,
                today_trades: 128,
                active_strategies: 3,
                system_status: '正常'
            });
            
            this.updateRecentActivities([
                {
                    title: '新客户注册',
                    description: '客户 cust_005 完成注册',
                    timestamp: new Date().toISOString()
                },
                {
                    title: '交易完成',
                    description: 'BTC-USDT 买入订单执行成功',
                    timestamp: new Date(Date.now() - 300000).toISOString()
                }
            ]);
        }
    }

    // 静默加载仪表盘数据（用于自动刷新）
    async loadDashboardDataSilent() {
        try {
            // 加载概览统计
            const statsResponse = await fetch(`${this.apiBaseUrl}/stats/overview`);
            if (statsResponse.ok) {
                const statsData = await statsResponse.json();
                this.updateDashboardStats(statsData.data);
            }

            // 加载最近活动
            const activitiesResponse = await fetch(`${this.apiBaseUrl}/activities/recent`);
            if (activitiesResponse.ok) {
                const activitiesData = await activitiesResponse.json();
                this.updateRecentActivities(activitiesData.data);
            }

            // 更新图表
            this.updateDashboardCharts();
            
        } catch (error) {
            console.error('静默加载仪表盘数据失败:', error);
        }
    }

    // 更新仪表盘统计
    updateDashboardStats(stats) {
        const elements = {
            'totalCustomers': document.getElementById('total-customers'),
            'totalTrades': document.getElementById('today-trades'),
            'activeStrategies': document.getElementById('active-strategies'),
            'systemStatus': document.getElementById('system-status')
        };

        if (elements.totalCustomers) {
            elements.totalCustomers.textContent = stats.total_customers || 0;
        }
        
        if (elements.totalTrades) {
            elements.totalTrades.textContent = stats.today_trades || 0;
        }
        
        if (elements.activeStrategies) {
            elements.activeStrategies.textContent = stats.active_strategies || 0;
        }
        
        if (elements.systemStatus) {
            elements.systemStatus.textContent = stats.system_status || '正常';
        }
    }

    // 更新最近活动
    updateRecentActivities(activities) {
        const container = document.getElementById('recent-activities');
        if (!container) {
            return;
        }

        if (!activities || activities.length === 0) {
            container.innerHTML = '<div class="text-muted">暂无活动</div>';
            return;
        }

        const activitiesHtml = activities.map(activity => `
            <div class="activity-item mb-3 p-3 border rounded">
                <div class="activity-title fw-bold">${activity.title}</div>
                <div class="activity-description text-muted">${activity.description}</div>
                <div class="activity-time text-muted small">${this.formatTime(activity.timestamp)}</div>
            </div>
        `).join('');

        container.innerHTML = activitiesHtml;
    }

    // 设置图表
    setupCharts() {
        // 只保留K线图，移除策略分布和交易趋势图表
    }

    // 更新仪表盘图表
    updateDashboardCharts() {
        // 只保留K线图，移除策略分布和交易趋势图表
    }



    // K线图相关方法
    initKlineChart() {
        const container = document.getElementById('klineChart');
        if (!container) {
            return;
        }

        // 检查 TradingView 库是否已加载
        if (typeof LightweightCharts === 'undefined') {
            container.innerHTML = `
                <div class="kline-error">
                    <div>
                        <i class="bi bi-exclamation-triangle-fill fs-1 mb-3"></i>
                        <h6>图表库加载失败</h6>
                        <p class="text-muted">请刷新页面重试</p>
                    </div>
                </div>
            `;
            return;
        }

        try {
            // 设置默认数据
            this.setDefaultKlineData();

            // 自动加载默认K线数据
            setTimeout(() => {
                this.loadKlineData();
            }, 1000);

        } catch (error) {
            container.innerHTML = `
                <div class="kline-error">
                    <div>
                        <i class-exclamation-triangle-fill fs-1 mb-3"></i>
                        <h6>图表初始化失败</h6>
                        <p class="text-muted">${error.message}</p>
                    </div>
                </div>
            `;
        }
    }

    // 设置默认K线数据
    setDefaultKlineData() {
        // 生成一些模拟数据用于初始化
        const now = Date.now();
        const data = [];
        let basePrice = 65000; // BTC价格基准

        for (let i = 0; i < 20; i++) {
            const time = now - (20 - i) * 15 * 60 * 1000; // 每15分钟一个数据点
            const open = basePrice + Math.random() * 2000 - 1000;
            const high = open + Math.random() * 500;
            const low = open - Math.random() * 500;
            const close = open + Math.random() * 1000 - 500;
            
            data.push({
                time: time,
                open: open,
                high: high,
                low: low,
                close: close,
                volume: Math.random() * 1000
            });
            
            basePrice = close;
        }

        // 显示默认数据
        this.updateKlineChart(data);
    }

    // 加载K线数据
    async loadKlineData() {
        const symbolInput = document.getElementById('symbolSearch');
        const timeframeSelect = document.getElementById('timeframeSelect');
        const chartContainer = document.getElementById('klineChart');
        
        if (!symbolInput || !timeframeSelect) {
            console.warn('未找到K线图相关元素');
            return;
        }

        const symbol = symbolInput.value.trim().toUpperCase();
        const timeframe = timeframeSelect.value;

        if (!symbol) {
            this.showToast('错误', '请输入币种名称', 'danger');
            return;
        }



        try {
            // 显示加载状态
            if (chartContainer) {
                chartContainer.innerHTML = `
                    <div class="kline-loading">
                        <div class="spinner-border spinner-border-sm" role="status">
                            <span class="visually-hidden">加载中...</span>
                        </div>
                        正在加载 ${symbol} K线数据...
                    </div>
                `;
            }

            // 调用OKX公共API获取K线数据
            const klineData = await this.fetchKlineData(symbol, timeframe);
            
            if (klineData && klineData.length > 0) {
                try {
                    this.updateKlineChart(klineData);
                    this.showToast('成功', `${symbol} K线数据加载成功`, 'success');
                } catch (error) {
                    console.warn('图表更新失败，使用备用方案:', error);
                    this.showKlineDataTable(klineData, symbol);
                    this.showToast('成功', `${symbol} K线数据加载成功（表格显示）`, 'success');
                }
            } else {
                if (chartContainer) {
                    chartContainer.innerHTML = `
                        <div class="kline-error">
                            <div>
                                <i class="bi bi-exclamation-triangle-fill fs-1 mb-3"></i>
                                <h6>未获取到K线数据</h6>
                                <p class="text-muted">请检查币种名称是否正确</p>
                            </div>
                        </div>
                    `;
                }
                this.showToast('错误', '未获取到K线数据', 'danger');
            }
        } catch (error) {
            console.error('加载K线数据失败:', error);
            if (chartContainer) {
                chartContainer.innerHTML = `
                    <div class="kline-error">
                        <div>
                            <i class="bi bi-exclamation-triangle-fill fs-1 mb-3"></i>
                            <h6>加载失败</h6>
                            <p class="text-muted">${error.message}</p>
                        </div>
                    </div>
                `;
            }
            this.showToast('错误', '加载K线数据失败: ' + error.message, 'danger');
        }
    }

    // 从OKX API获取K线数据
    async fetchKlineData(symbol, timeframe) {
        // 根据时间周期计算需要的数据量
        let limit = 100;
        const now = Date.now();
        
        // 计算3天前的时间戳
        const threeDaysAgo = now - (3 * 24 * 60 * 60 * 1000);
        
        // 根据时间周期调整数据量
        switch(timeframe) {
            case '1m':
                limit = 4320; // 3天 * 24小时 * 60分钟
                break;
            case '5m':
                limit = 864; // 3天 * 24小时 * 12
                break;
            case '15m':
                limit = 288; // 3天 * 24小时 * 4
                break;
            case '1H':
                limit = 72; // 3天 * 24小时
                break;
            case '4H':
                limit = 18; // 3天 * 6
                break;
            case '1D':
                limit = 3; // 3天
                break;
        }
        
        const url = `https://www.okx.com/api/v5/market/candles?instId=${symbol}&bar=${timeframe}&limit=${limit}`;
        

        
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();


        if (data.code !== '0') {
            throw new Error(data.msg || 'API请求失败');
        }

        // 转换数据格式并过滤最近3天的数据
        const klineData = data.data
            .map(item => ({
                time: parseInt(item[0]), // 保持毫秒级时间戳
                open: parseFloat(item[1]),
                high: parseFloat(item[2]),
                low: parseFloat(item[3]),
                close: parseFloat(item[4]),
                volume: parseFloat(item[5]),
            }))
            .filter(item => item.time >= threeDaysAgo) // 只保留最近3天的数据
            .sort((a, b) => a.time - b.time); // 按时间排序



        return klineData;
    }

    // 格式化北京时间
    formatBeijingTime(timestamp) {
        const date = new Date(timestamp);
        // 转换为东八区时间
        const utc = date.getTime() + (date.getTimezoneOffset() * 60000);
        const beijingTime = new Date(utc + (8 * 3600000));
        return beijingTime.toLocaleString('zh-CN');
    }

    // 计算移动平均线
    calculateMA(prices, period) {
        const ma = [];
        for (let i = 0; i < prices.length; i++) {
            if (i < period - 1) {
                ma.push(null);
            } else {
                const sum = prices.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0);
                ma.push(sum / period);
            }
        }
        return ma;
    }

    // 静默更新K线图数据
    async updateKlineDataSilent() {
        try {
            const symbolInput = document.getElementById('symbolSearch');
            const timeframeSelect = document.getElementById('timeframeSelect');
            
            if (!symbolInput || !timeframeSelect) {
                return;
            }

            const symbol = symbolInput.value.trim().toUpperCase();
            const timeframe = timeframeSelect.value;

            if (!symbol) {
                return;
            }

    

            // 获取最新K线数据
            const klineData = await this.fetchKlineData(symbol, timeframe);
            
            if (klineData && klineData.length > 0) {
                // 更新现有图表数据
                this.updateKlineChartData(klineData);
        
            }
        } catch (error) {
            console.error('❌ 静默更新K线图数据失败:', error);
        }
    }

    // 备用方案：显示K线数据表格
    showKlineDataTable(klineData, symbol) {
        const container = document.getElementById('klineChart');
        if (!container) return;

        const tableHtml = `
            <div class="table-responsive">
                <h6 class="mb-3">${symbol} K线数据</h6>
                <table class="table table-sm table-striped">
                    <thead>
                        <tr>
                            <th>时间</th>
                            <th>开盘价</th>
                            <th>最高价</th>
                            <th>最低价</th>
                            <th>收盘价</th>
                            <th>成交量</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${klineData.slice(0, 20).map(item => `
                            <tr>
                                <td>${this.formatBeijingTime(item.time)}</td>
                                <td>${item.open.toFixed(2)}</td>
                                <td>${item.high.toFixed(2)}</td>
                                <td>${item.low.toFixed(2)}</td>
                                <td>${item.close.toFixed(2)}</td>
                                <td>${item.volume.toFixed(2)}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
                <p class="text-muted small">显示最近20条数据，共${klineData.length}条</p>
            </div>
        `;

        container.innerHTML = tableHtml;
    }

    // 回退方案：显示K线数据表格
    updateKlineChartFallback(klineData) {
        const container = document.getElementById('klineChart');
        if (!container) return;

        // 如果TradingView图表失败，直接显示数据表格
        this.showKlineDataTable(klineData, 'K线数据');
    }

    // 更新K线图 - 使用专业的TradingView图表
    updateKlineChart(klineData) {
        const container = document.getElementById('klineChart');
        if (!container) {
            console.warn('未找到K线图容器');
            return;
        }

        // 检查 TradingView 库是否已加载
        if (typeof LightweightCharts === 'undefined') {
            console.error('TradingView LightweightCharts 库未加载');
            this.showKlineDataTable(klineData, 'K线数据');
            return;
        }

        try {
            // 清空容器
            container.innerHTML = '';

            // 创建专业图表
            const chart = LightweightCharts.createChart(container, {
                width: container.clientWidth,
                height: 500, // 增加高度以容纳分离的K线图和成交量
                layout: {
                    backgroundColor: '#1e1e1e',
                    textColor: '#d1d4dc',
                },
                grid: {
                    vertLines: {
                        color: '#2B2B43',
                    },
                    horzLines: {
                        color: '#2B2B43',
                    },
                },
                crosshair: {
                    mode: LightweightCharts.CrosshairMode.Normal,
                    vertLine: {
                        color: '#758696',
                        width: 1,
                        style: LightweightCharts.LineStyle.Dashed,
                    },
                    horzLine: {
                        color: '#758696',
                        width: 1,
                        style: LightweightCharts.LineStyle.Dashed,
                    },
                },
                rightPriceScale: {
                    borderColor: '#2B2B43',
                    scaleMargins: {
                        top: 0.1,
                        bottom: 0.25, // K线图占据上部75%的区域
                    },
                },
                leftPriceScale: {
                    borderColor: '#2B2B43',
                    scaleMargins: {
                        top: 0.75, // 成交量占据底部25%的区域
                        bottom: 0,
                    },
                    visible: true,
                },
                timeScale: {
                    borderColor: '#2B2B43',
                    timeVisible: true,
                    secondsVisible: false,
                    rightOffset: 12,
                    barSpacing: 3,
                    fixLeftEdge: true,
                    lockVisibleTimeRangeOnResize: true,
                    rightBarStaysOnScroll: true,
                    borderVisible: false,
                    visible: true,
                    tickMarkFormatter: (time) => {
                        const date = new Date(time * 1000);
                        // 转换为东八区时间
                        const utc = date.getTime() + (date.getTimezoneOffset() * 60000);
                        const beijingTime = new Date(utc + (8 * 3600000));
                        return beijingTime.toLocaleString('zh-CN', {
                            month: '2-digit',
                            day: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit'
                        });
                    },
                },
                handleScroll: {
                    mouseWheel: true,
                    pressedMouseMove: true,
                    horzTouchDrag: true,
                    vertTouchDrag: true,
                },
                handleScale: {
                    axisPressedMouseMove: true,
                    mouseWheel: true,
                    pinch: true,
                },
            });

            // 创建K线数据系列
            const candleSeries = chart.addCandlestickSeries({
                upColor: '#26a69a',
                downColor: '#ef5350',
                borderVisible: false,
                wickUpColor: '#26a69a',
                wickDownColor: '#ef5350',
                priceScaleId: 'right', // 使用右侧价格轴
            });

            // 创建成交量系列
            const volumeSeries = chart.addHistogramSeries({
                color: '#26a69a',
                priceFormat: {
                    type: 'volume',
                },
                priceScaleId: 'left', // 使用左侧价格轴
                scaleMargins: {
                    top: 0.75, // 成交量占据底部25%的区域
                    bottom: 0,
                },
            });

            // 计算移动平均线
            const closePrices = klineData.map(item => item.close);
            const ma7 = this.calculateMA(closePrices, 7);
            const ma25 = this.calculateMA(closePrices, 25);

            // 添加移动平均线
            const ma7Series = chart.addLineSeries({
                color: '#f7931a',
                lineWidth: 1,
                title: 'MA7',
                priceScaleId: 'right', // 使用右侧价格轴
            });

            const ma25Series = chart.addLineSeries({
                color: '#2196f3',
                lineWidth: 1,
                title: 'MA25',
                priceScaleId: 'right', // 使用右侧价格轴
            });

            // 添加分隔线
            const separatorSeries = chart.addLineSeries({
                color: '#666666',
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                priceScaleId: 'right',
            });

            // 准备数据
            const candleData = klineData.map(item => ({
                time: Math.floor(item.time / 1000),
                open: item.open,
                high: item.high,
                low: item.low,
                close: item.close,
            }));

            const volumeData = klineData.map(item => ({
                time: Math.floor(item.time / 1000),
                value: item.volume,
                color: item.close >= item.open ? '#26a69a' : '#ef5350',
            }));

            const ma7Data = ma7.map((value, index) => ({
                time: Math.floor(klineData[index].time / 1000),
                value: value,
            }));

            const ma25Data = ma25.map((value, index) => ({
                time: Math.floor(klineData[index].time / 1000),
                value: value,
            }));

            // 准备分隔线数据（在K线图底部画一条水平线）
            const minPrice = Math.min(...klineData.map(d => d.low));
            const maxPrice = Math.max(...klineData.map(d => d.high));
            const priceRange = maxPrice - minPrice;
            const separatorPrice = minPrice - priceRange * 0.05; // 在最低价下方5%处画线
            
            const separatorData = klineData.map(item => ({
                time: Math.floor(item.time / 1000),
                value: separatorPrice,
            }));

            // 设置数据
            candleSeries.setData(candleData);
            volumeSeries.setData(volumeData);
            ma7Series.setData(ma7Data);
            ma25Series.setData(ma25Data);
            separatorSeries.setData(separatorData);

            // 保存图表引用
            this.klineChart = chart;
            this.klineCandleSeries = candleSeries;
            this.klineVolumeSeries = volumeSeries;
            this.klineMA7Series = ma7Series;
            this.klineMA25Series = ma25Series;
            this.klineSeparatorSeries = separatorSeries;

            // 监听窗口大小变化
            const resizeObserver = new ResizeObserver(() => {
                chart.applyOptions({
                    width: container.clientWidth,
                    height: 500
                });
            });
            resizeObserver.observe(container);

    
        } catch (error) {
            console.error('专业K线图创建失败:', error);
            this.showKlineDataTable(klineData, 'K线数据');
        }
    }

    // 更新现有K线图数据（不重新创建图表）
    updateKlineChartData(klineData) {
        if (!this.klineChart || !this.klineCandleSeries) {
            console.warn('K线图未初始化，无法更新数据');
            return;
        }

        try {
            // 准备数据
            const candleData = klineData.map(item => ({
                time: Math.floor(item.time / 1000),
                open: item.open,
                high: item.high,
                low: item.low,
                close: item.close,
            }));

            const volumeData = klineData.map(item => ({
                time: Math.floor(item.time / 1000),
                value: item.volume,
                color: item.close >= item.open ? '#26a69a' : '#ef5350',
            }));

            // 计算移动平均线
            const closePrices = klineData.map(item => item.close);
            const ma7 = this.calculateMA(closePrices, 7);
            const ma25 = this.calculateMA(closePrices, 25);

            const ma7Data = ma7.map((value, index) => ({
                time: Math.floor(klineData[index].time / 1000),
                value: value,
            })).filter(item => item.value !== null);

            const ma25Data = ma25.map((value, index) => ({
                time: Math.floor(klineData[index].time / 1000),
                value: value,
            })).filter(item => item.value !== null);

            // 准备分隔线数据
            const minPrice = Math.min(...klineData.map(d => d.low));
            const maxPrice = Math.max(...klineData.map(d => d.high));
            const priceRange = maxPrice - minPrice;
            const separatorPrice = minPrice - priceRange * 0.05;
            
            const separatorData = klineData.map(item => ({
                time: Math.floor(item.time / 1000),
                value: separatorPrice,
            }));

            // 更新数据系列
            this.klineCandleSeries.setData(candleData);
            this.klineVolumeSeries.setData(volumeData);
            this.klineMA7Series.setData(ma7Data);
            this.klineMA25Series.setData(ma25Data);
            this.klineSeparatorSeries.setData(separatorData);

    
        } catch (error) {
            console.error('更新K线图数据失败:', error);
        }
    }

    // 加载客户数据
    async loadCustomersData() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/customers`);
            if (response.ok) {
                const data = await response.json();
                
                // 检查数据结构
                if (Array.isArray(data.data)) {
                    // 直接返回数组的情况
                    this.renderCustomersTable(data.data);
                } else if (data.data && Array.isArray(data.data.customers)) {
                    // 嵌套结构的情况
                    this.renderCustomersTable(data.data.customers);
                } else {
                    console.error('客户数据格式错误:', data.data);
                    this.renderCustomersTable([]);
                }
            } else {
                console.error('加载客户数据失败:', response.statusText);
                this.renderCustomersTable([]);
            }
        } catch (error) {
            console.error('加载客户数据失败:', error);
            this.renderCustomersTable([]);
        }
    }

    // 渲染客户表格
    renderCustomersTable(customers) {
        const tbody = document.getElementById('customersTableBody');
        if (!tbody) {
            console.warn('未找到 customersTableBody 元素');
            return;
        }

        // 确保 customers 是数组
        if (!Array.isArray(customers)) {
            console.warn('customers 不是数组:', customers);
            tbody.innerHTML = '<tr><td colspan="9" class="text-center">数据格式错误</td></tr>';
            return;
        }

        if (customers.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="text-center">暂无客户数据</td></tr>';
            return;
        }

        const rowsHtml = customers.map(customer => `
            <tr>
                <td>${customer.customer_uid || '未知'}</td>
                <td>${customer.name || '未设置'}</td>
                <td>${this.formatNumber(customer.init_asset || 0)}</td>
                <td>${this.formatNumber(customer.current_asset || customer.balance || 0)}</td>
                <td>${this.formatNumber(customer.trading_asset || 0)}</td>
                <td>${customer.leverage || 1}</td>
                <td>${customer.enabled ? '<span class="badge bg-success">启用</span>' : '<span class="badge bg-secondary">禁用</span>'}</td>
                <td>${customer.stop_loss_enabled ? '<span class="badge bg-warning">已设置</span>' : '<span class="badge bg-light text-dark">未设置</span>'}</td>
                <td>
                    <div class="btn-group" role="group">
                        <button class="btn btn-sm btn-outline-primary" onclick="app.editCustomer('${customer.customer_uid}')" title="编辑">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-info" onclick="app.viewCustomerDetails('${customer.customer_uid}')" title="查看详情">
                            <i class="bi bi-eye"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-warning" onclick="app.toggleCustomerStatus('${customer.customer_uid}')" title="${customer.enabled ? '禁用' : '启用'}">
                            <i class="bi bi-${customer.enabled ? 'pause' : 'play'}"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="app.deleteCustomer('${customer.customer_uid}')" title="删除">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');

        tbody.innerHTML = rowsHtml;
    }

    // 客户管理相关函数
    editCustomer(customerUid) {
        // TODO: 实现编辑客户功能
        this.showToast('提示', '编辑客户功能开发中', 'info');
    }

    async viewCustomerDetails(customerUid) {
        try {
            // 获取客户详情
            const response = await fetch(`${this.apiBaseUrl}/customers/${customerUid}`);
            if (response.ok) {
                const data = await response.json();
                const customer = data.data;
                
                // 填充详情模态框
                this.fillCustomerDetailModal(customer);
                
                // 显示模态框
                const modal = new bootstrap.Modal(document.getElementById('customerDetailModal'));
                modal.show();
            } else {
                this.showToast('错误', '获取客户详情失败', 'danger');
            }
        } catch (error) {
            console.error('获取客户详情失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }

    // 填充客户详情模态框
    fillCustomerDetailModal(customer) {
        // 基本信息
        document.getElementById('customerDetailUid').textContent = customer.customer_uid || '-';
        document.getElementById('customerDetailName').textContent = customer.name || '-';
        document.getElementById('customerDetailExchange').textContent = customer.exchange || '-';
        document.getElementById('customerDetailInitAsset').textContent = this.formatNumber(customer.init_asset || 0);
        document.getElementById('customerDetailCurrentAsset').textContent = this.formatNumber(customer.current_asset || 0);
        document.getElementById('customerDetailTradingAsset').textContent = this.formatNumber(customer.trading_asset || 0);
        
        // 交易设置
        document.getElementById('customerDetailLeverage').textContent = customer.leverage ? `${customer.leverage}x` : '-';
        document.getElementById('customerDetailStopLossPercent').textContent = customer.stop_loss_percent ? `${customer.stop_loss_percent}%` : '-';
        document.getElementById('customerDetailStopLossEnabled').textContent = customer.stop_loss_enabled ? '已启用' : '未启用';
        document.getElementById('customerDetailStatus').textContent = customer.enabled ? '启用' : '禁用';
        document.getElementById('customerDetailIsDemo').textContent = customer.is_demo ? '模拟账户' : '实盘账户';
        document.getElementById('customerDetailCreatedAt').textContent = this.formatDateTime(customer.created_at) || '-';
        
    }

    toggleCustomerStatus(customerUid) {
        // TODO: 实现切换客户状态功能
        this.showToast('提示', '切换客户状态功能开发中', 'info');
    }

    deleteCustomer(customerUid) {
        if (confirm('确定要删除这个客户吗？此操作不可恢复。')) {
            // TODO: 实现删除客户功能
            this.showToast('提示', '删除客户功能开发中', 'info');
        }
    }

    // 信号源管理相关函数
    async editSignalSource(sourceUid) {
        try {
            // 获取信号源详情
            const response = await fetch(`${this.apiBaseUrl}/signal_sources/${sourceUid}`);
            if (response.ok) {
                const data = await response.json();
                const signalSource = data.data;
                
                // 填充表单
                this.fillSignalSourceForm(signalSource, true);
                
                // 设置当前编辑的信号源ID
                this.currentEditSignalSourceUid = sourceUid;
                
                // 修改模态框标题
                document.getElementById('addSignalSourceModalLabel').textContent = '编辑信号源';
                
                // 显示模态框
                const modal = new bootstrap.Modal(document.getElementById('addSignalSourceModal'));
                modal.show();
            } else {
                this.showToast('错误', '获取信号源详情失败', 'danger');
            }
        } catch (error) {
            console.error('获取信号源详情失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }

    viewSignalSourceDetails(sourceUid) {
        // 这里可以实现查看详情的功能，比如显示一个只读的模态框
        this.showToast('信息', `查看信号源详情: ${sourceUid}`, 'info');
    }

    async toggleSignalSourceStatus(sourceUid) {
        try {
            // 获取当前信号源信息
            const response = await fetch(`${this.apiBaseUrl}/signal_sources/${sourceUid}`);
            if (response.ok) {
                const data = await response.json();
                const signalSource = data.data;
                const newStatus = !signalSource.enabled;
                
                // 更新状态
                const updateResponse = await fetch(`${this.apiBaseUrl}/signal_sources/${sourceUid}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        enabled: newStatus
                    })
                });
                
                if (updateResponse.ok) {
                    this.showToast('成功', `信号源状态已${newStatus ? '启用' : '禁用'}`, 'success');
                    // 刷新数据
                    this.loadSignalSourcesData();
                } else {
                    this.showToast('错误', '状态更新失败', 'danger');
                }
            } else {
                this.showToast('错误', '获取信号源信息失败', 'danger');
            }
        } catch (error) {
            console.error('切换信号源状态失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }

    async deleteSignalSource(sourceUid) {

        if (confirm('确定要删除这个信号源吗？此操作不可恢复。')) {
            try {
                const response = await fetch(`${this.apiBaseUrl}/signal_sources/${sourceUid}`, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    this.showToast('成功', '信号源删除成功', 'success');
                    // 刷新数据
                    this.loadSignalSourcesData();
                } else {
                    this.showToast('错误', '删除失败', 'danger');
                }
            } catch (error) {
                console.error('删除信号源失败:', error);
                this.showToast('错误', '网络请求失败', 'danger');
            }
        }
    }

    // 策略管理相关函数
    async editStrategy(strategyUid) {

        try {
            // 获取策略详情
            const response = await fetch(`${this.apiBaseUrl}/strategies/${strategyUid}`);
            if (response.ok) {
                const data = await response.json();
                const strategy = data.data;
                
                // 填充表单
                await this.fillStrategyForm(strategy, true);
                
                // 设置当前编辑的策略ID
                this.currentEditStrategyUid = strategyUid;
                
                // 修改模态框标题
                document.getElementById('addStrategyModalLabel').textContent = '编辑策略';
                
                // 显示模态框
                const modal = new bootstrap.Modal(document.getElementById('addStrategyModal'));
                modal.show();
            } else {
                this.showToast('错误', '获取策略详情失败', 'danger');
            }
        } catch (error) {
            console.error('获取策略详情失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }

    viewStrategyDetails(strategyUid) {

        // 这里可以实现查看详情的功能，比如显示一个只读的模态框
        this.showToast('信息', `查看策略详情: ${strategyUid}`, 'info');
    }

    async toggleStrategyStatus(strategyUid) {

        try {
            // 获取当前策略信息
            const response = await fetch(`${this.apiBaseUrl}/strategies/${strategyUid}`);
            if (response.ok) {
                const data = await response.json();
                const strategy = data.data;
                const newStatus = !strategy.enabled;
                
                // 更新状态
                const updateResponse = await fetch(`${this.apiBaseUrl}/strategies/${strategyUid}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        enabled: newStatus
                    })
                });
                
                if (updateResponse.ok) {
                    this.showToast('成功', `策略状态已${newStatus ? '启用' : '禁用'}`, 'success');
                    // 刷新数据
                    this.loadStrategiesData();
                } else {
                    this.showToast('错误', '状态更新失败', 'danger');
                }
            } else {
                this.showToast('错误', '获取策略信息失败', 'danger');
            }
        } catch (error) {
            console.error('切换策略状态失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }

    async deleteStrategy(strategyUid) {
        if (confirm('确定要删除这个策略吗？此操作不可恢复。')) {
            try {
                const response = await fetch(`${this.apiBaseUrl}/strategies/${strategyUid}`, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    this.showToast('成功', '策略删除成功', 'success');
                    // 刷新数据
                    this.loadStrategiesData();
                } else {
                    this.showToast('错误', '删除失败', 'danger');
                }
            } catch (error) {
                console.error('删除策略失败:', error);
                this.showToast('错误', '网络请求失败', 'danger');
            }
        }
    }

    // 策略搜索功能
    searchStrategies() {
        const searchTerm = document.getElementById('strategySearch').value.trim();
        
        if (!searchTerm) {
            // 如果搜索词为空，重新加载所有策略
            this.loadStrategiesData();
            return;
        }

        // 获取当前筛选状态
        const currentFilter = document.querySelector('input[name="strategyFilter"]:checked').value;
        
        // 调用带参数的加载函数
        this.loadStrategiesDataWithParams(searchTerm, currentFilter);
    }

    // 策略筛选功能
    filterStrategies(filterValue) {
        
        const searchTerm = document.getElementById('strategySearch').value.trim();
        
        // 调用带参数的加载函数
        this.loadStrategiesDataWithParams(searchTerm, filterValue);
    }

    // 带参数的策略数据加载
    async loadStrategiesDataWithParams(searchTerm = '', filterValue = 'all') {
        try {
            
            // 构建查询参数
            const params = new URLSearchParams();
            if (searchTerm) {
                params.append('name', searchTerm);
            }
            if (filterValue && filterValue !== 'all') {
                params.append('enabled', filterValue === 'enabled' ? '1' : '0');
            }

            const url = `${this.apiBaseUrl}/strategies${params.toString() ? '?' + params.toString() : ''}`;

            const response = await fetch(url);
            if (response.ok) {
                const data = await response.json();
                
                // 检查数据结构
                if (Array.isArray(data.data)) {
                    // 直接返回数组的情况
                    this.renderStrategiesTable(data.data);
                } else if (data.data && Array.isArray(data.data.strategies)) {
                    // 嵌套结构的情况
                    this.renderStrategiesTable(data.data.strategies);
                } else {
                    console.error('策略数据格式错误:', data.data);
                    this.renderStrategiesTable([]);
                }
            } else {
                console.error('加载策略数据失败:', response.statusText);
                this.renderStrategiesTable([]);
            }
        } catch (error) {
            console.error('加载策略数据失败:', error);
            this.renderStrategiesTable([]);
        }
    }

    // 规则管理相关函数
    async editRule(ruleUid) {

        try {
            // 获取规则详情
            const response = await fetch(`${this.apiBaseUrl}/rules/${ruleUid}`);
            if (response.ok) {
                const data = await response.json();
                const rule = data.data;
                
                // 填充表单
                await this.fillRuleForm(rule, true);
                
                // 设置当前编辑的规则ID
                this.currentEditRuleUid = ruleUid;
                
                // 修改模态框标题
                document.getElementById('addRuleModalLabel').textContent = '编辑规则';
                
                // 显示模态框
                const modal = new bootstrap.Modal(document.getElementById('addRuleModal'));
                modal.show();
            } else {
                this.showToast('错误', '获取规则详情失败', 'danger');
            }
        } catch (error) {
            console.error('获取规则详情失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }

    viewRuleDetails(ruleUid) {

        // 这里可以实现查看详情的功能，比如显示一个只读的模态框
        this.showToast('信息', `查看规则详情: ${ruleUid}`, 'info');
    }

    async toggleRuleStatus(ruleUid) {

        try {
            // 获取当前规则信息
            const response = await fetch(`${this.apiBaseUrl}/rules/${ruleUid}`);
            if (response.ok) {
                const data = await response.json();
                const rule = data.data;
                const newStatus = !rule.enabled;
                
                // 更新状态
                const updateResponse = await fetch(`${this.apiBaseUrl}/rules/${ruleUid}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        enabled: newStatus
                    })
                });
                
                if (updateResponse.ok) {
                    this.showToast('成功', `规则状态已${newStatus ? '启用' : '禁用'}`, 'success');
                    // 刷新数据
                    this.loadRulesData();
                } else {
                    this.showToast('错误', '状态更新失败', 'danger');
                }
            } else {
                this.showToast('错误', '获取规则信息失败', 'danger');
            }
        } catch (error) {
            console.error('切换规则状态失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }

    async deleteRule(ruleUid) {

        if (confirm('确定要删除这个规则吗？此操作不可恢复。')) {
            try {
                const response = await fetch(`${this.apiBaseUrl}/rules/${ruleUid}`, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    this.showToast('成功', '规则删除成功', 'success');
                    // 刷新数据
                    this.loadRulesData();
                } else {
                    this.showToast('错误', '删除失败', 'danger');
                }
            } catch (error) {
                console.error('删除规则失败:', error);
                this.showToast('错误', '网络请求失败', 'danger');
            }
        }
    }

    // 规则搜索功能
    searchRules() {
        const searchTerm = document.getElementById('ruleSearch').value.trim();
        
        if (!searchTerm) {
            // 如果搜索词为空，重新加载所有规则
            this.loadRulesData();
            return;
        }

        // 获取当前筛选状态
        const currentFilter = document.querySelector('input[name="ruleFilter"]:checked').value;
        
        // 调用带参数的加载函数
        this.loadRulesDataWithParams(searchTerm, currentFilter);
    }

    // 规则筛选功能
    filterRules(filterValue) {
        
        const searchTerm = document.getElementById('ruleSearch').value.trim();
        
        // 调用带参数的加载函数
        this.loadRulesDataWithParams(searchTerm, filterValue);
    }

    // 带参数的规则数据加载
    async loadRulesDataWithParams(searchTerm = '', filterValue = 'all') {
        try {
            
            // 构建查询参数
            const params = new URLSearchParams();
            if (searchTerm) {
                params.append('name', searchTerm);
            }
            if (filterValue && filterValue !== 'all') {
                params.append('enabled', filterValue === 'enabled' ? '1' : '0');
            }

            const url = `${this.apiBaseUrl}/rules${params.toString() ? '?' + params.toString() : ''}`;

            const response = await fetch(url);
            if (response.ok) {
                const data = await response.json();
                
                // 检查数据结构
                if (Array.isArray(data.data)) {
                    // 直接返回数组的情况
                    this.renderRulesTable(data.data);
                } else if (data.data && Array.isArray(data.data.rules)) {
                    // 嵌套结构的情况
                    this.renderRulesTable(data.data.rules);
                } else {
                    console.error('规则数据格式错误:', data.data);
                    this.renderRulesTable([]);
                }
            } else {
                console.error('加载规则数据失败:', response.statusText);
                this.renderRulesTable([]);
            }
        } catch (error) {
            console.error('加载规则数据失败:', error);
            this.renderRulesTable([]);
        }
    }

    // 交易记录管理相关函数
    editTrade(tradeUid) {

        this.showToast('提示', '编辑交易功能开发中', 'info');
    }

    deleteTrade(tradeUid) {

        if (confirm('确定要删除这个交易记录吗？此操作不可恢复。')) {
            this.showToast('提示', '删除交易功能开发中', 'info');
        }
    }

    // 系统操作函数
    async reloadRules() {
        try {
            this.showToast('信息', '正在重新加载规则...', 'info');
            const response = await fetch(`${this.apiBaseUrl}/reload/rules`, { method: 'POST' });
            if (response.ok) {
                this.showToast('成功', '规则重新加载成功', 'success');
            } else {
                throw new Error('重新加载失败');
            }
        } catch (error) {
            console.error('重新加载规则失败:', error);
            this.showToast('错误', '重新加载规则失败', 'danger');
        }
    }

    async reloadCustomers() {
        try {
            this.showToast('信息', '正在重新加载客户...', 'info');
            const response = await fetch(`${this.apiBaseUrl}/reload/customers`, { method: 'POST' });
            if (response.ok) {
                this.showToast('成功', '客户重新加载成功', 'success');
            } else {
                throw new Error('重新加载失败');
            }
        } catch (error) {
            console.error('重新加载客户失败:', error);
            this.showToast('错误', '重新加载客户失败', 'danger');
        }
    }

    async reloadSignalSources() {
        try {
            this.showToast('信息', '正在重新加载信号源...', 'info');
            const response = await fetch(`${this.apiBaseUrl}/reload/signal_sources`, { method: 'POST' });
            if (response.ok) {
                this.showToast('成功', '信号源重新加载成功', 'success');
            } else {
                throw new Error('重新加载失败');
            }
        } catch (error) {
            console.error('重新加载信号源失败:', error);
            this.showToast('error', '重新加载信号源失败', 'danger');
        }
    }

    async reloadTradeService() {
        try {
            this.showToast('信息', '正在重新加载交易服务...', 'info');
            const response = await fetch(`${this.apiBaseUrl}/reload/trade_service`, { method: 'POST' });
            if (response.ok) {
                this.showToast('成功', '交易服务重新加载成功', 'success');
            } else {
                throw new Error('重新加载失败');
            }
        } catch (error) {
            console.error('重新加载交易服务失败:', error);
            this.showToast('错误', '重新加载交易服务失败', 'danger');
        }
    }

    // 加载交易数据
    async loadTradesData() {
        try {
            const page = this.currentTradesPage || 1;
            const params = new URLSearchParams({
                page: page.toString(),
                page_size: '10'
            });

            Object.entries(this.tradesSearchParams).forEach(([key, value]) => {
                if (value && value.trim() !== '') {
                    params.append(key, value.trim());
                }
            });

            const response = await fetch(`${this.apiBaseUrl}/trades?${params.toString()}`);
            if (response.ok) {
                const data = await response.json();
                this.renderTradesTable(data.data);
                this.updateTradesCount(data.data.pagination);
            } else {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
        } catch (error) {
            console.error('加载交易数据失败:', error);
            this.showToast('错误', '加载交易数据失败', 'danger');
        }
    }

    // 静默加载交易数据（用于自动刷新）
    async loadTradesDataSilent() {
        try {
            const page = this.currentTradesPage || 1;
            const params = new URLSearchParams({
                page: page.toString(),
                page_size: '10'
            });

            Object.entries(this.tradesSearchParams).forEach(([key, value]) => {
                if (value && value.trim() !== '') {
                    params.append(key, value.trim());
                }
            });

            const response = await fetch(`${this.apiBaseUrl}/trades?${params.toString()}`);
            if (response.ok) {
                const data = await response.json();
                this.renderTradesTable(data.data);
                this.updateTradesCount(data.data.pagination);
            }
        } catch (error) {
            console.error('静默加载交易数据失败:', error);
        }
    }

    // 渲染交易表格
    renderTradesTable(data) {
        const tbody = document.getElementById('tradesTableBody');
        if (!tbody) {
            return;
        }

        // 确保 data 是对象且包含 trades 数组
        if (!data || !Array.isArray(data.trades)) {
            tbody.innerHTML = '<tr><td colspan="11" class="text-center">数据格式错误</td></tr>';
            return;
        }

        if (data.trades.length === 0) {
            tbody.innerHTML = '<tr><td colspan="11" class="text-center">暂无交易数据</td></tr>';
            return;
        }

        const rowsHtml = data.trades.map(trade => `
            <tr>
                <td>${trade.trade_uid || '未知'}</td>
                <td>${trade.customer_uid || '未知'}</td>
                <td>${trade.customer_name || '未知'}</td>
                <td>${trade.symbol || '未知'}</td>
                <td>${trade.direction === 'buy' ? '<span class="badge bg-success">买入</span>' : '<span class="badge bg-danger">卖出</span>'}</td>
                <td>${trade.pos_side === 'long' ? '多头' : '空头'}</td>
                <td>${this.formatNumber(trade.volume_contract || trade.sz || 0)}</td>
                <td>${this.formatNumber(trade.open_px || 0)}</td>
                <td>${trade.status === 'open' ? '<span class="badge bg-warning">开仓中</span>' : '<span class="badge bg-success">已平仓</span>'}</td>
                <td>${this.formatTime(trade.created_at)}</td>
                <td>
                    <div class="btn-group" role="group">
                        <button class="btn btn-sm btn-outline-info" onclick="app.viewTradeDetails('${trade.trade_uid}', '${trade.customer_uid}', '${trade.customer_name || ''}', '${trade.symbol}', '${trade.direction}', '${trade.pos_side}', '${trade.volume_contract || trade.sz}', '${trade.open_px}', '${trade.status}', '${trade.created_at}')" title="查看详情">
                            <i class="bi bi-eye"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-warning" onclick="app.closeTrade('${trade.trade_uid}')" ${trade.status === 'closed' ? 'disabled' : ''} title="平仓">
                            <i class="bi bi-x-circle"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-primary" onclick="app.editTrade('${trade.trade_uid}')" title="编辑">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="app.deleteTrade('${trade.trade_uid}')" title="删除">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');

        tbody.innerHTML = rowsHtml;

        if (data.pagination) {
            this.renderTradesPagination(data.pagination);
        }
    }

    // 渲染交易分页
    renderTradesPagination(pagination) {
        const container = document.getElementById('tradesPagination');
        if (!container) return;

        const { total, page, page_size, total_pages } = pagination;
        
        let paginationHtml = '';
        
        // 上一页
        if (page > 1) {
            paginationHtml += `<li class="page-item"><a class="page-link" href="#" onclick="app.loadTradesPage(${page - 1})">上一页</a></li>`;
        }
        
        // 页码
        for (let i = Math.max(1, page - 2); i <= Math.min(total_pages, page + 2); i++) {
            paginationHtml += `<li class="page-item ${i === page ? 'active' : ''}"><a class="page-link" href="#" onclick="app.loadTradesPage(${i})">${i}</a></li>`;
        }
        
        // 下一页
        if (page < total_pages) {
            paginationHtml += `<li class="page-item"><a class="page-link" href="#" onclick="app.loadTradesPage(${page + 1})">下一页</a></li>`;
        }
        
        container.innerHTML = paginationHtml;
    }

    // 加载交易页面
    async loadTradesPage(page) {
        this.currentTradesPage = page;
        await this.loadTradesData();
    }

    // 搜索交易
    async searchTrades(event) {
        event.preventDefault();
        
        this.tradesSearchParams = {
            customer_uid: document.getElementById('searchCustomerUid').value,
            customer_name: document.getElementById('searchCustomerName').value,
            symbol: document.getElementById('searchSymbol').value,
            direction: document.getElementById('searchDirection').value,
            pos_side: document.getElementById('searchPosSide').value,
            status: document.getElementById('searchStatus').value
        };
        
        this.currentTradesPage = 1;
        await this.loadTradesData();
        
        this.showToast('成功', '搜索完成', 'success');
    }

    // 重置交易搜索
    async resetTradesSearch() {
        document.getElementById('searchCustomerUid').value = '';
        document.getElementById('searchCustomerName').value = '';
        document.getElementById('searchSymbol').value = '';
        document.getElementById('searchDirection').value = '';
        document.getElementById('searchPosSide').value = '';
        document.getElementById('searchStatus').value = '';
        
        this.tradesSearchParams = {};
        this.currentTradesPage = 1;
        await this.loadTradesData();
        
        this.showToast('信息', '搜索条件已重置', 'info');
    }

    // 更新交易记录数量显示
    updateTradesCount(pagination) {
        const countElement = document.getElementById('tradesCount');
        if (countElement && pagination) {
            countElement.textContent = `共 ${pagination.total} 条记录`;
        }
    }

    // 查看交易详情
    viewTradeDetails(tradeUid, customerUid, customerName, symbol, direction, posSide, volume, openPx, status, createdAt) {
        // 填充弹窗数据
        document.getElementById('detailTradeUid').textContent = tradeUid;
        document.getElementById('detailCustomerUid').textContent = customerUid || '系统';
        document.getElementById('detailCustomerName').textContent = customerName || '未知';
        document.getElementById('detailSymbol').textContent = symbol;
        document.getElementById('detailDirection').textContent = direction === 'buy' ? '买入' : '卖出';
        document.getElementById('detailPosSide').textContent = posSide === 'long' ? '多头' : '空头';
        document.getElementById('detailVolume').textContent = this.formatNumber(volume);
        document.getElementById('detailOpenPx').textContent = this.formatNumber(openPx);
        document.getElementById('detailStatus').textContent = this.getStatusText(status);
        document.getElementById('detailCreatedAt').textContent = this.formatTime(createdAt);
        
        // 设置状态样式
        const statusElement = document.getElementById('detailStatus');
        statusElement.className = this.getStatusClass(status);
        
        // 填充其他信息（模拟数据）
        document.getElementById('detailOrderId').textContent = `ord_${tradeUid.slice(-8)}`;
        document.getElementById('detailLeverage').textContent = '10x';
        document.getElementById('detailMargin').textContent = this.formatNumber(volume * openPx * 0.1);
        document.getElementById('detailFee').textContent = this.formatNumber(volume * openPx * 0.0005);
        
        // 计算盈亏（模拟数据）
        const currentPrice = openPx * (1 + (Math.random() - 0.5) * 0.1);
        const unrealizedPnl = direction === 'buy' ? 
            (currentPrice - openPx) * volume : 
            (openPx - currentPrice) * volume;
        const returnRate = (unrealizedPnl / (openPx * volume * 0.1)) * 100;
        
        document.getElementById('detailCurrentPx').textContent = this.formatNumber(currentPrice);
        document.getElementById('detailUnrealizedPnl').textContent = this.formatNumber(unrealizedPnl);
        document.getElementById('detailReturnRate').textContent = `${returnRate.toFixed(2)}%`;
        document.getElementById('detailRiskLevel').innerHTML = this.getRiskLevel(returnRate);
        
        // 生成操作按钮
        this.generateTradeActionButtons(tradeUid, status);
        
        // 显示弹窗
        const modal = new bootstrap.Modal(document.getElementById('tradeDetailModal'));
        modal.show();
    }

    // 生成交易操作按钮
    generateTradeActionButtons(tradeUid, status) {
        const container = document.getElementById('tradeActionButtons');
        let buttonsHtml = '';
        
        if (status === 'open') {
            buttonsHtml = `
                <button type="button" class="btn btn-warning me-2" onclick="app.closeTrade('${tradeUid}')">
                    <i class="bi bi-x-circle"></i> 平仓
                </button>
                <button type="button" class="btn btn-info me-2" onclick="app.modifyTrade('${tradeUid}')">
                    <i class="bi bi-pencil"></i> 修改
                </button>
            `;
        } else if (status === 'closed') {
            buttonsHtml = `
                <button type="button" class="btn btn-secondary me-2" disabled>
                    <i class="bi bi-check-circle"></i> 已平仓
                </button>
            `;
        } else {
            buttonsHtml = `
                <button type="button" class="btn btn-primary me-2" onclick="app.retryTrade('${tradeUid}')">
                    <i class="bi bi-arrow-clockwise"></i> 重试
                </button>
            `;
        }
        
        container.innerHTML = buttonsHtml;
    }

    // 获取状态文本
    getStatusText(status) {
        const statusMap = {
            'open': '开仓中',
            'closed': '已平仓',
            'pending': '待处理',
            'failed': '失败'
        };
        return statusMap[status] || status;
    }

    // 获取状态样式类
    getStatusClass(status) {
        const classMap = {
            'open': 'badge bg-warning',
            'closed': 'badge bg-success',
            'pending': 'badge bg-secondary',
            'failed': 'badge bg-danger'
        };
        return classMap[status] || 'badge bg-secondary';
    }

    // 获取订单状态徽章样式
    getOrderStatusBadge(status) {
        const badgeMap = {
            'pending': 'secondary',
            'live': 'warning',
            'filled': 'success',
            'canceled': 'danger',
            'expired': 'dark',
            'rejected': 'danger'
        };
        return badgeMap[status] || 'secondary';
    }

    // 获取订单状态文本
    getOrderStatusText(status) {
        const statusMap = {
            'pending': '待处理',
            'live': '活跃',
            'filled': '已成交',
            'canceled': '已取消',
            'expired': '已过期',
            'rejected': '已拒绝'
        };
        return statusMap[status] || status;
    }

    // 获取风险等级
    getRiskLevel(returnRate) {
        if (returnRate > 20) return '<span class="badge bg-success">低风险</span>';
        if (returnRate > 10) return '<span class="badge bg-warning">中风险</span>';
        if (returnRate > 0) return '<span class="badge bg-info">较低风险</span>';
        if (returnRate > -10) return '<span class="badge bg-warning">较高风险</span>';
        return '<span class="badge bg-danger">高风险</span>';
    }

    // 平仓交易
    async closeTrade(tradeUid) {
        if (!confirm(`确定要平仓交易 ${tradeUid} 吗？此操作将调用交易所平仓并更新数据库状态。`)) {
            return;
        }

        try {
            this.showToast('信息', '正在执行平仓操作...', 'info');
            
            // 首先获取交易详情
            const tradeResponse = await fetch(`${this.apiBaseUrl}/trades`);
            if (!tradeResponse.ok) {
                throw new Error('获取交易数据失败');
            }
            
            const tradeData = await tradeResponse.json();
            const trades = Array.isArray(tradeData.data) ? tradeData.data : (tradeData.data?.trades || []);
            const trade = trades.find(t => t.trade_uid === tradeUid);
            
            if (!trade) {
                throw new Error('交易记录不存在');
            }
            
            if (trade.status === 'closed') {
                throw new Error('交易已经平仓');
            }
            
            // 使用手动平仓接口
            const response = await fetch(`${this.apiBaseUrl}/manual/close_position`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    customer_uid: trade.customer_uid,
                    symbol: trade.symbol,
                    pos_side: trade.pos_side,
                    close_sz: parseFloat(trade.volume_contract || trade.sz || 0),
                    is_demo: trade.is_demo || 1,
                    reason: '前端手动平仓'
                })
            });

            if (response.ok) {
                const result = await response.json();
                this.showToast('成功', `交易平仓成功: ${result.message}`, 'success');
                this.loadTradesData();
                
                const modal = bootstrap.Modal.getInstance(document.getElementById('tradeDetailModal'));
                if (modal) {
                    modal.hide();
                }
            } else {
                const errorData = await response.json();
                throw new Error(errorData.message || '平仓失败');
            }
        } catch (error) {
            console.error('平仓失败:', error);
            this.showToast('错误', `平仓失败: ${error.message}`, 'danger');
        }
    }

    // 修改交易
    modifyTrade(tradeUid) {
        this.showToast('信息', `修改交易 ${tradeUid} 功能开发中...`, 'info');
    }

    // 重试交易
    async retryTrade(tradeUid) {
        if (!confirm(`确定要重试交易 ${tradeUid} 吗？`)) {
            return;
        }

        try {
            const response = await fetch(`${this.apiBaseUrl}/trades/${tradeUid}/retry`, {
                method: 'PUT'
            });

            if (response.ok) {
                this.showToast('成功', '交易重试成功', 'success');
                this.loadTradesData();
            } else {
                throw new Error('重试失败');
            }
        } catch (error) {
            console.error('重试失败:', error);
            this.showToast('错误', error.message, 'danger');
        }
    }

    // 加载其他页面数据
    async loadSignalSourcesData() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/signal_sources`);
            if (response.ok) {
                const data = await response.json();
                
                // 检查数据结构
                if (Array.isArray(data.data)) {
                    // 直接返回数组的情况
                    this.renderSignalSourcesTable(data.data);
                } else if (data.data && Array.isArray(data.data.sources)) {
                    // 嵌套结构的情况
                    this.renderSignalSourcesTable(data.data.sources);
                } else {
                    console.error('信号源数据格式错误:', data.data);
                    this.renderSignalSourcesTable([]);
                }
            } else {
                console.error('加载信号源数据失败:', response.statusText);
                this.renderSignalSourcesTable([]);
            }
        } catch (error) {
            console.error('加载信号源数据失败:', error);
            this.renderSignalSourcesTable([]);
        }
    }

    async loadStrategiesData() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/strategies`);
            if (response.ok) {
                const data = await response.json();
                
                // 检查数据结构
                if (Array.isArray(data.data)) {
                    // 直接返回数组的情况
                    this.renderStrategiesTable(data.data);
                } else if (data.data && Array.isArray(data.data.strategies)) {
                    // 嵌套结构的情况
                    this.renderStrategiesTable(data.data.strategies);
                } else {
                    console.error('策略数据格式错误:', data.data);
                    this.renderStrategiesTable([]);
                }
            } else {
                console.error('加载策略数据失败:', response.statusText);
                this.renderStrategiesTable([]);
            }
        } catch (error) {
            console.error('加载策略数据失败:', error);
            this.renderStrategiesTable([]);
        }
    }

    async loadRulesData() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/rules`);
            if (response.ok) {
                const data = await response.json();
                
                // 检查数据结构
                if (Array.isArray(data.data)) {
                    // 直接返回数组的情况
                    this.renderRulesTable(data.data);
                } else if (data.data && Array.isArray(data.data.rules)) {
                    // 嵌套结构的情况
                    this.renderRulesTable(data.data.rules);
                } else {
                    console.error('规则数据格式错误:', data.data);
                    this.renderRulesTable([]);
                }
            } else {
                console.error('加载规则数据失败:', response.statusText);
                this.renderRulesTable([]);
            }
        } catch (error) {
            console.error('加载规则数据失败:', error);
            this.renderRulesTable([]);
        }
    }

    async loadRiskControlData() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/risk/config`);
            if (response.ok) {
                const data = await response.json();
                this.updateRiskControlForm(data.data);
            }
        } catch (error) {
            console.error('加载风控数据失败:', error);
        }
    }

    async loadSystemData() {
        try {
            
            const healthResponse = await fetch(`${this.apiBaseUrl}/health`);
            if (healthResponse.ok) {
                const healthData = await healthResponse.json();
                this.updateSystemHealth(healthData.data);
                this.updateHealthCheckResults(healthData.data);
            } else {
                console.error('系统健康检查失败:', healthResponse.statusText);
                this.updateHealthCheckResults(null, '系统健康检查失败');
            }

            const statsResponse = await fetch(`${this.apiBaseUrl}/stats/system`);
            if (statsResponse.ok) {
                const statsData = await statsResponse.json();
                this.updateSystemStats(statsData.data);
            } else {
                console.error('系统统计获取失败:', statsResponse.statusText);
            }

            // 加载系统日志
            const logsResponse = await fetch(`${this.apiBaseUrl}/system/logs?limit=${this.systemLogsPageSize}&page=${this.systemLogsPage}`);
            if (logsResponse.ok) {
                const logsData = await logsResponse.json();
                this.updateSystemLogs(logsData.data || []);
                this.updateSystemLogsPagination(logsData.count || 0);
            } else {
                console.error('系统日志获取失败:', logsResponse.statusText);
                this.updateSystemLogs([]);
                this.updateSystemLogsPagination(0);
            }
        } catch (error) {
            console.error('加载系统数据失败:', error);
            this.updateHealthCheckResults(null, '加载系统数据失败');
        }
    }

    // 渲染其他表格
    renderSignalSourcesTable(sources) {
        
        const tbody = document.getElementById('signalSourcesTableBody');
        if (!tbody) {
            console.warn('未找到 signalSourcesTableBody 元素');
            return;
        }

        // 确保 sources 是数组
        if (!Array.isArray(sources)) {
            console.warn('sources 不是数组:', sources);
            tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted">数据格式错误</td></tr>';
            return;
        }

        if (sources.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted">暂无信号源数据</td></tr>';
            return;
        }

        const rowsHtml = sources.map(source => `
            <tr>
                <td>${source.source_uid || '未知'}</td>
                <td>${source.name || '未设置'}</td>
                <td>${source.exchange || 'OKX'}</td>
                <td>${this.formatNumber(source.init_assets || 0)}</td>
                <td>${this.formatNumber(source.current_asset || 0)}</td>
                <td>${source.leverage || 1}</td>
                <td>${source.enabled ? '<span class="badge bg-success">启用</span>' : '<span class="badge bg-secondary">禁用</span>'}</td>
                <td>${source.stop_loss_enabled ? '<span class="badge bg-warning">已设置</span>' : '<span class="badge bg-light text-dark">未设置</span>'}</td>
                <td>
                    <div class="btn-group" role="group">
                        <button class="btn btn-sm btn-outline-primary" onclick="app.editSignalSource('${source.source_uid}')" title="编辑">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-info" onclick="app.viewSignalSourceDetails('${source.source_uid}')" title="查看详情">
                            <i class="bi bi-eye"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-warning" onclick="app.toggleSignalSourceStatus('${source.source_uid}')" title="${source.enabled ? '禁用' : '启用'}">
                            <i class="bi bi-${source.enabled ? 'pause' : 'play'}"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="app.deleteSignalSource('${source.source_uid}')" title="删除">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');

        tbody.innerHTML = rowsHtml;
    }

    renderStrategiesTable(strategies) {

        const tbody = document.getElementById('strategiesTableBody');
        if (!tbody) {
            console.warn('未找到 strategiesTableBody 元素');
            return;
        }

        // 确保 strategies 是数组
        if (!Array.isArray(strategies)) {
            console.warn('strategies 不是数组:', strategies);
            tbody.innerHTML = '<tr><td colspan="7" class="text-center">数据格式错误</td></tr>';
            return;
        }

        if (strategies.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center">暂无策略数据</td></tr>';
            return;
        }

        const rowsHtml = strategies.map(strategy => `
            <tr>
                <td>${strategy.strategy_uid || '未知'}</td>
                <td>${strategy.name || '未设置'}</td>
                <td>${strategy.signal_sources || '未设置'}</td>
                <td>${strategy.signal_source_count || 0}</td>
                <td>${strategy.enabled ? '<span class="badge bg-success">启用</span>' : '<span class="badge bg-secondary">禁用</span>'}</td>
                <td>${this.formatTime(strategy.created_at)}</td>
                <td>
                    <div class="btn-group" role="group">
                        <button class="btn btn-sm btn-outline-primary" onclick="app.editStrategy('${strategy.strategy_uid}')" title="编辑">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-info" onclick="app.viewStrategyDetails('${strategy.strategy_uid}')" title="查看详情">
                            <i class="bi bi-eye"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-warning" onclick="app.toggleStrategyStatus('${strategy.strategy_uid}')" title="${strategy.enabled ? '禁用' : '启用'}">
                            <i class="bi bi-${strategy.enabled ? 'pause' : 'play'}"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="app.deleteStrategy('${strategy.strategy_uid}')" title="删除">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');

        tbody.innerHTML = rowsHtml;
    }

    renderRulesTable(rules) {
        const tbody = document.getElementById('rulesTableBody');
        if (!tbody) {
            console.warn('未找到 rulesTableBody 元素');
            return;
        }

        // 确保 rules 是数组
        if (!Array.isArray(rules)) {
            console.warn('rules 不是数组:', rules);
            tbody.innerHTML = '<tr><td colspan="7" class="text-center">数据格式错误</td></tr>';
            return;
        }

        if (rules.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center">暂无规则数据</td></tr>';
            return;
        }

        const rowsHtml = rules.map(rule => `
            <tr>
                <td>${rule.rule_uid || '未知'}</td>
                <td>${rule.name || '未设置'}</td>
                <td>${rule.strategy_name || '未设置'}</td>
                <td>${Math.round(rule.position_ratio || 0)}：1</td>
                <td>${parseFloat(rule.max_leverage || 1).toFixed(1)}</td>
                <td>${rule.enabled ? '<span class="badge bg-success">启用</span>' : '<span class="badge bg-secondary">禁用</span>'}</td>
                <td>
                    <div class="btn-group" role="group">
                        <button class="btn btn-sm btn-outline-primary" onclick="app.editRule('${rule.rule_uid}')" title="编辑">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-info" onclick="app.viewRuleDetails('${rule.rule_uid}')" title="查看详情">
                            <i class="bi bi-eye"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-warning" onclick="app.toggleRuleStatus('${rule.rule_uid}')" title="${rule.enabled ? '禁用' : '启用'}">
                            <i class="bi bi-${rule.enabled ? 'pause' : 'play'}"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="app.deleteRule('${rule.rule_uid}')" title="删除">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');

        tbody.innerHTML = rowsHtml;
    }

    updateRiskControlForm(config) {
        if (config.max_positions_per_direction) {
            document.getElementById('maxPositionsPerDirection').value = config.max_positions_per_direction;
        }
        if (config.min_trade_interval_minutes) {
            document.getElementById('minTradeIntervalMinutes').value = config.min_trade_interval_minutes;
        }
        if (config.max_leverage) {
            document.getElementById('maxLeverage').value = config.max_leverage;
        }
        if (config.enable_time_interval_check !== undefined) {
            document.getElementById('enableTimeIntervalCheck').checked = config.enable_time_interval_check;
        }
        if (config.enable_position_limit_check !== undefined) {
            document.getElementById('enablePositionLimitCheck').checked = config.enable_position_limit_check;
        }
    }

    updateSystemHealth(health) {
        if (!health) return;
        
        const elements = {
            'db-status': document.getElementById('db-status'),
            'ws-status': document.getElementById('ws-status'),
            'trade-service-status': document.getElementById('trade-service-status'),
            'memory-usage': document.getElementById('memory-usage')
        };

        if (elements['db-status']) {
            const isHealthy = health.database === 'connected';
            elements['db-status'].textContent = isHealthy ? '正常' : '异常';
            elements['db-status'].className = isHealthy ? 'text-success' : 'text-danger';
        }

        if (elements['ws-status']) {
            const isHealthy = health.websocket === 'connected';
            elements['ws-status'].textContent = isHealthy ? '正常' : '异常';
            elements['ws-status'].className = isHealthy ? 'text-success' : 'text-danger';
        }

        if (elements['trade-service-status']) {
            const isHealthy = health.trade_service === 'running';
            elements['trade-service-status'].textContent = isHealthy ? '正常' : '异常';
            elements['trade-service-status'].className = isHealthy ? 'text-success' : 'text-danger';
        }

        if (elements['memory-usage']) {
            if (health.memory && health.memory.usage) {
                // 使用徽章样式显示内存使用，更清晰可见
                const usage = health.memory.usage;
                let badgeClass = 'bg-secondary';
                let textColor = 'text-white';
                
                if (health.memory.status === 'normal') {
                    badgeClass = 'bg-success';
                    textColor = 'text-white';
                } else if (health.memory.status === 'warning') {
                    badgeClass = 'bg-warning';
                    textColor = 'text-dark';
                } else if (health.memory.status === 'critical') {
                    badgeClass = 'bg-danger';
                    textColor = 'text-white';
                }
                
                elements['memory-usage'].innerHTML = `<span class="badge ${badgeClass} ${textColor} fs-6">${usage}</span>`;
            } else {
                elements['memory-usage'].innerHTML = '<span class="badge bg-secondary text-white">未知</span>';
            }
        }
    }

    updateSystemStats(stats) {
        const elements = {
            'cpu-usage': document.getElementById('cpu-usage'),
            'memory-usage-stats': document.getElementById('memory-usage-stats'),
            'disk-usage': document.getElementById('disk-usage'),
            'network-status': document.getElementById('network-status'),
            'db-connections': document.getElementById('db-connections'),
            'websocket-connections': document.getElementById('websocket-connections'),
            'active-tasks': document.getElementById('active-tasks'),
            'uptime': document.getElementById('uptime')
        };

        if (elements['cpu-usage']) {
            elements['cpu-usage'].textContent = `${stats.cpu_usage || 0}%`;
        }
        if (elements['memory-usage-stats']) {
            elements['memory-usage-stats'].textContent = stats.memory_usage || '0MB';
        }
        if (elements['disk-usage']) {
            elements['disk-usage'].textContent = `${stats.disk_usage || 0}%`;
        }
        if (elements['network-status']) {
            elements['network-status'].textContent = stats.network_status || '正常';
        }
        if (elements['db-connections']) {
            elements['db-connections'].textContent = stats.db_connections || 0;
        }
        if (elements['websocket-connections']) {
            elements['websocket-connections'].textContent = stats.websocket_connections || 0;
        }
        if (elements['active-tasks']) {
            elements['active-tasks'].textContent = stats.active_tasks || 0;
        }
        if (elements['uptime']) {
            elements['uptime'].textContent = stats.uptime || '0小时';
        }
    }

    updateSystemLogs(logs) {
        const container = document.getElementById('systemLogs');
        if (!container) {
            console.warn('未找到 systemLogs 元素');
            return;
        }

        if (!Array.isArray(logs) || logs.length === 0) {
            container.innerHTML = '<div class="text-center text-muted">暂无系统日志</div>';
            return;
        }

        const logsHtml = logs.map(log => {
            let badgeClass = 'bg-secondary';
            let icon = 'bi-info-circle';
            
            switch (log.level) {
                case 'info':
                    badgeClass = 'bg-info';
                    icon = 'bi-info-circle';
                    break;
                case 'warning':
                    badgeClass = 'bg-warning';
                    icon = 'bi-exclamation-triangle';
                    break;
                case 'error':
                    badgeClass = 'bg-danger';
                    icon = 'bi-x-circle';
                    break;
                case 'success':
                    badgeClass = 'bg-success';
                    icon = 'bi-check-circle';
                    break;
            }

            return `
                <div class="log-item mb-2 p-2 border rounded">
                    <div class="d-flex justify-content-between align-items-start">
                        <div class="flex-grow-1">
                            <div class="d-flex align-items-center mb-1">
                                <span class="badge ${badgeClass} me-2">
                                    <i class="bi ${icon}"></i>
                                    ${log.level.toUpperCase()}
                                </span>
                                <strong>${log.title || '系统事件'}</strong>
                            </div>
                            <div class="text-muted small">${log.message || ''}</div>
                        </div>
                        <div class="text-muted small ms-2">
                            ${this.formatDateTime(log.timestamp)}
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        container.innerHTML = logsHtml;
    }

    // 加载系统日志
    async loadSystemLogs() {
        try {

            // 更新调试信息
            this.updateDebugInfo(`正在加载... 第${this.systemLogsPage}页，每页${this.systemLogsPageSize}条`);
            
            const url = `${this.apiBaseUrl}/system/logs?limit=${this.systemLogsPageSize}&page=${this.systemLogsPage}`;
            
            const logsResponse = await fetch(url);
            
            if (logsResponse.ok) {
                const logsData = await logsResponse.json();
                
                this.updateSystemLogs(logsData.data || []);
                this.updateSystemLogsPagination(logsData.count || 0);
            } else {
                console.error('系统日志获取失败:', logsResponse.statusText);
                this.updateSystemLogs([]);
                this.updateSystemLogsPagination(0);
                this.updateDebugInfo(`加载失败: ${logsResponse.statusText}`);
            }
        } catch (error) {
            console.error('系统日志请求失败:', error);
            this.updateSystemLogs([]);
            this.updateSystemLogsPagination(0);
            this.updateDebugInfo(`请求失败: ${error.message}`);
        }
    }

    // 测试系统日志分页功能
    testSystemLogsPagination() {

        // 测试按钮元素是否存在
        const refreshBtn = document.getElementById('refreshSystemLogsBtn');
        const testBtn = document.getElementById('testSystemLogsPaginationBtn');
        const prevBtn = document.getElementById('systemLogsPrevBtn');
        const nextBtn = document.getElementById('systemLogsNextBtn');
        
        // 测试页面大小选择器
        const pageSizeSelect = document.getElementById('systemLogsPageSize');
        
        // 模拟一些测试数据
        const testTotal = 25;
        this.updateSystemLogsPagination(testTotal);
        
        // 测试分页控件是否显示
        const pagination = document.getElementById('systemLogsPagination');
        if (pagination) {
        }
        
        // 测试手动调用loadSystemLogs
        this.loadSystemLogs();
        
    }

    // 更新系统日志分页控件
    updateSystemLogsPagination(total) {
        this.systemLogsTotal = total;
        
        // 更新调试信息
        this.updateDebugInfo(`总数: ${total}, 当前页: ${this.systemLogsPage}, 每页: ${this.systemLogsPageSize}`);
        
        const pagination = document.getElementById('systemLogsPagination');
        const totalSpan = document.getElementById('systemLogsTotal');
        const prevBtn = document.getElementById('systemLogsPrevBtn');
        const nextBtn = document.getElementById('systemLogsNextBtn');
        
        // 检查所有必需的元素是否存在
        if (!pagination) {
            console.warn('分页容器元素未找到: systemLogsPagination');
            return;
        }
        
        if (!totalSpan) {
            console.warn('总数元素未找到: systemLogsTotal');
            return;
        }
        
        if (!prevBtn) {
            console.warn('上一页按钮未找到: systemLogsPrevBtn');
            return;
        }
        
        if (!nextBtn) {
            console.warn('下一页按钮未找到: systemLogsNextBtn');
            return;
        }
        
        if (total === 0) {
            pagination.style.display = 'none';
            return;
        }
        
        // 显示分页控件
        pagination.style.display = 'flex';
        
        // 更新总数
        totalSpan.textContent = total;
        
        // 计算最大页数
        const maxPage = Math.ceil(total / this.systemLogsPageSize);
        
        // 更新按钮状态
        prevBtn.classList.toggle('disabled', this.systemLogsPage <= 1);
        nextBtn.classList.toggle('disabled', this.systemLogsPage >= maxPage);
        
        // 显示当前页信息
        const currentPageInfo = document.createElement('span');
        currentPageInfo.className = 'text-muted ms-2';
        currentPageInfo.textContent = `第 ${this.systemLogsPage} 页，共 ${maxPage} 页`;
        
        // 移除旧的页信息
        const oldPageInfo = pagination.querySelector('.text-muted.ms-2');
        if (oldPageInfo) {
            oldPageInfo.remove();
        }
        
        // 添加新的页信息 - 添加安全检查
        try {
            const dFlexContainer = pagination.querySelector('.d-flex');
            if (dFlexContainer) {
                dFlexContainer.appendChild(currentPageInfo);
            } else {
                // 如果没有 .d-flex 容器，直接添加到分页容器
                pagination.appendChild(currentPageInfo);
            }
        } catch (error) {
            console.error('添加页信息时出错:', error);
            // 如果出错，尝试添加到第一个可用的容器
            const firstContainer = pagination.querySelector('div') || pagination;
            firstContainer.appendChild(currentPageInfo);
        }
    }

    getMemoryStatusBadge(memory) {
        
        if (!memory || !memory.status) {
            return 'secondary'; // 未知状态，灰色
        }
        
        let badgeClass;
        switch (memory.status) {
            case 'normal':
                badgeClass = 'success'; // 正常状态，绿色
                break;
            case 'warning':
                badgeClass = 'warning'; // 警告状态，黄色
                break;
            case 'critical':
                badgeClass = 'danger'; // 危险状态，红色
                break;
            default:
                badgeClass = 'secondary'; // 默认灰色
                break;
        }
        
        return badgeClass;
    }

    updateHealthCheckResults(health, errorMessage = null) {
        const container = document.getElementById('healthCheckResults');
        if (!container) {
            console.warn('未找到 healthCheckResults 元素');
            return;
        }

        if (errorMessage) {
            container.innerHTML = `
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle"></i>
                    ${errorMessage}
                </div>
            `;
            return;
        }

        if (!health) {
            container.innerHTML = `
                <div class="text-center text-muted">
                    <i class="bi bi-question-circle"></i>
                    系统健康状态未知
                </div>
            `;
            return;
        }

        const healthItems = [
            {
                name: '数据库连接',
                status: health.database === 'connected' ? 'success' : 'danger',
                icon: 'bi-database-fill',
                text: health.database === 'connected' ? '正常' : '异常'
            },
            {
                name: 'WebSocket连接',
                status: health.websocket === 'connected' ? 'success' : 'danger',
                icon: 'bi-wifi',
                text: health.websocket === 'connected' ? '正常' : '异常'
            },
            {
                name: '交易服务',
                status: health.trade_service === 'running' ? 'success' : 'danger',
                icon: 'bi-gear-fill',
                text: health.trade_service === 'running' ? '运行中' : '异常'
            },
            {
                name: '内存使用',
                status: this.getMemoryStatusBadge(health.memory),
                icon: 'bi-memory',
                text: health.memory?.usage || '未知',
                isMemory: true
            }
        ];

        const healthHtml = healthItems.map(item => `
            <div class="d-flex justify-content-between align-items-center mb-2">
                <div class="d-flex align-items-center">
                    <i class="bi ${item.icon} me-2"></i>
                    <span>${item.name}</span>
                </div>
                <span class="badge bg-${item.status} ${item.isMemory ? 'fs-6' : ''}">${item.text}</span>
            </div>
        `).join('');

        container.innerHTML = `
            <div class="health-check-results">
                ${healthHtml}
                <div class="mt-3 text-center">
                    <small class="text-muted">
                        <i class="bi bi-clock"></i>
                        最后检查时间: ${new Date().toLocaleString('zh-CN')}
                    </small>
                </div>
            </div>
        `;
    }

    // 工具函数
    formatNumber(num) {
        if (num === null || num === undefined) return '0';
        return parseFloat(num).toLocaleString('zh-CN', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }

    formatTime(timestamp) {
        if (!timestamp) return '未知';
        try {
            const date = new Date(timestamp);
            if (isNaN(date.getTime())) {
                return timestamp; // 如果无法解析，直接返回原字符串
            }
            return date.toLocaleString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        } catch (e) {
            return timestamp || '未知';
        }
    }

    showToast(title, message, type = 'info') {
        // 简单的提示实现
        alert(`${title}: ${message}`);
    }

    // 其他功能函数
    refreshCurrentPage() {
        this.loadPageData(this.currentPage);
    }

    exportCurrentPageData() {
        this.showToast('信息', '导出功能开发中...', 'info');
    }

    logout() {
        if (confirm('确定要退出登录吗？')) {
            this.showToast('信息', '退出登录功能开发中...', 'info');
        }
    }

    // 客户搜索功能
    searchCustomers() {
        const searchTerm = document.getElementById('customerSearch').value.trim();
        
        if (!searchTerm) {
            // 如果搜索词为空，重新加载所有客户
            this.loadCustomersData();
            return;
        }

        // 获取当前筛选状态
        const currentFilter = document.querySelector('input[name="customerFilter"]:checked').value;
        
        // 调用带参数的加载函数
        this.loadCustomersDataWithParams(searchTerm, currentFilter);
    }

    // 客户筛选功能
    filterCustomers(filterValue) {
        
        const searchTerm = document.getElementById('customerSearch').value.trim();
        
        // 调用带参数的加载函数
        this.loadCustomersDataWithParams(searchTerm, filterValue);
    }

    // 带参数的客户数据加载
    async loadCustomersDataWithParams(searchTerm = '', filterValue = 'all') {
        try {
            
            // 构建查询参数
            const params = new URLSearchParams();
            if (searchTerm) {
                params.append('name', searchTerm);
            }
            if (filterValue && filterValue !== 'all') {
                params.append('enabled', filterValue === 'enabled' ? '1' : '0');
            }

            const url = `${this.apiBaseUrl}/customers${params.toString() ? '?' + params.toString() : ''}`;

            const response = await fetch(url);
            if (response.ok) {
                const data = await response.json();
                
                // 检查数据结构
                if (Array.isArray(data.data)) {
                    // 直接返回数组的情况
                    this.renderCustomersTable(data.data);
                } else if (data.data && Array.isArray(data.data.customers)) {
                    // 嵌套结构的情况
                    this.renderCustomersTable(data.data.customers);
                } else {
                    console.error('客户数据格式错误:', data.data);
                    this.renderCustomersTable([]);
                }
            } else {
                console.error('加载客户数据失败:', response.statusText);
                this.renderCustomersTable([]);
            }
        } catch (error) {
            console.error('加载客户数据失败:', error);
            this.renderCustomersTable([]);
        }
    }

    async saveCustomer() {
        try {
            const form = document.getElementById('addCustomerForm');
            if (form && form.checkValidity()) {
                const customerData = {
                    name: document.getElementById('customerName').value,
                    customer_uid: document.getElementById('customerUid').value,
                    api_key: document.getElementById('apiKey').value,
                    api_secret: document.getElementById('apiSecret').value,
                    passphrase: document.getElementById('passphrase').value,
                    init_asset: parseFloat(document.getElementById('initAsset').value),
                    leverage: parseInt(document.getElementById('leverage').value) || 1,
                    stop_loss_percent: parseFloat(document.getElementById('stopLossPercent').value) || 0,
                    is_demo: document.getElementById('isDemo').checked
                };
                
                
                let response;
                if (this.currentEditCustomerUid) {
                    // 编辑模式
                    response = await fetch(`${this.apiBaseUrl}/customers/${this.currentEditCustomerUid}`, {
                        method: 'PUT',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify(customerData)
                    });
                } else {
                    // 添加模式
                    response = await fetch(`${this.apiBaseUrl}/customers`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify(customerData)
                    });
                }
                
                if (response.ok) {
                    const result = await response.json();
                    this.showToast('成功', this.currentEditCustomerUid ? '客户更新成功' : '客户创建成功', 'success');
                    
                    // 关闭模态框
                    const modal = bootstrap.Modal.getInstance(document.getElementById('addCustomerModal'));
                    if (modal) {
                        modal.hide();
                    }
                    
                    // 清空表单
                    this.clearCustomerForm();
                    
                    // 重新加载客户数据
                    this.loadCustomersData();
                    
                } else {
                    const errorData = await response.json();
                    throw new Error(errorData.message || '保存失败');
                }
            } else {
                this.showToast('错误', '请填写必填字段', 'danger');
            }
        } catch (error) {
            console.error('保存客户失败:', error);
            this.showToast('错误', `保存客户失败: ${error.message}`, 'danger');
        }
    }

    async editCustomer(customerUid) {
        try {
            
            // 获取客户数据
            const response = await fetch(`${this.apiBaseUrl}/customers/${customerUid}`);
            if (response.ok) {
                const data = await response.json();
                const customer = data.data;
                
                // 填充表单数据
                this.fillCustomerForm(customer, true);
                
                // 显示模态框
                const modal = new bootstrap.Modal(document.getElementById('addCustomerModal'));
                modal.show();
                
                // 更新模态框标题
                document.querySelector('#addCustomerModal .modal-title').textContent = '编辑客户';
                
                // 设置编辑模式
                this.currentEditCustomerUid = customerUid;
                
            } else {
                console.error('获取客户数据失败:', response.statusText);
                this.showToast('错误', '获取客户数据失败', 'danger');
            }
        } catch (error) {
            console.error('编辑客户失败:', error);
            this.showToast('错误', '编辑客户失败', 'danger');
        }
    }

    // 填充客户表单
    fillCustomerForm(customer, isEdit = false) {
        // 填充表单字段
        document.getElementById('customerName').value = customer.name || '';
        document.getElementById('customerUid').value = customer.customer_uid || '';
        document.getElementById('apiKey').value = customer.api_key || '';
        document.getElementById('apiSecret').value = customer.api_secret || '';
        document.getElementById('passphrase').value = customer.passphrase || '';
        document.getElementById('initAsset').value = customer.init_asset || '';
        document.getElementById('leverage').value = customer.leverage || 1;
        document.getElementById('stopLossPercent').value = customer.stop_loss_percent || '';
        document.getElementById('isDemo').checked = customer.is_demo || false;
        
        // 如果是编辑模式，禁用客户UID字段
        const customerUidField = document.getElementById('customerUid');
        if (isEdit) {
            customerUidField.disabled = true;
            customerUidField.classList.add('form-control-plaintext');
        } else {
            customerUidField.disabled = false;
            customerUidField.classList.remove('form-control-plaintext');
        }
    }

    // 清空客户表单
    clearCustomerForm() {
        document.getElementById('addCustomerForm').reset();
        document.getElementById('customerUid').disabled = false;
        document.getElementById('customerUid').classList.remove('form-control-plaintext');
        this.currentEditCustomerUid = null;
    }

    deleteCustomer(customerUid) {
        if (confirm(`确定要删除客户 ${customerUid} 吗？`)) {
            this.showToast('信息', `删除客户功能开发中...`, 'info');
        }
    }

    // 信号源搜索功能
    searchSignalSources() {
        const searchTerm = document.getElementById('signalSourceSearch').value.trim();
        
        if (!searchTerm) {
            // 如果搜索词为空，重新加载所有信号源
            this.loadSignalSourcesData();
            return;
        }

        // 获取当前筛选状态
        const currentFilter = document.querySelector('input[name="signalSourceFilter"]:checked').value;
        
        // 调用带参数的加载函数
        this.loadSignalSourcesDataWithParams(searchTerm, currentFilter);
    }

    // 信号源筛选功能
    filterSignalSources(filterValue) {
        
        const searchTerm = document.getElementById('signalSourceSearch').value.trim();
        
        // 调用带参数的加载函数
        this.loadSignalSourcesDataWithParams(searchTerm, filterValue);
    }

    // 带参数的信号源数据加载
    async loadSignalSourcesDataWithParams(searchTerm = '', filterValue = 'all') {
        try {
            
            // 构建查询参数
            const params = new URLSearchParams();
            if (searchTerm) {
                params.append('name', searchTerm);
            }
            if (filterValue && filterValue !== 'all') {
                params.append('enabled', filterValue === 'enabled' ? '1' : '0');
            }

            const url = `${this.apiBaseUrl}/signal_sources${params.toString() ? '?' + params.toString() : ''}`;

            const response = await fetch(url);
            if (response.ok) {
                const data = await response.json();
                
                // 检查数据结构
                if (Array.isArray(data.data)) {
                    // 直接返回数组的情况
                    this.renderSignalSourcesTable(data.data);
                } else if (data.data && Array.isArray(data.data.sources)) {
                    // 嵌套结构的情况
                    this.renderSignalSourcesTable(data.data.sources);
                } else {
                    console.error('信号源数据格式错误:', data.data);
                    this.renderSignalSourcesTable([]);
                }
            } else {
                console.error('加载信号源数据失败:', response.statusText);
                this.renderSignalSourcesTable([]);
            }
        } catch (error) {
            console.error('加载信号源数据失败:', error);
            this.renderSignalSourcesTable([]);
        }
    }

    // 保存策略
    saveStrategy() {
        const form = document.getElementById('addStrategyForm');
        if (form && form.checkValidity()) {
            const strategyData = {
                name: document.getElementById('strategyName').value,
                description: document.getElementById('strategyDescription').value,
                signal_source_uid: document.getElementById('signalSources').value,
                strategy_type: document.getElementById('strategyType').value,
                enabled: document.getElementById('strategyEnabled').checked
            };
            
            
            // 判断是新增还是编辑
            if (this.currentEditStrategyUid) {
                // 编辑模式
                this.updateStrategy(this.currentEditStrategyUid, strategyData);
            } else {
                // 新增模式
                this.createStrategy(strategyData);
            }
        } else {
            this.showToast('错误', '请填写必填字段', 'danger');
        }
    }

    // 创建策略
    async createStrategy(strategyData) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/strategies`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(strategyData)
            });
            
            if (response.ok) {
                this.showToast('成功', '策略创建成功', 'success');
                // 关闭模态框
                const modal = bootstrap.Modal.getInstance(document.getElementById('addStrategyModal'));
                if (modal) {
                    modal.hide();
                }
                // 刷新数据
                this.loadStrategiesData();
            } else {
                const errorData = await response.json();
                this.showToast('错误', errorData.message || '创建失败', 'danger');
            }
        } catch (error) {
            console.error('创建策略失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }

    // 更新策略
    async updateStrategy(strategyUid, strategyData) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/strategies/${strategyUid}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(strategyData)
            });
            
            if (response.ok) {
                this.showToast('成功', '策略更新成功', 'success');
                // 关闭模态框
                const modal = bootstrap.Modal.getInstance(document.getElementById('addStrategyModal'));
                if (modal) {
                    modal.hide();
                }
                // 刷新数据
                this.loadStrategiesData();
            } else {
                const errorData = await response.json();
                this.showToast('错误', errorData.message || '更新失败', 'danger');
            }
        } catch (error) {
            console.error('更新策略失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }

    // 填充策略表单
    async fillStrategyForm(strategy, isEdit = false) {
        // 先加载信号源选项
        await this.loadSignalSourcesOptions();
        
        document.getElementById('strategyName').value = strategy.name || '';
        document.getElementById('strategyDescription').value = strategy.description || '';
        document.getElementById('signalSources').value = strategy.signal_source_uid || '';
        document.getElementById('strategyType').value = strategy.strategy_type || 'trend';
        document.getElementById('strategyEnabled').checked = strategy.enabled || false;
        
        // 如果是编辑模式，禁用某些字段
        if (isEdit) {
            document.getElementById('strategyName').disabled = true;
        } else {
            document.getElementById('strategyName').disabled = false;
        }
    }

    // 清空策略表单
    clearStrategyForm() {
        const form = document.getElementById('addStrategyForm');
        if (form) {
            form.reset();
        }
        
        // 重置编辑状态
        this.currentEditStrategyUid = null;
        
        // 重置模态框标题
        document.getElementById('addStrategyModalLabel').textContent = '添加策略';
        
        // 启用所有字段
        document.getElementById('strategyName').disabled = false;
    }

    // 保存规则
    saveRule() {
        const form = document.getElementById('addRuleForm');
        if (form && form.checkValidity()) {
            const ruleData = {
                name: document.getElementById('ruleName').value,
                strategy_uid: document.getElementById('ruleStrategy').value,
                position_ratio: parseFloat(document.getElementById('positionRatio').value),
                max_leverage: parseFloat(document.getElementById('maxLeverage').value),
                stop_loss_percent: parseFloat(document.getElementById('ruleStopLossPercent').value) || null,
                take_profit_percent: parseFloat(document.getElementById('takeProfitPercent').value) || null,
                enabled: document.getElementById('ruleEnabled').checked
            };
            
            
            // 判断是新增还是编辑
            if (this.currentEditRuleUid) {
                // 编辑模式
                this.updateRule(this.currentEditRuleUid, ruleData);
            } else {
                // 新增模式
                this.createRule(ruleData);
            }
        } else {
            this.showToast('错误', '请填写必填字段', 'danger');
        }
    }

    // 创建规则
    async createRule(ruleData) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/rules`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(ruleData)
            });
            
            if (response.ok) {
                this.showToast('成功', '规则创建成功', 'success');
                // 关闭模态框
                const modal = bootstrap.Modal.getInstance(document.getElementById('addRuleModal'));
                if (modal) {
                    modal.hide();
                }
                // 刷新数据
                this.loadRulesData();
            } else {
                const errorData = await response.json();
                this.showToast('错误', errorData.message || '创建失败', 'danger');
            }
        } catch (error) {
            console.error('创建规则失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }

    // 更新规则
    async updateRule(ruleUid, ruleData) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/rules/${ruleUid}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(ruleData)
            });
            
            if (response.ok) {
                this.showToast('成功', '规则更新成功', 'success');
                // 关闭模态框
                const modal = bootstrap.Modal.getInstance(document.getElementById('addRuleModal'));
                if (modal) {
                    modal.hide();
                }
                // 刷新数据
                this.loadRulesData();
            } else {
                const errorData = await response.json();
                this.showToast('错误', errorData.message || '更新失败', 'danger');
            }
        } catch (error) {
            console.error('更新规则失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }

    // 填充规则表单
    async fillRuleForm(rule, isEdit = false) {
        // 先加载策略选项
        await this.loadStrategiesOptions();
        
        document.getElementById('ruleName').value = rule.name || '';
        document.getElementById('ruleStrategy').value = rule.strategy_uid || '';
        document.getElementById('positionRatio').value = rule.position_ratio || '';
        document.getElementById('maxLeverage').value = rule.max_leverage || '';
        document.getElementById('ruleStopLossPercent').value = rule.stop_loss_percent || '';
        document.getElementById('takeProfitPercent').value = rule.take_profit_percent || '';
        document.getElementById('ruleEnabled').checked = rule.enabled || false;
        
        // 如果是编辑模式，禁用某些字段
        if (isEdit) {
            document.getElementById('ruleName').disabled = true;
        } else {
            document.getElementById('ruleName').disabled = false;
        }
    }

    // 清空规则表单
    clearRuleForm() {
        const form = document.getElementById('addRuleForm');
        if (form) {
            form.reset();
        }
        
        // 重置编辑状态
        this.currentEditRuleUid = null;
        
        // 重置模态框标题
        document.getElementById('addRuleModalLabel').textContent = '添加规则';
        
        // 启用所有字段
        document.getElementById('ruleName').disabled = false;
    }

    // 加载信号源交易记录数据
    async loadSignalTradesData() {
        try {
            
            const response = await fetch(`${this.apiBaseUrl}/signal-trades?page=1&page_size=10`);
            if (response.ok) {
                const data = await response.json();
                
                if (data.data && data.data.trades) {
                    this.renderSignalTradesTable(data.data.trades);
                    this.updateSignalTradesPagination(data.data.pagination);
                } else {
                    console.error('信号源交易记录数据格式错误:', data.data);
                    this.renderSignalTradesTable([]);
                }
            } else {
                console.error('加载信号源交易记录失败:', response.statusText);
                this.renderSignalTradesTable([]);
            }
        } catch (error) {
            console.error('加载信号源交易记录失败:', error);
            this.renderSignalTradesTable([]);
        }
    }

    // 静默加载信号源交易记录数据（用于自动刷新）
    async loadSignalTradesDataSilent() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/signal-trades?page=1&page_size=10`);
            if (response.ok) {
                const data = await response.json();
                
                if (data.data && data.data.trades) {
                    this.renderSignalTradesTable(data.data.trades);
                    this.updateSignalTradesPagination(data.data.pagination);
                }
            }
        } catch (error) {
            console.error('静默加载信号源交易记录失败:', error);
        }
    }

    // 渲染信号源交易记录表格
    renderSignalTradesTable(trades) {
        const tbody = document.getElementById('signalTradesTableBody');
        if (!tbody) {
            console.error('未找到信号源交易记录表格体');
            return;
        }

        if (!Array.isArray(trades) || trades.length === 0) {
            tbody.innerHTML = '<tr><td colspan="12" class="text-center text-muted">暂无数据</td></tr>';
            return;
        }

        tbody.innerHTML = trades.map(trade => `
            <tr>
                <td>${trade.trade_uid || '-'}</td>
                <td>${trade.signal_source_uid || '-'}</td>
                <td>${trade.symbol || '-'}</td>
                <td>
                    <span class="badge ${trade.pos_side === 'long' ? 'bg-success' : 'bg-danger'}">
                        ${trade.pos_side === 'long' ? '多' : '空'}
                    </span>
                </td>
                <td>${trade.volume_contract || trade.volume || 0}</td>
                <td>${trade.open_px || '-'}</td>
                <td>${trade.close_px || '-'}</td>
                <td>
                    <span class="${(trade.profit || 0) >= 0 ? 'text-success' : 'text-danger'}">
                        ${trade.profit || 0}
                    </span>
                </td>
                <td>
                    <span class="badge ${trade.status === 'open' ? 'bg-warning' : 'bg-success'}">
                        ${trade.status === 'open' ? '开仓中' : '已平仓'}
                    </span>
                </td>
                <td>${this.formatDateTime(trade.created_at)}</td>
                <td>${trade.closed_at ? this.formatDateTime(trade.closed_at) : '-'}</td>
                <td>
                    <div class="btn-group btn-group-sm" role="group">
                        <button class="btn btn-outline-info" onclick="app.viewSignalTradeDetails('${trade.trade_uid}')" title="查看详情">
                            <i class="bi bi-eye"></i>
                        </button>
                        ${trade.status === 'open' ? `
                            <button class="btn btn-outline-warning" onclick="app.closeSignalTrade('${trade.trade_uid}')" title="平仓">
                                <i class="bi bi-x-circle"></i>
                            </button>
                        ` : ''}
                    </div>
                </td>
            </tr>
        `).join('');
    }

    // 更新信号源交易记录分页
    updateSignalTradesPagination(pagination) {
        const totalCountElement = document.getElementById('signalTradesTotalCount');
        const paginationElement = document.getElementById('signalTradesPagination');
        
        if (totalCountElement) {
            totalCountElement.textContent = pagination.total_count || 0;
        }
        
        if (paginationElement) {
            // 这里可以添加分页逻辑
        }
    }

    // 加载持仓数据
    async loadPositionsData() {
        try {
            
            let signalPositions = [];
            let customerPositions = [];
            
            // 加载信号源持仓
            const signalPositionsResponse = await fetch(`${this.apiBaseUrl}/signal-positions`);
            if (signalPositionsResponse.ok) {
                const signalData = await signalPositionsResponse.json();
                signalPositions = signalData.data || [];
                this.renderSignalPositionsTable(signalPositions);
                this.updatePositionsStats('signal', signalPositions.length);
            }

            // 加载客户持仓
            const customerPositionsResponse = await fetch(`${this.apiBaseUrl}/customer-positions`);
            if (customerPositionsResponse.ok) {
                const customerData = await customerPositionsResponse.json();
                customerPositions = customerData.data || [];
                this.renderCustomerPositionsTable(customerPositions);
                this.updatePositionsStats('customer', customerPositions.length);
            }

            // 加载未成交订单
            await this.loadPendingOrdersForPositions();

            // 计算总持仓价值
            const totalValue = this.calculateTotalPositionsValue(signalPositions, customerPositions);
            
            // 更新持仓统计
            this.updatePositionsStats('total', totalValue);
            this.updatePositionsStats('status', '正常');
            
        } catch (error) {
            console.error('加载持仓数据失败:', error);
            this.renderSignalPositionsTable([]);
            this.renderCustomerPositionsTable([]);
        }
    }

    // 静默加载持仓数据（用于自动刷新）
    async loadPositionsDataSilent() {
        try {
            let signalPositions = [];
            let customerPositions = [];
            
            // 加载信号源持仓
            const signalPositionsResponse = await fetch(`${this.apiBaseUrl}/signal-positions`);
            if (signalPositionsResponse.ok) {
                const signalData = await signalPositionsResponse.json();
                signalPositions = signalData.data || [];
                this.renderSignalPositionsTable(signalPositions);
                this.updatePositionsStats('signal', signalPositions.length);
            }

            // 加载客户持仓
            const customerPositionsResponse = await fetch(`${this.apiBaseUrl}/customer-positions`);
            if (customerPositionsResponse.ok) {
                const customerData = await customerPositionsResponse.json();
                customerPositions = customerData.data || [];
                this.renderCustomerPositionsTable(customerPositions);
                this.updatePositionsStats('customer', customerPositions.length);
            }

            // 计算总持仓价值
            const totalValue = this.calculateTotalPositionsValue(signalPositions, customerPositions);
            
            // 更新持仓统计
            this.updatePositionsStats('total', totalValue);
            this.updatePositionsStats('status', '正常');
            
        } catch (error) {
            console.error('静默加载持仓数据失败:', error);
        }
    }

    // 渲染信号源持仓表格
    renderSignalPositionsTable(positions) {
        const tbody = document.getElementById('signalPositionsTableBody');
        if (!tbody) {
            console.error('未找到信号源持仓表格体');
            return;
        }

        if (!Array.isArray(positions) || positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted">暂无持仓</td></tr>';
            return;
        }

        tbody.innerHTML = positions.map(pos => `
            <tr>
                <td>${pos.signal_source_uid || '-'}</td>
                <td>${pos.symbol || '-'}</td>
                <td>
                    <span class="badge ${pos.pos_side === 'long' ? 'bg-success' : 'bg-danger'}">
                        ${pos.pos_side === 'long' ? '多' : '空'}
                    </span>
                </td>
                <td>${pos.total_volume || 0}</td>
                <td>${pos.closed_volume || 0}</td>
                <td>${pos.remaining_volume || 0}</td>
                <td>${pos.avg_open_price || 0}</td>
                <td>${this.formatDateTime(pos.first_open_time)}</td>
                <td>${this.formatDateTime(pos.last_open_time)}</td>
                <td>
                    <div class="btn-group btn-group-sm" role="group">
                        <button class="btn btn-outline-info" onclick="app.viewSignalPositionDetails('${pos.signal_source_uid}', '${pos.symbol}', '${pos.pos_side}')" title="查看详情">
                            <i class="bi bi-eye"></i>
                        </button>
                        <button class="btn btn-outline-warning" onclick="app.closeSignalPosition('${pos.signal_source_uid}', '${pos.symbol}', '${pos.pos_side}')" title="平仓">
                            <i class="bi bi-x-circle"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
    }

    // 渲染客户持仓表格
    renderCustomerPositionsTable(positions) {
        const tbody = document.getElementById('customerPositionsTableBody');
        if (!tbody) {
            console.error('未找到客户持仓表格体');
            return;
        }

        if (!Array.isArray(positions) || positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted">暂无持仓</td></tr>';
            return;
        }

        tbody.innerHTML = positions.map(pos => `
            <tr>
                <td>${pos.customer_uid || '-'}</td>
                <td>${pos.symbol || '-'}</td>
                <td>
                    <span class="badge ${pos.pos_side === 'long' ? 'bg-success' : 'bg-danger'}">
                        ${pos.pos_side === 'long' ? '多' : '空'}
                    </span>
                </td>
                <td>${pos.total_volume || 0}</td>
                <td>${pos.closed_volume || 0}</td>
                <td>${pos.remaining_volume || 0}</td>
                <td>${pos.avg_open_price || 0}</td>
                <td>${this.formatDateTime(pos.first_open_time)}</td>
                <td>${this.formatDateTime(pos.last_open_time)}</td>
                <td>
                    <div class="btn-group btn-group-sm" role="group">
                        <button class="btn btn-outline-info" onclick="app.viewCustomerPositionDetails('${pos.customer_uid}', '${pos.symbol}', '${pos.pos_side}')" title="查看详情">
                            <i class="bi bi-eye"></i>
                        </button>
                        <button class="btn btn-outline-warning" onclick="app.closeCustomerPosition('${pos.customer_uid}', '${pos.symbol}', '${pos.pos_side}')" title="平仓">
                            <i class="bi bi-x-circle"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
    }

    // 计算总持仓价值
    calculateTotalPositionsValue(signalPositions, customerPositions) {
        let totalValue = 0;
        
        // 只计算客户持仓价值（信号源持仓不计入总价值）
        customerPositions.forEach(pos => {
            const positionValue = (pos.remaining_volume || 0) * (pos.avg_open_price || 0);
            totalValue += positionValue;
        });
        
        // 格式化显示，保留2位小数
        return totalValue.toFixed(2);
    }

    // 更新持仓统计
    updatePositionsStats(type, value) {
        const elements = {
            'signal': document.getElementById('signal-positions-count'),
            'customer': document.getElementById('customer-positions-count'),
            'total': document.getElementById('total-positions-value'),
            'status': document.getElementById('positions-status')
        };

        if (elements[type]) {
            if (type === 'total') {
                // 总持仓价值显示为货币格式
                elements[type].textContent = `$${value}`;
            } else {
                elements[type].textContent = value;
            }
        }
    }

    // 查看信号源交易详情
    viewSignalTradeDetails(tradeUid) {
        this.showToast('信息', `查看信号源交易详情: ${tradeUid}`, 'info');
    }

    // 平仓信号源交易
    closeSignalTrade(tradeUid) {
        if (confirm(`确定要平仓信号源交易 ${tradeUid} 吗？`)) {
            this.showToast('信息', `平仓信号源交易: ${tradeUid}`, 'info');
        }
    }

    // 查看信号源持仓详情
    async viewSignalPositionDetails(signalSourceUid, symbol, posSide) {
        try {
            
            // 设置当前查看的持仓信息
            this.currentPositionInfo = {
                type: 'signal',
                accountId: signalSourceUid,
                symbol: symbol,
                posSide: posSide
            };
            
            // 加载持仓详情数据
            await this.loadPositionDetails();
            
            // 显示模态框
            const modal = new bootstrap.Modal(document.getElementById('positionDetailsModal'));
            modal.show();
            
        } catch (error) {
            console.error('查看信号源持仓详情失败:', error);
            this.showToast('错误', '查看持仓详情失败', 'danger');
        }
    }

    // 平仓信号源持仓
    closeSignalPosition(signalSourceUid, symbol, posSide) {
        if (confirm(`确定要平仓信号源持仓 ${signalSourceUid} ${symbol} ${posSide} 吗？`)) {
            this.showToast('信息', `平仓信号源持仓: ${signalSourceUid} ${symbol} ${posSide}`, 'info');
        }
    }

    // 查看客户持仓详情
    async viewCustomerPositionDetails(customerUid, symbol, posSide) {
        try {
            
            // 设置当前查看的持仓信息
            this.currentPositionInfo = {
                type: 'customer',
                accountId: customerUid,
                symbol: symbol,
                posSide: posSide
            };
            
            // 加载持仓详情数据
            await this.loadPositionDetails();
            
            // 显示模态框
            const modal = new bootstrap.Modal(document.getElementById('positionDetailsModal'));
            modal.show();
            
        } catch (error) {
            console.error('查看客户持仓详情失败:', error);
            this.showToast('错误', '查看持仓详情失败', 'danger');
        }
    }

    // 平仓客户持仓
    closeCustomerPosition(customerUid, symbol, posSide) {
        // 显示平仓选择模态框
        this.showClosePositionModal(customerUid, symbol, posSide);
    }

    // 显示平仓选择模态框
    showClosePositionModal(accountUid, symbol, posSide, accountType = 'customer') {
        // 创建平仓选择模态框
        const modalHtml = `
            <div class="modal fade" id="closePositionModal" tabindex="-1" aria-labelledby="closePositionModalLabel" aria-hidden="true">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="closePositionModalLabel">平仓设置</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <div class="mb-3">
                                <label class="form-label">平仓类型</label>
                                <div class="form-check">
                                    <input class="form-check-input" type="radio" name="closeType" id="closeTypeAll" value="all" checked>
                                    <label class="form-check-label" for="closeTypeAll">
                                        全平仓
                                    </label>
                                </div>
                                <div class="form-check">
                                    <input class="form-check-input" type="radio" name="closeType" id="closeTypePartial" value="partial">
                                    <label class="form-check-label" for="closeTypePartial">
                                        部分平仓
                                    </label>
                                </div>
                                <div class="form-check">
                                    <input class="form-check-input" type="radio" name="closeType" id="closeTypeSpecific" value="specific">
                                    <label class="form-check-label" for="closeTypeSpecific">
                                        选择订单平仓
                                    </label>
                                </div>
                            </div>
                            
                            <div class="mb-3" id="partialCloseSection" style="display: none;">
                                <label for="closeAmount" class="form-label">平仓数量</label>
                                <input type="number" class="form-control" id="closeAmount" placeholder="请输入平仓数量" step="0.01" min="0">
                                <div class="form-text">当前持仓数量: <span id="currentPositionAmount">-</span></div>
                            </div>
                            
                            <div class="mb-3" id="specificOrderSection" style="display: none;">
                                <label class="form-label">选择要平仓的订单</label>
                                <div class="table-responsive">
                                    <table class="table table-sm table-striped">
                                        <thead>
                                            <tr>
                                                <th><input type="checkbox" id="selectAllOrders" class="form-check-input"></th>
                                                <th>交易ID</th>
                                                <th>开仓时间</th>
                                                <th>数量</th>
                                                <th>开仓价格</th>
                                                <th>状态</th>
                                            </tr>
                                        </thead>
                                        <tbody id="orderSelectionTableBody">
                                            <tr><td colspan="6" class="text-center text-muted">加载中...</td></tr>
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                            
                            <div class="mb-3">
                                <label for="closeReason" class="form-label">平仓原因</label>
                                <select class="form-select" id="closeReason">
                                    <option value="手动平仓">手动平仓</option>
                                    <option value="止损平仓">止损平仓</option>
                                    <option value="止盈平仓">止盈平仓</option>
                                    <option value="风险控制">风险控制</option>
                                    <option value="其他">其他</option>
                                </select>
                            </div>
                            <div class="alert ${accountType === 'signal' ? 'alert-warning' : 'alert-info'}">
                                <strong>平仓信息:</strong><br>
                                ${accountType === 'signal' ? '信号源' : '客户'}: ${accountUid}<br>
                                交易对: ${symbol}<br>
                                持仓方向: ${posSide === 'long' ? '多' : '空'}
                                ${accountType === 'signal' ? '<br><strong>⚠️ 警告：信号源手动平仓可能影响跟单系统！</strong>' : ''}
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-warning" id="confirmCloseBtn">确认平仓</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // 移除已存在的模态框
        const existingModal = document.getElementById('closePositionModal');
        if (existingModal) {
            existingModal.remove();
        }

        // 添加新模态框到页面
        document.body.insertAdjacentHTML('beforeend', modalHtml);

        // 获取当前持仓数量和订单列表
        this.loadCurrentPositionAmount(accountUid, symbol, posSide, accountType);
        this.loadOrderSelectionData(accountUid, symbol, posSide, accountType);

        // 绑定事件
        const modal = new bootstrap.Modal(document.getElementById('closePositionModal'));
        modal.show();

        // 平仓类型切换事件
        document.querySelectorAll('input[name="closeType"]').forEach(radio => {
            radio.addEventListener('change', (e) => {
                const partialSection = document.getElementById('partialCloseSection');
                const specificSection = document.getElementById('specificOrderSection');
                
                // 隐藏所有选择区域
                partialSection.style.display = 'none';
                specificSection.style.display = 'none';
                
                // 显示对应的选择区域
                if (e.target.value === 'partial') {
                    partialSection.style.display = 'block';
                } else if (e.target.value === 'specific') {
                    specificSection.style.display = 'block';
                }
            });
        });

        // 全选订单事件
        const selectAllCheckbox = document.getElementById('selectAllOrders');
        if (selectAllCheckbox) {
            selectAllCheckbox.addEventListener('change', (e) => {
                const orderCheckboxes = document.querySelectorAll('input[name="orderCheckbox"]');
                orderCheckboxes.forEach(checkbox => {
                    checkbox.checked = e.target.checked;
                });
            });
        }

        // 确认平仓按钮事件
        document.getElementById('confirmCloseBtn').addEventListener('click', () => {
            this.executeClosePosition(accountUid, symbol, posSide, accountType);
        });

        // 模态框关闭时清理
        document.getElementById('closePositionModal').addEventListener('hidden.bs.modal', () => {
            document.getElementById('closePositionModal').remove();
        });
    }

    // 加载当前持仓数量
    async loadCurrentPositionAmount(accountUid, symbol, posSide, accountType = 'customer') {
        try {
            const endpoint = accountType === 'signal' ? 'signal-positions' : 'customer-positions';
            const uidParam = accountType === 'signal' ? 'signal_source_uid' : 'customer_uid';
            const response = await fetch(`${this.apiBaseUrl}/${endpoint}?${uidParam}=${accountUid}&symbol=${symbol}&pos_side=${posSide}`);
            
            if (response.ok) {
                const data = await response.json();
                const position = data.data.find(p => 
                    p[accountType === 'signal' ? 'signal_source_uid' : 'customer_uid'] === accountUid && 
                    p.symbol === symbol && 
                    p.pos_side === posSide
                );
                
                if (position) {
                    const remainingVolume = position.remaining_volume || 0;
                    document.getElementById('currentPositionAmount').textContent = this.formatNumber(remainingVolume);
                    document.getElementById('closeAmount').max = remainingVolume;
                    document.getElementById('closeAmount').placeholder = `最大可平仓: ${this.formatNumber(remainingVolume)}`;
                }
            }
        } catch (error) {
            console.error('加载持仓数量失败:', error);
        }
    }

    // 加载订单选择数据
    async loadOrderSelectionData(accountUid, symbol, posSide, accountType = 'customer') {
        try {
            const endpoint = accountType === 'signal' ? 'signal-trades' : 'trades';
            const uidParam = accountType === 'signal' ? 'signal_source_uid' : 'customer_uid';
            const response = await fetch(`${this.apiBaseUrl}/${endpoint}?${uidParam}=${accountUid}&symbol=${symbol}&pos_side=${posSide}&status=open`);
            
            if (response.ok) {
                const data = await response.json();
                const trades = data.data?.trades || data.data || [];
                
                this.renderOrderSelectionTable(trades);
            } else {
                this.renderOrderSelectionTable([]);
            }
        } catch (error) {
            console.error('加载订单选择数据失败:', error);
            this.renderOrderSelectionTable([]);
        }
    }

    // 渲染订单选择表格
    renderOrderSelectionTable(trades) {
        const tbody = document.getElementById('orderSelectionTableBody');
        if (!tbody) return;

        if (!Array.isArray(trades) || trades.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">暂无开仓订单</td></tr>';
            return;
        }

        const rowsHtml = trades.map(trade => {
            const remainingVolume = (trade.volume_contract || 0) - (trade.close_volume_contract || 0);
            const isFullyClosed = remainingVolume <= 0;
            
            return `
                <tr>
                    <td>
                        <input type="checkbox" name="orderCheckbox" value="${trade.trade_uid}" 
                               class="form-check-input" ${isFullyClosed ? 'disabled' : ''}>
                    </td>
                    <td>${trade.trade_uid || '-'}</td>
                    <td>${this.formatDateTime(trade.created_at)}</td>
                    <td>${this.formatNumber(remainingVolume)}</td>
                    <td>${this.formatNumber(trade.open_px || 0)}</td>
                    <td>
                        <span class="badge ${isFullyClosed ? 'bg-secondary' : 'bg-success'}">
                            ${isFullyClosed ? '已平仓' : '开仓中'}
                        </span>
                    </td>
                </tr>
            `;
        }).join('');

        tbody.innerHTML = rowsHtml;
    }

    // 执行平仓操作
    async executeClosePosition(accountUid, symbol, posSide, accountType = 'customer') {
        try {
            const closeType = document.querySelector('input[name="closeType"]:checked').value;
            const closeReason = document.getElementById('closeReason').value;
            let closeAmount = 0;
            let selectedTradeUids = [];

            if (closeType === 'partial') {
                closeAmount = parseFloat(document.getElementById('closeAmount').value);
                if (!closeAmount || closeAmount <= 0) {
                    this.showToast('错误', '请输入有效的平仓数量', 'danger');
                    return;
                }
            } else if (closeType === 'specific') {
                // 获取选中的订单
                const selectedCheckboxes = document.querySelectorAll('input[name="orderCheckbox"]:checked');
                if (selectedCheckboxes.length === 0) {
                    this.showToast('错误', '请选择要平仓的订单', 'danger');
                    return;
                }
                selectedTradeUids = Array.from(selectedCheckboxes).map(cb => cb.value);
            }

            // 构建平仓请求数据
            const closeData = {
                [accountType === 'signal' ? 'signal_source_uid' : 'customer_uid']: accountUid,
                symbol: symbol,
                pos_side: posSide,
                close_sz: closeAmount,
                reason: closeReason,
                is_demo: this.isDemo,
                trade_uids: selectedTradeUids,  // 添加选中的订单ID
                account_type: accountType  // 添加账户类型标识
            };

            // 发送平仓请求
            const endpoint = accountType === 'signal' ? '/manual/close_signal_position' : '/manual/close_position';
            const response = await fetch(`${this.apiBaseUrl}${endpoint}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(closeData)
            });

            const result = await response.json();

            if (result.success === 200) {
                let successMessage = '';
                if (closeType === 'all') {
                    successMessage = '全平仓操作已提交';
                } else if (closeType === 'partial') {
                    successMessage = `部分平仓操作已提交: ${closeAmount}`;
                } else if (closeType === 'specific') {
                    successMessage = `选择订单平仓操作已提交: ${selectedTradeUids.length}个订单`;
                }
                
                this.showToast('成功', successMessage, 'success');
                
                // 关闭模态框
                const modal = bootstrap.Modal.getInstance(document.getElementById('closePositionModal'));
                modal.hide();
                
                // 刷新持仓数据
                this.loadPositionsData();
            } else {
                this.showToast('错误', `平仓失败: ${result.message}`, 'danger');
            }

        } catch (error) {
            console.error('平仓操作失败:', error);
            this.showToast('错误', '平仓操作失败，请稍后重试', 'danger');
        }
    }

    // 加载持仓详情数据
    async loadPositionDetails() {
        try {
            if (!this.currentPositionInfo) {
                throw new Error('没有持仓信息');
            }

            const { type, accountId, symbol, posSide } = this.currentPositionInfo;
            
            // 更新模态框标题
            const modalTitle = document.getElementById('positionDetailsModalLabel');
            modalTitle.textContent = `${type === 'signal' ? '信号源' : '客户'}持仓详情`;

            // 更新基本信息
            document.getElementById('positionAccountType').textContent = type === 'signal' ? '信号源' : '客户';
            document.getElementById('positionAccountId').textContent = accountId;
            document.getElementById('positionSymbol').textContent = symbol;
            document.getElementById('positionPosSide').textContent = posSide;

            // 获取持仓汇总信息
            const summaryResponse = await fetch(`${this.apiBaseUrl}/${type === 'signal' ? 'signal-positions' : 'customer-positions'}`);
            if (summaryResponse.ok) {
                const summaryData = await summaryResponse.json();
                const position = summaryData.data.find(p => 
                    p[type === 'signal' ? 'signal_source_uid' : 'customer_uid'] === accountId &&
                    p.symbol === symbol &&
                    p.pos_side === posSide
                );

                if (position) {
                    document.getElementById('positionTotalVolume').textContent = this.formatNumber(position.total_volume || 0);
                    document.getElementById('positionClosedVolume').textContent = this.formatNumber(position.closed_volume || 0);
                    document.getElementById('positionRemainingVolume').textContent = this.formatNumber(position.remaining_volume || 0);
                    document.getElementById('positionAvgOpenPrice').textContent = this.formatNumber(position.avg_open_price || 0);
                }
            }

            // 获取交易记录
            const tradesResponse = await fetch(`${this.apiBaseUrl}/${type === 'signal' ? 'signal-trades' : 'trades'}?${type === 'signal' ? 'signal_source_uid' : 'customer_uid'}=${accountId}&symbol=${symbol}&pos_side=${posSide}`);
            if (tradesResponse.ok) {
                const tradesData = await tradesResponse.json();
                this.renderPositionTradesTable(tradesData.data?.trades || tradesData.data || []);
            } else {
                this.renderPositionTradesTable([]);
            }

        } catch (error) {
            console.error('加载持仓详情失败:', error);
            this.showToast('错误', '加载持仓详情失败', 'danger');
        }
    }

    // 渲染持仓交易记录表格
    renderPositionTradesTable(trades) {
        const tbody = document.getElementById('positionTradesTableBody');
        if (!tbody) return;

        if (!Array.isArray(trades) || trades.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">暂无交易记录</td></tr>';
            return;
        }

        const rowsHtml = trades.map(trade => `
            <tr>
                <td>${trade.trade_uid || trade.id || '-'}</td>
                <td>${this.formatDateTime(trade.created_at)}</td>
                <td>${this.formatNumber(trade.volume_contract || trade.sz || 0)}</td>
                <td>${this.formatNumber(trade.open_px || trade.px || 0)}</td>
                <td>
                    <span class="badge ${trade.status === 'open' ? 'bg-success' : 'bg-secondary'}">
                        ${trade.status === 'open' ? '开仓中' : '已平仓'}
                    </span>
                </td>
            </tr>
        `).join('');

        tbody.innerHTML = rowsHtml;
    }

    // 平仓当前持仓
    async closeCurrentPosition() {
        try {
            if (!this.currentPositionInfo) {
                this.showToast('错误', '没有持仓信息', 'danger');
                return;
            }

            const { type, accountId, symbol, posSide } = this.currentPositionInfo;
            
            // 如果是信号源持仓，询问是否确认手动平仓
            if (type === 'signal') {
                const confirmed = confirm('⚠️ 警告：信号源持仓通常不应该手动平仓！\n\n手动平仓信号源可能会：\n• 影响跟单系统的正常运行\n• 导致客户账户与信号源不一致\n• 影响策略执行效果\n\n您确定要继续吗？');
                if (!confirmed) {
                    return;
                }
            }
            
            // 显示平仓选择模态框
            this.showClosePositionModal(accountId, symbol, posSide, type);
            
            // 关闭持仓详情模态框
            const positionModal = bootstrap.Modal.getInstance(document.getElementById('positionDetailsModal'));
            if (positionModal) {
                positionModal.hide();
            }
        } catch (error) {
            console.error('平仓失败:', error);
            this.showToast('错误', '平仓失败', 'danger');
        }
    }

    // 搜索信号源交易
    searchSignalTrades() {
        const searchTerm = document.getElementById('signalTradesSearch')?.value || '';
        const symbol = document.getElementById('signalTradesSymbol')?.value || '';
        const status = document.getElementById('signalTradesStatus')?.value || '';
        const direction = document.getElementById('signalTradesDirection')?.value || '';

        
        // 构建查询参数
        const params = new URLSearchParams();
        if (searchTerm) params.append('signal_source_uid', searchTerm);
        if (symbol) params.append('symbol', symbol);
        if (status) params.append('status', status);
        if (direction) params.append('pos_side', direction);
        params.append('page', '1');
        params.append('page_size', '10');

        // 重新加载数据
        this.loadSignalTradesDataWithParams(params.toString());
    }

    // 重置信号源交易搜索
    resetSignalTradesSearch() {
        // 清空搜索表单
        const form = document.getElementById('signalTradesSearchForm');
        if (form) {
            form.reset();
        }

        // 重新加载数据
        this.loadSignalTradesData();
    }

    // 带参数加载信号源交易数据
    async loadSignalTradesDataWithParams(params) {
        try {
            
            const response = await fetch(`${this.apiBaseUrl}/signal-trades?${params}`);
            if (response.ok) {
                const data = await response.json();
                
                if (data.data && data.data.trades) {
                    this.renderSignalTradesTable(data.data.trades);
                    this.updateSignalTradesPagination(data.data.pagination);
                } else {
                    console.error('信号源交易记录数据格式错误:', data.data);
                    this.renderSignalTradesTable([]);
                }
            } else {
                console.error('加载信号源交易记录失败:', response.statusText);
                this.renderSignalTradesTable([]);
            }
        } catch (error) {
            console.error('加载信号源交易记录失败:', error);
            this.renderSignalTradesTable([]);
        }
    }

    // 保存信号源
    saveSignalSource() {
        const form = document.getElementById('addSignalSourceForm');
        if (form && form.checkValidity()) {
            const signalSourceData = {
                name: document.getElementById('signalSourceName').value,
                exchange: document.getElementById('signalSourceExchange').value,
                api_key: document.getElementById('signalSourceApiKey').value,
                api_secret: document.getElementById('signalSourceApiSecret').value,
                passphrase: document.getElementById('signalSourcePassphrase').value,
                init_asset: parseFloat(document.getElementById('signalSourceInitAsset').value),
                leverage: parseInt(document.getElementById('signalSourceLeverage').value) || 1,
                stop_loss_percent: parseFloat(document.getElementById('signalSourceStopLossPercent').value) || 0,
                enabled: document.getElementById('signalSourceEnabled').checked
            };
            
            // 判断是新增还是编辑
            if (this.currentEditSignalSourceUid) {
                // 编辑模式
                this.updateSignalSource(this.currentEditSignalSourceUid, signalSourceData);
            } else {
                // 新增模式
                this.createSignalSource(signalSourceData);
            }
        } else {
            this.showToast('错误', '请填写必填字段', 'danger');
        }
    }

    // 创建信号源
    async createSignalSource(signalSourceData) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/signal_sources`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(signalSourceData)
            });
            
            if (response.ok) {
                this.showToast('成功', '信号源创建成功', 'success');
                // 关闭模态框
                const modal = bootstrap.Modal.getInstance(document.getElementById('addSignalSourceModal'));
                if (modal) {
                    modal.hide();
                }
                // 刷新数据
                this.loadSignalSourcesData();
            } else {
                const errorData = await response.json();
                this.showToast('错误', errorData.message || '创建失败', 'danger');
            }
        } catch (error) {
            console.error('创建信号源失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }

    // 更新信号源
    async updateSignalSource(sourceUid, signalSourceData) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/signal_sources/${sourceUid}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(signalSourceData)
            });
            
            if (response.ok) {
                this.showToast('成功', '信号源更新成功', 'success');
                // 关闭模态框
                const modal = bootstrap.Modal.getInstance(document.getElementById('addSignalSourceModal'));
                if (modal) {
                    modal.hide();
                }
                // 刷新数据
                this.loadSignalSourcesData();
            } else {
                const errorData = await response.json();
                this.showToast('错误', errorData.message || '更新失败', 'danger');
            }
        } catch (error) {
            console.error('更新信号源失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }

    // 填充信号源表单
    fillSignalSourceForm(signalSource, isEdit = false) {
        document.getElementById('signalSourceName').value = signalSource.name || '';
        document.getElementById('signalSourceExchange').value = signalSource.exchange || '';
        document.getElementById('signalSourceApiKey').value = signalSource.api_key || '';
        document.getElementById('signalSourceApiSecret').value = signalSource.api_secret || '';
        document.getElementById('signalSourcePassphrase').value = signalSource.passphrase || '';
        document.getElementById('signalSourceInitAsset').value = signalSource.init_asset || '';
        document.getElementById('signalSourceLeverage').value = signalSource.leverage || 1;
        document.getElementById('signalSourceStopLossPercent').value = signalSource.stop_loss_percent || 0;
        document.getElementById('signalSourceEnabled').checked = signalSource.enabled || false;
        
        // 如果是编辑模式，禁用某些字段
        if (isEdit) {
            document.getElementById('signalSourceName').disabled = true;
        } else {
            document.getElementById('signalSourceName').disabled = false;
        }
    }

    // 清空信号源表单
    clearSignalSourceForm() {
        const form = document.getElementById('addSignalSourceForm');
        if (form) {
            form.reset();
        }
        
        // 重置编辑状态
        this.currentEditSignalSourceUid = null;
        
        // 重置模态框标题
        document.getElementById('addSignalSourceModalLabel').textContent = '添加信号源';
        
        // 启用所有字段
        document.getElementById('signalSourceName').disabled = false;
    }

    // 账户类型变化处理
    async onManualAccountTypeChange() {
        const accountType = document.getElementById('manualAccountType').value;
        const accountSelect = document.getElementById('manualAccount');
        
        if (!accountType) {
            accountSelect.innerHTML = '<option value="">请先选择账户类型</option>';
            return;
        }
        
        try {
            if (accountType === 'customer') {
                // 加载客户列表
                const response = await fetch(`${this.apiBaseUrl}/customers`);
                if (response.ok) {
                    const data = await response.json();
                    accountSelect.innerHTML = '<option value="">请选择客户</option>';
                    
                    const customers = data.data?.customers || data.data || [];
                    customers.forEach(customer => {
                        const option = document.createElement('option');
                        option.value = customer.customer_uid;
                        option.textContent = `${customer.name} (${customer.customer_uid})`;
                        accountSelect.appendChild(option);
                    });
                }
            } else if (accountType === 'signal') {
                // 加载信号源列表
                const response = await fetch(`${this.apiBaseUrl}/signal_sources`);
                if (response.ok) {
                    const data = await response.json();
                    accountSelect.innerHTML = '<option value="">请选择信号源</option>';
                    
                    const signalSources = Array.isArray(data.data) ? data.data : (data.data?.sources || []);
                    signalSources.forEach(source => {
                        const option = document.createElement('option');
                        option.value = source.source_uid;
                        option.textContent = `${source.name} (${source.source_uid})`;
                        accountSelect.appendChild(option);
                    });
                }
            }
        } catch (error) {
            console.error('加载账户列表失败:', error);
            this.showToast('错误', '加载账户列表失败', 'danger');
        }
    }

    // 保存手动开仓数据
    async saveManualPosition() {
        const form = document.getElementById('manualOpenPositionForm');
        if (form && form.checkValidity()) {
            const accountType = document.getElementById('manualAccountType').value;
            const accountUid = document.getElementById('manualAccount').value;
            const orderType = document.getElementById('manualOrderType').value;
            const price = document.getElementById('manualPrice').value;
            
            // 验证限价单价格
            if (orderType === 'limit' && (!price || parseFloat(price) <= 0)) {
                this.showToast('错误', '限价单必须填写有效价格', 'danger');
                return;
            }
            
            const manualPositionData = {
                strategy_uid: document.getElementById('manualStrategy').value,
                rule_uid: document.getElementById('manualRule').value,
                symbol: document.getElementById('manualSymbol').value.trim(),
                pos_side: document.getElementById('manualDirection').value,
                open_sz: parseFloat(document.getElementById('manualVolume').value),
                order_type: orderType,
                price: orderType === 'limit' ? parseFloat(price) : null,
                is_demo: document.getElementById('manualIsDemo').checked ? 1 : 0,
                reason: '手动开仓'
            };
            
            // 根据账户类型设置相应的UID字段
            if (accountType === 'signal') {
                manualPositionData.signal_source_uid = accountUid;
            } else {
                manualPositionData.customer_uid = accountUid;
            }
            
            try {
                // 根据账户类型选择API端点
                const endpoint = accountType === 'signal' ? '/manual/open_signal_position' : '/manual/open_position';
                const response = await fetch(`${this.apiBaseUrl}${endpoint}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(manualPositionData)
                });
                
                if (response.ok) {
                    const result = await response.json();
                    this.showToast('成功', '手动开仓成功', 'success');
                    
                    // 如果是限价单，显示撤单区域
                    const orderType = document.getElementById('manualOrderType').value;
                    if (orderType === 'limit') {
                        this.showCancelOrderSection();
                    } else {
                        // 市价单直接关闭模态框
                    const modal = bootstrap.Modal.getInstance(document.getElementById('manualOpenPositionModal'));
                    if (modal) {
                        modal.hide();
                        }
                    }
                    
                    // 刷新持仓数据
                    this.loadPositionsData();
                } else {
                    const errorData = await response.json();
                    console.error('手动开仓失败:', errorData);
                    this.showToast('错误', errorData.message || '手动开仓失败', 'danger');
                }
            } catch (error) {
                console.error('手动开仓请求失败:', error);
                this.showToast('错误', '网络请求失败，请检查网络连接', 'danger');
            }
        } else {
            this.showToast('错误', '请填写所有必填字段', 'danger');
            form.reportValidity();
        }
    }

    // 初始化限价单相关功能
    initLimitOrderFeatures() {
        const orderTypeSelect = document.getElementById('manualOrderType');
        const priceInput = document.getElementById('manualPrice');
        const priceHelpText = document.getElementById('priceHelpText');
        const priceAdjustmentRow = document.getElementById('priceAdjustmentRow');
        const getCurrentPriceBtn = document.getElementById('getCurrentPriceBtn');
        
        // 防止重复绑定事件监听器
        if (orderTypeSelect && !orderTypeSelect.hasAttribute('data-limit-features-initialized')) {
            orderTypeSelect.addEventListener('change', () => {
                this.handleOrderTypeChange();
            });
            orderTypeSelect.setAttribute('data-limit-features-initialized', 'true');
        }
        
        if (getCurrentPriceBtn && !getCurrentPriceBtn.hasAttribute('data-limit-features-initialized')) {
            getCurrentPriceBtn.addEventListener('click', () => {
                this.getCurrentPrice();
            });
            getCurrentPriceBtn.setAttribute('data-limit-features-initialized', 'true');
        }
        
        // 价格微调按钮事件（也需要防止重复绑定）
        this.initPriceAdjustmentButtons();
        
        // 初始化状态
        this.handleOrderTypeChange();
    }
    
    // 处理订单类型变化
    handleOrderTypeChange() {
        const orderTypeSelect = document.getElementById('manualOrderType');
        const priceInput = document.getElementById('manualPrice');
        const priceHelpText = document.getElementById('priceHelpText');
        const priceAdjustmentRow = document.getElementById('priceAdjustmentRow');
        const getCurrentPriceBtn = document.getElementById('getCurrentPriceBtn');
        
        // 检查元素是否存在
        if (!orderTypeSelect || !priceInput || !priceHelpText || !priceAdjustmentRow || !getCurrentPriceBtn) {
            console.warn('限价单相关DOM元素未找到，跳过处理');
            return;
        }
        
        const orderType = orderTypeSelect.value;
        
        if (orderType === 'limit') {
            priceInput.required = true;
            priceInput.disabled = false;
            priceHelpText.textContent = '限价单必须填写价格';
            priceAdjustmentRow.style.display = 'block';
            getCurrentPriceBtn.disabled = false;
        } else {
            priceInput.required = false;
            priceInput.disabled = true;
            priceInput.value = '';
            priceHelpText.textContent = '市价单时无需填写价格';
            priceAdjustmentRow.style.display = 'none';
            getCurrentPriceBtn.disabled = true;
        }
    }
    
    // 获取当前价格
    async getCurrentPrice() {
        const symbol = document.getElementById('manualSymbol').value;
        if (!symbol || symbol === 'custom') {
            this.showToast('错误', '请先选择交易对', 'danger');
            return;
        }
        
        try {
            // 使用WebSocket获取实时价格
            const price = await this.getTickerPrice(symbol);
            if (price) {
                document.getElementById('manualPrice').value = price.toFixed(2);
                this.showToast('成功', `已获取${symbol}当前价格: ${price.toFixed(2)}`, 'success');
            } else {
                this.showToast('错误', '获取价格失败', 'danger');
            }
        } catch (error) {
            console.error('获取价格失败:', error);
            this.showToast('错误', '获取价格失败', 'danger');
        }
    }
    
    // 通过OKX API获取ticker价格
    async getTickerPrice(symbol) {
        try {
            // 使用OKX公共API获取ticker数据
            const url = `https://www.okx.com/api/v5/market/ticker?instId=${symbol}`;
            
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.code !== '0') {
                throw new Error(data.msg || 'API请求失败');
            }
            
            if (data.data && data.data.length > 0) {
                const ticker = data.data[0];
                return parseFloat(ticker.last);
            } else {
                throw new Error('未获取到价格数据');
            }
        } catch (error) {
            console.error('获取ticker价格失败:', error);
            throw error;
        }
    }
    
    // 初始化价格微调按钮
    initPriceAdjustmentButtons() {
        const adjustments = [
            { id: 'priceMinus5', percent: -5 },
            { id: 'priceMinus1', percent: -1 },
            { id: 'priceMinus01', percent: -0.1 },
            { id: 'pricePlus01', percent: 0.1 },
            { id: 'pricePlus1', percent: 1 },
            { id: 'pricePlus5', percent: 5 }
        ];
        
        adjustments.forEach(adj => {
            const btn = document.getElementById(adj.id);
            if (btn && !btn.hasAttribute('data-price-adjustment-initialized')) {
                btn.addEventListener('click', () => {
                    this.adjustPrice(adj.percent);
                });
                btn.setAttribute('data-price-adjustment-initialized', 'true');
            }
        });
        
        // 重置按钮
        const resetBtn = document.getElementById('priceReset');
        if (resetBtn && !resetBtn.hasAttribute('data-price-adjustment-initialized')) {
            resetBtn.addEventListener('click', () => {
                this.resetPrice();
            });
            resetBtn.setAttribute('data-price-adjustment-initialized', 'true');
        }
    }
    
    // 调整价格
    adjustPrice(percent) {
        const priceInput = document.getElementById('manualPrice');
        const currentPrice = parseFloat(priceInput.value) || 0;
        
        if (currentPrice > 0) {
            const adjustment = currentPrice * (percent / 100);
            const newPrice = currentPrice + adjustment;
            priceInput.value = newPrice.toFixed(2);
        }
    }
    
    // 重置价格
    resetPrice() {
        this.getCurrentPrice();
    }
    
    // 显示撤单区域
    showCancelOrderSection() {
        const cancelOrderSection = document.getElementById('cancelOrderSection');
        if (cancelOrderSection) {
            cancelOrderSection.style.display = 'block';
            this.refreshPendingOrders();
        }
    }
    
    // 隐藏撤单区域
    hideCancelOrderSection() {
        const cancelOrderSection = document.getElementById('cancelOrderSection');
        if (cancelOrderSection) {
            cancelOrderSection.style.display = 'none';
        }
    }
    
    // 刷新未成交订单
    async refreshPendingOrders() {
        const accountType = document.getElementById('manualAccountType').value;
        const accountUid = document.getElementById('manualAccount').value;
        const isDemo = document.getElementById('manualIsDemo').checked ? 1 : 0;
        
        if (!accountType || !accountUid) {
            this.showToast('错误', '请先选择账户类型和账户', 'danger');
            return;
        }
        
        try {
            const response = await fetch(`${this.apiBaseUrl}/manual/orders?account_uid=${accountUid}&account_type=${accountType}&is_demo=${isDemo}&status=live`);
            
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.updatePendingOrdersTable(result.data);
                    this.showToast('成功', `刷新成功，共${result.count}个未成交订单`, 'success');
                } else {
                    this.showToast('错误', result.message || '刷新失败', 'danger');
                }
            } else {
                this.showToast('错误', '刷新订单状态失败', 'danger');
            }
        } catch (error) {
            console.error('刷新订单状态失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }
    
    // 更新未成交订单表格
    updatePendingOrdersTable(orders) {
        const tbody = document.getElementById('pendingOrdersTableBody');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        if (!orders || orders.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">暂无未成交订单</td></tr>';
            return;
        }
        
        orders.forEach(order => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${order.order_id}</td>
                <td>${order.symbol}</td>
                <td><span class="badge ${order.pos_side === 'long' ? 'bg-success' : 'bg-danger'}">${order.pos_side === 'long' ? '多' : '空'}</span></td>
                <td>${order.sz}</td>
                <td><span class="badge bg-warning">${this.getStatusText(order.status)}</span></td>
                <td>${this.formatDateTime(order.created_at)}</td>
                <td>
                    <button type="button" class="btn btn-outline-danger btn-sm" onclick="app.cancelSingleOrder('${order.order_id}', '${order.account_uid || ''}', '${order.account_type || 'customer'}')">
                        <i class="bi bi-x-circle"></i> 撤单
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
    }
    
    // 获取状态文本
    getStatusText(status) {
        const statusMap = {
            'live': '未成交',
            'partially_filled': '部分成交',
            'filled': '已成交',
            'canceled': '已撤单',
            'unknown': '未知'
        };
        return statusMap[status] || status;
    }
    
    // 撤单单个订单
    async cancelSingleOrder(orderId, accountUid, accountType) {
        if (!confirm(`确定要撤单订单 ${orderId} 吗？`)) {
            return;
        }
        
        // 如果accountUid为空，从当前表单获取
        if (!accountUid) {
            accountUid = document.getElementById('manualAccount').value;
            accountType = document.getElementById('manualAccountType').value;
        }
        
        if (!accountUid) {
            this.showToast('错误', '无法获取账户信息', 'danger');
            return;
        }
        
        const isDemo = document.getElementById('manualIsDemo').checked ? 1 : 0;
        
        try {
            const response = await fetch(`${this.apiBaseUrl}/manual/cancel_order`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    order_id: orderId,
                    account_uid: accountUid,
                    account_type: accountType,
                    is_demo: isDemo
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.showToast('成功', '撤单成功', 'success');
                    this.refreshPendingOrders(); // 刷新订单列表
                } else {
                    console.error('撤单失败:', result);
                    this.showToast('错误', result.message || '撤单失败', 'danger');
                }
            } else {
                const errorText = await response.text();
                console.error('撤单请求失败:', response.status, errorText);
                this.showToast('错误', `撤单失败: ${response.status} - ${errorText}`, 'danger');
            }
        } catch (error) {
            console.error('撤单失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }
    
    // 为持仓页面加载未成交订单
    async loadPendingOrdersForPositions() {
        try {
            
            // 获取所有客户和信号源的未成交订单
            const allOrders = [];
            
            // 获取客户未成交订单
            const customersResponse = await fetch(`${this.apiBaseUrl}/customers?is_demo=1`);
            if (customersResponse.ok) {
                const customersData = await customersResponse.json();
                const customers = customersData.data?.customers || [];
                
                for (const customer of customers) {
                    try {
                        const ordersResponse = await fetch(
                            `${this.apiBaseUrl}/manual/orders?account_uid=${customer.customer_uid}&account_type=customer&is_demo=1&status=live`
                        );
                        if (ordersResponse.ok) {
                            const ordersData = await ordersResponse.json();
                            const orders = ordersData.data || [];
                            allOrders.push(...orders.map(order => ({
                                ...order,
                                account_name: customer.name,
                                account_type: 'customer'
                            })));
                        }
                    } catch (error) {
                        console.warn(`获取客户 ${customer.name} 订单失败:`, error);
                    }
                }
            }
            
            // 获取信号源未成交订单
            const signalSourcesResponse = await fetch(`${this.apiBaseUrl}/signal_sources?is_demo=1`);
            if (signalSourcesResponse.ok) {
                const signalSourcesData = await signalSourcesResponse.json();
                const signalSources = signalSourcesData.data || [];
                
                for (const signalSource of signalSources) {
                    try {
                        const ordersResponse = await fetch(
                            `${this.apiBaseUrl}/manual/orders?account_uid=${signalSource.source_uid}&account_type=signal&is_demo=1&status=live`
                        );
                        if (ordersResponse.ok) {
                            const ordersData = await ordersResponse.json();
                            const orders = ordersData.data || [];
                            allOrders.push(...orders.map(order => ({
                                ...order,
                                account_name: signalSource.name,
                                account_type: 'signal'
                            })));
                        }
                    } catch (error) {
                        console.warn(`获取信号源 ${signalSource.name} 订单失败:`, error);
                    }
                }
            }
            
            // 渲染未成交订单表格
            this.renderPendingOrdersTableForPositions(allOrders);
            
        } catch (error) {
            console.error('加载未成交订单失败:', error);
            this.renderPendingOrdersTableForPositions([]);
        }
    }
    
    // 渲染持仓页面的未成交订单表格
    renderPendingOrdersTableForPositions(orders) {
        const tbody = document.getElementById('pendingOrdersTableBody');
        if (!tbody) {
            console.error('未找到未成交订单表格体');
            return;
        }
        
        if (!orders || orders.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">暂无未成交订单</td></tr>';
            return;
        }
        
        tbody.innerHTML = orders.map(order => `
            <tr>
                <td>
                    <span class="badge ${order.account_type === 'signal' ? 'bg-primary' : 'bg-success'}">
                        ${order.account_type === 'signal' ? '信号源' : '客户'}
                    </span>
                    ${order.account_name || order.account_uid}
                </td>
                <td>${order.symbol || '-'}</td>
                <td>
                    <span class="badge ${order.pos_side === 'long' ? 'bg-success' : 'bg-danger'}">
                        ${order.pos_side === 'long' ? '多' : '空'}
                    </span>
                </td>
                <td>${order.sz || '-'}</td>
                <td>${order.order_data?.px || '-'}</td>
                <td>
                    <span class="badge bg-warning">
                        ${this.getStatusText(order.status)}
                    </span>
                </td>
                <td>${this.formatDateTime(order.created_at)}</td>
                <td>
                    <button type="button" class="btn btn-outline-danger btn-sm" 
                            onclick="app.cancelSingleOrderFromPositions('${order.order_id}', '${order.account_uid}', '${order.account_type}')">
                        <i class="bi bi-x-circle"></i> 撤单
                    </button>
                    <button type="button" class="btn btn-outline-info btn-sm ms-1" 
                            onclick="app.checkOrderStatus('${order.order_id}')" title="检查订单状态">
                        <i class="bi bi-info-circle"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    }
    
    // 从持仓页面撤单单个订单
    async cancelSingleOrderFromPositions(orderId, accountUid, accountType) {
        if (!confirm(`确定要撤单订单 ${orderId} 吗？`)) {
            return;
        }
        
        try {
            
            const response = await fetch(`${this.apiBaseUrl}/manual/cancel_order`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    order_id: orderId,
                    account_uid: accountUid,
                    account_type: accountType,
                    is_demo: 1
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.showToast('成功', '撤单成功', 'success');
                    
                    // 延迟一下再刷新，确保数据库状态已更新
                    setTimeout(async () => {
                        await this.loadPendingOrdersForPositions();
                    }, 1000);
                } else {
                    console.error('撤单失败:', result);
                    this.showToast('错误', result.message || '撤单失败', 'danger');
                }
            } else {
                const errorText = await response.text();
                console.error('撤单请求失败:', response.status, errorText);
                this.showToast('错误', `撤单失败: ${response.status} - ${errorText}`, 'danger');
            }
        } catch (error) {
            console.error('撤单失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }
    
    // 调试所有订单状态
    async debugAllOrders() {
        try {
            
            // 获取所有客户和信号源
            const [customersResponse, signalSourcesResponse] = await Promise.all([
                fetch(`${this.apiBaseUrl}/customers?is_demo=1`),
                fetch(`${this.apiBaseUrl}/signal_sources?is_demo=1`)
            ]);
            
            const customers = customersResponse.ok ? (await customersResponse.json()).data?.customers || [] : [];
            const signalSources = signalSourcesResponse.ok ? (await signalSourcesResponse.json()).data || [] : [];
            
            
            // 检查所有账户的订单
            for (const customer of customers) {
                try {
                    const response = await fetch(
                        `${this.apiBaseUrl}/manual/orders?account_uid=${customer.customer_uid}&account_type=customer&is_demo=1&status=all`
                    );
                    if (response.ok) {
                        const data = await response.json();
                    }
                } catch (error) {
                    console.warn(`[调试] 客户 ${customer.name} 订单查询失败:`, error);
                }
            }
            
            for (const signalSource of signalSources) {
                try {
                    const response = await fetch(
                        `${this.apiBaseUrl}/manual/orders?account_uid=${signalSource.source_uid}&account_type=signal&is_demo=1&status=all`
                    );
                    if (response.ok) {
                        const data = await response.json();
                    }
                } catch (error) {
                    console.warn(`[调试] 信号源 ${signalSource.name} 订单查询失败:`, error);
                }
            }
            
            this.showToast('调试', '请查看控制台输出', 'info');
            
        } catch (error) {
            console.error('[调试] 调试失败:', error);
            this.showToast('错误', '调试失败', 'danger');
        }
    }
    
    // 检查订单状态（调试功能）
    async checkOrderStatus(orderId) {
        try {
            
            const response = await fetch(`${this.apiBaseUrl}/manual/check_order_status?order_id=${orderId}`);
            
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.showToast('调试', `订单状态: ${result.data.execution_status}`, 'info');
                } else {
                    console.error('检查失败:', result);
                    this.showToast('错误', result.message || '检查失败', 'danger');
                }
            } else {
                const errorText = await response.text();
                console.error('检查请求失败:', response.status, errorText);
                this.showToast('错误', `检查失败: ${response.status}`, 'danger');
            }
        } catch (error) {
            console.error('检查失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }
    
    // 清理重复订单
    async cleanupDuplicateOrders() {
        if (!confirm('确定要清理重复的订单记录吗？此操作不可撤销！')) {
            return;
        }
        
        try {
            const response = await fetch(`${this.apiBaseUrl}/manual/cleanup_duplicates`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.showToast('成功', result.message, 'success');
                    // 重新加载未成交订单
                    await this.loadPendingOrdersForPositions();
                } else {
                    console.error('清理失败:', result);
                    this.showToast('错误', result.message || '清理失败', 'danger');
                }
            } else {
                const errorText = await response.text();
                console.error('清理请求失败:', response.status, errorText);
                this.showToast('错误', `清理失败: ${response.status} - ${errorText}`, 'danger');
            }
        } catch (error) {
            console.error('清理失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }
    
    // 清理无效持仓
    async cleanupInvalidPositions() {
        if (!confirm('确定要清理无效的持仓记录吗？此操作将删除已撤单但仍有持仓记录的情况，不可撤销！')) {
            return;
        }
        
        try {
            const response = await fetch(`${this.apiBaseUrl}/manual/cleanup_invalid_positions`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.showToast('成功', result.message, 'success');
                    // 重新加载持仓数据
                    await this.loadPositionsData();
                } else {
                    console.error('清理失败:', result);
                    this.showToast('错误', result.message || '清理失败', 'danger');
                }
            } else {
                const errorText = await response.text();
                console.error('清理请求失败:', response.status, errorText);
                this.showToast('错误', `清理失败: ${response.status} - ${errorText}`, 'danger');
            }
        } catch (error) {
            console.error('清理失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }
    
    // 从持仓页面撤单所有未成交订单
    async cancelAllPendingOrdersForPositions() {
        if (!confirm('确定要撤单所有未成交订单吗？此操作不可撤销！')) {
            return;
        }
        
        try {
            // 获取所有未成交订单
            const tbody = document.getElementById('pendingOrdersTableBody');
            if (!tbody) {
                this.showToast('错误', '未找到订单列表', 'danger');
                return;
            }
            
            const rows = tbody.querySelectorAll('tr');
            if (rows.length === 0 || (rows.length === 1 && rows[0].cells[0].textContent.includes('暂无'))) {
                this.showToast('提示', '没有未成交订单', 'info');
                return;
            }
            
            let successCount = 0;
            let failCount = 0;
            
            // 遍历所有订单进行撤单
            for (const row of rows) {
                const cancelBtn = row.querySelector('button[onclick*="cancelSingleOrderFromPositions"]');
                if (cancelBtn) {
                    const onclick = cancelBtn.getAttribute('onclick');
                    const match = onclick.match(/cancelSingleOrderFromPositions\('([^']+)', '([^']+)', '([^']+)'\)/);
                    if (match) {
                        const [, orderId, accountUid, accountType] = match;
                        try {
                            const response = await fetch(`${this.apiBaseUrl}/manual/cancel_order`, {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                },
                                body: JSON.stringify({
                                    order_id: orderId,
                                    account_uid: accountUid,
                                    account_type: accountType,
                                    is_demo: 1
                                })
                            });
                            
                            if (response.ok) {
                                const result = await response.json();
                                if (result.success === 200) {
                                    successCount++;
                                } else {
                                    failCount++;
                                }
                            } else {
                                failCount++;
                            }
                        } catch (error) {
                            failCount++;
                        }
                    }
                }
            }
            
            this.showToast('完成', `批量撤单完成：成功${successCount}个，失败${failCount}个`, successCount > 0 ? 'success' : 'warning');
            
            // 重新加载未成交订单
            await this.loadPendingOrdersForPositions();
            
        } catch (error) {
            console.error('批量撤单失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }
    
    // 撤单所有未成交订单
    async cancelAllPendingOrders() {
        const accountType = document.getElementById('manualAccountType').value;
        const accountUid = document.getElementById('manualAccount').value;
        
        if (!accountType || !accountUid) {
            this.showToast('错误', '请先选择账户类型和账户', 'danger');
            return;
        }
        
        if (!confirm('确定要撤单所有未成交订单吗？此操作不可撤销！')) {
            return;
        }
        
        // 先获取所有未成交订单
        try {
            const response = await fetch(`${this.apiBaseUrl}/manual/orders?account_uid=${accountUid}&account_type=${accountType}&is_demo=${document.getElementById('manualIsDemo').checked ? 1 : 0}&status=live`);
            
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200 && result.data && result.data.length > 0) {
                    // 批量撤单
                    let successCount = 0;
                    let failCount = 0;
                    
                    for (const order of result.data) {
                        try {
                            const cancelResponse = await fetch(`${this.apiBaseUrl}/manual/cancel_order`, {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                },
                                body: JSON.stringify({
                                    order_id: order.order_id,
                                    account_uid: accountUid,
                                    account_type: accountType,
                                    is_demo: document.getElementById('manualIsDemo').checked ? 1 : 0
                                })
                            });
                            
                            if (cancelResponse.ok) {
                                const cancelResult = await cancelResponse.json();
                                if (cancelResult.success === 200) {
                                    successCount++;
                                } else {
                                    failCount++;
                                }
                            } else {
                                failCount++;
                            }
                        } catch (error) {
                            failCount++;
                        }
                    }
                    
                    this.showToast('完成', `批量撤单完成：成功${successCount}个，失败${failCount}个`, successCount > 0 ? 'success' : 'warning');
                    this.refreshPendingOrders(); // 刷新订单列表
                } else {
                    this.showToast('提示', '没有未成交订单', 'info');
                }
            } else {
                this.showToast('错误', '获取订单列表失败', 'danger');
            }
        } catch (error) {
            console.error('批量撤单失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        }
    }

    // 清空手动开仓表单
    clearManualPositionForm() {
        const form = document.getElementById('manualOpenPositionForm');
        if (form) {
            form.reset();
        }
        
        // 清空账户选择
        const accountSelect = document.getElementById('manualAccount');
        if (accountSelect) {
            accountSelect.innerHTML = '<option value="">请先选择账户类型</option>';
        }
        
        // 设置默认值
        const isDemoCheckbox = document.getElementById('manualIsDemo');
        if (isDemoCheckbox) {
            isDemoCheckbox.checked = false;
        }
        
        // 隐藏撤单区域
        this.hideCancelOrderSection();
        
        // 重置限价单相关状态（如果元素存在）
        try {
            this.handleOrderTypeChange();
        } catch (error) {
            console.warn('重置限价单状态时出错:', error);
        }
        
    }

    // 加载手动开仓表单数据
    async loadManualPositionFormData() {
        try {
            // 清空账户选择
            const accountSelect = document.getElementById('manualAccount');
            if (accountSelect) {
                accountSelect.innerHTML = '<option value="">请先选择账户类型</option>';
            }
            

            // 加载策略列表
            const strategiesResponse = await fetch(`${this.apiBaseUrl}/strategies`);
            if (strategiesResponse.ok) {
                const strategiesData = await strategiesResponse.json();
                const strategySelect = document.getElementById('manualStrategy');
                if (strategySelect && strategiesData.success) {
                    strategySelect.innerHTML = '<option value="manual">手动操作</option>';
                    const strategies = strategiesData.data.strategies || strategiesData.data;
                    if (Array.isArray(strategies)) {
                        strategies.forEach(strategy => {
                            const option = document.createElement('option');
                            option.value = strategy.strategy_uid;
                            option.textContent = strategy.name;
                            strategySelect.appendChild(option);
                        });
                    } else {
                        console.error('❌ 策略数据格式错误:', strategies);
                    }
                }
            } else {
                console.error('❌ 加载策略数据失败:', strategiesResponse.status);
            }

            // 加载规则列表
            const rulesResponse = await fetch(`${this.apiBaseUrl}/rules`);
            if (rulesResponse.ok) {
                const rulesData = await rulesResponse.json();
                const ruleSelect = document.getElementById('manualRule');
                if (ruleSelect && rulesData.success) {
                    ruleSelect.innerHTML = '<option value="manual">手动操作</option>';
                    const rules = rulesData.data.rules || rulesData.data;
                    if (Array.isArray(rules)) {
                        rules.forEach(rule => {
                            const option = document.createElement('option');
                            option.value = rule.rule_uid;
                            option.textContent = rule.name;
                            ruleSelect.appendChild(option);
                        });
                    } else {
                        console.error('❌ 规则数据格式错误:', rules);
                    }
                }
            } else {
                console.error('❌ 加载规则数据失败:', rulesResponse.status);
            }
        } catch (error) {
            console.error('❌ 加载手动开仓表单数据失败:', error);
        }
    }

    // 初始化自动刷新
    initAutoRefresh() {
        // 直接启动当前页面的自动刷新
        this.startAutoRefresh(this.currentPage);
    }





    // 启动自动刷新
    startAutoRefresh(pageName) {
        // 停止之前的定时器
        this.stopAutoRefresh(pageName);

        const interval = this.autoRefreshConfig.intervals[pageName];
        if (!interval) {
            return;
        }
        
        this.autoRefreshConfig.timers[pageName] = setInterval(() => {
            this.autoRefreshPage(pageName);
        }, interval);

        // 记录启动时间
        this.autoRefreshConfig.lastRefresh[pageName] = Date.now();
    }

    // 停止自动刷新
    stopAutoRefresh(pageName) {
        if (this.autoRefreshConfig.timers[pageName]) {
            clearInterval(this.autoRefreshConfig.timers[pageName]);
            delete this.autoRefreshConfig.timers[pageName];
        }
    }

    // 自动刷新页面
    async autoRefreshPage(pageName) {
        try {
            // 检查是否需要刷新（避免频繁刷新）
            const now = Date.now();
            const lastRefresh = this.autoRefreshConfig.lastRefresh[pageName] || 0;
            // K线图允许更频繁的刷新，其他页面保持5秒最小间隔
            const minInterval = pageName === 'kline' ? 500 : 5000;
            
            if (now - lastRefresh < minInterval) {
                return;
            }
            
            // 静默刷新，不显示加载状态
            switch (pageName) {
                case 'trades':
                    await this.loadTradesDataSilent();
                    break;
                case 'signal-trades':
                    await this.loadSignalTradesDataSilent();
                    break;
                case 'positions':
                    await this.loadPositionsDataSilent();
                    break;
                case 'dashboard':
                    await this.loadDashboardDataSilent();
                    break;
                case 'limit-follow':
                    await this.loadLimitFollowDataSilent();
                    break;
                case 'kline':
                    await this.updateKlineDataSilent();
                    break;
                default:
                    return;
            }

            // 更新最后刷新时间
            this.autoRefreshConfig.lastRefresh[pageName] = now;
            
        } catch (error) {
            console.error(`自动刷新失败:`, error);
        }
    }

    // 切换自动刷新开关
    toggleAutoRefresh(enabled) {
        this.autoRefreshConfig.enabled = enabled;
        
        if (enabled) {
            this.startAutoRefresh(this.currentPage);
            this.showToast('信息', '自动刷新已启用', 'info');
        } else {
            this.stopAutoRefresh(this.currentPage);
            this.showToast('信息', '自动刷新已禁用', 'info');
        }
        
        // 保存设置到localStorage
        localStorage.setItem('autoRefreshEnabled', enabled.toString());
    }

    // 更新调试信息
    updateDebugInfo(message) {
        const debugContainer = document.getElementById('systemLogsDebug');
        const debugInfo = document.getElementById('debugInfo');
        
        if (debugContainer && debugInfo) {
            debugInfo.textContent = message;
            debugContainer.style.display = 'block';
        }
    }

    // ==================== 限价跟单模块 ====================
    
    // 初始化限价跟单模块
    initLimitFollowModule() {
        // 初始化限价跟单模块
        console.log('初始化限价跟单模块...');
        
        // 绑定事件
        this.bindLimitFollowEvents();
        
        // 加载策略和订单数据
        this.loadLimitFollowData();
        
        // 加载跟单员数据
        this.loadLimitFollowTraders();
        
        // 设置自动刷新
        this.startAutoRefresh('limit-follow');
    }
    
    bindLimitFollowEvents() {
        // 绑定限价跟单相关事件
        const self = this;
        
        // 跟单员管理事件
        document.addEventListener('click', function(e) {
            if (e.target.matches('#addLimitFollowTrader')) {
                self.showAddLimitFollowTraderModal();
            } else if (e.target.matches('#saveLimitFollowTraderBtn')) {
                self.saveLimitFollowTrader();
            } else if (e.target.matches('.edit-limit-follow-trader')) {
                const traderId = e.target.dataset.traderId;
                self.editLimitFollowTrader(traderId);
            } else if (e.target.matches('.delete-limit-follow-trader')) {
                const traderId = e.target.dataset.traderId;
                self.deleteLimitFollowTrader(traderId);
            } else if (e.target.matches('.toggle-limit-follow-trader')) {
                const traderId = e.target.dataset.traderId;
                self.toggleLimitFollowTrader(traderId);
            }
        });
        
        // 策略管理事件
        document.addEventListener('click', function(e) {
            if (e.target.matches('#addLimitFollowStrategy')) {
                self.showAddLimitFollowStrategyModal();
            } else if (e.target.matches('#saveLimitFollowModalStrategy')) {
                self.saveLimitFollowStrategy();
            } else if (e.target.matches('.edit-limit-follow-strategy')) {
                const strategyId = e.target.dataset.strategyId;
                self.editLimitFollowStrategy(strategyId);
            } else if (e.target.matches('.delete-limit-follow-strategy')) {
                const strategyId = e.target.dataset.strategyId;
                self.deleteLimitFollowStrategy(strategyId);
            } else if (e.target.matches('.toggle-limit-follow-strategy')) {
                const strategyId = e.target.dataset.strategyId;
                self.toggleLimitFollowStrategy(strategyId);
            }
        });
        
        // 订单管理事件
        document.addEventListener('click', function(e) {
            if (e.target.matches('.cancel-limit-follow-order')) {
                const orderUid = e.target.dataset.orderUid;
                self.cancelLimitFollowOrder(orderUid);
            } else if (e.target.matches('#refreshLimitFollowOrders')) {
                self.loadLimitFollowOrders();
            }
        });
        
        // 交易对设置切换事件
        document.addEventListener('change', function(e) {
            if (e.target.matches('input[name="symbolType"]')) {
                self.handleSymbolTypeChange();
            }
        });
    }
    
    // 加载限价跟单数据
    async loadLimitFollowData() {
        try {
            // 加载策略列表
            await this.loadLimitFollowStrategies();
            
            // 加载订单列表
            await this.loadLimitFollowOrders();
            
            // 加载下拉选项数据
            await this.loadLimitFollowOptions();
            
            // 启动限价跟单页面自动刷新
            this.startAutoRefresh('limit-follow');
            
        } catch (error) {
            console.error('加载限价跟单数据失败:', error);
        }
    }

    // 静默加载限价跟单数据（用于自动刷新）
    async loadLimitFollowDataSilent() {
        try {
            // 静默加载策略列表和订单列表，不显示加载状态
            await this.loadLimitFollowStrategies();
            await this.loadLimitFollowOrders();
        } catch (error) {
            console.error('静默加载限价跟单数据失败:', error);
        }
    }
    
    // 加载限价跟单策略列表
    async loadLimitFollowStrategies() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/strategies`);
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.renderLimitFollowStrategiesTable(result.data);
                } else {
                    console.error('获取策略列表失败:', result.message);
                }
            } else {
                console.error('获取策略列表请求失败:', response.status);
            }
        } catch (error) {
            console.error('加载策略列表失败:', error);
        }
    }
    
    // 渲染限价跟单策略表格
    renderLimitFollowStrategiesTable(strategies) {
        const tbody = document.querySelector('#limitFollowStrategiesTable tbody');
        if (!tbody) {
            console.error('找不到策略表格tbody元素');
            return;
        }
        
        tbody.innerHTML = '';
        
        if (!strategies || strategies.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted">暂无策略</td></tr>';
            return;
        }
        
        strategies.forEach(strategy => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${strategy.strategy_name || strategy.name || '未命名策略'}</td>
                <td>${strategy.trader_name || strategy.trader_unique_name || '未知跟单员'}</td>
                <td>${strategy.customer_name || strategy.customer_uid || '未知客户'}</td>
                <td>${strategy.symbol}</td>
                <td><span class="badge bg-${strategy.pos_side === 'both' ? 'info' : (strategy.pos_side === 'long' ? 'success' : 'danger')}">${strategy.pos_side === 'both' ? '双向' : (strategy.pos_side === 'long' ? '多仓' : '空仓')}</span></td>
                <td>${strategy.follow_type === 'percentage' ? '价格偏移' : '固定价格'}</td>
                <td>${strategy.follow_value}% (${strategy.min_follow_value}% - ${strategy.max_follow_value}%)</td>
                <td><span class="badge bg-${strategy.enabled ? 'success' : 'secondary'}">${strategy.enabled ? '启用' : '禁用'}</span></td>
                <td>
                    <button class="btn btn-sm btn-outline-primary" onclick="app.editLimitFollowStrategy(${strategy.id})">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="app.deleteLimitFollowStrategy(${strategy.id})">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
    }
    
    // 加载限价跟单订单列表
    async loadLimitFollowOrders() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/orders`);
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.renderLimitFollowOrdersTable(result.data);
                } else {
                    console.error('获取订单列表失败:', result.message);
                }
            } else {
                console.error('获取订单列表请求失败:', response.status);
            }
        } catch (error) {
            console.error('加载订单列表失败:', error);
        }
    }
    
    // 渲染限价跟单订单表格
    renderLimitFollowOrdersTable(orders) {
        const tbody = document.querySelector('#limitFollowOrdersTable tbody');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        if (!orders || orders.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted">暂无订单</td></tr>';
            return;
        }
        
        orders.forEach(order => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${order.order_uid}</td>
                <td>${order.customer_uid}</td>
                <td>${order.symbol}</td>
                <td><span class="badge bg-${order.pos_side === 'long' ? 'success' : 'danger'}">${order.pos_side}</span></td>
                <td>${order.target_price}</td>
                <td>${order.order_size}</td>
                <td><span class="badge bg-${this.getOrderStatusBadge(order.status)}">${this.getOrderStatusText(order.status)}</span></td>
                <td>${this.formatDateTime(order.created_at)}</td>
                <td>
                    <button class="btn btn-sm btn-outline-warning" onclick="app.cancelLimitFollowOrder('${order.order_uid}')" ${order.status !== 'pending' && order.status !== 'live' ? 'disabled' : ''}>
                        <i class="bi bi-x-circle"></i> 撤单
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
    }
    
    // 加载限价跟单选项数据
    async loadLimitFollowOptions() {
        try {
            // 加载跟单员列表
            const tradersResponse = await fetch(`${this.apiBaseUrl}/limit-follow/traders`);
            if (tradersResponse.ok) {
                const result = await tradersResponse.json();
                if (result.success === 200 && result.data) {
                    this.populateSelectOptions('limitFollowStrategyTrader', result.data, 'unique_name', 'name');
                } else {
                    console.warn('跟单员API返回失败:', result);
                }
            } else {
                console.warn('跟单员API请求失败:', tradersResponse.status);
            }
            
            // 加载客户列表
            const customersResponse = await fetch(`${this.apiBaseUrl}/customers`);
            if (customersResponse.ok) {
                const result = await customersResponse.json();
                if (result.success === 200 && result.data && result.data.customers) {
                    // 先添加普通客户
                    this.populateSelectOptions('limitFollowStrategyCustomer', result.data.customers, 'customer_uid', 'name');
                } else {
                    console.warn('客户API返回失败:', result);
                }
            } else {
                console.warn('客户API请求失败:', customersResponse.status);
            }
            
            // 加载信号源列表并添加到客户选项中
            const signalSourcesResponse = await fetch(`${this.apiBaseUrl}/signal_sources`);
            if (signalSourcesResponse.ok) {
                const result = await signalSourcesResponse.json();
                if (result.success === 200 && result.data) {
                    // 将信号源也添加到客户选项中
                    const customerSelect = document.getElementById('limitFollowStrategyCustomer');
                    if (customerSelect) {
                        // 添加分隔符
                        const separator = document.createElement('option');
                        separator.disabled = true;
                        separator.textContent = '--- 信号源 ---';
                        customerSelect.appendChild(separator);
                        
                        // 添加信号源选项
                        result.data.forEach(signalSource => {
                            const option = document.createElement('option');
                            option.value = signalSource.source_uid;  // 直接使用source_uid，不加signal_前缀
                            option.textContent = `[信号源] ${signalSource.name}`;
                            customerSelect.appendChild(option);
                        });
                    }
                } else {
                    console.warn('信号源API返回失败:', result);
                }
            } else {
                console.warn('信号源API请求失败:', signalSourcesResponse.status);
            }
            
        } catch (error) {
            console.error('加载选项数据失败:', error);
        }
    }

    // 填充下拉选项
    populateSelectOptions(selectId, data, valueField, textField) {

        const select = document.getElementById(selectId);
        if (!select) {
            console.error(`populateSelectOptions: 找不到元素 ${selectId}`);
            return;
        }
        
        // 更强的数据检查
        if (!data) {
            console.error(`populateSelectOptions: data为null或undefined`, data);
            return;
        }
        
        if (!Array.isArray(data)) {
            console.error(`populateSelectOptions: data不是数组，类型: ${typeof data}`, data);
            return;
        }
        
        // 保留第一个选项
        const firstOption = select.options[0];
        select.innerHTML = '';
        if (firstOption) {
            select.appendChild(firstOption);
        }
        
        try {
            data.forEach(item => {
                if (item && item[valueField] !== undefined && item[textField] !== undefined) {
                    const option = document.createElement('option');
                    option.value = item[valueField];
                    option.textContent = item[textField];
                    select.appendChild(option);
                }
            });
        } catch (error) {
            console.error(`populateSelectOptions: forEach执行失败`, error, data);
        }
    }
    
    // 保存限价跟单策略
    async saveLimitFollowStrategy() {
        try {
            const formData = this.getLimitFollowFormData();
            if (!formData) {
                return;
            }
            
            // 检查是否为编辑模式
            const modal = document.getElementById('addLimitFollowStrategyModal');
            const isEditMode = modal.dataset.editMode === 'true';
            const strategyId = modal.dataset.strategyId;
            
            let url, method;
            if (isEditMode) {
                url = `${this.apiBaseUrl}/limit-follow/strategies/${strategyId}`;
                method = 'PUT';
            } else {
                url = `${this.apiBaseUrl}/limit-follow/strategies`;
                method = 'POST';
            }
            
            const response = await fetch(url, {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            });
            
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    const message = isEditMode ? '策略更新成功' : '策略保存成功';
                    this.showToast('成功', message, 'success');
                    
                    // 关闭模态框
                    const modalInstance = bootstrap.Modal.getInstance(document.getElementById('addLimitFollowStrategyModal'));
                    if (modalInstance) {
                        modalInstance.hide();
                    }
                    
                    // 重新加载数据
                    await this.loadLimitFollowData();
                    
                    // 清空表单和编辑模式标识
                    this.clearLimitFollowForm();
                    modal.dataset.editMode = 'false';
                    modal.dataset.strategyId = '';
                    
                    // 重置模态框标题
                    document.querySelector('#addLimitFollowStrategyModal .modal-title').textContent = '新建策略';
                    
                } else {
                    this.showToast('错误', result.message || '保存失败', 'danger');
                }
            } else {
                const errorText = await response.text();
                console.error('API请求失败，状态:', response.status, '响应:', errorText);
                this.showToast('错误', `保存请求失败: ${response.status}`, 'danger');
            }
            
        } catch (error) {
            console.error('保存策略失败:', error);
            this.showToast('错误', '保存失败，请检查网络连接', 'danger');
        }
    }
    
    // 显示添加限价跟单策略模态框
    async showAddLimitFollowStrategyModal() {
        // 加载选项数据
        await this.loadLimitFollowOptions();
        
        // 显示模态框
        const modal = new bootstrap.Modal(document.getElementById('addLimitFollowStrategyModal'));
        modal.show();
    }
    
    // 生成策略UID
    generateStrategyUid() {
        const timestamp = Date.now();
        const random = Math.floor(Math.random() * 1000);
        return `LIMIT_FOLLOW_${timestamp}_${random}`;
    }
    
    // 获取表单数据
    getLimitFollowFormData() {
        const strategyName = document.getElementById('limitFollowStrategyName').value;
        const traderUniqueName = document.getElementById('limitFollowStrategyTrader').value;
        const customerUid = document.getElementById('limitFollowStrategyCustomer').value;
        const symbol = document.getElementById('limitFollowStrategySymbol').value;
        const posSide = document.getElementById('limitFollowStrategyPosSide').value;
        const followType = document.getElementById('limitFollowStrategyFollowType').value;
        const followValue = parseFloat(document.getElementById('limitFollowStrategyFollowValue').value);
        const maxOrders = parseInt(document.getElementById('limitFollowStrategyMaxOrdersPerSignal').value);
        const minValue = parseFloat(document.getElementById('limitFollowStrategyMinFollowValue').value);
        const maxValue = parseFloat(document.getElementById('limitFollowStrategyMaxFollowValue').value);
        const autoCancel = document.getElementById('limitFollowStrategyAutoCancelOnSignalClose').value === 'true';

        // 验证必填字段
        if (!strategyName || !traderUniqueName || !customerUid || !symbol || !posSide || !followType || !followValue) {
            this.showToast('错误', '请填写所有必填字段', 'danger');
            return null;
        }

        // 验证跟单值范围
        if (followValue < 0.1 || followValue > 10) {
            this.showToast('错误', '跟单值建议在 0.1% - 10% 之间', 'danger');
            return null;
        }

        // 验证最小值和最大值
        if (minValue < 0.1 || maxValue > 10) {
            this.showToast('错误', '最小值和最大值建议在 0.1% - 10% 之间', 'danger');
            return null;
        }

        // 验证跟单值必须在最小值和最大值之间
        if (followValue < minValue || followValue > maxValue) {
            this.showToast('错误', '跟单值必须在最小值和最大值之间', 'danger');
            return null;
        }

        // 验证最大订单数量
        if (maxOrders < 1 || maxOrders > 10) {
            this.showToast('错误', '最大订单数量建议在 1 - 10 之间', 'danger');
            return null;
        }

        const result = {
            strategy_name: strategyName,
            trader_unique_name: traderUniqueName,
            customer_uid: customerUid,
            symbol: symbol,
            pos_side: posSide,
            follow_type: followType,
            follow_value: followValue,
            max_orders_per_signal: maxOrders,
            min_follow_value: minValue,
            max_follow_value: maxValue,
            auto_cancel_on_signal_close: autoCancel
        };

        return result;
    }
    
    // 清空表单
    clearLimitFollowForm() {
        document.getElementById('addLimitFollowStrategyForm').reset();
        
        // 重置编辑模式标识
        const modal = document.getElementById('addLimitFollowStrategyModal');
        modal.dataset.editMode = 'false';
        modal.dataset.strategyId = '';
        
        // 重置模态框标题
        document.querySelector('#addLimitFollowStrategyModal .modal-title').textContent = '新建策略';
    }
    
    // 编辑策略
    async editLimitFollowStrategy(strategyId) {
        try {
            
            // 获取策略数据
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/strategies/${strategyId}`);
            if (!response.ok) {
                this.showToast('错误', '获取策略数据失败', 'danger');
                return;
            }
            
            const result = await response.json();
            if (result.success !== 200) {
                this.showToast('错误', result.message || '获取策略数据失败', 'danger');
                return;
            }
            
            const strategy = result.data;
            
            // 加载选项数据
            await this.loadLimitFollowOptions();
            
            // 填充表单数据
            document.getElementById('limitFollowStrategyName').value = strategy.strategy_name || '';
            document.getElementById('limitFollowStrategyTrader').value = strategy.trader_unique_name || '';
            document.getElementById('limitFollowStrategyCustomer').value = strategy.customer_uid || '';
            if (strategy.symbol === 'ALL') {
                document.getElementById('symbolTypeAll').checked = true;
                document.getElementById('symbolTypeSpecific').checked = false;
                document.getElementById('specificSymbolsContainer').style.display = 'none';
            } else {
                document.getElementById('symbolTypeAll').checked = false;
                document.getElementById('symbolTypeSpecific').checked = true;
                document.getElementById('specificSymbolsContainer').style.display = 'block';
                
                // 设置选中的交易对
                if (strategy.symbols && Array.isArray(strategy.symbols)) {
                    const symbolsSelect = document.getElementById('limitFollowStrategySymbols');
                    Array.from(symbolsSelect.options).forEach(option => {
                        option.selected = strategy.symbols.includes(option.value);
                    });
                }
            };
            document.getElementById('limitFollowStrategyPosSide').value = strategy.pos_side || 'both';
            document.getElementById('limitFollowStrategyFollowType').value = strategy.follow_type || 'percentage';
            document.getElementById('limitFollowStrategyFollowValue').value = strategy.follow_value || '';
            document.getElementById('limitFollowStrategyMaxOrdersPerSignal').value = strategy.max_orders_per_signal || 4;
            document.getElementById('limitFollowStrategyMaxNetLeverage').value = strategy.max_net_leverage || 10.0;
            document.getElementById('limitFollowStrategyProportionalPosition').checked = strategy.proportional_position || false;
            document.getElementById('limitFollowStrategyMinFollowValue').value = strategy.min_follow_value || 0.5;
            document.getElementById('limitFollowStrategyMaxFollowValue').value = strategy.max_follow_value || 5.0;
            document.getElementById('limitFollowStrategyAutoCancelOnSignalClose').value = strategy.auto_cancel_on_signal_close ? 'true' : 'false';
            
            // 修改模态框标题
            document.querySelector('#addLimitFollowStrategyModal .modal-title').textContent = '编辑策略';
            
            // 设置编辑模式标识
            document.getElementById('addLimitFollowStrategyModal').dataset.editMode = 'true';
            document.getElementById('addLimitFollowStrategyModal').dataset.strategyId = strategyId;
            
            // 显示模态框
            const modal = new bootstrap.Modal(document.getElementById('addLimitFollowStrategyModal'));
            modal.show();
            
        } catch (error) {
            console.error('编辑策略失败:', error);
            this.showToast('错误', '编辑策略失败，请检查网络连接', 'danger');
        }
    }

    // 删除限价跟单策略
    async deleteLimitFollowStrategy(strategyId) {
        try {
            if (!confirm(`确定要删除策略 ${strategyId} 吗？此操作不可恢复。`)) {
                return;
            }
            
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/strategies/${strategyId}`, {
                method: 'DELETE'
            });
            
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.showToast('成功', '策略删除成功', 'success');
                    // 重新加载策略列表
                    this.loadLimitFollowStrategies();
                } else {
                    console.error('删除策略失败:', result.message);
                    this.showToast('错误', `删除策略失败: ${result.message}`, 'danger');
                }
            } else {
                console.error('删除策略请求失败:', response.status);
                this.showToast('错误', '删除策略请求失败', 'danger');
            }
        } catch (error) {
            console.error('删除策略失败:', error);
            this.showToast('错误', `删除策略失败: ${error.message}`, 'danger');
        }
    }

    // 切换限价跟单策略启用状态
    async toggleLimitFollowStrategy(strategyId) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/strategies/${strategyId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    enabled: 'toggle' // 特殊值，后端会切换状态
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.showToast('成功', '策略状态切换成功', 'success');
                    // 重新加载策略列表
                    this.loadLimitFollowStrategies();
                } else {
                    console.error('切换策略状态失败:', result.message);
                    this.showToast('错误', `切换策略状态失败: ${result.message}`, 'danger');
                }
            } else {
                console.error('切换策略状态请求失败:', response.status);
                this.showToast('错误', '切换策略状态请求失败', 'danger');
            }
        } catch (error) {
            console.error('切换策略状态失败:', error);
            this.showToast('错误', `切换策略状态失败: ${error.message}`, 'danger');
        }
    }

    // 取消限价跟单订单
    async cancelLimitFollowOrder(orderUid) {
        try {
            if (!confirm(`确定要取消订单 ${orderUid} 吗？`)) {
                return;
            }
            
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/orders/${orderUid}/cancel`, {
                method: 'POST'
            });
            
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.showToast('成功', '订单取消成功', 'success');
                    // 重新加载订单列表
                    this.loadLimitFollowOrders();
                } else {
                    console.error('取消订单失败:', result.message);
                    this.showToast('错误', `取消订单失败: ${result.message}`, 'danger');
                }
            } else {
                console.error('取消订单请求失败:', response.status);
                this.showToast('错误', '取消订单请求失败', 'danger');
            }
        } catch (error) {
            console.error('取消订单失败:', error);
            this.showToast('错误', `取消订单失败: ${error.message}`, 'danger');
        }
    }

    // 保存限价跟单配置
    async saveLimitFollowConfig() {
        try {
            this.showToast('信息', '配置保存功能开发中...', 'info');
        } catch (error) {
            console.error('保存配置失败:', error);
            this.showToast('错误', `保存配置失败: ${error.message}`, 'danger');
        }
    }

    // 重置限价跟单配置
    resetLimitFollowConfig() {
        try {
            this.showToast('信息', '配置重置功能开发中...', 'info');
        } catch (error) {
            console.error('重置配置失败:', error);
            this.showToast('错误', `重置配置失败: ${error.message}`, 'danger');
        }
    }

    // 显示执行跟单模态框
    showExecuteLimitFollowModal() {
        try {
            this.showToast('信息', '执行跟单功能开发中...', 'info');
        } catch (error) {
            console.error('显示执行跟单模态框失败:', error);
            this.showToast('错误', `显示执行跟单模态框失败: ${error.message}`, 'danger');
        }
    }

    // 提交执行跟单
    async submitLimitFollowExecution() {
        try {
            this.showToast('信息', '执行跟单功能开发中...', 'info');
        } catch (error) {
            console.error('提交执行跟单失败:', error);
            this.showToast('错误', `提交执行跟单失败: ${error.message}`, 'danger');
        }

    }

    // ==================== 跟单员管理 ====================
    
    async loadLimitFollowTraders() {
        try {
            const response = await fetch('/api/v1/limit-follow/traders');
            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.renderLimitFollowTradersTable(data.data);
                } else {
                    console.error('加载跟单员数据失败:', data.message);
                }
            } else {
                console.error('加载跟单员数据失败:', response.status);
            }
        } catch (error) {
            console.error('加载跟单员数据失败:', error);
        }
    }
    
    renderLimitFollowTradersTable(traders) {
        const tbody = document.querySelector('#limitFollowTradersTable tbody');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        if (!traders || traders.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">暂无跟单员数据</td></tr>';
            return;
        }
        
        traders.forEach(trader => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><code>${trader.unique_name}</code></td>
                <td>${trader.name}</td>
                <td>${trader.description || '-'}</td>
                <td>
                    <span class="badge ${trader.enabled ? 'bg-success' : 'bg-secondary'}">
                        ${trader.enabled ? '启用' : '禁用'}
                    </span>
                </td>
                <td>${this.formatDateTime(trader.created_at)}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary edit-limit-follow-trader" 
                            data-trader-id="${trader.id}">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-warning toggle-limit-follow-trader" 
                            data-trader-id="${trader.id}">
                        <i class="bi bi-${trader.enabled ? 'pause' : 'play'}"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger delete-limit-follow-trader" 
                            data-trader-id="${trader.id}">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
    }
    
    showAddLimitFollowTraderModal() {
        // 清空表单
        document.getElementById('addLimitFollowTraderForm').reset();
        
        // 显示模态框
        const modal = new bootstrap.Modal(document.getElementById('addLimitFollowTraderModal'));
        modal.show();
    }
    
    async saveLimitFollowTrader() {
        try {
            const formData = this.getLimitFollowTraderFormData();
            
            const response = await fetch('/api/v1/limit-follow/traders', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(formData)
            });
            
            if (response.ok) {
                const result = await response.json();
                if (result.success) {
                    this.showToast('成功', '跟单员创建成功', 'success');
                    
                    // 关闭模态框
                    const modal = bootstrap.Modal.getInstance(document.getElementById('addLimitFollowTraderModal'));
                    modal.hide();
                    
                    // 重新加载数据
                    this.loadLimitFollowTraders();
                } else {
                    this.showToast('错误', result.message, 'error');
                }
            } else {
                this.showToast('错误', '创建跟单员失败', 'error');
            }
        } catch (error) {
            console.error('保存跟单员失败:', error);
            this.showToast('错误', '保存跟单员失败', 'error');
        }
    }
    
    getLimitFollowTraderFormData() {
        return {
            unique_name: document.getElementById('traderUniqueName').value,
            name: document.getElementById('traderName').value,
            description: document.getElementById('traderDescription').value,
            enabled: document.getElementById('traderEnabled').checked
        };
    }
    
    // ==================== 交易对设置处理 ====================
    
    handleSymbolTypeChange() {
        const symbolTypeAll = document.getElementById('symbolTypeAll');
        const specificSymbolsContainer = document.getElementById('specificSymbolsContainer');
        
        if (symbolTypeAll.checked) {
            specificSymbolsContainer.style.display = 'none';
        } else {
            specificSymbolsContainer.style.display = 'block';
        }
    }
    
    getLimitFollowFormData() {
        const formData = {
            strategy_name: document.getElementById('limitFollowStrategyName').value,
            customer_uid: document.getElementById('limitFollowStrategyCustomer').value,
            trader_unique_name: document.getElementById('limitFollowStrategyTrader').value,
            pos_side: document.getElementById('limitFollowStrategyPosSide').value,
            follow_type: document.getElementById('limitFollowStrategyFollowType').value,
            follow_value: parseFloat(document.getElementById('limitFollowStrategyFollowValue').value),
            min_follow_value: parseFloat(document.getElementById('limitFollowStrategyMinFollowValue').value),
            max_follow_value: parseFloat(document.getElementById('limitFollowStrategyMaxFollowValue').value),
            max_orders_per_signal: parseInt(document.getElementById('limitFollowStrategyMaxOrdersPerSignal').value),
            max_net_leverage: parseFloat(document.getElementById('limitFollowStrategyMaxNetLeverage').value),
            proportional_position: document.getElementById('limitFollowStrategyProportionalPosition').checked,
            auto_cancel_on_signal_close: document.getElementById('limitFollowStrategyAutoCancelOnSignalClose').checked,
            enabled: document.getElementById('limitFollowStrategyEnabled').checked
        };
        
        // 处理交易对设置
        const symbolTypeAll = document.getElementById('symbolTypeAll');
        if (symbolTypeAll.checked) {
            formData.symbol = 'ALL'; // 跟随全部交易对
            formData.symbols = []; // 空数组表示全部
        } else {
            formData.symbol = 'SPECIFIC'; // 指定交易对
            const symbolsSelect = document.getElementById('limitFollowStrategySymbols');
            formData.symbols = Array.from(symbolsSelect.selectedOptions).map(option => option.value);
        }
        
        return formData;
    }

    // ==================== 策略交易模块 ====================
    
    // 加载策略交易数据
    async loadStrategyTradeData() {
        try {
            // 加载策略统计
            await this.loadStrategyTradeStats();
            
            // 加载策略列表
            await this.loadStrategyTradeList();
            
            // 加载回测历史
            await this.loadBacktestHistory();
            
        } catch (error) {
            console.error('加载策略交易数据失败:', error);
            this.showToast('错误', '加载策略交易数据失败', 'danger');
        }
    }
    
    // 加载策略交易统计
    async loadStrategyTradeStats() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/strategy-trade/status`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.data) {
                    // 更新统计卡片 - 如果API返回了统计数据
                    document.getElementById('running-strategies').textContent = data.data.running_strategies || '-';
                    document.getElementById('total-return').textContent = data.data.total_return ? 
                        (data.data.total_return * 100).toFixed(2) + '%' : '-';
                    document.getElementById('total-trades').textContent = data.data.total_trades || '-';
                    document.getElementById('win-rate').textContent = data.data.win_rate ? 
                        (data.data.win_rate * 100).toFixed(2) + '%' : '-';
                }
            } else {
                // 如果策略交易API不可用，显示默认值
                document.getElementById('running-strategies').textContent = '0';
                document.getElementById('total-return').textContent = '-';
                document.getElementById('total-trades').textContent = '0';
                document.getElementById('win-rate').textContent = '-';
            }
        } catch (error) {
            console.error('加载策略交易统计失败:', error);
            // 显示默认值
            document.getElementById('running-strategies').textContent = '0';
            document.getElementById('total-return').textContent = '-';
            document.getElementById('total-trades').textContent = '0';
            document.getElementById('win-rate').textContent = '-';
        }
    }
    
    // 加载策略列表
    async loadStrategyTradeList() {
        try {
            const tableBody = document.getElementById('strategyTradeTableBody');
            if (!tableBody) {
                console.warn('策略表格不存在，可能不在策略交易页面');
                return;
            }
            
            tableBody.innerHTML = '<tr><td colspan="9" class="text-center">加载中...</td></tr>';
            
            const response = await fetch(`${this.apiBaseUrl}/strategy/instances`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && Array.isArray(data.data)) {
                    this.renderStrategyTradeTable(data.data);
                } else {
                    tableBody.innerHTML = '<tr><td colspan="9" class="text-center text-muted">暂无策略数据</td></tr>';
                }
            } else {
                tableBody.innerHTML = '<tr><td colspan="9" class="text-center text-danger">策略交易模块不可用</td></tr>';
            }
        } catch (error) {
            console.error('加载策略列表失败:', error);
            const tableBody = document.getElementById('strategyTradeTableBody');
            if (tableBody) {
                tableBody.innerHTML = '<tr><td colspan="9" class="text-center text-danger">加载失败</td></tr>';
            }
        }
    }
    
    // 渲染策略交易表格
    renderStrategyTradeTable(strategies) {
        const tableBody = document.getElementById('strategyTradeTableBody');
        if (!tableBody) return;
        
        if (!strategies || strategies.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="9" class="text-center text-muted">暂无策略数据</td></tr>';
            return;
        }
        
        tableBody.innerHTML = strategies.map(strategy => `
            <tr>
                <td>${strategy.name || strategy.instance_name || '-'}</td>
                <td>${strategy.strategy_type || strategy.type || '-'}</td>
                <td>${strategy.symbol || '-'}</td>
                <td>
                    <span class="badge ${this.getStatusBadgeClass(strategy.status)}">
                        ${this.getStatusText(strategy.status)}
                    </span>
                </td>
                <td class="${strategy.total_return >= 0 ? 'text-success' : 'text-danger'}">
                    ${strategy.total_return ? (strategy.total_return * 100).toFixed(2) + '%' : '-'}
                </td>
                <td>${strategy.win_rate ? (strategy.win_rate * 100).toFixed(2) + '%' : '-'}</td>
                <td>${strategy.total_trades || '0'}</td>
                <td class="text-danger">${strategy.max_drawdown ? (strategy.max_drawdown * 100).toFixed(2) + '%' : '-'}</td>
                <td>
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-primary btn-sm" onclick="app.viewStrategyDetail('${strategy.name || strategy.instance_name}')" title="查看详情">
                            <i class="bi bi-eye"></i>
                        </button>
                        <button class="btn btn-outline-secondary btn-sm" onclick="app.editStrategy('${strategy.name || strategy.instance_name}')" title="编辑策略">
                            <i class="bi bi-pencil"></i>
                        </button>
                        ${strategy.status === 'STOPPED' ? 
                            `<button class="btn btn-outline-success btn-sm" onclick="app.startStrategy('${strategy.name || strategy.instance_name}')" title="启动策略">
                                <i class="bi bi-play"></i>
                            </button>` :
                            `<button class="btn btn-outline-warning btn-sm" onclick="app.stopStrategy('${strategy.name || strategy.instance_name}')" title="停止策略">
                                <i class="bi bi-pause"></i>
                            </button>`
                        }
                        <button class="btn btn-outline-info btn-sm" onclick="app.showBacktestModal('${strategy.name || strategy.instance_name}')" title="运行回测">
                            <i class="bi bi-graph-up"></i>
                        </button>
                        <button class="btn btn-outline-danger btn-sm" onclick="app.deleteStrategy('${strategy.name || strategy.instance_name}')" title="删除策略">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');
    }
    
    // 获取状态徽章样式
    getStatusBadgeClass(status) {
        switch (status) {
            case 'RUNNING': return 'bg-success';
            case 'STOPPED': return 'bg-secondary';
            case 'PAUSED': return 'bg-warning';
            case 'ERROR': return 'bg-danger';
            default: return 'bg-secondary';
        }
    }
    
    // 获取状态文本
    getStatusText(status) {
        switch (status) {
            case 'RUNNING': return '运行中';
            case 'STOPPED': return '已停止';
            case 'PAUSED': return '已暂停';
            case 'ERROR': return '错误';
            default: return '未知';
        }
    }
    
    // 加载回测历史
    async loadBacktestHistory() {
        try {
            const tableBody = document.getElementById('backtestTableBody');
            if (!tableBody) {
                console.warn('回测表格不存在，可能不在策略交易页面');
                return;
            }
            
            tableBody.innerHTML = '<tr><td colspan="11" class="text-center">加载中...</td></tr>';
            
            const response = await fetch(`${this.apiBaseUrl}/strategy/backtests`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && Array.isArray(data.data)) {
                    this.renderBacktestTable(data.data);
                } else {
                    tableBody.innerHTML = '<tr><td colspan="11" class="text-center text-muted">暂无回测数据</td></tr>';
                }
            } else {
                tableBody.innerHTML = '<tr><td colspan="11" class="text-center text-danger">无法加载回测数据</td></tr>';
            }
        } catch (error) {
            console.error('加载回测历史失败:', error);
            const tableBody = document.getElementById('backtestTableBody');
            if (tableBody) {
                tableBody.innerHTML = '<tr><td colspan="11" class="text-center text-danger">加载失败</td></tr>';
            }
        }
    }
    
    // 渲染回测表格
    renderBacktestTable(backtests) {
        const tableBody = document.getElementById('backtestTableBody');
        if (!tableBody) return;
        
        if (!backtests || backtests.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="11" class="text-center text-muted">暂无回测数据</td></tr>';
            return;
        }
        
        tableBody.innerHTML = backtests.map(backtest => `
            <tr>
                <td>${backtest.backtest_name || '-'}</td>
                <td>${backtest.strategy_name || '-'}</td>
                <td>${backtest.start_date ? this.formatTimestamp(backtest.start_date) : '-'}</td>
                <td>${backtest.end_date ? this.formatTimestamp(backtest.end_date) : '-'}</td>
                <td>${backtest.initial_capital ? Number(backtest.initial_capital).toLocaleString() : '-'}</td>
                <td>${backtest.final_capital ? Number(backtest.final_capital).toLocaleString() : '-'}</td>
                <td class="${backtest.total_return >= 0 ? 'text-success' : 'text-danger'}">
                    ${backtest.total_return ? (backtest.total_return * 100).toFixed(2) + '%' : '-'}
                </td>
                <td class="text-danger">${backtest.max_drawdown ? (backtest.max_drawdown * 100).toFixed(2) + '%' : '-'}</td>
                <td>${backtest.sharpe_ratio ? backtest.sharpe_ratio.toFixed(2) : '-'}</td>
                <td>
                    <span class="badge ${this.getBacktestStatusBadgeClass(backtest.status)}">
                        ${this.getBacktestStatusText(backtest.status)}
                    </span>
                </td>
                <td>
                    <button class="btn btn-outline-primary btn-sm" onclick="app.viewBacktestDetail('${backtest.id}')">
                        <i class="bi bi-eye"></i> 详情
                    </button>
                </td>
            </tr>
        `).join('');
    }
    
    // 获取回测状态徽章样式
    getBacktestStatusBadgeClass(status) {
        switch (status) {
            case 'COMPLETED': return 'bg-success';
            case 'RUNNING': return 'bg-primary';
            case 'FAILED': return 'bg-danger';
            default: return 'bg-secondary';
        }
    }
    
    // 获取回测状态文本
    getBacktestStatusText(status) {
        switch (status) {
            case 'COMPLETED': return '已完成';
            case 'RUNNING': return '运行中';
            case 'FAILED': return '失败';
            default: return '未知';
        }
    }
    
    // 查看策略详情
    async viewStrategyDetail(strategyName) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/strategy/instances/${strategyName}`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.data) {
                    this.showStrategyDetailModal(data.data);
                } else {
                    this.showToast('错误', '获取策略详情失败', 'danger');
                }
            } else {
                this.showToast('错误', '获取策略详情失败', 'danger');
            }
        } catch (error) {
            console.error('获取策略详情失败:', error);
            this.showToast('错误', '获取策略详情失败', 'danger');
        }
    }
    
    // 显示策略详情模态框
    showStrategyDetailModal(strategy) {
        // 填充基本信息
        const elements = {
            'strategyDetailName': strategy.name || '-',
            'strategyDetailType': strategy.strategy_type || '-',
            'strategyDetailSymbol': strategy.symbol || '-',
            'strategyDetailTimeframe': strategy.timeframe || '-',
            'strategyDetailReturn': strategy.total_return ? (strategy.total_return * 100).toFixed(2) + '%' : '-',
            'strategyDetailWinRate': strategy.win_rate ? (strategy.win_rate * 100).toFixed(2) + '%' : '-',
            'strategyDetailDrawdown': strategy.max_drawdown ? (strategy.max_drawdown * 100).toFixed(2) + '%' : '-',
            'strategyDetailTrades': strategy.total_trades || '0',
            'strategyDetailSharpe': strategy.sharpe_ratio ? strategy.sharpe_ratio.toFixed(2) : '-'
        };
        
        for (const [id, value] of Object.entries(elements)) {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value;
            }
        }
        
        // 设置状态
        const statusElement = document.getElementById('strategyDetailStatus');
        if (statusElement) {
            statusElement.innerHTML = `<span class="badge ${this.getStatusBadgeClass(strategy.status)}">${this.getStatusText(strategy.status)}</span>`;
        }
        
        // 显示模态框
        const modal = new bootstrap.Modal(document.getElementById('strategyDetailModal'));
        modal.show();
    }
    
    // 启动策略
    async startStrategy(strategyName) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/strategy/instances/${strategyName}/start`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.showToast('成功', '策略启动成功', 'success');
                    this.loadStrategyTradeList(); // 刷新列表
                } else {
                    this.showToast('错误', data.message || '策略启动失败', 'danger');
                }
            } else {
                this.showToast('错误', '策略启动请求失败', 'danger');
            }
        } catch (error) {
            console.error('启动策略失败:', error);
            this.showToast('错误', '策略启动失败', 'danger');
        }
    }
    
    // 停止策略
    async stopStrategy(strategyName) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/strategy/instances/${strategyName}/stop`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.showToast('成功', '策略停止成功', 'success');
                    this.loadStrategyTradeList(); // 刷新列表
                } else {
                    this.showToast('错误', data.message || '策略停止失败', 'danger');
                }
            } else {
                this.showToast('错误', '策略停止请求失败', 'danger');
            }
        } catch (error) {
            console.error('停止策略失败:', error);
            this.showToast('错误', '策略停止失败', 'danger');
        }
    }
    
    // 删除策略
    async deleteStrategy(strategyName) {
        console.log(`🗑️ 尝试删除策略: ${strategyName}`);
        
        if (!confirm(`确定要删除策略 "${strategyName}" 吗？此操作不可撤销。`)) {
            console.log('❌ 用户取消删除操作');
            return;
        }
        
        try {
            const url = `${this.apiBaseUrl}/strategy/instances/${strategyName}`;
            console.log(`📡 发送删除请求到: ${url}`);
            
            const response = await fetch(url, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            console.log(`📊 响应状态: ${response.status}`);
            
            if (response.ok) {
                const data = await response.json();
                console.log('📋 API响应数据:', data);
                
                if (data.success) {
                    console.log('✅ 策略删除成功');
                    this.showToast('成功', '策略删除成功', 'success');
                    this.loadStrategyTradeList(); // 刷新列表
                } else {
                    console.error('❌ API返回删除失败:', data.message);
                    this.showToast('错误', data.message || '策略删除失败', 'danger');
                }
            } else {
                const errorText = await response.text();
                console.error(`❌ HTTP请求失败: ${response.status}`, errorText);
                this.showToast('错误', `策略删除请求失败: ${response.status}`, 'danger');
            }
        } catch (error) {
            console.error('❌ 删除策略异常:', error);
            this.showToast('错误', `策略删除失败: ${error.message}`, 'danger');
        }
    }
    
    // 加载策略列表用于回测
    async loadStrategiesForBacktest() {
        try {
            const strategySelect = document.getElementById('backtestStrategy');
            if (!strategySelect) {
                console.warn('回测策略选择框不存在');
                return;
            }
            
            // 清空现有选项，保留默认选项
            strategySelect.innerHTML = '<option value="">请选择策略</option>';
            
            // 首先获取策略模板（所有可用的策略类型）
            const templatesResponse = await fetch(`${this.apiBaseUrl}/strategy/templates`);
            const templates = [];
            
            if (templatesResponse.ok) {
                const templatesData = await templatesResponse.json();
                if (templatesData.success && templatesData.data) {
                    // 如果返回的是对象，转换为数组
                    if (Array.isArray(templatesData.data)) {
                        templates.push(...templatesData.data);
                    } else {
                        // 将对象转换为数组
                        Object.values(templatesData.data).forEach(template => {
                            templates.push(template);
                        });
                    }
                    console.log(`✅ 获取到 ${templates.length} 个策略模板`);
                }
            }
            
            // 然后获取已创建的策略实例
            const instancesResponse = await fetch(`${this.apiBaseUrl}/strategy/instances`);
            const instances = [];
            
            if (instancesResponse.ok) {
                const instancesData = await instancesResponse.json();
                if (instancesData.success && Array.isArray(instancesData.data)) {
                    instances.push(...instancesData.data);
                    console.log(`✅ 获取到 ${instances.length} 个策略实例`);
                }
            }
            
            // 添加分组：策略模板
            if (templates.length > 0) {
                const templateGroup = document.createElement('optgroup');
                templateGroup.label = '策略模板（使用默认配置）';
                
                templates.forEach(template => {
                    const option = document.createElement('option');
                    option.value = `template:${template.id}`;
                    option.textContent = `${template.name} - ${template.description}`;
                    option.style.fontStyle = 'italic';
                    templateGroup.appendChild(option);
                });
                
                strategySelect.appendChild(templateGroup);
            }
            
            // 添加分组：已创建的策略实例
            if (instances.length > 0) {
                const instanceGroup = document.createElement('optgroup');
                instanceGroup.label = '已创建的策略实例';
                
                instances.forEach(strategy => {
                    const option = document.createElement('option');
                    option.value = `instance:${strategy.name || strategy.instance_name}`;
                    option.textContent = `${strategy.name || strategy.instance_name} (${strategy.strategy_type || strategy.type || '未知类型'})`;
                    instanceGroup.appendChild(option);
                });
                
                strategySelect.appendChild(instanceGroup);
            }
            
            // 如果没有任何策略，显示提示
            if (templates.length === 0 && instances.length === 0) {
                const option = document.createElement('option');
                option.value = '';
                option.textContent = '暂无可用策略，请先创建策略';
                option.disabled = true;
                strategySelect.appendChild(option);
            }
            
            console.log(`✅ 加载策略完成: ${templates.length} 个模板 + ${instances.length} 个实例`);
            
        } catch (error) {
            console.error('加载策略列表失败:', error);
            // 添加错误提示选项
            const strategySelect = document.getElementById('backtestStrategy');
            if (strategySelect) {
                strategySelect.innerHTML = '<option value="">请选择策略</option>';
                const option = document.createElement('option');
                option.value = '';
                option.textContent = '加载失败，请重试';
                option.disabled = true;
                strategySelect.appendChild(option);
            }
        }
    }
    
    // 策略选择变化处理（回测用）
    async onBacktestStrategyChange(strategyValue) {
        const paramsArea = document.getElementById('backtestStrategyParams');
        
        if (!strategyValue || !strategyValue.startsWith('template:')) {
            // 如果不是策略模板，隐藏参数配置
            if (paramsArea) paramsArea.style.display = 'none';
            return;
        }
        
        // 提取策略类型
        const strategyType = strategyValue.replace('template:', '');
        
        console.log(`🔄 回测策略变化: ${strategyType}`);
        
        // 显示参数配置区域
        if (paramsArea) paramsArea.style.display = 'block';
        
        // 使用动态参数生成
        await this.showBacktestStrategyParams(strategyType);
    }
    
    // 显示回测策略参数
    async showBacktestStrategyParams(strategyType) {
        try {
            console.log(`📡 获取策略 ${strategyType} 的参数模板...`);
            
            const response = await fetch(`${this.apiBaseUrl}/strategy/templates/${strategyType}`);
            if (!response.ok) {
                throw new Error(`获取策略模板失败: ${response.status}`);
            }
            
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message);
            }
            
            const template = data.data;
            console.log(`✅ 获取到策略模板:`, template);
            
            // 生成动态参数表单
            const paramsHtml = this.generateBacktestStrategyParamsForm(strategyType, template.default_config, template.validation_rules, template.parameters);
            
            // 更新HTML
            const paramsArea = document.getElementById('backtestStrategyParams');
            if (paramsArea) {
                paramsArea.innerHTML = paramsHtml;
                console.log(`📝 回测参数表单已生成`);
            }
            
        } catch (error) {
            console.error('生成回测策略参数失败:', error);
            // 降级到硬编码参数
            this.generateLegacyBacktestParams(strategyType);
        }
    }
    
    // 生成回测策略参数表单
    generateBacktestStrategyParamsForm(strategyType, config, validation, parameters) {
        console.log(`🎨 生成回测参数表单:`, strategyType, config);
        
        let formHtml = '<div class="row">';
        let hasParams = false;
        
        // 根据参数信息生成表单
        if (parameters) {
            Object.entries(parameters).forEach(([paramName, paramInfo]) => {
                // 跳过symbol和timeframe（已在主表单中）
                if (paramName === 'symbol' || paramName === 'timeframe') {
                    return;
                }
                
                formHtml += this.generateBacktestParamInput(paramName, paramInfo);
                hasParams = true;
            });
        }
        
        if (!hasParams) {
            formHtml += '<div class="col-12"><p class="text-muted">该策略使用默认参数配置</p></div>';
        }
        
        formHtml += '</div>';
        return formHtml;
    }
    
    // 生成回测参数输入框
    generateBacktestParamInput(paramName, paramInfo) {
        const label = paramInfo.label || paramName;
        const defaultValue = paramInfo.default || '';
        const inputType = paramInfo.input_type || 'text';
        const description = paramInfo.description || '';
        
        let inputHtml = '';
        
        if (inputType === 'checkbox') {
            inputHtml = `
                <div class="col-md-4">
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" name="${paramName}" id="backtest_${paramName}" ${defaultValue ? 'checked' : ''}>
                        <label class="form-check-label" for="backtest_${paramName}">
                            ${label}
                        </label>
                    </div>
                    ${description ? `<div class="form-text">${description}</div>` : ''}
                </div>
            `;
        } else {
            const step = paramInfo.step || (inputType === 'number' ? '0.001' : '');
            const min = paramInfo.min !== undefined ? `min="${paramInfo.min}"` : '';
            const max = paramInfo.max !== undefined ? `max="${paramInfo.max}"` : '';
            const stepAttr = step ? `step="${step}"` : '';
            
            inputHtml = `
                <div class="col-md-4">
                    <label for="backtest_${paramName}" class="form-label">${label}</label>
                    <input type="${inputType}" class="form-control" name="${paramName}" id="backtest_${paramName}" 
                           value="${defaultValue}" ${min} ${max} ${stepAttr} required>
                    ${description ? `<div class="form-text">${description}</div>` : ''}
                </div>
            `;
        }
        
        return inputHtml;
    }
    
    // 降级到硬编码参数（备用方案）
    generateLegacyBacktestParams(strategyType) {
        console.warn(`⚠️ 降级到硬编码参数: ${strategyType}`);
        
        // 生成策略特定参数表单
        let paramsHtml = '';
        
        switch (strategyType) {
            case 'MA_Cross_Strategy':
                paramsHtml = `
                    <div class="row">
                        <div class="col-md-6">
                            <label for="backtest_short_period" class="form-label">短期均线周期</label>
                            <input type="number" class="form-control" id="backtest_short_period" value="10" min="5" max="50" required>
                            <div class="form-text">短期移动平均线的计算周期</div>
                        </div>
                        <div class="col-md-6">
                            <label for="backtest_long_period" class="form-label">长期均线周期</label>
                            <input type="number" class="form-control" id="backtest_long_period" value="20" min="10" max="100" required>
                            <div class="form-text">长期移动平均线的计算周期</div>
                        </div>
                    </div>
                `;
                break;
                
            case 'RSI_Strategy':
                paramsHtml = `
                    <div class="row">
                        <div class="col-md-4">
                            <label for="backtest_rsi_period" class="form-label">RSI周期</label>
                            <input type="number" class="form-control" id="backtest_rsi_period" value="14" min="5" max="30" required>
                        </div>
                        <div class="col-md-4">
                            <label for="backtest_oversold" class="form-label">超卖线</label>
                            <input type="number" class="form-control" id="backtest_oversold" value="30" min="10" max="40" required>
                        </div>
                        <div class="col-md-4">
                            <label for="backtest_overbought" class="form-label">超买线</label>
                            <input type="number" class="form-control" id="backtest_overbought" value="70" min="60" max="90" required>
                        </div>
                    </div>
                `;
                break;
                
            case 'MACD_Strategy':
                paramsHtml = `
                    <div class="row">
                        <div class="col-md-4">
                            <label for="backtest_fast_period" class="form-label">快速EMA周期</label>
                            <input type="number" class="form-control" id="backtest_fast_period" value="12" min="5" max="20" required>
                        </div>
                        <div class="col-md-4">
                            <label for="backtest_slow_period" class="form-label">慢速EMA周期</label>
                            <input type="number" class="form-control" id="backtest_slow_period" value="26" min="20" max="50" required>
                        </div>
                        <div class="col-md-4">
                            <label for="backtest_signal_period" class="form-label">信号线周期</label>
                            <input type="number" class="form-control" id="backtest_signal_period" value="9" min="5" max="15" required>
                        </div>
                    </div>
                `;
                break;
                
            case 'Bollinger_Strategy':
                paramsHtml = `
                    <div class="row">
                        <div class="col-md-6">
                            <label for="backtest_bb_period" class="form-label">布林带周期</label>
                            <input type="number" class="form-control" id="backtest_bb_period" value="20" min="10" max="50" required>
                        </div>
                        <div class="col-md-6">
                            <label for="backtest_bb_std" class="form-label">标准差倍数</label>
                            <input type="number" class="form-control" id="backtest_bb_std" value="2" min="1" max="3" step="0.1" required>
                        </div>
                    </div>
                `;
                break;
                
            case 'Grid_Strategy':
                paramsHtml = `
                    <div class="row">
                        <div class="col-md-4">
                            <label for="backtest_grid_size" class="form-label">网格大小 (%)</label>
                            <input type="number" class="form-control" id="backtest_grid_size" value="1" min="0.1" max="5" step="0.1" required>
                        </div>
                        <div class="col-md-4">
                            <label for="backtest_max_grids" class="form-label">最大网格数</label>
                            <input type="number" class="form-control" id="backtest_max_grids" value="10" min="3" max="20" required>
                        </div>
                        <div class="col-md-4">
                            <label for="backtest_base_amount" class="form-label">基础下单金额</label>
                            <input type="number" class="form-control" id="backtest_base_amount" value="100" min="10" max="1000" required>
                        </div>
                    </div>
                `;
                break;
                
            default:
                paramsHtml = '<p class="text-muted">该策略使用默认参数配置</p>';
        }
        
        if (paramsContainer) {
            paramsContainer.innerHTML = paramsHtml;
        }
    }
    
    // 显示回测模态框
    async showBacktestModal(strategyName) {
        // 设置默认日期
        const endDate = new Date();
        const startDate = new Date();
        startDate.setMonth(startDate.getMonth() - 3); // 默认3个月前
        
        const startDateElement = document.getElementById('backtestStartDate');
        const endDateElement = document.getElementById('backtestEndDate');
        const strategyElement = document.getElementById('backtestStrategy');
        const nameElement = document.getElementById('backtestName');
        
        if (startDateElement) startDateElement.value = startDate.toISOString().split('T')[0];
        if (endDateElement) endDateElement.value = endDate.toISOString().split('T')[0];
        
        // 加载策略列表到下拉框
        await this.loadStrategiesForBacktest();
        
        // 绑定策略选择变化事件
        if (strategyElement) {
            strategyElement.addEventListener('change', async (e) => {
                await this.onBacktestStrategyChange(e.target.value);
            });
        }
        
        if (strategyName) {
            if (strategyElement) {
                strategyElement.value = strategyName;
                // 触发参数配置显示
                await this.onBacktestStrategyChange(strategyName);
            }
            if (nameElement) nameElement.value = `${strategyName}_backtest_${Date.now()}`;
        }
        
        const modal = new bootstrap.Modal(document.getElementById('backtestModal'));
        modal.show();
    }
    
    // 查看回测详情
    async viewBacktestDetail(backtestId) {
        try {
            console.log('查看回测详情:', backtestId);
            
            // 获取回测详情数据
            const response = await fetch(`${this.apiBaseUrl}/strategy/backtests/${backtestId}`);
            
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.data) {
                    this.showBacktestDetailModal(data.data);
                } else {
                    this.showToast('错误', data.message || '获取回测详情失败', 'danger');
                }
            } else {
                this.showToast('错误', '获取回测详情请求失败', 'danger');
            }
        } catch (error) {
            console.error('查看回测详情失败:', error);
            this.showToast('错误', '查看回测详情失败', 'danger');
        }
    }

    // 显示回测详情模态框
    showBacktestDetailModal(backtestData) {
        console.log('显示回测详情:', backtestData);

        // 填充基本信息
        document.getElementById('detailBacktestName').textContent = backtestData.backtest_name || '-';
        document.getElementById('detailStrategyName').textContent = backtestData.strategy_name || '-';
        document.getElementById('detailSymbol').textContent = backtestData.symbol || '-';
        document.getElementById('detailDateRange').textContent = 
            `${this.formatTimestamp(backtestData.start_date)} 至 ${this.formatTimestamp(backtestData.end_date)}`;

        // 填充性能指标
        document.getElementById('detailInitialCapital').textContent = 
            `¥${this.formatNumber(backtestData.initial_capital)}`;
        document.getElementById('detailFinalCapital').textContent = 
            `¥${this.formatNumber(backtestData.final_capital)}`;
        const totalReturnElement = document.getElementById('detailTotalReturn');
        const totalReturnValue = backtestData.total_return * 100;
        totalReturnElement.textContent = `${totalReturnValue.toFixed(2)}%`;
        
        // 添加颜色样式
        totalReturnElement.classList.remove('positive', 'negative');
        if (totalReturnValue > 0) {
            totalReturnElement.classList.add('positive');
        } else if (totalReturnValue < 0) {
            totalReturnElement.classList.add('negative');
        }
        document.getElementById('detailMaxDrawdown').textContent = 
            `${(backtestData.max_drawdown * 100).toFixed(2)}%`;
        document.getElementById('detailSharpeRatio').textContent = 
            backtestData.sharpe_ratio?.toFixed(3) || '-';
        document.getElementById('detailWinRate').textContent = 
            `${(backtestData.win_rate * 100).toFixed(1)}%`;

        // 显示模态框
        const modal = new bootstrap.Modal(document.getElementById('backtestDetailModal'));
        modal.show();

        // 等待模态框显示后再初始化图表
        modal._element.addEventListener('shown.bs.modal', () => {
            this.initBacktestCharts(backtestData);
        }, { once: true });
    }

    // 初始化回测图表
    initBacktestCharts(backtestData) {
        console.log('初始化回测图表:', backtestData);

        // 解析结果数据
        let results = {};
        try {
            if (typeof backtestData.results_json === 'string') {
                results = JSON.parse(backtestData.results_json);
            } else {
                results = backtestData.results_json || {};
            }
        } catch (e) {
            console.warn('解析回测结果数据失败:', e);
            results = {};
        }

        // 初始化收益曲线图表
        this.initEquityChart(results);
        
        // 初始化回撤分析图表
        this.initDrawdownChart(results);
        
        // 填充交易记录表格
        this.populateTradeHistory(results.trade_history || []);
    }

    // 初始化价格图表（包含买入卖出点）
    initPriceChart(results) {
        const chartContainer = document.getElementById('backtestChart');
        if (!chartContainer) return;

        // 清除现有图表
        chartContainer.innerHTML = '';

        try {
            // 创建图表
            const chart = LightweightCharts.createChart(chartContainer, {
                width: chartContainer.offsetWidth,
                height: 400,
                layout: {
                    backgroundColor: '#ffffff',
                    textColor: '#333',
                },
                grid: {
                    vertLines: { color: '#f0f0f0' },
                    horzLines: { color: '#f0f0f0' },
                },
                timeScale: {
                    borderColor: '#ccc',
                },
                rightPriceScale: {
                    borderColor: '#ccc',
                },
            });

            // 模拟价格数据（实际应该从后端获取）
            const priceData = this.generateSamplePriceData(results);
            
            // 添加K线图
            const candlestickSeries = chart.addCandlestickSeries({
                upColor: '#26a69a',
                downColor: '#ef5350',
                borderVisible: false,
                wickUpColor: '#26a69a',
                wickDownColor: '#ef5350',
            });
            
            candlestickSeries.setData(priceData);

            // 添加买入卖出标记
            this.addTradeMarkers(chart, results.trade_history || []);

            // 响应式调整
            new ResizeObserver(() => {
                chart.applyOptions({ width: chartContainer.offsetWidth });
            }).observe(chartContainer);

        } catch (error) {
            console.error('初始化价格图表失败:', error);
            chartContainer.innerHTML = '<div class="text-center p-4 text-muted">价格图表加载失败</div>';
        }
    }

    // 初始化收益曲线图表
    initEquityChart(results) {
        console.log('🎯 初始化收益曲线图表', results);
        const chartContainer = document.getElementById('equityChart');
        if (!chartContainer) {
            console.error('❌ 找不到equityChart容器');
            return;
        }

        // 清除现有图表
        chartContainer.innerHTML = '';

        try {
            // 创建图表
            const chart = LightweightCharts.createChart(chartContainer, {
                width: chartContainer.offsetWidth,
                height: 400,
                layout: {
                    backgroundColor: '#ffffff',
                    textColor: '#333',
                },
                grid: {
                    vertLines: { color: '#f0f0f0' },
                    horzLines: { color: '#f0f0f0' },
                },
                timeScale: {
                    borderColor: '#ccc',
                    timeVisible: true,
                    secondsVisible: false,
                },
                rightPriceScale: {
                    borderColor: '#ccc',
                    visible: true,
                },
            });

            // 生成收益曲线数据
            const equityData = this.generateEquityCurve(results);
            const returnData = this.generateReturnCurve(equityData);
            
            // 添加收益率曲线（主图）
            const returnSeries = chart.addLineSeries({
                color: '#26a69a',
                lineWidth: 3,
                title: '累计收益率',
            });
            
            returnSeries.setData(returnData);

            // 添加基准线（0%收益率）
            const baselineSeries = chart.addLineSeries({
                color: '#666666',
                lineWidth: 1,
                lineStyle: 2, // 虚线
                title: '基准线',
            });
            
            const baselineData = returnData.map(point => ({
                time: point.time,
                value: 0
            }));
            baselineSeries.setData(baselineData);

            // 标记交易点
            this.addTradeMarkersToChart(chart, results.trade_history || []);

            // 响应式调整
            new ResizeObserver(() => {
                chart.applyOptions({ width: chartContainer.offsetWidth });
            }).observe(chartContainer);

            // 添加图表说明
            this.addChartLegend(chartContainer, {
                '绿色线': '策略累计收益率',
                '灰色虚线': '0%基准线',
                '🔺': '买入信号',
                '🔻': '卖出信号'
            });

        } catch (error) {
            console.error('初始化收益曲线图表失败:', error);
            chartContainer.innerHTML = '<div class="text-center p-4 text-muted">收益曲线图表加载失败</div>';
        }
    }

    // 初始化回撤分析图表
    initDrawdownChart(results) {
        const chartContainer = document.getElementById('drawdownChart');
        if (!chartContainer) return;

        // 清除现有图表
        chartContainer.innerHTML = '';

        try {
            // 创建图表
            const chart = LightweightCharts.createChart(chartContainer, {
                width: chartContainer.offsetWidth,
                height: 300,
                layout: {
                    backgroundColor: '#ffffff',
                    textColor: '#333',
                },
                grid: {
                    vertLines: { color: '#f0f0f0' },
                    horzLines: { color: '#f0f0f0' },
                },
                timeScale: {
                    borderColor: '#ccc',
                },
                rightPriceScale: {
                    borderColor: '#ccc',
                },
            });

            // 生成回撤数据
            const drawdownData = this.generateDrawdownCurve(results);
            
            // 添加回撤曲线
            const drawdownSeries = chart.addAreaSeries({
                topColor: 'rgba(239, 83, 80, 0.4)',
                bottomColor: 'rgba(239, 83, 80, 0.1)', 
                lineColor: '#ef5350',
                lineWidth: 2,
                title: '回撤百分比',
            });
            
            drawdownSeries.setData(drawdownData);

            // 响应式调整
            new ResizeObserver(() => {
                chart.applyOptions({ width: chartContainer.offsetWidth });
            }).observe(chartContainer);

            // 添加回撤统计信息
            this.addDrawdownStats(chartContainer, results);

        } catch (error) {
            console.error('初始化回撤分析图表失败:', error);
            chartContainer.innerHTML = '<div class="text-center p-4 text-muted">回撤分析图表加载失败</div>';
        }
    }

    // 生成示例价格数据
    generateSamplePriceData(results) {
        const data = [];
        const startPrice = 50000;
        let currentPrice = startPrice;
        
        // 生成30天的数据
        for (let i = 0; i < 30; i++) {
            const date = new Date();
            date.setDate(date.getDate() - 30 + i);
            
            // 模拟价格波动
            const change = (Math.random() - 0.5) * 0.1;
            currentPrice *= (1 + change);
            
            const high = currentPrice * (1 + Math.random() * 0.02);
            const low = currentPrice * (1 - Math.random() * 0.02);
            const open = currentPrice * (1 + (Math.random() - 0.5) * 0.01);
            
            data.push({
                time: Math.floor(date.getTime() / 1000),
                open: open,
                high: Math.max(open, high),
                low: Math.min(open, low),
                close: currentPrice,
            });
        }
        
        return data;
    }

    // 添加交易标记
    addTradeMarkers(chart, tradeHistory) {
        const markers = [];
        
        tradeHistory.forEach(trade => {
            if (trade.type === 'BUY' || trade.type === 'SELL') {
                const timestamp = this.parseTradeTimestamp(trade.timestamp);
                
                markers.push({
                    time: timestamp,
                    position: trade.type === 'BUY' ? 'belowBar' : 'aboveBar',
                    color: trade.type === 'BUY' ? '#26a69a' : '#ef5350',
                    shape: trade.type === 'BUY' ? 'arrowUp' : 'arrowDown',
                    text: trade.type === 'BUY' ? 'B' : 'S',
                    size: 1,
                });
            }
        });
        
        if (markers.length > 0) {
            chart.setMarkers(markers);
        }
    }

    // 解析交易时间戳
    parseTradeTimestamp(timestamp) {
        try {
            if (typeof timestamp === 'string') {
                return Math.floor(new Date(timestamp).getTime() / 1000);
            } else if (typeof timestamp === 'number') {
                return timestamp > 1000000000000 ? Math.floor(timestamp / 1000) : timestamp;
            }
        } catch (e) {
            console.warn('解析时间戳失败:', timestamp);
        }
        return Math.floor(Date.now() / 1000);
    }

    // 生成资金曲线数据
    generateEquityCurve(results) {
        const equityData = [];
        
        if (results.equity_curve && Array.isArray(results.equity_curve)) {
            console.log('📈 处理equity_curve数据:', results.equity_curve.length, '个点');
            results.equity_curve.forEach(point => {
                equityData.push({
                    time: this.parseTradeTimestamp(point.timestamp || point.time),
                    value: point.total_value || point.equity || point.value || 0
                });
            });
            console.log('📊 生成equity数据:', equityData.length, '个点');
        } else {
            // 如果没有资金曲线数据，从交易历史生成
            let equity = results.initial_capital || 100000;
            equityData.push({
                time: Math.floor(Date.now() / 1000) - 30 * 24 * 3600,
                value: equity
            });
            
            const trades = results.trade_history || [];
            trades.forEach(trade => {
                if (trade.type === 'CLOSE') {
                    equity += trade.pnl || 0;
                    equityData.push({
                        time: this.parseTradeTimestamp(trade.timestamp),
                        value: equity
                    });
                }
            });
        }
        
        return equityData;
    }

    // 生成收益率曲线数据
    generateReturnCurve(equityData) {
        if (!equityData || equityData.length === 0) return [];
        
        const initialValue = equityData[0].value;
        return equityData.map(point => ({
            time: point.time,
            value: ((point.value - initialValue) / initialValue) * 100 // 转换为百分比
        }));
    }

    // 生成回撤曲线数据
    generateDrawdownCurve(results) {
        const equityData = this.generateEquityCurve(results);
        if (equityData.length === 0) return [];
        
        const drawdownData = [];
        let peak = equityData[0].value;
        
        equityData.forEach(point => {
            // 更新最高点
            if (point.value > peak) {
                peak = point.value;
            }
            
            // 计算回撤百分比
            const drawdown = ((point.value - peak) / peak) * 100;
            drawdownData.push({
                time: point.time,
                value: drawdown // 负数表示回撤
            });
        });
        
        return drawdownData;
    }

    // 为图表添加交易标记
    addTradeMarkersToChart(chart, tradeHistory) {
        const markers = [];
        
        tradeHistory.forEach(trade => {
            if (trade.type === 'BUY' || trade.type === 'SELL') {
                const timestamp = this.parseTradeTimestamp(trade.timestamp);
                
                markers.push({
                    time: timestamp,
                    position: trade.type === 'BUY' ? 'belowBar' : 'aboveBar',
                    color: trade.type === 'BUY' ? '#26a69a' : '#ef5350',
                    shape: trade.type === 'BUY' ? 'arrowUp' : 'arrowDown',
                    text: trade.type === 'BUY' ? 'B' : 'S',
                    size: 1,
                });
            }
        });
        
        if (markers.length > 0) {
            chart.setMarkers(markers);
        }
    }

    // 添加图表图例
    addChartLegend(container, legendItems) {
        const legend = document.createElement('div');
        legend.className = 'chart-legend mt-2';
        legend.style.cssText = 'font-size: 12px; color: #666; text-align: center;';
        
        const legendText = Object.entries(legendItems)
            .map(([key, value]) => `<span style="margin: 0 10px;"><strong>${key}:</strong> ${value}</span>`)
            .join('');
        
        legend.innerHTML = legendText;
        container.appendChild(legend);
    }

    // 添加回撤统计信息
    addDrawdownStats(container, results) {
        const maxDrawdown = results.performance_stats?.max_drawdown || 0;
        const avgDrawdown = this.calculateAverageDrawdown(results);
        
        const statsDiv = document.createElement('div');
        statsDiv.className = 'drawdown-stats mt-2 p-2';
        statsDiv.style.cssText = 'background: #f8f9fa; border-radius: 4px; font-size: 12px;';
        
        statsDiv.innerHTML = `
            <div class="row text-center">
                <div class="col-md-4">
                    <strong>最大回撤:</strong> 
                    <span class="text-danger">${(maxDrawdown * 100).toFixed(2)}%</span>
                </div>
                <div class="col-md-4">
                    <strong>平均回撤:</strong> 
                    <span class="text-warning">${(avgDrawdown * 100).toFixed(2)}%</span>
                </div>
                <div class="col-md-4">
                    <strong>回撤风险:</strong> 
                    <span class="${this.getDrawdownRiskClass(maxDrawdown)}">${this.getDrawdownRiskText(maxDrawdown)}</span>
                </div>
            </div>
        `;
        
        container.appendChild(statsDiv);
    }

    // 计算平均回撤
    calculateAverageDrawdown(results) {
        const drawdownData = this.generateDrawdownCurve(results);
        if (drawdownData.length === 0) return 0;
        
        const negativeDrawdowns = drawdownData.filter(point => point.value < 0);
        if (negativeDrawdowns.length === 0) return 0;
        
        const totalDrawdown = negativeDrawdowns.reduce((sum, point) => sum + Math.abs(point.value), 0);
        return (totalDrawdown / negativeDrawdowns.length) / 100; // 转换为小数
    }

    // 获取回撤风险等级样式
    getDrawdownRiskClass(maxDrawdown) {
        const dd = Math.abs(maxDrawdown);
        if (dd < 0.05) return 'text-success';      // 小于5%：低风险
        if (dd < 0.15) return 'text-warning';      // 5%-15%：中等风险  
        return 'text-danger';                      // 大于15%：高风险
    }

    // 获取回撤风险等级文本
    getDrawdownRiskText(maxDrawdown) {
        const dd = Math.abs(maxDrawdown);
        if (dd < 0.05) return '低风险';
        if (dd < 0.15) return '中等风险';
        return '高风险';
    }

    // 填充交易记录表格
    populateTradeHistory(tradeHistory) {
        const tbody = document.getElementById('backtestTradesTableBody');
        if (!tbody) return;

        tbody.innerHTML = '';
        
        let cumulativePnl = 0;
        
        tradeHistory.forEach(trade => {
            if (trade.pnl) {
                cumulativePnl += trade.pnl;
            }
            
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${this.formatTimestamp(trade.timestamp)}</td>
                <td><span class="badge bg-${trade.type === 'BUY' ? 'primary' : 'secondary'}">${trade.type}</span></td>
                <td><span class="badge bg-${trade.side === 'LONG' ? 'success' : 'danger'}">${trade.side}</span></td>
                <td>$${this.formatNumber(trade.price)}</td>
                <td>${this.formatNumber(trade.quantity)}</td>
                <td>$${this.formatNumber(trade.price * trade.quantity)}</td>
                <td class="${trade.pnl > 0 ? 'text-success' : trade.pnl < 0 ? 'text-danger' : ''}">
                    ${trade.pnl ? `$${this.formatNumber(trade.pnl)}` : '-'}
                </td>
                <td class="${cumulativePnl > 0 ? 'text-success' : cumulativePnl < 0 ? 'text-danger' : ''}">
                    $${this.formatNumber(cumulativePnl)}
                </td>
            `;
            tbody.appendChild(row);
        });
        
        if (tradeHistory.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">暂无交易记录</td></tr>';
        }
    }

    // 格式化时间戳
    formatTimestamp(timestamp) {
        try {
            const date = new Date(timestamp);
            return date.toLocaleString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        } catch (e) {
            return timestamp || '-';
        }
    }
    
    // 初始化数据库
    async initDatabase() {
        try {
            this.showToast('信息', '正在初始化数据库...', 'info');
            
            const response = await fetch(`${this.apiBaseUrl}/strategy/init-database`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.showToast('成功', '数据库初始化成功', 'success');
                } else {
                    this.showToast('错误', data.message || '数据库初始化失败', 'danger');
                }
            } else {
                this.showToast('错误', '数据库初始化请求失败', 'danger');
            }
        } catch (error) {
            console.error('初始化数据库失败:', error);
            this.showToast('错误', '数据库初始化失败', 'danger');
        }
    }
    
    // 创建策略交易
    async createStrategyTrade() {
        try {
            const form = document.getElementById('createStrategyTradeForm');
            if (!form) {
                this.showToast('错误', '表单不存在', 'danger');
                return;
            }
            
            const formData = new FormData(form);
            const strategyType = formData.get('strategyType') || document.getElementById('strategyType')?.value;
            const strategyName = formData.get('strategyName') || document.getElementById('strategyName')?.value;
            const tradingSymbol = formData.get('tradingSymbol') || document.getElementById('tradingSymbol')?.value;
            const timeframe = formData.get('timeframe') || document.getElementById('timeframe')?.value;
            const riskPerTrade = formData.get('riskPerTrade') || document.getElementById('riskPerTrade')?.value;
            const maxPositions = formData.get('maxPositions') || document.getElementById('maxPositions')?.value;
            const stopLossPct = formData.get('stopLossPct') || document.getElementById('stopLossPct')?.value;
            const takeProfitPct = formData.get('takeProfitPct') || document.getElementById('takeProfitPct')?.value;
            
            if (!strategyType || !strategyName || !tradingSymbol || !timeframe) {
                this.showToast('错误', '请填写所有必需字段', 'danger');
                return;
            }
            
            const config = {
                symbol: tradingSymbol,
                timeframe: timeframe,
                risk_per_trade: parseFloat(riskPerTrade),
                max_positions: parseInt(maxPositions),
                stop_loss_pct: parseFloat(stopLossPct),
                take_profit_pct: parseFloat(takeProfitPct)
            };
            
            // 动态收集策略特定参数
            this.collectDynamicStrategyParams(config);
            
            // 获取选中的客户和信号源
            const selectedSignalSources = Array.from(document.getElementById('signalSources')?.selectedOptions || [])
                .map(option => option.value);
            const selectedCustomers = Array.from(document.getElementById('customers')?.selectedOptions || [])
                .map(option => option.value);

            const requestData = {
                strategy_type: strategyType,
                name: strategyName,
                config: config,
                signal_sources: selectedSignalSources,
                customers: selectedCustomers
            };
            
            this.showToast('信息', '正在创建策略...', 'info');
            
            const response = await fetch(`${this.apiBaseUrl}/strategy/create`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.showToast('成功', '策略创建成功', 'success');
                    
                    // 关闭模态框
                    const modal = bootstrap.Modal.getInstance(document.getElementById('createStrategyTradeModal'));
                    if (modal) modal.hide();
                    
                    // 重置表单
                    form.reset();
                    
                    // 刷新策略列表
                    this.loadStrategyTradeList();
                } else {
                    this.showToast('错误', data.message || '策略创建失败', 'danger');
                }
            } else {
                this.showToast('错误', '策略创建请求失败', 'danger');
            }
        } catch (error) {
            console.error('创建策略失败:', error);
            this.showToast('错误', '策略创建失败', 'danger');
        }
    }
    
    // 编辑策略
    async editStrategy(strategyName) {
        try {
            console.log('编辑策略:', strategyName);
            
            // 获取策略详情
            const response = await fetch(`${this.apiBaseUrl}/strategy/instances/${strategyName}`);
            
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.data) {
                    this.showEditStrategyModal(data.data);
                } else {
                    this.showToast('错误', data.message || '获取策略详情失败', 'danger');
                }
            } else {
                this.showToast('错误', '获取策略详情请求失败', 'danger');
            }
        } catch (error) {
            console.error('编辑策略失败:', error);
            this.showToast('错误', '编辑策略失败', 'danger');
        }
    }

    // 显示策略编辑模态框
    async showEditStrategyModal(strategyData) {
        console.log('显示策略编辑模态框:', strategyData);

        // 填充基本信息
        document.getElementById('editStrategyId').value = strategyData.name || strategyData.instance_name;
        document.getElementById('editStrategyName').value = strategyData.name || strategyData.instance_name;
        document.getElementById('editStrategyType').value = strategyData.strategy_type || strategyData.type;
        document.getElementById('editTradingSymbol').value = strategyData.symbol || 'BTC-USDT';
        document.getElementById('editTimeframe').value = strategyData.timeframe || '1h';

        // 填充风险参数
        if (strategyData.config) {
            document.getElementById('editRiskPerTrade').value = strategyData.config.risk_per_trade || 0.02;
            document.getElementById('editMaxPositions').value = strategyData.config.max_positions || 3;
            document.getElementById('editStopLossPct').value = strategyData.config.stop_loss_pct || 0.02;
            document.getElementById('editTakeProfitPct').value = strategyData.config.take_profit_pct || 0.06;
        }

        // 加载客户和信号源列表
        await this.loadAccountsForStrategy('edit');

        // 显示模态框
        const modal = new bootstrap.Modal(document.getElementById('editStrategyModal'));
        modal.show();

        // 动态显示策略特定参数
        this.showEditStrategyParams(strategyData.strategy_type || strategyData.type, strategyData.config);
    }

    // 显示编辑策略的特定参数
    showEditStrategyParams(strategyType, config) {
        const paramsContainer = document.getElementById('editStrategySpecificParams');
        if (!paramsContainer) return;

        let paramsHtml = '';

        switch (strategyType) {
            case 'MA_Cross_Strategy':
                paramsHtml = `
                    <div class="row">
                        <div class="col-md-6">
                            <label for="edit_short_period" class="form-label">短期均线周期</label>
                            <input type="number" class="form-control" id="edit_short_period" 
                                   value="${config?.short_period || 10}" min="5" max="50" required>
                        </div>
                        <div class="col-md-6">
                            <label for="edit_long_period" class="form-label">长期均线周期</label>
                            <input type="number" class="form-control" id="edit_long_period" 
                                   value="${config?.long_period || 20}" min="10" max="100" required>
                        </div>
                    </div>
                `;
                break;
            case 'RSI_Strategy':
                paramsHtml = `
                    <div class="row">
                        <div class="col-md-4">
                            <label for="edit_rsi_period" class="form-label">RSI周期</label>
                            <input type="number" class="form-control" id="edit_rsi_period" 
                                   value="${config?.rsi_period || 14}" min="5" max="50" required>
                        </div>
                        <div class="col-md-4">
                            <label for="edit_oversold" class="form-label">超卖线</label>
                            <input type="number" class="form-control" id="edit_oversold" 
                                   value="${config?.rsi_oversold || config?.oversold || 30}" min="10" max="40" required>
                        </div>
                        <div class="col-md-4">
                            <label for="edit_overbought" class="form-label">超买线</label>
                            <input type="number" class="form-control" id="edit_overbought" 
                                   value="${config?.rsi_overbought || config?.overbought || 70}" min="60" max="90" required>
                        </div>
                    </div>
                `;
                break;
            case 'MACD_Strategy':
                paramsHtml = `
                    <div class="row">
                        <div class="col-md-4">
                            <label for="edit_fast_period" class="form-label">快速EMA周期</label>
                            <input type="number" class="form-control" id="edit_fast_period" 
                                   value="${config?.fast_period || 12}" min="5" max="30" required>
                        </div>
                        <div class="col-md-4">
                            <label for="edit_slow_period" class="form-label">慢速EMA周期</label>
                            <input type="number" class="form-control" id="edit_slow_period" 
                                   value="${config?.slow_period || 26}" min="15" max="60" required>
                        </div>
                        <div class="col-md-4">
                            <label for="edit_signal_period" class="form-label">信号线周期</label>
                            <input type="number" class="form-control" id="edit_signal_period" 
                                   value="${config?.signal_period || 9}" min="5" max="20" required>
                        </div>
                    </div>
                `;
                break;
            default:
                paramsHtml = '<p class="text-muted">该策略类型使用默认参数</p>';
        }

        paramsContainer.innerHTML = paramsHtml;
    }

    // 加载账号列表用于策略关联
    async loadAccountsForStrategy(mode = 'create') {
        try {
            let signalSourcesId, customersId;
            if (mode === 'edit') {
                signalSourcesId = 'editSignalSources';
                customersId = 'editCustomers';
            } else {
                signalSourcesId = 'signalSources';
                customersId = 'customers';
            }
            
            const signalSourcesSelect = document.getElementById(signalSourcesId);
            const customersSelect = document.getElementById(customersId);

            if (!signalSourcesSelect || !customersSelect) return;

            // 加载信号源
            const signalSourcesResponse = await fetch(`${this.apiBaseUrl}/signal_sources`);
            if (signalSourcesResponse.ok) {
                const signalSourcesData = await signalSourcesResponse.json();
                if (signalSourcesData.success && Array.isArray(signalSourcesData.data)) {
                    signalSourcesSelect.innerHTML = signalSourcesData.data.map(source => 
                        `<option value="${source.source_uid}">${source.name} (${source.source_uid})</option>`
                    ).join('');
                }
            }

            // 加载客户
            const customersResponse = await fetch(`${this.apiBaseUrl}/customers`);
            if (customersResponse.ok) {
                const customersData = await customersResponse.json();
                if (customersData.success && Array.isArray(customersData.data)) {
                    customersSelect.innerHTML = customersData.data.map(customer => 
                        `<option value="${customer.customer_uid}">${customer.name} (${customer.customer_uid})</option>`
                    ).join('');
                }
            }

        } catch (error) {
            console.error('加载账号列表失败:', error);
        }
    }

    // 保存策略编辑
    async saveStrategyEdit() {
        try {
            const form = document.getElementById('editStrategyForm');
            if (!form) {
                this.showToast('错误', '编辑表单不存在', 'danger');
                return;
            }

            const strategyId = document.getElementById('editStrategyId').value;
            const strategyName = document.getElementById('editStrategyName').value;
            const tradingSymbol = document.getElementById('editTradingSymbol').value;
            const timeframe = document.getElementById('editTimeframe').value;
            const riskPerTrade = document.getElementById('editRiskPerTrade').value;
            const maxPositions = document.getElementById('editMaxPositions').value;
            const stopLossPct = document.getElementById('editStopLossPct').value;
            const takeProfitPct = document.getElementById('editTakeProfitPct').value;

            if (!strategyName || !tradingSymbol || !timeframe) {
                this.showToast('错误', '请填写所有必需字段', 'danger');
                return;
            }

            // 构建配置对象
            const config = {
                symbol: tradingSymbol,
                timeframe: timeframe,
                risk_per_trade: parseFloat(riskPerTrade),
                max_positions: parseInt(maxPositions),
                stop_loss_pct: parseFloat(stopLossPct),
                take_profit_pct: parseFloat(takeProfitPct)
            };

            // 获取策略特定参数
            const strategyType = document.getElementById('editStrategyType').value;
            this.collectEditStrategyParams(strategyType, config);

            // 获取选中的客户和信号源
            const selectedSignalSources = Array.from(document.getElementById('editSignalSources').selectedOptions)
                .map(option => option.value);
            const selectedCustomers = Array.from(document.getElementById('editCustomers').selectedOptions)
                .map(option => option.value);

            const requestData = {
                name: strategyName,
                config: config,
                signal_sources: selectedSignalSources,
                customers: selectedCustomers
            };

            this.showToast('信息', '正在保存策略...', 'info');

            const response = await fetch(`${this.apiBaseUrl}/strategy/instances/${strategyId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.showToast('成功', '策略更新成功', 'success');

                    // 关闭模态框
                    const modal = bootstrap.Modal.getInstance(document.getElementById('editStrategyModal'));
                    if (modal) modal.hide();

                    // 刷新策略列表
                    this.loadStrategyTradeList();
                } else {
                    this.showToast('错误', data.message || '策略更新失败', 'danger');
                }
            } else {
                this.showToast('错误', '策略更新请求失败', 'danger');
            }
        } catch (error) {
            console.error('保存策略编辑失败:', error);
            this.showToast('错误', '保存策略失败', 'danger');
        }
    }

    // 收集编辑策略的特定参数
    collectEditStrategyParams(strategyType, config) {
        switch (strategyType) {
            case 'MA_Cross_Strategy':
                const shortPeriod = document.getElementById('edit_short_period')?.value;
                const longPeriod = document.getElementById('edit_long_period')?.value;
                if (shortPeriod) config.short_period = parseInt(shortPeriod);
                if (longPeriod) config.long_period = parseInt(longPeriod);
                break;
            case 'RSI_Strategy':
                const rsiPeriod = document.getElementById('edit_rsi_period')?.value;
                const oversold = document.getElementById('edit_oversold')?.value;
                const overbought = document.getElementById('edit_overbought')?.value;
                if (rsiPeriod) config.rsi_period = parseInt(rsiPeriod);
                if (oversold) config.rsi_oversold = parseInt(oversold);
                if (overbought) config.rsi_overbought = parseInt(overbought);
                break;
            case 'MACD_Strategy':
                const fastPeriod = document.getElementById('edit_fast_period')?.value;
                const slowPeriod = document.getElementById('edit_slow_period')?.value;
                const signalPeriod = document.getElementById('edit_signal_period')?.value;
                if (fastPeriod) config.fast_period = parseInt(fastPeriod);
                if (slowPeriod) config.slow_period = parseInt(slowPeriod);
                if (signalPeriod) config.signal_period = parseInt(signalPeriod);
                break;
        }
    }
    
    // 策略类型变化处理
    async onStrategyTypeChange(strategyType) {
        console.log('🔄 策略类型变化:', strategyType);
        await this.showStrategyParams(strategyType);
    }

    // 根据策略类型显示参数表单
    async showStrategyParams(strategyType) {
        console.log('📋 开始生成策略参数表单:', strategyType);
        const paramsContainer = document.getElementById('strategySpecificParams');
        if (!paramsContainer) {
            console.error('❌ 找不到参数容器 strategySpecificParams');
            return;
        }

        paramsContainer.innerHTML = '';

        if (!strategyType) {
            console.log('⚠️ 策略类型为空，清空参数区域');
            return;
        }

        try {
            console.log('🌐 正在获取策略模板:', `${this.apiBaseUrl}/strategy/templates/${strategyType}`);
            // 获取策略模板
            const response = await fetch(`${this.apiBaseUrl}/strategy/templates/${strategyType}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            console.log('📥 API响应数据:', data);
            
            if (!data.success) {
                throw new Error(data.message || '获取策略模板失败');
            }

            const template = data.data;
            const config = template.default_config;
            const validation = template.validation_rules || {};

            console.log('⚙️ 策略模板数据:', {
                name: template.display_name,
                config: Object.keys(config),
                validation: Object.keys(validation)
            });

            // 创建参数表单
            const formHtml = this.generateStrategyParamsForm(strategyType, config, validation);
            console.log('🎨 生成的表单HTML长度:', formHtml.length);
            
            if (formHtml) {
                paramsContainer.innerHTML = `
                    <hr>
                    <h6>策略参数 - ${template.display_name}</h6>
                    <p class="text-muted small">${template.description}</p>
                    ${formHtml}
                `;
                console.log('✅ 策略参数表单已渲染');
            } else {
                console.log('⚠️ 生成的表单HTML为空');
                paramsContainer.innerHTML = `
                    <hr>
                    <h6>策略参数 - ${template.display_name}</h6>
                    <p class="text-muted">该策略使用默认参数配置</p>
                `;
            }

        } catch (error) {
            console.error('❌ 显示策略参数失败:', error);
            paramsContainer.innerHTML = `
                <hr>
                <h6>策略参数</h6>
                <div class="alert alert-warning">无法加载策略参数: ${error.message}</div>
            `;
        }
    }

    // 生成策略参数表单
    generateStrategyParamsForm(strategyType, config, validation) {
        console.log('🔧 开始生成参数表单:', strategyType);
        console.log('📝 配置参数:', config);
        console.log('✅ 验证规则:', validation);
        
        let formHtml = '<div class="row">';

        // 策略特定参数
        switch (strategyType) {
            case 'MA_Cross_Strategy':
                ['short_period', 'long_period'].forEach(param => {
                    if (config.hasOwnProperty(param)) {
                        formHtml += this.generateParamInput(param, config[param], validation[param]);
                    }
                });
                break;
                
            case 'RSI_Strategy':
                ['rsi_period', 'rsi_oversold', 'rsi_overbought'].forEach(param => {
                    if (config.hasOwnProperty(param)) {
                        formHtml += this.generateParamInput(param, config[param], validation[param]);
                    }
                });
                break;
                
            case 'Bollinger_Strategy':
                ['bb_period', 'bb_std'].forEach(param => {
                    if (config.hasOwnProperty(param)) {
                        formHtml += this.generateParamInput(param, config[param], validation[param]);
                    }
                });
                break;
                
            case 'MACD_Strategy':
                ['fast_period', 'slow_period', 'signal_period'].forEach(param => {
                    if (config.hasOwnProperty(param)) {
                        formHtml += this.generateParamInput(param, config[param], validation[param]);
                    }
                });
                break;
                
            case 'Grid_Strategy':
                ['grid_levels', 'grid_spacing', 'base_price'].forEach(param => {
                    if (config.hasOwnProperty(param)) {
                        formHtml += this.generateParamInput(param, config[param], validation[param]);
                    }
                });
                break;
        }

        formHtml += '</div>';
        console.log('🎯 最终表单HTML:', formHtml);
        return formHtml;
    }

    // 生成单个参数输入框
    generateParamInput(paramName, defaultValue, validation) {
        const label = this.getParamLabel(paramName);
        const type = this.getParamInputType(paramName, validation);
        const min = validation?.min || '';
        const max = validation?.max || '';
        const step = type === 'number' && paramName.includes('pct') ? '0.001' : 
                    type === 'number' && paramName.includes('std') ? '0.1' : '1';

        return `
            <div class="col-md-6 mb-3">
                <label for="${paramName}" class="form-label">${label}</label>
                <input type="${type}" 
                       class="form-control" 
                       id="${paramName}" 
                       name="${paramName}"
                       value="${defaultValue}"
                       ${min ? `min="${min}"` : ''}
                       ${max ? `max="${max}"` : ''}
                       ${type === 'number' ? `step="${step}"` : ''}
                       required>
                <div class="form-text">${this.getParamDescription(paramName)}</div>
            </div>
        `;
    }

    // 获取参数标签
    getParamLabel(paramName) {
        const labels = {
            'short_period': '短期均线周期',
            'long_period': '长期均线周期',
            'rsi_period': 'RSI周期',
            'rsi_oversold': 'RSI超卖线',
            'rsi_overbought': 'RSI超买线',
            'bb_period': '布林带周期',
            'bb_std': '布林带标准差',
            'fast_period': 'MACD快线周期',
            'slow_period': 'MACD慢线周期',
            'signal_period': 'MACD信号线周期',
            'grid_levels': '网格层数',
            'grid_spacing': '网格间距',
            'base_price': '基准价格'
        };
        return labels[paramName] || paramName;
    }

    // 获取参数输入类型
    getParamInputType(paramName, validation) {
        if (validation?.type === 'int') return 'number';
        if (validation?.type === 'float') return 'number';
        return 'number';
    }

    // 获取参数描述
    getParamDescription(paramName) {
        const descriptions = {
            'short_period': '短期移动平均线周期',
            'long_period': '长期移动平均线周期',
            'rsi_period': 'RSI计算周期',
            'rsi_oversold': '超卖阈值 (通常20-40)',
            'rsi_overbought': '超买阈值 (通常60-80)',
            'bb_period': '布林带计算周期',
            'bb_std': '标准差倍数',
            'fast_period': 'MACD快线周期',
            'slow_period': 'MACD慢线周期',
            'signal_period': 'MACD信号线周期',
            'grid_levels': '网格总层数',
            'grid_spacing': '网格间距百分比',
            'base_price': '网格中心价格'
        };
        return descriptions[paramName] || '';
    }

    // 动态收集策略参数
    collectDynamicStrategyParams(config) {
        const paramsContainer = document.getElementById('strategySpecificParams');
        if (!paramsContainer) return;

        // 获取所有参数输入框
        const inputs = paramsContainer.querySelectorAll('input[name]');
        inputs.forEach(input => {
            const paramName = input.name;
            let value = input.value;

            // 根据输入类型转换值
            if (input.type === 'number') {
                if (paramName.includes('period') || paramName.includes('levels') || paramName.includes('oversold') || paramName.includes('overbought')) {
                    value = parseInt(value);
                } else {
                    value = parseFloat(value);
                }
            }

            // 添加到配置中
            config[paramName] = value;
        });
    }
    
    // 收集回测策略参数
    collectBacktestStrategyParams(strategyType, symbol) {
        const config = {
            symbol: symbol,
            timeframe: '1h'
        };
        
        try {
            console.log(`🔍 动态收集策略 ${strategyType} 的参数...`);
            
            // 使用动态参数收集而不是硬编码
            const paramsContainer = document.getElementById('backtestStrategyParams');
            if (paramsContainer) {
                const inputs = paramsContainer.querySelectorAll('input[name], select[name]');
                console.log(`📋 找到 ${inputs.length} 个动态参数输入框`);
                
                inputs.forEach(input => {
                    const paramName = input.name;
                    let value = input.value;
                    
                    if (input.type === 'number') {
                        // 根据参数名判断是整数还是浮点数
                        if (paramName.includes('period') || paramName.includes('levels') || 
                            paramName.includes('oversold') || paramName.includes('overbought') ||
                            paramName.includes('threshold') && !paramName.includes('adjustment')) {
                            value = parseInt(value);
                        } else {
                            value = parseFloat(value);
                        }
                    } else if (input.type === 'checkbox') {
                        value = input.checked;
                    }
                    
                    config[paramName] = value;
                    console.log(`📝 动态参数: ${paramName} = ${value} (${typeof value})`);
                });
            } else {
                console.warn('⚠️ 未找到动态参数容器，使用默认值');
            }
            
            // 验证必需参数
            this.validateStrategyParams(strategyType, config);
            
            console.log(`✅ 收集到策略参数:`, config);
            return config;
            
        } catch (error) {
            console.error('策略参数收集失败:', error);
            this.showToast('错误', error.message, 'danger');
            return null;
        }
    }
    
    // 验证策略参数
    validateStrategyParams(strategyType, config) {
        switch (strategyType) {
            case 'MA_Cross_Strategy':
                if (!config.short_period || !config.long_period) {
                    throw new Error('移动平均线周期参数无效');
                }
                if (config.short_period >= config.long_period) {
                    throw new Error('短期均线周期必须小于长期均线周期');
                }
                break;
                
            case 'RSI_Strategy':
                if (!config.rsi_period) {
                    throw new Error('RSI周期参数无效');
                }
                // 使用动态发现的参数名
                const oversold = config.oversold_level || config.rsi_oversold;
                const overbought = config.overbought_level || config.rsi_overbought;
                if (oversold && overbought && oversold >= overbought) {
                    throw new Error('超卖线必须小于超买线');
                }
                break;
                
            case 'Grid_Strategy':
                if (!config.grid_levels || !config.grid_spacing || !config.base_price) {
                    throw new Error('网格策略参数无效：需要网格层数、网格间距和基准价格');
                }
                if (config.grid_levels < 3) {
                    throw new Error('网格层数不能少于3层');
                }
                if (config.grid_spacing <= 0 || config.grid_spacing > 0.5) {
                    throw new Error('网格间距必须在0到50%之间');
                }
                break;
                
            case 'Bollinger_Strategy':
                if (!config.period || !config.std_dev) {
                    throw new Error('布林带参数无效');
                }
                break;
                
            default:
                console.log(`✅ 策略 ${strategyType} 使用默认参数验证`);
                break;
        }
    }
    
    // 运行回测
    async runBacktest() {
        try {
            const form = document.getElementById('backtestForm');
            if (!form) {
                this.showToast('错误', '回测表单不存在', 'danger');
                return;
            }
            
            // 获取表单数据
            const strategySelectValue = document.getElementById('backtestStrategy')?.value;
            const backtestName = document.getElementById('backtestName')?.value;
            const startDate = document.getElementById('backtestStartDate')?.value;
            const endDate = document.getElementById('backtestEndDate')?.value;
            const capital = document.getElementById('backtestCapital')?.value;
            const symbol = document.getElementById('backtestSymbol')?.value;
            
            if (!strategySelectValue || !backtestName || !startDate || !endDate || !capital) {
                this.showToast('错误', '请填写所有必需字段', 'danger');
                return;
            }
            
            // 解析策略选择值（可能是模板或实例）
            let strategyName;
            let isTemplate = false;
            
            if (strategySelectValue.startsWith('template:')) {
                strategyName = strategySelectValue.replace('template:', '');
                isTemplate = true;
            } else if (strategySelectValue.startsWith('instance:')) {
                strategyName = strategySelectValue.replace('instance:', '');
                isTemplate = false;
            } else {
                // 兼容旧格式
                strategyName = strategySelectValue;
                isTemplate = false;
            }
            
            this.showToast('信息', `正在运行回测 (${isTemplate ? '策略模板' : '策略实例'})，请稍候...`, 'info');
            
            // 收集策略参数
            let strategyConfig = {
                symbol: symbol,
                timeframe: '1h'
            };
            
            // 如果是策略模板，需要收集用户输入的参数
            if (isTemplate) {
                strategyConfig = this.collectBacktestStrategyParams(strategyName, symbol);
                if (!strategyConfig) {
                    this.showToast('错误', '策略参数配置无效', 'danger');
                    return;
                }
            }
            
            // 调用回测API
            const requestData = {
                strategy_name: strategyName,
                backtest_name: backtestName,
                start_date: startDate,
                end_date: endDate,
                initial_capital: parseFloat(capital),
                symbol: symbol,
                is_template: isTemplate,  // 新增字段，告诉后端这是模板还是实例
                strategy_config: strategyConfig  // 策略配置参数
            };
            
            console.log('开始回测，参数:', requestData);
            
            const response = await fetch(`${this.apiBaseUrl}/strategy/backtests`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.showToast('成功', '回测运行完成！', 'success');
                    console.log('回测结果:', data.data);
                    
                    // 关闭模态框
                    const modal = bootstrap.Modal.getInstance(document.getElementById('backtestModal'));
                    if (modal) modal.hide();
                    
                    // 重置表单
                    form.reset();
                    
                    // 刷新回测历史
                    this.loadBacktestHistory();
                    
                    // 显示回测结果摘要
                    if (data.data && data.data.performance_stats) {
                        const stats = data.data.performance_stats;
                        this.showToast('信息', 
                            `回测完成！总收益率: ${(stats.total_return * 100).toFixed(2)}%, ` +
                            `胜率: ${(stats.win_rate * 100).toFixed(1)}%, ` +
                            `最大回撤: ${(stats.max_drawdown * 100).toFixed(2)}%`, 
                            'info');
                    }
                } else {
                    this.showToast('错误', data.message || '回测运行失败', 'danger');
                }
            } else {
                const errorData = await response.json().catch(() => ({}));
                this.showToast('错误', errorData.message || `回测请求失败 (${response.status})`, 'danger');
            }
            
        } catch (error) {
            console.error('运行回测失败:', error);
            this.showToast('错误', `回测运行失败: ${error.message}`, 'danger');
        }
    }
}

// 页面加载完成后初始化应用
document.addEventListener('DOMContentLoaded', () => {
    window.app = new OKXTradingApp();
});

// 全局错误处理
window.addEventListener('error', (event) => {
    console.error('全局错误:', event.error);
    if (window.app) {
        window.app.showToast('错误', '系统发生错误，请查看控制台', 'danger');
    }
});

// ==================== 策略交易事件处理 ====================

// 等待DOM加载完成后绑定事件
document.addEventListener('DOMContentLoaded', function() {
    // 初始化数据库按钮
    const initDbBtn = document.getElementById('initDatabaseBtn');
    if (initDbBtn) {
        initDbBtn.addEventListener('click', () => {
            if (window.app) {
                window.app.initDatabase();
            }
        });
    }
    
    // 创建策略按钮
    const createStrategyBtn = document.getElementById('createStrategyBtn');
    if (createStrategyBtn) {
        createStrategyBtn.addEventListener('click', () => {
            if (window.app) {
                window.app.createStrategyTrade();
            }
        });
    }
    
    // 运行回测按钮
    const runBacktestBtn = document.getElementById('runBacktestBtn');
    if (runBacktestBtn) {
        runBacktestBtn.addEventListener('click', () => {
            if (window.app) {
                window.app.runBacktest();
            }
        });
    }
    
    // 策略类型变化事件
    const strategyTypeSelect = document.getElementById('strategyType');
    if (strategyTypeSelect) {
        strategyTypeSelect.addEventListener('change', (e) => {
            if (window.app) {
                window.app.onStrategyTypeChange(e.target.value);
            }
        });
    }
    
    // 创建策略模态框显示事件
    const createStrategyModal = document.getElementById('createStrategyTradeModal');
    if (createStrategyModal) {
        createStrategyModal.addEventListener('show.bs.modal', () => {
            if (window.app) {
                window.app.loadAccountsForStrategy('create');
            }
        });
    }
    
    // 编辑策略保存按钮事件
    const saveStrategyBtn = document.getElementById('saveStrategyBtn');
    if (saveStrategyBtn) {
        saveStrategyBtn.addEventListener('click', () => {
            if (window.app) {
                window.app.saveStrategyEdit();
            }
        });
    }
});

// 未处理的Promise拒绝
window.addEventListener('unhandledrejection', (event) => {
    console.error('未处理的Promise拒绝:', event.reason);
    if (window.app) {
        window.app.showToast('错误', '网络请求失败，请检查网络连接', 'danger');
    }
}); 