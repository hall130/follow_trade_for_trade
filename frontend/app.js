// OKX跟单交易系统前端应用
class OKXTradingApp {
    constructor() {
        this.apiBaseUrl = window.APP_CONFIG?.api?.baseUrl || '/api/v1';
        this.currentPage = 'dashboard';
        this.currentTradesPage = 1;
        this.tradesSearchParams = {};
        
        // 用户和权限信息
        this.currentUser = null;
        this.userPermissions = {};
        this.isLoggedIn = false;
        
        // 防重复点击标志
        this.isUpdatingAssets = false;
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
                'message-forward': 5000, // 消息转发：5秒
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

    /**
     * 动态获取 is_demo 值
     * 优先级：表单元素 > URL参数 > localStorage > 默认值
     * 
     * @param {Object} options - 选项
     * @param {string} options.elementId - 表单元素ID（如 'manualIsDemo', 'isDemo'）
     * @param {number} options.defaultValue - 默认值（0=实盘, 1=模拟），默认1
     * @param {boolean} options.asBoolean - 返回布尔值而不是数字
     * @returns {number|boolean} is_demo 值
     */
    getIsDemo(options = {}) {
        const {
            elementId = null,
            defaultValue = 1,
            asBoolean = false
        } = options;
        
        // 1. 优先从指定表单元素获取
        if (elementId) {
            const element = document.getElementById(elementId);
            if (element) {
                const value = element.type === 'checkbox' ? element.checked : (element.value === '1' || element.value === 'true');
                return asBoolean ? value : (value ? 1 : 0);
            }
        }
        
        // 2. 尝试从常见的表单元素获取
        const commonElementIds = ['manualIsDemo', 'isDemo', 'customerIsDemo', 'signalSourceIsDemo'];
        for (const id of commonElementIds) {
            const element = document.getElementById(id);
            if (element) {
                const value = element.type === 'checkbox' ? element.checked : (element.value === '1' || element.value === 'true');
                return asBoolean ? value : (value ? 1 : 0);
            }
        }
        
        // 3. 从 URL 参数获取
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('is_demo')) {
            const value = urlParams.get('is_demo') === '1' || urlParams.get('is_demo') === 'true';
            return asBoolean ? value : (value ? 1 : 0);
        }
        if (urlParams.has('isdemo')) {
            const value = urlParams.get('isdemo') === '1' || urlParams.get('isdemo') === 'true';
            return asBoolean ? value : (value ? 1 : 0);
        }
        if (urlParams.has('IsDemo')) {
            const value = urlParams.get('IsDemo') === '1' || urlParams.get('IsDemo') === 'true';
            return asBoolean ? value : (value ? 1 : 0);
        }
        
        // 4. 从 localStorage 获取用户偏好
        try {
            const savedDemo = localStorage.getItem('preferredDemoMode');
            if (savedDemo !== null) {
                const value = savedDemo === '1' || savedDemo === 'true';
                return asBoolean ? value : (value ? 1 : 0);
            }
        } catch (e) {
            // localStorage 不可用，忽略
        }
        
        // 5. 返回默认值
        return asBoolean ? (defaultValue === 1) : defaultValue;
    }
    
    /**
     * 设置用户偏好的 demo 模式（保存到 localStorage）
     * @param {number|boolean} isDemo - demo 模式值
     */
    setIsDemoPreference(isDemo) {
        try {
            const value = typeof isDemo === 'boolean' ? (isDemo ? '1' : '0') : String(isDemo);
            localStorage.setItem('preferredDemoMode', value);
        } catch (e) {
            console.warn('无法保存 demo 模式偏好:', e);
        }
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

    async init() {
        try {
            // 首先检查登录状态（等待完成）
            await this.checkLoginStatus();
            
            // 绑定事件（同步操作，不阻塞）
        this.bindEvents();
            this.initStrategyTradeModalEvents();
            this.initSymbolSearch();
            
            // 如果当前在仪表板页面，加载数据
            if (this.currentPage === 'dashboard' || !this.currentPage) {
                // 异步加载数据，不阻塞页面渲染
                this.loadDashboardData().catch(err => {
                    console.error('加载仪表板数据失败:', err);
                });
            }
            
            // 初始化图表（异步，不阻塞）
        this.setupCharts();
        this.initKlineChart();
        
            // 初始化自动刷新
            this.initAutoRefresh();
            if (this.currentPage === 'dashboard' || !this.currentPage) {
                this.startAutoRefresh('kline');
            }
        } catch (error) {
            console.error('初始化失败:', error);
            // 即使初始化失败，也显示页面
        }
    }

    // 检查登录状态
    async checkLoginStatus() {
        try {
            // 从localStorage获取登录状态
            const loginStatus = localStorage.getItem('loginStatus');
            if (!loginStatus) {
                this.redirectToLogin();
                return;
            }
            
            const status = JSON.parse(loginStatus);
            if (!status.isLoggedIn || status.expiresAt <= Date.now()) {
                this.redirectToLogin();
                return;
            }
            
            // 验证Token是否有效（使用apiRequest自动包含认证Token）
            // 注意：这里需要手动设置token，因为可能在登录状态检查时使用
            const response = await this.apiRequest(`${this.apiBaseUrl}/auth/me`, {
                method: 'GET'
            });
            
            if (!response.ok) {
                this.redirectToLogin();
                return;
            }
            
            const result = await response.json();
            if (result.success) {
                this.currentUser = result.data;
                this.userPermissions = status.permissions;
                this.isLoggedIn = true;
                
                // 更新用户显示
                this.updateUserDisplay();
                
                // 应用权限控制
                this.applyPermissionControl();
                
                // 重新加载公告列表以更新按钮显示（如果已在仪表板页面）
                if (document.getElementById('addAnnouncementBtn')) {
                    this.loadAnnouncements();
                }
            } else {
                this.redirectToLogin();
            }
            
        } catch (error) {
            console.error('检查登录状态失败:', error);
            this.redirectToLogin();
        }
    }
    
    // 通用API请求方法（带超时控制）
    async apiRequest(url, options = {}) {
        try {
            // 获取登录状态
            const loginStatus = localStorage.getItem('loginStatus');
            if (!loginStatus) {
                this.redirectToLogin();
                return null;
            }
            
            const status = JSON.parse(loginStatus);
            
            if (!status.isLoggedIn || status.expiresAt <= Date.now()) {
                this.redirectToLogin();
                return null;
            }
            
            // 设置默认headers
            const defaultHeaders = {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${status.token}`
            };
            
            // 合并headers
            const headers = {
                ...defaultHeaders,
                ...(options.headers || {})
            };
            
            // 设置超时（默认30秒）
            const timeout = options.timeout || 30000;
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), timeout);
            
            try {
            // 发起请求
            const response = await fetch(url, {
                ...options,
                    headers,
                    signal: controller.signal
            });
            
                clearTimeout(timeoutId);
            
            // 如果返回401，说明token过期或无效
            if (response.status === 401) {
                this.redirectToLogin();
                return null;
            }
            
            return response;
            } catch (error) {
                clearTimeout(timeoutId);
                if (error.name === 'AbortError') {
                    console.error(`API请求超时: ${url}`);
                    return null;
                }
                throw error;
            }
            
        } catch (error) {
            console.error('API请求失败:', error);
            return null;
        }
    }
    
    // 显示用户资料
    showUserProfile() {
        if (!this.currentUser) {
            this.showToast('错误', '用户信息未加载', 'danger');
            return;
        }
        
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">用户资料</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="row">
                            <div class="col-md-6">
                                <label class="form-label">用户名</label>
                                <input type="text" class="form-control" value="${this.currentUser.username || ''}" readonly>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label">姓名</label>
                                <input type="text" class="form-control" value="${this.currentUser.full_name || ''}" readonly>
                            </div>
                        </div>
                        <div class="row mt-3">
                            <div class="col-md-6">
                                <label class="form-label">邮箱</label>
                                <input type="email" class="form-control" value="${this.currentUser.email || ''}" readonly>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label">角色</label>
                                <input type="text" class="form-control" value="${this.currentUser.role || ''}" readonly>
                            </div>
                        </div>
                        <div class="row mt-3">
                            <div class="col-md-6">
                                <label class="form-label">状态</label>
                                <input type="text" class="form-control" value="${this.currentUser.status || ''}" readonly>
                            </div>
                            <div class="col-md-6">
                                <label class="form-label">最后登录</label>
                                <input type="text" class="form-control" value="${this.currentUser.last_login_at || '未知'}" readonly>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
        
        // 模态框关闭后移除DOM元素
        modal.addEventListener('hidden.bs.modal', () => {
            document.body.removeChild(modal);
        });
    }
    
    // 更新用户显示
    updateUserDisplay() {
        const userDisplayName = document.getElementById('userDisplayName');
        if (userDisplayName && this.currentUser) {
            const displayName = this.currentUser.full_name || this.currentUser.username;
            const roleBadge = this.currentUser.role === 'admin' ? ' <span class="badge bg-danger">管理员</span>' : '';
            userDisplayName.innerHTML = displayName + roleBadge;
        }
        
        // 更新"发布公告"按钮显示状态
        const addBtn = document.getElementById('addAnnouncementBtn');
        if (addBtn) {
            const isAdmin = this.currentUser && this.currentUser.role === 'admin';
            addBtn.style.display = isAdmin ? 'inline-block' : 'none';
        }
    }
    
    // 应用权限控制
    applyPermissionControl() {
        // 第一步：隐藏所有无权限的子菜单项
        document.querySelectorAll('.nav-item [data-permission]').forEach(element => {
            const requiredPermission = element.getAttribute('data-permission');
            if (!this.hasPermission(requiredPermission)) {
                element.closest('li').style.display = 'none';
            }
        });
        
        // 第二步：检查父菜单项，如果所有子项都被隐藏，则隐藏父菜单项
        document.querySelectorAll('.nav-item').forEach(navItem => {
            const menuToggle = navItem.querySelector('.menu-toggle');
            if (!menuToggle) return; // 没有子菜单的项跳过
            
            // 检查父菜单项本身的权限
            const parentPermission = menuToggle.getAttribute('data-permission');
            if (parentPermission && !this.hasPermission(parentPermission)) {
                navItem.style.display = 'none';
                return;
            }
            
            // 获取子菜单容器
            const subMenuId = menuToggle.getAttribute('data-bs-target');
            if (!subMenuId) return;
            
            const subMenu = navItem.querySelector(subMenuId);
            if (!subMenu) return;
            
            // 检查子菜单中的所有子项
            const subItems = subMenu.querySelectorAll('li');
            let visibleCount = 0;
            
            subItems.forEach(subItem => {
                // 检查分隔线（hr）是否应该显示
                if (subItem.querySelector('hr')) {
                    // 分隔线：检查前后是否有可见项
                    const prevVisible = Array.from(subItems).slice(0, Array.from(subItems).indexOf(subItem))
                        .some(item => item.style.display !== 'none' && !item.querySelector('hr'));
                    const nextVisible = Array.from(subItems).slice(Array.from(subItems).indexOf(subItem) + 1)
                        .some(item => item.style.display !== 'none' && !item.querySelector('hr'));
                    
                    if (!prevVisible || !nextVisible) {
                        subItem.style.display = 'none';
                    } else {
                        visibleCount++; // 分隔线也算可见
                    }
                } else if (subItem.style.display !== 'none') {
                    visibleCount++;
                }
            });
            
            // 如果所有子项都被隐藏，隐藏父菜单项
            if (visibleCount === 0) {
                navItem.style.display = 'none';
            }
        });
        
        // 第三步：隐藏没有子菜单但无权限的菜单项
        document.querySelectorAll('.nav-item > .nav-link:not(.menu-toggle)[data-permission]').forEach(element => {
            const requiredPermission = element.getAttribute('data-permission');
            if (!this.hasPermission(requiredPermission)) {
                element.closest('.nav-item').style.display = 'none';
            }
        });
        
        // 显示管理员专用菜单
        if (this.currentUser && this.currentUser.role === 'admin') {
            const adminMenus = document.querySelectorAll('#admin-menu-users, #admin-menu-permissions');
            adminMenus.forEach(menu => {
                menu.style.display = 'block';
            });
        }
        
        // 策略交易模块权限控制：显示/隐藏账号选择区域
        this.applyStrategyTradePermissionControl();
    }
    
    // 策略交易模块权限控制
    applyStrategyTradePermissionControl() {
        const isAdmin = this.currentUser && this.currentUser.role === 'admin';
        
        // 账号关联区域（仅管理员可见）
        const accountSection = document.getElementById('strategyAccountSection');
        const accountSelects = document.getElementById('strategyAccountSelects');
        const accountHint = document.getElementById('strategyAccountHint');
        
        if (accountSection) {
            accountSection.style.display = isAdmin ? 'flex' : 'none';
        }
        if (accountSelects) {
            accountSelects.style.display = isAdmin ? 'flex' : 'none';
        }
        if (accountHint) {
            accountHint.style.display = isAdmin ? 'none' : 'flex';
        }
    }
    
    // 初始化策略交易模态框事件监听
    initStrategyTradeModalEvents() {
        const createStrategyTradeModal = document.getElementById('createStrategyTradeModal');
        if (createStrategyTradeModal) {
            // 当模态框显示时，应用权限控制
            createStrategyTradeModal.addEventListener('show.bs.modal', () => {
                this.applyStrategyTradePermissionControl();
            });
        }
    }
    
    // 加载用户权限
    async loadUserPermissions() {
        try {
            if (!this.currentUser) {
                this.userPermissions = {};
                return;
            }
            
            // 管理员拥有所有权限
            if (this.currentUser.role === 'admin') {
                this.userPermissions = {
                    'customers': 'admin',
                    'signal_sources': 'admin',
                    'strategies': 'admin',
                    'rules': 'admin',
                    'market_follow': 'admin',
                    'limit_follow': 'admin',
                    'backtest': 'admin',
                    'strategy_live': 'admin',
                    'message_forward': 'admin',
                    'system_settings': 'admin',
                    'users': 'admin'
                };
                return;
            }
            
            // 普通用户通过API获取权限
            const response = await this.apiRequest(`${this.apiBaseUrl}/auth/permissions/user/${this.currentUser.id}`);
            if (response && response.ok) {
                const data = await response.json();
                if (data.success && data.data) {
                    this.userPermissions = data.data;
                } else {
                    this.userPermissions = {};
                }
            } else {
                this.userPermissions = {};
            }
            
            
        } catch (error) {
            console.error('加载用户权限失败:', error);
            this.userPermissions = {};
        }
    }

    // 检查权限
    hasPermission(moduleCode, requiredLevel = 'read') {
        if (!this.currentUser) return false;
        
        // 管理员拥有所有权限
        if (this.currentUser.role === 'admin') return true;
        
        // 检查具体权限
        const userPermission = this.userPermissions[moduleCode];
        if (!userPermission) return false;
        
        // 权限级别比较
        const permissionLevels = {
            'none': 0,
            'read': 1,
            'write': 2,
            'admin': 3
        };
        
        const requiredWeight = permissionLevels[requiredLevel] || 0;
        const userWeight = permissionLevels[userPermission] || 0;
        
        return userWeight >= requiredWeight;
    }
    
    // 权限检查装饰器
    requirePermission(moduleCode, requiredLevel = 'read') {
        return (target, propertyKey, descriptor) => {
            const originalMethod = descriptor.value;
            descriptor.value = function(...args) {
                if (!this.hasPermission(moduleCode, requiredLevel)) {
                    this.showError('没有访问权限');
                    return;
                }
                return originalMethod.apply(this, args);
            };
        };
    }
    
    // 登出
    async logout() {
        try {
            const loginStatus = JSON.parse(localStorage.getItem('loginStatus') || '{}');
            
            if (loginStatus.sessionId) {
                // 使用apiRequest自动包含认证Token
                await this.apiRequest(`${this.apiBaseUrl}/auth/logout`, {
                    method: 'POST'
                });
            }
            
        } catch (error) {
            console.error('登出请求失败:', error);
        } finally {
            // 清除本地状态并跳转
            localStorage.removeItem('loginStatus');
            this.redirectToLogin();
        }
    }

    bindEvents() {
        // 侧边栏切换
        const sidebarToggle = document.getElementById('sidebarToggle');
        const sidebar = document.getElementById('sidebar');
        const sidebarOverlay = document.getElementById('sidebarOverlay');
        
        if (sidebarToggle) {
            sidebarToggle.addEventListener('click', () => {
                sidebar.classList.toggle('collapsed');
                if (window.innerWidth <= 768) {
                    sidebar.classList.toggle('show');
                    sidebarOverlay.classList.toggle('show');
                }
            });
        }
        
        if (sidebarOverlay) {
            sidebarOverlay.addEventListener('click', () => {
                sidebar.classList.remove('show');
                sidebarOverlay.classList.remove('show');
            });
        }
        
        // 侧边栏子菜单展开/收起时更新箭头方向
        document.querySelectorAll('[data-bs-toggle="collapse"]').forEach(toggle => {
            toggle.addEventListener('click', (e) => {
                // 如果点击的是带有data-page的链接，不阻止默认行为
                if (!e.target.closest('[data-page]')) {
                    // 让Bootstrap处理collapse
                }
            });
        });
        
        // 导航事件
        document.querySelectorAll('[data-page]').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                // 获取最近的带有data-page属性的元素
                const targetElement = e.target.closest('[data-page]');
                const pageName = targetElement ? targetElement.dataset.page : null;
                
                if (pageName) {
                    this.navigateToPage(pageName);
                    // 移动端点击后关闭侧边栏
                    if (window.innerWidth <= 768) {
                        sidebar.classList.remove('show');
                        sidebarOverlay.classList.remove('show');
                    }
                } else {
                    console.warn('页面不存在:', pageName);
                }
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
        
        // 个人资料
        const userProfileBtn = document.getElementById('userProfile');
        if (userProfileBtn) {
            userProfileBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.showUserProfile();
            });
        }
        
        // 修改密码
        const changePasswordBtn = document.getElementById('changePassword');
        if (changePasswordBtn) {
            changePasswordBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.showChangePasswordModal();
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
        
        // 执行限价跟单按钮
        const submitLimitFollowBtn = document.getElementById('submitLimitFollowExecution');
        if (submitLimitFollowBtn) {
            submitLimitFollowBtn.addEventListener('click', () => {
                this.submitLimitFollowExecution();
            });
        }

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

        // 策略管理模态框事件
        const saveStrategyManagementBtn = document.getElementById('saveStrategyManagementBtn');
        if (saveStrategyManagementBtn) {
            saveStrategyManagementBtn.addEventListener('click', () => {
                this.saveStrategyManagement();
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
        
        // 管理策略客户相关事件
        const addCustomerToStrategyBtn = document.getElementById('addCustomerToStrategyBtn');
        if (addCustomerToStrategyBtn) {
            addCustomerToStrategyBtn.addEventListener('click', () => {
                this.addCustomerToStrategy();
            });
        }
        
        // 编辑客户相关事件
        const saveEditCustomerBtn = document.getElementById('saveEditCustomerBtn');
        if (saveEditCustomerBtn) {
            saveEditCustomerBtn.addEventListener('click', () => {
                this.saveEditCustomer();
            });
        }
        
        // 编辑交易相关事件
        const saveEditTradeBtn = document.getElementById('saveEditTradeBtn');
        if (saveEditTradeBtn) {
            saveEditTradeBtn.addEventListener('click', () => {
                this.saveEditTrade();
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
                this.loadSignalSourcesOptions();
                this.loadCustomersOptions();
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
            const response = await this.apiRequest(`${this.apiBaseUrl}/signal_sources`);
            if (response && response.ok) {
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

    // 加载客户选项
    async loadCustomersOptions() {
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/customers`);
            if (response && response.ok) {
                const data = await response.json();
                const select = document.getElementById('strategyCustomers');
                if (select) {
                    // 清空现有选项
                    select.innerHTML = '';
                    
                    // 修复数据结构：客户API返回的是 {data: {customers: [...]}}
                    const customers = data.data && data.data.customers ? data.data.customers : [];
                    
                    if (Array.isArray(customers)) {
                        customers.forEach(customer => {
                            const option = document.createElement('option');
                            option.value = customer.customer_uid;
                            option.textContent = customer.name || customer.customer_uid;
                            select.appendChild(option);
                        });
                    }
                }
            }
        } catch (error) {
            console.error('加载客户选项失败:', error);
        }
    }

    // 动态加载策略下拉选项
    async loadStrategiesOptions() {
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/strategies`);
            if (response && response.ok) {
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
        // 检查页面权限（除了仪表板和登录页面）
        if (pageName !== 'dashboard' && pageName !== 'login') {
            const pageLink = document.querySelector(`[data-page="${pageName}"]`);
            if (pageLink) {
                const requiredPermission = pageLink.getAttribute('data-permission');
                if (requiredPermission && !this.hasPermission(requiredPermission)) {
                    this.showToast('错误', '您没有访问此页面的权限', 'danger');
                    // 如果当前不在仪表板，则跳转到仪表板
                    if (this.currentPage !== 'dashboard') {
                        this.navigateToPage('dashboard');
                    }
                    return;
                }
            }
        }
        
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
                this.applyTradesPagePermissionControl();
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
            case 'message-forward':
                this.loadMessageForwardData();
                break;
            case 'user-management':
                this.loadUserManagementData();
                break;
            case 'permission-management':
                this.loadPermissionManagementData();
                break;
            case 'market-maker':
                this.loadMarketMakers();
                break;
            case 'market-maker-stats':
                this.loadMarketMakerStats();
                break;
            case 'popular-traders':
                this.loadPopularTraders();
                break;
            case 'hyperliquid-discovery':
                this.loadHyperliquidTraders();
                break;
            case 'hyperliquid-follow':
                this.loadHyperliquidFollow();
                break;
            case 'echosync-leaderboard':
                // 默认加载 PNL 排行榜（使用筛选器的时间范围）
                const defaultPeriod = this.getLeaderboardPeriod();
                this.loadEchosyncLeaderboard('total_pnl', defaultPeriod);
                break;
            case 'echosync-whale-orders':
                this.loadWhaleOrders();
                break;
            case 'echosync-whale-moves':
                this.loadWhaleMoves();
                break;
            default:
                console.warn('未知页面:', pageName);
        }
    }

    // 加载仪表盘数据
    async loadDashboardData() {
        try {
            // 并行加载数据，提高速度
            const [statsResponse, announcementsResponse] = await Promise.allSettled([
                this.apiRequest(`${this.apiBaseUrl}/stats/overview`, { timeout: 10000 }),
                fetch(`${this.apiBaseUrl}/announcements`).catch(() => null)
            ]);
            
            // 处理统计数据
            if (statsResponse.status === 'fulfilled' && statsResponse.value && statsResponse.value.ok) {
                try {
                    const statsData = await statsResponse.value.json();
                this.updateDashboardStats(statsData.data);
                } catch (e) {
                    console.error('解析统计数据失败:', e);
                }
            } else {
                // 使用默认数据，不阻塞页面
                this.updateDashboardStats({
                    total_customers: 0,
                    today_trades: 0,
                    active_strategies: 0,
                    system_status: '加载中...'
                });
            }
            
            // 处理公告数据
            if (announcementsResponse.status === 'fulfilled' && announcementsResponse.value && announcementsResponse.value.ok) {
                try {
                    const data = await announcementsResponse.value.json();
                    this.renderAnnouncements(data.data || []);
                } catch (e) {
                    console.error('解析公告数据失败:', e);
                    this.renderAnnouncements([]);
                }
            } else {
                this.renderAnnouncements([]);
            }

            // 更新图表（异步，不阻塞）
            this.updateDashboardCharts();
            
        } catch (error) {
            console.error('加载仪表盘数据失败:', error);
            // 显示默认数据，确保页面可用
            this.updateDashboardStats({
                total_customers: 0,
                today_trades: 0,
                active_strategies: 0,
                system_status: '加载失败'
            });
            this.renderAnnouncements([]);
        }
    }

    // 静默加载仪表盘数据（用于自动刷新）
    async loadDashboardDataSilent() {
        try {
            // 加载概览统计（使用apiRequest自动包含认证Token）
            const statsResponse = await this.apiRequest(`${this.apiBaseUrl}/stats/overview`);
            if (statsResponse && statsResponse.ok) {
                const statsData = await statsResponse.json();
                this.updateDashboardStats(statsData.data);
            }

            // 加载最近活动（使用apiRequest自动包含认证Token）
            const activitiesResponse = await this.apiRequest(`${this.apiBaseUrl}/activities/recent`);
            if (activitiesResponse && activitiesResponse.ok) {
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

    // ==================== 公告管理 ====================
    
    // 加载公告列表（带超时控制）
    async loadAnnouncements() {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000); // 10秒超时
            
            try {
                const response = await fetch(`${this.apiBaseUrl}/announcements`, {
                    signal: controller.signal
                });
                clearTimeout(timeoutId);
                
                if (!response.ok) throw new Error('获取公告失败');
                
                const data = await response.json();
                this.renderAnnouncements(data.data || []);
            } catch (error) {
                clearTimeout(timeoutId);
                if (error.name === 'AbortError') {
                    console.error('加载公告超时');
                } else {
                    throw error;
                }
            }
        } catch (error) {
            console.error('加载公告失败:', error);
            const container = document.getElementById('announcements-list');
            if (container) {
                container.innerHTML = `
                    <div class="alert alert-warning">
                        <i class="bi bi-exclamation-triangle"></i> 暂无公告
                    </div>
                `;
            }
        }
    }
    
    // 渲染公告列表
    renderAnnouncements(announcements) {
        const container = document.getElementById('announcements-list');
        if (!container) return;
        
        if (!announcements || announcements.length === 0) {
            container.innerHTML = `
                <div class="alert alert-info">
                    <i class="bi bi-info-circle"></i> 暂无公告
                </div>
            `;
            return;
        }

        // 按优先级和时间排序
        announcements.sort((a, b) => {
            if (a.is_pinned !== b.is_pinned) return b.is_pinned - a.is_pinned;
            if (a.priority !== b.priority) return b.priority - a.priority;
            return new Date(b.created_at) - new Date(a.created_at);
        });
        
        // 检查是否是管理员
        const isAdmin = this.currentUser && this.currentUser.role === 'admin';
        
        const html = announcements.map(ann => {
            const typeClass = {
                'info': 'primary',
                'warning': 'warning',
                'success': 'success',
                'danger': 'danger'
            }[ann.type] || 'primary';
            
            const typeIcon = {
                'info': 'info-circle',
                'warning': 'exclamation-triangle',
                'success': 'check-circle',
                'danger': 'x-circle'
            }[ann.type] || 'info-circle';
            
            // 只有管理员才显示编辑/删除按钮
            const adminButtons = isAdmin ? `
                <div class="btn-group btn-group-sm">
                    <button class="btn btn-outline-secondary" onclick="window.app.editAnnouncement(${ann.id})" title="编辑">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-outline-danger" onclick="window.app.deleteAnnouncement(${ann.id})" title="删除">
                        <i class="bi bi-trash"></i>
                    </button>
            </div>
            ` : '';
            
            return `
                <div class="alert alert-${typeClass} d-flex align-items-start mb-3" role="alert">
                    <i class="bi bi-${typeIcon} me-3 fs-4"></i>
                    <div class="flex-grow-1">
                        <div class="d-flex justify-content-between align-items-start">
                            <h6 class="alert-heading mb-1">
                                ${ann.is_pinned ? '<i class="bi bi-pin-angle-fill text-danger"></i> ' : ''}
                                ${this.escapeHtml(ann.title)}
                            </h6>
                            ${adminButtons}
                        </div>
                        <p class="mb-2">${this.escapeHtml(ann.content)}</p>
                        <small class="text-muted">
                            <i class="bi bi-clock"></i> ${this.formatTime(ann.created_at)}
                            ${ann.created_by ? ` · 发布人: ${ann.created_by}` : ''}
                        </small>
                    </div>
                </div>
            `;
        }).join('');
        
        container.innerHTML = html;
        
        // 显示/隐藏"发布公告"按钮
        const addBtn = document.getElementById('addAnnouncementBtn');
        if (addBtn) {
            addBtn.style.display = isAdmin ? 'inline-block' : 'none';
        }
    }
    
    // 显示添加公告模态框
    showAddAnnouncementModal() {
        // 权限检查：只有管理员可以发布公告
        if (!this.currentUser || this.currentUser.role !== 'admin') {
            this.showToast('错误', '只有管理员可以发布公告', 'danger');
            return;
        }
        
        // 重置表单
        document.getElementById('announcementForm').reset();
        document.getElementById('announcementId').value = '';
        document.getElementById('announcementModalTitle').textContent = '发布公告';
        
        // 显示模态框
        const modal = new bootstrap.Modal(document.getElementById('announcementModal'));
        modal.show();
    }
    
    // 保存公告
    async saveAnnouncement() {
        // 权限检查：只有管理员可以保存公告
        if (!this.currentUser || this.currentUser.role !== 'admin') {
            this.showToast('错误', '只有管理员可以保存公告', 'danger');
            return;
        }
        
        const id = document.getElementById('announcementId').value;
        const title = document.getElementById('announcementTitle').value.trim();
        const content = document.getElementById('announcementContent').value.trim();
        const type = document.getElementById('announcementType').value;
        const priority = parseInt(document.getElementById('announcementPriority').value);
        const isPinned = document.getElementById('announcementPinned').checked;
        
        if (!title || !content) {
            this.showToast('错误', '请填写标题和内容', 'danger');
            return;
        }
        
        try {
            const url = id ? `${this.apiBaseUrl}/announcements/${id}` : `${this.apiBaseUrl}/announcements`;
            const method = id ? 'PUT' : 'POST';
            
            const response = await fetch(url, {
                method,
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    title,
                    content,
                    type,
                    priority,
                    is_pinned: isPinned ? 1 : 0
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast('成功', id ? '公告更新成功' : '公告发布成功', 'success');
                bootstrap.Modal.getInstance(document.getElementById('announcementModal')).hide();
                await this.loadAnnouncements();
            } else {
                this.showToast('错误', data.message || '保存失败', 'danger');
            }
        } catch (error) {
            console.error('保存公告失败:', error);
            this.showToast('错误', '保存公告失败', 'danger');
        }
    }
    
    // 编辑公告
    async editAnnouncement(id) {
        // 权限检查：只有管理员可以编辑公告
        if (!this.currentUser || this.currentUser.role !== 'admin') {
            this.showToast('错误', '只有管理员可以编辑公告', 'danger');
            return;
        }
        
        try {
            const response = await fetch(`${this.apiBaseUrl}/announcements/${id}`);
            const data = await response.json();
            
            if (data.success && data.data) {
                const ann = data.data;
                document.getElementById('announcementId').value = ann.id;
                document.getElementById('announcementTitle').value = ann.title;
                document.getElementById('announcementContent').value = ann.content;
                document.getElementById('announcementType').value = ann.type;
                document.getElementById('announcementPriority').value = ann.priority;
                document.getElementById('announcementPinned').checked = ann.is_pinned;
                document.getElementById('announcementModalTitle').textContent = '编辑公告';
                
                const modal = new bootstrap.Modal(document.getElementById('announcementModal'));
                modal.show();
            }
        } catch (error) {
            console.error('获取公告失败:', error);
            this.showToast('错误', '获取公告失败', 'danger');
        }
    }
    
    // 删除公告
    async deleteAnnouncement(id) {
        // 权限检查：只有管理员可以删除公告
        if (!this.currentUser || this.currentUser.role !== 'admin') {
            this.showToast('错误', '只有管理员可以删除公告', 'danger');
            return;
        }
        
        if (!confirm('确定要删除这条公告吗？')) return;
        
        try {
            const response = await fetch(`${this.apiBaseUrl}/announcements/${id}`, {
                method: 'DELETE'
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast('成功', '公告已删除', 'success');
                await this.loadAnnouncements();
            } else {
                this.showToast('错误', data.message || '删除失败', 'danger');
            }
        } catch (error) {
            console.error('删除公告失败:', error);
            this.showToast('错误', '删除公告失败', 'danger');
        }
    }
    
    // HTML转义
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
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
                } catch (error) {
                    console.warn('图表更新失败，使用备用方案:', error);
                    this.showKlineDataTable(klineData, symbol);
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

    // 从OKX API获取K线数据（通过后端代理）
    async fetchKlineData(symbol, timeframe) {
        // 根据时间周期计算需要的数据量
        let limit = 100;
        const now = Date.now();
        
        // 计算7天前的时间戳
        const sevenDaysAgo = now - (7 * 24 * 60 * 60 * 1000);
        
        // 根据时间周期调整数据量
        switch(timeframe) {
            case '1m':
                limit = 4320; // 7天 * 24小时 * 60分钟
                break;
            case '5m':
                limit = 2016; // 7天 * 24小时 * 12
                break;
            case '15m':
                limit = 672; // 7天 * 24小时 * 4
                break;
            case '1H':
                limit = 168; // 7天 * 24小时
                break;
            case '4H':
                limit = 42; // 7天 * 6
                break;
            case '1D':
                limit = 7; // 7天
                break;
        }
        
        // 使用后端代理，避免 CORS 问题
        const url = `${this.apiBaseUrl}/market/candles?instId=${symbol}&bar=${timeframe}&limit=${limit}`;
        
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
            .filter(item => item.time >= sevenDaysAgo) // 只保留最近7天的数据
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
    async loadCustomersData(page = 1, pageSize = 10) {
        try {
            const params = new URLSearchParams({
                page: page,
                page_size: pageSize
            });
            
            const response = await this.apiRequest(`${this.apiBaseUrl}/customers?${params}`);
            if (response && response.ok) {
                const data = await response.json();
                
                
                // 检查数据结构
                if (Array.isArray(data.data)) {
                    // 直接返回数组的情况
                    this.renderCustomersTable(data.data, data.pagination);
                } else if (data.data && Array.isArray(data.data.customers)) {
                    // 嵌套结构的情况 - 从data中提取分页信息
                    const pagination = {
                        current_page: data.data.page || 1,
                        total_pages: Math.ceil((data.data.total || 0) / (data.data.page_size || 10)),
                        total_count: data.data.total || 0,
                        page_size: data.data.page_size || 10
                    };
                    this.renderCustomersTable(data.data.customers, pagination);
                } else {
                    console.error('客户数据格式错误:', data.data);
                    this.renderCustomersTable([], null);
                }
            } else {
                console.error('加载客户数据失败:', response.statusText);
                this.renderCustomersTable([], null);
            }
        } catch (error) {
            console.error('加载客户数据失败:', error);
            this.renderCustomersTable([], null);
        }
    }

    // 渲染客户表格
    renderCustomersTable(customers, pagination = null) {
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
            this.renderCustomersPagination(null);
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
                        <button class="btn btn-sm btn-outline-success update-asset-btn" data-customer-uid="${customer.customer_uid}" title="更新资产">
                            <i class="bi bi-arrow-clockwise"></i>
                        </button>
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
        // 为资产更新按钮添加事件监听器
        this.attachAssetUpdateListeners();
        
        // 渲染分页
        this.renderCustomersPagination(pagination);
        
        // 渲染分页信息
        this.renderCustomersPaginationInfo(pagination);
    }

    // 渲染客户分页
    renderCustomersPagination(pagination) {
        const paginationContainer = document.getElementById('customersPagination');
        if (!paginationContainer) {
            console.warn('未找到 customersPagination 元素');
            return;
        }


        if (!pagination) {
            paginationContainer.innerHTML = '';
            return;
        }

        const { current_page, total_pages, total_count, page_size } = pagination;
        
        if (total_pages <= 1) {
            paginationContainer.innerHTML = '';
            return;
        }

        let paginationHtml = '';
        
        // 上一页按钮
        if (current_page > 1) {
            paginationHtml += `
                <li class="page-item">
                    <a class="page-link" href="#" data-page="${current_page - 1}">
                        <i class="bi bi-chevron-left"></i> 上一页
                    </a>
                </li>
            `;
        } else {
            paginationHtml += `
                <li class="page-item disabled">
                    <span class="page-link">
                        <i class="bi bi-chevron-left"></i> 上一页
                    </span>
                </li>
            `;
        }

        // 页码按钮
        const startPage = Math.max(1, current_page - 2);
        const endPage = Math.min(total_pages, current_page + 2);

        if (startPage > 1) {
            paginationHtml += `
                <li class="page-item">
                    <a class="page-link" href="#" data-page="1">1</a>
                </li>
            `;
            if (startPage > 2) {
                paginationHtml += `
                    <li class="page-item disabled">
                        <span class="page-link">...</span>
                    </li>
                `;
            }
        }

        for (let i = startPage; i <= endPage; i++) {
            if (i === current_page) {
                paginationHtml += `
                    <li class="page-item active">
                        <span class="page-link">${i}</span>
                    </li>
                `;
            } else {
                paginationHtml += `
                    <li class="page-item">
                        <a class="page-link" href="#" data-page="${i}">${i}</a>
                    </li>
                `;
            }
        }

        if (endPage < total_pages) {
            if (endPage < total_pages - 1) {
                paginationHtml += `
                    <li class="page-item disabled">
                        <span class="page-link">...</span>
                    </li>
                `;
            }
            paginationHtml += `
                <li class="page-item">
                    <a class="page-link" href="#" data-page="${total_pages}">${total_pages}</a>
                </li>
            `;
        }

        // 下一页按钮
        if (current_page < total_pages) {
            paginationHtml += `
                <li class="page-item">
                    <a class="page-link" href="#" data-page="${current_page + 1}">
                        下一页 <i class="bi bi-chevron-right"></i>
                    </a>
                </li>
            `;
        } else {
            paginationHtml += `
                <li class="page-item disabled">
                    <span class="page-link">
                        下一页 <i class="bi bi-chevron-right"></i>
                    </span>
                </li>
            `;
        }

        paginationContainer.innerHTML = paginationHtml;

        // 添加分页事件监听器
        paginationContainer.addEventListener('click', (e) => {
            e.preventDefault();
            const pageLink = e.target.closest('a[data-page]');
            if (pageLink) {
                const page = parseInt(pageLink.dataset.page);
                
                // 检查是否有搜索或筛选条件
                const searchTerm = document.getElementById('customerSearch')?.value.trim() || '';
                const currentFilter = document.querySelector('input[name="customerFilter"]:checked')?.value || 'all';
                
                if (searchTerm || currentFilter !== 'all') {
                    // 有搜索或筛选条件，使用带参数的加载函数
                    this.loadCustomersDataWithParams(searchTerm, currentFilter, page);
                } else {
                    // 没有搜索或筛选条件，使用普通加载函数
                    this.loadCustomersData(page);
                }
            }
        });
    }

    // 渲染客户分页信息
    renderCustomersPaginationInfo(pagination) {
        const infoContainer = document.getElementById('customersPaginationInfo');
        if (!infoContainer) {
            console.warn('未找到 customersPaginationInfo 元素');
            return;
        }

        if (!pagination) {
            infoContainer.innerHTML = '';
            return;
        }

        const { current_page, total_pages, total_count, page_size } = pagination;
        const startItem = (current_page - 1) * page_size + 1;
        const endItem = Math.min(current_page * page_size, total_count);

        infoContainer.innerHTML = `
            显示第 ${startItem}-${endItem} 条，共 ${total_count} 条记录
        `;
    }

    // 设置客户页面大小
    setCustomersPageSize(pageSize) {
        // 更新页面大小按钮状态
        document.querySelectorAll('#customersPageSize10, #customersPageSize20, #customersPageSize50').forEach(btn => {
            btn.classList.remove('active');
        });
        
        const activeBtn = document.getElementById(`customersPageSize${pageSize}`);
        if (activeBtn) {
            activeBtn.classList.add('active');
        }
        
        // 重新加载数据
        this.loadCustomersData(1, pageSize);
    }

    // 客户管理相关函数
    async editCustomer(customerUid) {
        try {
            // 获取客户详细信息（使用apiRequest自动包含认证Token）
            const response = await this.apiRequest(`${this.apiBaseUrl}/customers/${customerUid}`);
            if (!response || !response.ok) {
                const errorMsg = response ? (response.statusText || '获取客户信息失败') : '网络错误，请检查连接';
                this.showToast('错误', errorMsg, 'danger');
                return;
            }
            
            const result = await response.json();
            if (result.success !== 200) {
                this.showToast('错误', result.message || '获取客户信息失败', 'danger');
                return;
            }
            
            const customer = result.data;
            
            // 填充表单数据
            document.getElementById('editCustomerName').value = customer.name || '';
            document.getElementById('editCustomerUid').value = customer.customer_uid || '';
            document.getElementById('editApiKey').value = customer.api_key || '';
            document.getElementById('editApiSecret').value = customer.api_secret || '';
            document.getElementById('editPassphrase').value = customer.passphrase || '';
            document.getElementById('editLeverage').value = customer.leverage || 1;
            document.getElementById('editInitAsset').value = customer.init_asset || 0;
            document.getElementById('editTradingAsset').value = customer.trading_asset || 0;
            document.getElementById('editEnabled').checked = customer.enabled || false;
            document.getElementById('editStopLossEnabled').checked = customer.stop_loss_enabled || false;
            
            // 显示模态框
            const modal = new bootstrap.Modal(document.getElementById('editCustomerModal'));
            modal.show();
            
        } catch (error) {
            console.error('编辑客户失败:', error);
            this.showToast('错误', '编辑客户失败，请检查网络连接', 'danger');
        }
    }
    
    // 保存编辑的客户
    async saveEditCustomer() {
        try {
            const customerUid = document.getElementById('editCustomerUid').value;
            if (!customerUid) {
                this.showToast('错误', '客户UID不能为空', 'danger');
                return;
            }
            
            const formData = {
                name: document.getElementById('editCustomerName').value,
                api_key: document.getElementById('editApiKey').value,
                api_secret: document.getElementById('editApiSecret').value,
                passphrase: document.getElementById('editPassphrase').value,
                leverage: parseInt(document.getElementById('editLeverage').value) || 1,
                init_asset: parseFloat(document.getElementById('editInitAsset').value) || 0,
                trading_asset: parseFloat(document.getElementById('editTradingAsset').value) || 0,
                enabled: document.getElementById('editEnabled').checked,
                stop_loss_enabled: document.getElementById('editStopLossEnabled').checked
            };
            
            // 验证必填字段
            if (!formData.name || !formData.api_key || !formData.api_secret || !formData.passphrase) {
                this.showToast('错误', '请填写所有必填字段', 'danger');
                return;
            }
            
            const response = await this.apiRequest(`${this.apiBaseUrl}/customers/${customerUid}`, {
                method: 'PUT',
                body: JSON.stringify(formData)
            });
            
            if (response && response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.showToast('成功', '客户信息更新成功', 'success');
                    
                    // 关闭模态框
                    const modal = bootstrap.Modal.getInstance(document.getElementById('editCustomerModal'));
                    modal.hide();
                    
                    // 重新加载客户列表
                    this.loadCustomersData();
                } else {
                    this.showToast('错误', result.message || '更新客户信息失败', 'danger');
                }
            } else {
                const errorMsg = response ? (response.statusText || '更新失败') : '网络错误，请检查连接';
                try {
                    if (response) {
                        const errorText = await response.text();
                        try {
                            const errorData = JSON.parse(errorText);
                            this.showToast('错误', errorData.message || errorMsg, 'danger');
                        } catch (e) {
                            this.showToast('错误', errorText || errorMsg, 'danger');
                        }
                    } else {
                        this.showToast('错误', errorMsg, 'danger');
                    }
                } catch (e) {
                    console.error('更新客户信息失败:', e);
                    this.showToast('错误', errorMsg, 'danger');
                }
            }
            
        } catch (error) {
            console.error('保存编辑客户失败:', error);
            this.showToast('错误', '保存客户信息失败，请检查网络连接', 'danger');
        }
    }

    // 为资产更新按钮添加事件监听器
    attachAssetUpdateListeners() {
        // 为每个客户的资产更新按钮添加事件监听器
        const updateButtons = document.querySelectorAll('.update-asset-btn');
        updateButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                const customerUid = e.target.closest('.update-asset-btn').getAttribute('data-customer-uid');
                this.forceUpdateCustomerAsset(customerUid);
            });
        });
    }

    // 强制更新所有客户资产
    async forceUpdateAllCustomerAssets() {
        // 防止重复点击
        if (this.isUpdatingAssets) {
            this.showToast('提示', '正在更新中，请稍候...', 'info');
            return;
        }
        
        try {
            this.isUpdatingAssets = true;
            this.showToast('提示', '正在更新所有客户资产...', 'info');
            
            const isDemo = this.getIsDemo();
            const response = await this.apiRequest(`${this.apiBaseUrl}/force_update_customer_assets`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    is_demo: isDemo
                })
            });

            if (response.ok) {
                const result = await response.json();
                this.showToast('成功', '所有客户资产更新完成', 'success');
                // 刷新客户列表
                await this.loadCustomersData();
            } else {
                const error = await response.json();
                this.showToast('错误', `更新失败: ${error.message}`, 'danger');
            }
        } catch (error) {
            console.error('更新客户资产失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        } finally {
            this.isUpdatingAssets = false;
        }
    }

    // 强制更新指定客户资产
    async forceUpdateCustomerAsset(customerUid) {
        // 防止重复点击
        if (this.isUpdatingAssets) {
            this.showToast('提示', '正在更新中，请稍候...', 'info');
            return;
        }
        
        try {
            this.isUpdatingAssets = true;
            this.showToast('提示', `正在更新客户 ${customerUid} 的资产...`, 'info');
            
            const isDemo = this.getIsDemo();
            const response = await this.apiRequest(`${this.apiBaseUrl}/force_update_customer_assets`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    customer_uid: customerUid,
                    is_demo: isDemo
                })
            });

            if (response.ok) {
                const result = await response.json();
                this.showToast('成功', `客户 ${customerUid} 资产更新完成`, 'success');
                // 刷新客户列表
                await this.loadCustomersData();
            } else {
                const error = await response.json();
                this.showToast('错误', `更新失败: ${error.message}`, 'danger');
            }
        } catch (error) {
            console.error('更新客户资产失败:', error);
            this.showToast('错误', '网络请求失败', 'danger');
        } finally {
            this.isUpdatingAssets = false;
        }
    }
    async viewCustomerDetails(customerUid) {
        try {
            // 获取客户详情（使用apiRequest自动包含认证Token）
            const response = await this.apiRequest(`${this.apiBaseUrl}/customers/${customerUid}`);
            if (response && response.ok) {
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

    async toggleCustomerStatus(customerUid) {
        try {
            // 获取当前客户信息（使用apiRequest自动包含认证Token）
            const response = await this.apiRequest(`${this.apiBaseUrl}/customers/${customerUid}`);
            if (!response || !response.ok) {
                this.showToast('错误', '获取客户信息失败', 'danger');
                return;
            }
            
            const result = await response.json();
            if (result.success !== 200) {
                this.showToast('错误', result.message || '获取客户信息失败', 'danger');
                return;
            }
            
            const customer = result.data;
            const newStatus = !customer.enabled;
            const action = newStatus ? '启用' : '禁用';
            
            if (!confirm(`确定要${action}客户 "${customer.name || customer.customer_uid}" 吗？`)) {
                return;
            }
            
            // 更新客户状态（使用apiRequest自动包含认证Token）
            const updateResponse = await this.apiRequest(`${this.apiBaseUrl}/customers/${customerUid}`, {
                method: 'PUT',
                body: JSON.stringify({
                    enabled: newStatus
                })
            });
            
            if (updateResponse && updateResponse.ok) {
                const updateResult = await updateResponse.json();
                if (updateResult.success === 200) {
                    this.showToast('成功', `客户${action}成功`, 'success');
                    // 重新加载客户列表
                    this.loadCustomersData();
                } else {
                    this.showToast('错误', updateResult.message || `${action}客户失败`, 'danger');
                }
            } else {
                this.showToast('错误', `${action}客户失败`, 'danger');
            }
            
        } catch (error) {
            console.error('切换客户状态失败:', error);
            this.showToast('错误', '切换客户状态失败，请检查网络连接', 'danger');
        }
    }

    async deleteCustomer(customerUid) {
        try {
            // 获取客户信息用于确认（使用apiRequest自动包含认证Token）
            const response = await this.apiRequest(`${this.apiBaseUrl}/customers/${customerUid}`);
            if (!response || !response.ok) {
                this.showToast('错误', '获取客户信息失败', 'danger');
                return;
            }
            
            const result = await response.json();
            if (result.success !== 200) {
                this.showToast('错误', result.message || '获取客户信息失败', 'danger');
                return;
            }
            
            const customer = result.data;
            const customerName = customer.name || customer.customer_uid;
            
            if (!confirm(`确定要删除客户 "${customerName}" 吗？\n\n此操作将：\n- 删除客户的所有数据\n- 删除相关的交易记录\n- 删除持仓信息\n- 此操作不可恢复！`)) {
                return;
            }
            
            // 执行删除操作（使用apiRequest自动包含认证Token）
            const deleteResponse = await this.apiRequest(`${this.apiBaseUrl}/customers/${customerUid}`, {
                method: 'DELETE'
            });
            
            if (deleteResponse && deleteResponse.ok) {
                const deleteResult = await deleteResponse.json();
                if (deleteResult.success === 200) {
                    this.showToast('成功', '客户删除成功', 'success');
                    // 重新加载客户列表
                    this.loadCustomersData();
                } else {
                    this.showToast('错误', deleteResult.message || '删除客户失败', 'danger');
                }
            } else {
                const errorMsg = deleteResponse ? `删除客户失败: ${deleteResponse.status}` : '删除客户失败: 网络错误';
                console.error('删除客户失败:', errorMsg);
                this.showToast('错误', errorMsg, 'danger');
            }
            
        } catch (error) {
            console.error('删除客户失败:', error);
            this.showToast('错误', '删除客户失败，请检查网络连接', 'danger');
        }
    }

    // 信号源管理相关函数
    async editSignalSource(sourceUid) {
        try {
            // 获取信号源详情（使用apiRequest自动包含认证Token）
            const response = await this.apiRequest(`${this.apiBaseUrl}/signal_sources/${sourceUid}`);
            if (response && response.ok) {
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

    async viewSignalSourceDetails(sourceUid) {
        try {
            // 获取信号源详细信息（使用apiRequest自动包含认证Token）
            const response = await this.apiRequest(`${this.apiBaseUrl}/signal_sources/${sourceUid}`);
            if (!response || !response.ok) {
                this.showToast('错误', '获取信号源信息失败', 'danger');
                return;
            }
            
            const result = await response.json();
            if (result.success !== 200) {
                this.showToast('错误', result.message || '获取信号源信息失败', 'danger');
                return;
            }
            
            const source = result.data;
            
            // 填充详情数据
            this.populateSignalSourceDetails(source);
            
            // 显示模态框
            const modal = new bootstrap.Modal(document.getElementById('signalSourceDetailModal'));
            modal.show();
            
        } catch (error) {
            console.error('查看信号源详情失败:', error);
            this.showToast('错误', '查看信号源详情失败，请检查网络连接', 'danger');
        }
    }
    
    // 填充信号源详情数据
    populateSignalSourceDetails(source) {
        // 基本信息
        document.getElementById('signalSourceDetailUid').textContent = source.source_uid || '-';
        document.getElementById('signalSourceDetailName').textContent = source.name || '-';
        document.getElementById('signalSourceDetailExchange').textContent = source.exchange || 'OKX';
        document.getElementById('signalSourceDetailInitAssets').textContent = this.formatNumber(source.init_assets || 0);
        document.getElementById('signalSourceDetailCurrentAsset').textContent = this.formatNumber(source.current_asset || 0);
        document.getElementById('signalSourceDetailLeverage').textContent = source.leverage || 1;
        
        // 配置信息
        document.getElementById('signalSourceDetailStopLossPercent').textContent = 
            source.stop_loss_percent ? `${source.stop_loss_percent}%` : '-';
        document.getElementById('signalSourceDetailStopLossEnabled').innerHTML = 
            source.stop_loss_enabled ? '<span class="badge bg-success">已启用</span>' : '<span class="badge bg-secondary">未启用</span>';
        document.getElementById('signalSourceDetailStatus').innerHTML = 
            source.enabled ? '<span class="badge bg-success">启用</span>' : '<span class="badge bg-secondary">禁用</span>';
        document.getElementById('signalSourceDetailIsDemo').textContent = source.is_demo ? '模拟账户' : '实盘账户';
        document.getElementById('signalSourceDetailCreatedAt').textContent = this.formatDateTime(source.created_at) || '-';
        document.getElementById('signalSourceDetailLastAssetCheck').textContent = this.formatDateTime(source.last_asset_check) || '-';
    }

    async toggleSignalSourceStatus(sourceUid) {
        try {
            // 获取当前信号源信息（使用apiRequest自动包含认证Token）
            const response = await this.apiRequest(`${this.apiBaseUrl}/signal_sources/${sourceUid}`);
            if (!response || !response.ok) {
                this.showToast('错误', '获取信号源信息失败', 'danger');
                return;
            }
            
            const result = await response.json();
            if (result.success !== 200) {
                this.showToast('错误', result.message || '获取信号源信息失败', 'danger');
                return;
            }
            
            const signalSource = result.data;
            const newStatus = !signalSource.enabled;
            const action = newStatus ? '启用' : '禁用';
            const sourceName = signalSource.name || signalSource.source_uid;
            
            if (!confirm(`确定要${action}信号源 "${sourceName}" 吗？`)) {
                return;
            }
            
            // 更新状态（使用apiRequest自动包含认证Token）
            const updateResponse = await this.apiRequest(`${this.apiBaseUrl}/signal_sources/${sourceUid}`, {
                method: 'PUT',
                body: JSON.stringify({
                    enabled: newStatus
                })
            });
            
            if (updateResponse && updateResponse.ok) {
                const updateResult = await updateResponse.json();
                if (updateResult.success === 200) {
                    this.showToast('成功', `信号源${action}成功`, 'success');
                    // 刷新数据
                    this.loadSignalSourcesData();
                } else {
                    this.showToast('错误', updateResult.message || `${action}信号源失败`, 'danger');
                }
            } else {
                this.showToast('错误', `${action}信号源失败`, 'danger');
            }
            
        } catch (error) {
            console.error('切换信号源状态失败:', error);
            this.showToast('错误', '切换信号源状态失败，请检查网络连接', 'danger');
        }
    }

    async deleteSignalSource(sourceUid) {
        try {
            // 获取信号源信息用于确认（使用apiRequest自动包含认证Token）
            const response = await this.apiRequest(`${this.apiBaseUrl}/signal_sources/${sourceUid}`);
            if (!response || !response.ok) {
                this.showToast('错误', '获取信号源信息失败', 'danger');
                return;
            }
            
            const result = await response.json();
            if (result.success !== 200) {
                this.showToast('错误', result.message || '获取信号源信息失败', 'danger');
                return;
            }
            
            const source = result.data;
            const sourceName = source.name || source.source_uid;
            
            if (!confirm(`确定要删除信号源 "${sourceName}" 吗？\n\n此操作将：\n- 删除信号源的所有数据\n- 删除相关的交易记录\n- 删除持仓信息\n- 此操作不可恢复！`)) {
                return;
            }
            
            // 执行删除操作（使用apiRequest自动包含认证Token）
            const deleteResponse = await this.apiRequest(`${this.apiBaseUrl}/signal_sources/${sourceUid}`, {
                method: 'DELETE'
            });
            
            if (deleteResponse && deleteResponse.ok) {
                const deleteResult = await deleteResponse.json();
                if (deleteResult.success === 200) {
                    this.showToast('成功', '信号源删除成功', 'success');
                    // 刷新数据
                    this.loadSignalSourcesData();
                } else {
                    this.showToast('错误', deleteResult.message || '删除信号源失败', 'danger');
                }
            } else {
                const errorMsg = deleteResponse ? `删除信号源失败: ${deleteResponse.status}` : '删除信号源失败: 网络错误';
                console.error('删除信号源失败:', errorMsg);
                this.showToast('错误', errorMsg, 'danger');
            }
            
        } catch (error) {
            console.error('删除信号源失败:', error);
            this.showToast('错误', '删除信号源失败，请检查网络连接', 'danger');
        }
    }

    // 策略管理相关函数
    async editStrategy(strategyUid) {

        try {
            // 获取策略详情（使用apiRequest自动包含认证Token）
            const response = await this.apiRequest(`${this.apiBaseUrl}/strategies/${strategyUid}`);
            if (response && response.ok) {
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

    async viewStrategyDetails(strategyId) {
        try {
            this.showToast('加载中', '正在获取策略详情...', 'info');
            
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/strategies/${strategyId}`);
            
            if (response && response.ok) {
                const result = await response.json();
                
                if (result.success === 200) {
                    this.showStrategyDetailModal(result.data);
                } else {
                    this.showToast('错误', result.message || '获取策略详情失败', 'error');
                }
            } else {
                this.showToast('错误', '获取策略详情失败', 'error');
            }
        } catch (error) {
            console.error('获取策略详情失败:', error);
            this.showToast('错误', '获取策略详情失败: ' + error.message, 'error');
        }
    }
    
    showStrategyDetailModal(strategy) {
        // 填充策略详情数据
        document.getElementById('strategyDetailUid').textContent = strategy.strategy_uid || '-';
        document.getElementById('strategyDetailName').textContent = strategy.name || '-';
        document.getElementById('strategyDetailDescription').textContent = strategy.description || '-';
        document.getElementById('strategyDetailType').textContent = '市价单策略';
        document.getElementById('strategyDetailStatus').textContent = strategy.enabled ? '启用' : '禁用';
        document.getElementById('strategyDetailIsDemo').textContent = strategy.is_demo ? '演示账户' : '实盘账户';
        
        // 填充更多详情 - 市价单策略特有字段
        document.getElementById('strategyDetailTrader').textContent = strategy.signal_sources || '-';
        document.getElementById('strategyDetailSymbol').textContent = strategy.rules || '-';
        document.getElementById('strategyDetailPosSide').textContent = strategy.signal_source_count || '0';
        document.getElementById('strategyDetailFollowValue').textContent = strategy.rule_count || '0';
        document.getElementById('strategyDetailLeverage').textContent = '-';
        document.getElementById('strategyDetailMaxLeverage').textContent = '-';
        document.getElementById('strategyDetailMaxOrders').textContent = '-';
        
        // 填充客户列表 - 市价单策略的客户关联
        const customerList = document.getElementById('strategyDetailCustomers');
        if (strategy.customers && strategy.customers.length > 0) {
            customerList.innerHTML = strategy.customers.map(customer => `
                <div class="badge bg-primary me-1 mb-1">
                    ${customer.customer_name || customer.customer_uid}
                    ${customer.enabled ? '' : ' (禁用)'}
                </div>
            `).join('');
        } else {
            customerList.innerHTML = '<span class="text-muted">无关联客户</span>';
        }
        
        // 显示模态框
        const modal = new bootstrap.Modal(document.getElementById('strategyDetailModal'));
        modal.show();
    }

    async toggleStrategyStatus(strategyUid) {

        try {
            // 获取当前策略信息（使用apiRequest自动包含认证Token）
            const response = await this.apiRequest(`${this.apiBaseUrl}/strategies/${strategyUid}`);
            if (response && response.ok) {
                const data = await response.json();
                const strategy = data.data;
                const newStatus = !strategy.enabled;
                
                // 更新状态（使用apiRequest自动包含认证Token）
                const updateResponse = await this.apiRequest(`${this.apiBaseUrl}/strategies/${strategyUid}`, {
                    method: 'PUT',
                    body: JSON.stringify({
                        enabled: newStatus
                    })
                });
                
                if (updateResponse && updateResponse.ok) {
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
                // 使用apiRequest自动包含认证Token
                const response = await this.apiRequest(`${this.apiBaseUrl}/strategies/${strategyUid}`, {
                    method: 'DELETE'
                });
                
                if (response && response.ok) {
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
            // 获取规则详情（使用apiRequest自动包含认证Token）
            const response = await this.apiRequest(`${this.apiBaseUrl}/rules/${ruleUid}`);
            if (response && response.ok) {
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

    async viewRuleDetails(ruleUid) {
        try {
            // 获取规则详情（使用apiRequest自动包含认证Token）
            const response = await this.apiRequest(`${this.apiBaseUrl}/rules/${ruleUid}`);
            if (response && response.ok) {
                const data = await response.json();
                const rule = data.data;
                
                // 显示规则详情的模态框
                this.showRuleDetailsModal(rule);
            } else {
                this.showToast('错误', '获取规则详情失败', 'danger');
            }
        } catch (error) {
            console.error('获取规则详情失败:', error);
            this.showToast('错误', '获取规则详情失败', 'danger');
        }
    }

    showRuleDetailsModal(rule) {
        // 创建规则详情模态框
        const modalHtml = `
            <div class="modal fade" id="ruleDetailsModal" tabindex="-1" aria-labelledby="ruleDetailsModalLabel" aria-hidden="true">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="ruleDetailsModalLabel">规则详情</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <div class="row">
                                <div class="col-md-6">
                                    <h6>基本信息</h6>
                                    <table class="table table-sm">
                                        <tr><td><strong>规则ID:</strong></td><td>${rule.rule_uid}</td></tr>
                                        <tr><td><strong>规则名称:</strong></td><td>${rule.name || '未设置'}</td></tr>
                                        <tr><td><strong>策略名称:</strong></td><td>${rule.strategy_name || '未关联'}</td></tr>
                                        <tr><td><strong>策略类型:</strong></td><td>${rule.strategy_type || '未设置'}</td></tr>
                                        <tr><td><strong>状态:</strong></td><td>
                                            <span class="badge bg-${rule.enabled ? 'success' : 'secondary'}">
                                                ${rule.enabled ? '启用' : '禁用'}
                                            </span>
                                        </td></tr>
                                    </table>
                                </div>
                                <div class="col-md-6">
                                    <h6>交易参数</h6>
                                    <table class="table table-sm">
                                        <tr><td><strong>仓位比例:</strong></td><td>${rule.position_ratio || '未设置'}</td></tr>
                                        <tr><td><strong>最大杠杆:</strong></td><td>${rule.max_leverage || '未设置'}</td></tr>
                                        <tr><td><strong>创建时间:</strong></td><td>${rule.created_at || '未知'}</td></tr>
                                        <tr><td><strong>更新时间:</strong></td><td>${rule.updated_at || '未知'}</td></tr>
                                    </table>
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                            <button type="button" class="btn btn-primary" onclick="app.editRule('${rule.rule_uid}')" data-bs-dismiss="modal">编辑规则</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // 移除已存在的模态框
        const existingModal = document.getElementById('ruleDetailsModal');
        if (existingModal) {
            existingModal.remove();
        }
        
        // 添加新的模态框到页面
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // 显示模态框
        const modal = new bootstrap.Modal(document.getElementById('ruleDetailsModal'));
        modal.show();
    }

    async toggleRuleStatus(ruleUid) {

        try {
            // 获取当前规则信息（使用apiRequest自动包含认证Token）
            const response = await this.apiRequest(`${this.apiBaseUrl}/rules/${ruleUid}`);
            if (response && response.ok) {
                const data = await response.json();
                const rule = data.data;
                const newStatus = !rule.enabled;
                
                // 更新状态（使用apiRequest自动包含认证Token）
                const updateResponse = await this.apiRequest(`${this.apiBaseUrl}/rules/${ruleUid}`, {
                    method: 'PUT',
                    body: JSON.stringify({
                        enabled: newStatus
                    })
                });
                
                if (updateResponse && updateResponse.ok) {
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
                // 使用apiRequest自动包含认证Token
                const response = await this.apiRequest(`${this.apiBaseUrl}/rules/${ruleUid}`, {
                    method: 'DELETE'
                });
                
                if (response && response.ok) {
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
    async editTrade(tradeUid) {
        try {
            // 获取交易详细信息（使用apiRequest自动包含认证Token）
            const response = await this.apiRequest(`${this.apiBaseUrl}/trades/${tradeUid}`);
            if (!response || !response.ok) {
                this.showToast('错误', '获取交易信息失败', 'danger');
                return;
            }
            
            const result = await response.json();
            if (result.success !== 200) {
                this.showToast('错误', result.message || '获取交易信息失败', 'danger');
                return;
            }
            
            const trade = result.data;
            
            // 填充表单数据
            document.getElementById('editTradeUid').value = trade.trade_uid || '';
            document.getElementById('editTradeCustomerUid').value = trade.customer_uid || '';
            document.getElementById('editSymbol').value = trade.symbol || '';
            document.getElementById('editDirection').value = trade.direction || 'buy';
            document.getElementById('editPosSide').value = trade.pos_side || 'long';
            document.getElementById('editVolume').value = trade.volume_contract || trade.sz || 0;
            document.getElementById('editOpenPx').value = trade.open_px || 0;
            document.getElementById('editStatus').value = trade.status || 'open';
            
            // 显示模态框
            const modal = new bootstrap.Modal(document.getElementById('editTradeModal'));
            modal.show();
            
        } catch (error) {
            console.error('编辑交易失败:', error);
            this.showToast('错误', '编辑交易失败，请检查网络连接', 'danger');
        }
    }
    
    // 保存编辑的交易
    async saveEditTrade() {
        try {
            const tradeUid = document.getElementById('editTradeUid').value;
            if (!tradeUid) {
                this.showToast('错误', '交易ID不能为空', 'danger');
                return;
            }
            
            const formData = {
                symbol: document.getElementById('editSymbol').value,
                direction: document.getElementById('editDirection').value,
                pos_side: document.getElementById('editPosSide').value,
                volume_contract: parseFloat(document.getElementById('editVolume').value) || 0,
                open_px: parseFloat(document.getElementById('editOpenPx').value) || 0,
                status: document.getElementById('editStatus').value
            };
            
            // 验证必填字段
            if (!formData.symbol || !formData.direction || !formData.pos_side) {
                this.showToast('错误', '请填写所有必填字段', 'danger');
                return;
            }
            
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/trades/${tradeUid}`, {
                method: 'PUT',
                body: JSON.stringify(formData)
            });
            
            if (response && response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.showToast('成功', '交易记录更新成功', 'success');
                    
                    // 关闭模态框
                    const modal = bootstrap.Modal.getInstance(document.getElementById('editTradeModal'));
                    modal.hide();
                    
                    // 重新加载交易列表
                    this.loadTradesData();
                } else {
                    this.showToast('错误', result.message || '更新交易记录失败', 'danger');
                }
            } else {
                const errorMsg = response ? `更新交易记录失败: ${response.status}` : '更新交易记录失败: 网络错误';
                console.error('更新交易记录失败:', errorMsg);
                this.showToast('错误', errorMsg, 'danger');
            }
            
        } catch (error) {
            console.error('保存编辑交易失败:', error);
            this.showToast('错误', '保存交易记录失败，请检查网络连接', 'danger');
        }
    }

    async deleteTrade(tradeUid) {
        try {
            // 获取交易信息用于确认（使用apiRequest自动包含认证Token）
            const response = await this.apiRequest(`${this.apiBaseUrl}/trades/${tradeUid}`);
            if (!response || !response.ok) {
                this.showToast('错误', '获取交易信息失败', 'danger');
                return;
            }
            
            const result = await response.json();
            if (result.success !== 200) {
                this.showToast('错误', result.message || '获取交易信息失败', 'danger');
                return;
            }
            
            const trade = result.data;
            const tradeInfo = `${trade.symbol} - ${trade.direction === 'buy' ? '买入' : '卖出'} - ${trade.volume_contract || trade.sz}手`;
            
            if (!confirm(`确定要删除交易记录吗？\n\n交易信息: ${tradeInfo}\n\n此操作将：\n- 删除交易记录\n- 删除相关的持仓信息\n- 此操作不可恢复！`)) {
                return;
            }
            
            // 执行删除操作（使用apiRequest自动包含认证Token）
            const deleteResponse = await this.apiRequest(`${this.apiBaseUrl}/trades/${tradeUid}`, {
                method: 'DELETE'
            });
            
            if (deleteResponse && deleteResponse.ok) {
                const deleteResult = await deleteResponse.json();
                if (deleteResult.success === 200) {
                    this.showToast('成功', '交易记录删除成功', 'success');
                    // 重新加载交易列表
                    this.loadTradesData();
                } else {
                    this.showToast('错误', deleteResult.message || '删除交易记录失败', 'danger');
                }
            } else {
                const errorMsg = deleteResponse ? `删除交易记录失败: ${deleteResponse.status}` : '删除交易记录失败: 网络错误';
                console.error('删除交易记录失败:', errorMsg);
                this.showToast('错误', errorMsg, 'danger');
            }
            
        } catch (error) {
            console.error('删除交易记录失败:', error);
            this.showToast('错误', '删除交易记录失败，请检查网络连接', 'danger');
        }
    }

    // 系统操作函数
    async reloadRules() {
        try {
            this.showToast('信息', '正在重新加载规则...', 'info');
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/reload/rules`, { method: 'POST' });
            if (response && response.ok) {
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
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/reload/customers`, { method: 'POST' });
            if (response && response.ok) {
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
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/reload/signal_sources`, { method: 'POST' });
            if (response && response.ok) {
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
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/reload/trade_service`, { method: 'POST' });
            if (response && response.ok) {
                this.showToast('成功', '交易服务重新加载成功', 'success');
            } else {
                throw new Error('重新加载失败');
            }
        } catch (error) {
            console.error('重新加载交易服务失败:', error);
            this.showToast('错误', '重新加载交易服务失败', 'danger');
        }
    }

    // 应用交易记录页面权限控制
    applyTradesPagePermissionControl() {
        // 检查当前用户是否为管理员
        const isAdmin = this.currentUser && this.currentUser.role === 'admin';
        
        // 获取客户筛选字段容器
        const customerUidContainer = document.getElementById('searchCustomerUidContainer');
        const customerNameContainer = document.getElementById('searchCustomerNameContainer');
        const searchCustomerUid = document.getElementById('searchCustomerUid');
        const searchCustomerName = document.getElementById('searchCustomerName');
        
        if (!isAdmin) {
            // 普通用户：隐藏客户筛选字段
            if (customerUidContainer) {
                customerUidContainer.style.display = 'none';
            }
            if (customerNameContainer) {
                customerNameContainer.style.display = 'none';
            }
            
            // 清空客户筛选参数（如果存在）
            if (searchCustomerUid) {
                searchCustomerUid.value = '';
            }
            if (searchCustomerName) {
                searchCustomerName.value = '';
            }
            
            // 从搜索参数中移除客户相关参数
            if (this.tradesSearchParams) {
                delete this.tradesSearchParams.customer_uid;
                delete this.tradesSearchParams.customer_name;
            }
        } else {
            // 管理员：显示所有筛选字段
            if (customerUidContainer) {
                customerUidContainer.style.display = 'block';
            }
            if (customerNameContainer) {
                customerNameContainer.style.display = 'block';
            }
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

            // 普通用户：移除客户筛选参数（后端会自动过滤）
            const isAdmin = this.currentUser && this.currentUser.role === 'admin';
            const searchParams = { ...this.tradesSearchParams };
            
            if (!isAdmin) {
                // 普通用户不允许通过前端参数筛选其他客户
                delete searchParams.customer_uid;
                delete searchParams.customer_name;
            }

            Object.entries(searchParams).forEach(([key, value]) => {
                if (value && value.trim() !== '') {
                    params.append(key, value.trim());
                }
            });

            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/trades?${params.toString()}`);
            if (response && response.ok) {
                const data = await response.json();
                this.renderTradesTable(data.data);
                this.updateTradesCount(data.data.pagination);
            } else {
                throw new Error(`HTTP ${response ? response.status : '网络错误'}: ${response ? response.statusText : '连接失败'}`);
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

            // 普通用户：移除客户筛选参数（后端会自动过滤）
            const isAdmin = this.currentUser && this.currentUser.role === 'admin';
            const searchParams = { ...this.tradesSearchParams };
            
            if (!isAdmin) {
                // 普通用户不允许通过前端参数筛选其他客户
                delete searchParams.customer_uid;
                delete searchParams.customer_name;
            }

            Object.entries(searchParams).forEach(([key, value]) => {
                if (value && value.trim() !== '') {
                    params.append(key, value.trim());
                }
            });

            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/trades?${params.toString()}`);
            if (response && response.ok) {
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
        
        const isAdmin = this.currentUser && this.currentUser.role === 'admin';
        
        this.tradesSearchParams = {
            symbol: document.getElementById('searchSymbol').value,
            direction: document.getElementById('searchDirection').value,
            pos_side: document.getElementById('searchPosSide').value,
            status: document.getElementById('searchStatus').value
        };
        
        // 只有管理员才能筛选客户
        if (isAdmin) {
            const customerUidInput = document.getElementById('searchCustomerUid');
            const customerNameInput = document.getElementById('searchCustomerName');
            if (customerUidInput) {
                this.tradesSearchParams.customer_uid = customerUidInput.value;
            }
            if (customerNameInput) {
                this.tradesSearchParams.customer_name = customerNameInput.value;
            }
        }
        
        this.currentTradesPage = 1;
        await this.loadTradesData();
        
        this.showToast('成功', '搜索完成', 'success');
    }

    // 重置交易搜索
    async resetTradesSearch() {
        const isAdmin = this.currentUser && this.currentUser.role === 'admin';
        
        if (isAdmin) {
            const customerUidInput = document.getElementById('searchCustomerUid');
            const customerNameInput = document.getElementById('searchCustomerName');
            if (customerUidInput) {
                customerUidInput.value = '';
            }
            if (customerNameInput) {
                customerNameInput.value = '';
            }
        }
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
            
            // 首先获取交易详情（使用apiRequest自动包含认证Token）
            const tradeResponse = await this.apiRequest(`${this.apiBaseUrl}/trades`);
            if (!tradeResponse || !tradeResponse.ok) {
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
            
            // 使用手动平仓接口（使用apiRequest自动包含认证Token）
            const response = await this.apiRequest(`${this.apiBaseUrl}/manual/close_position`, {
                method: 'POST',
                body: JSON.stringify({
                    customer_uid: trade.customer_uid,
                    symbol: trade.symbol,
                    pos_side: trade.pos_side,
                    close_sz: parseFloat(trade.volume_contract || trade.sz || 0),
                    is_demo: trade.is_demo !== undefined ? trade.is_demo : this.getIsDemo(),
                    reason: '前端手动平仓'
                })
            });

            if (response && response.ok) {
                const result = await response.json();
                this.showToast('成功', `交易平仓成功: ${result.message}`, 'success');
                this.loadTradesData();
                
                const modal = bootstrap.Modal.getInstance(document.getElementById('tradeDetailModal'));
                if (modal) {
                    modal.hide();
                }
            } else {
                const errorMsg = response ? (response.statusText || '平仓失败') : '网络错误，请检查连接';
                if (response) {
                    try {
                        const errorData = await response.json();
                        throw new Error(errorData.message || errorMsg);
                    } catch (e) {
                        throw new Error(errorMsg);
                    }
                } else {
                    throw new Error(errorMsg);
                }
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
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/trades/${tradeUid}/retry`, {
                method: 'PUT'
            });

            if (response && response.ok) {
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
            const response = await this.apiRequest(`${this.apiBaseUrl}/signal_sources`);
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
            const response = await this.apiRequest(`${this.apiBaseUrl}/strategies`);
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
            const response = await this.apiRequest(`${this.apiBaseUrl}/rules`);
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
            const response = await this.apiRequest(`${this.apiBaseUrl}/risk/config`);
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
            
            const healthResponse = await this.apiRequest(`${this.apiBaseUrl}/health`);
            if (healthResponse.ok) {
                const healthData = await healthResponse.json();
                this.updateSystemHealth(healthData.data);
                this.updateHealthCheckResults(healthData.data);
            } else {
                console.error('系统健康检查失败:', healthResponse.statusText);
                this.updateHealthCheckResults(null, '系统健康检查失败');
            }

            const statsResponse = await this.apiRequest(`${this.apiBaseUrl}/stats/system`);
            if (statsResponse.ok) {
                const statsData = await statsResponse.json();
                this.updateSystemStats(statsData.data);
            } else {
                console.error('系统统计获取失败:', statsResponse.statusText);
            }

            // 加载系统日志
            const logsResponse = await this.apiRequest(`${this.apiBaseUrl}/system/logs?limit=${this.systemLogsPageSize}&page=${this.systemLogsPage}`);
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
            try {
                // 清除本地存储的登录状态
                localStorage.removeItem('loginStatus');
                
                // 显示退出成功消息
                this.showToast('成功', '已退出登录', 'success');
                
                // 延迟跳转到登录页面
                setTimeout(() => {
                    window.location.href = 'login.html';
                }, 1000);
                
            } catch (error) {
                console.error('退出登录失败:', error);
                this.showToast('错误', '退出登录失败', 'danger');
            }
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
        this.loadCustomersDataWithParams(searchTerm, currentFilter, 1);
    }

    // 客户筛选功能
    filterCustomers(filterValue) {
        
        const searchTerm = document.getElementById('customerSearch').value.trim();
        
        // 调用带参数的加载函数
        this.loadCustomersDataWithParams(searchTerm, filterValue, 1);
    }

    // 带参数的客户数据加载
    async loadCustomersDataWithParams(searchTerm = '', filterValue = 'all', page = 1, pageSize = 10) {
        try {
            
            // 构建查询参数
            const params = new URLSearchParams({
                page: page,
                page_size: pageSize
            });
            if (searchTerm) {
                params.append('name', searchTerm);
            }
            if (filterValue && filterValue !== 'all') {
                params.append('enabled', filterValue === 'enabled' ? '1' : '0');
            }

            const url = `${this.apiBaseUrl}/customers?${params.toString()}`;

            const response = await fetch(url);
            if (response.ok) {
                const data = await response.json();
                
                
                // 检查数据结构
                if (Array.isArray(data.data)) {
                    // 直接返回数组的情况
                    this.renderCustomersTable(data.data, data.pagination);
                } else if (data.data && Array.isArray(data.data.customers)) {
                    // 嵌套结构的情况 - 从data中提取分页信息
                    const pagination = {
                        current_page: data.data.page || 1,
                        total_pages: Math.ceil((data.data.total || 0) / (data.data.page_size || 10)),
                        total_count: data.data.total || 0,
                        page_size: data.data.page_size || 10
                    };
                    this.renderCustomersTable(data.data.customers, pagination);
                } else {
                    console.error('客户数据格式错误:', data.data);
                    this.renderCustomersTable([], null);
                }
            } else {
                console.error('加载客户数据失败:', response.statusText);
                this.renderCustomersTable([], null);
            }
        } catch (error) {
            console.error('加载客户数据失败:', error);
            this.renderCustomersTable([], null);
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
                    exchange: document.getElementById('Exchange').value,
                    enabled: document.getElementById('isEnabled').checked,
                    is_demo: this.getIsDemo({ elementId: 'isDemo', defaultValue: 0 })
                };
                
                
                let response;
                if (this.currentEditCustomerUid) {
                    // 编辑模式（使用apiRequest自动包含认证Token）
                    response = await this.apiRequest(`${this.apiBaseUrl}/customers/${this.currentEditCustomerUid}`, {
                        method: 'PUT',
                        body: JSON.stringify(customerData)
                    });
                } else {
                    // 添加模式（使用apiRequest自动包含认证Token）
                    response = await this.apiRequest(`${this.apiBaseUrl}/customers`, {
                        method: 'POST',
                        body: JSON.stringify(customerData)
                    });
                }
                
                if (response && response.ok) {
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
                    const errorMsg = response ? (response.statusText || '保存失败') : '网络错误，请检查连接';
                    if (response) {
                        try {
                            const errorData = await response.json();
                            throw new Error(errorData.message || errorMsg);
                        } catch (e) {
                            throw new Error(errorMsg);
                        }
                    } else {
                        throw new Error(errorMsg);
                    }
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
            // 获取客户数据（使用apiRequest自动包含认证Token）
            const response = await this.apiRequest(`${this.apiBaseUrl}/customers/${customerUid}`);
            if (response && response.ok) {
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
                const errorMsg = response ? (response.statusText || '获取客户数据失败') : '网络错误，请检查连接';
                console.error('获取客户数据失败:', errorMsg);
                this.showToast('错误', errorMsg, 'danger');
            }
        } catch (error) {
            console.error('编辑客户失败:', error);
            this.showToast('错误', '编辑客户失败: ' + error.message, 'danger');
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

            const response = await this.apiRequest(url);
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
    saveStrategyManagement() {
        const form = document.getElementById('addStrategyForm');
        if (form && form.checkValidity()) {
            // 获取选中的信号源
            const signalSourcesSelect = document.getElementById('signalSources');
            const selectedSignalSources = Array.from(signalSourcesSelect.selectedOptions).map(option => option.value);
            
            // 获取选中的客户
            const customersSelect = document.getElementById('strategyCustomers');
            const selectedCustomers = Array.from(customersSelect.selectedOptions).map(option => option.value);
            
            const strategyData = {
                name: document.getElementById('strategyName').value,
                // 移除描述字段
                // description: document.getElementById('strategyDescription').value,
                signal_source_uid: selectedSignalSources,
                customer_uids: selectedCustomers,
                // strategy_type 字段已移除，因为 strategies 表中没有此字段
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
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/strategies`, {
                method: 'POST',
                body: JSON.stringify(strategyData)
            });
            
            if (response && response.ok) {
                this.showToast('成功', '策略创建成功', 'success');
                // 关闭模态框
                const modal = bootstrap.Modal.getInstance(document.getElementById('addStrategyModal'));
                if (modal) {
                    modal.hide();
                }
                // 刷新数据
                this.loadStrategiesData();
            } else {
                const errorData = response ? await response.json() : { message: '创建失败' };
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
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/strategies/${strategyUid}`, {
                method: 'PUT',
                body: JSON.stringify(strategyData)
            });
            
            if (response.ok) {
                this.showToast('成功', '策略更新成功', 'success');
                // 关闭模态框
                const modal = bootstrap.Modal.getInstance(document.getElementById('addStrategyTradeModal'));
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
        
        // 加载客户选项
        await this.loadCustomersOptions();
        
        document.getElementById('strategyName').value = strategy.name || '';
        // 移除描述字段
        // document.getElementById('strategyDescription').value = strategy.description || '';
        
        // 设置信号源选择
        if (strategy.signal_source_uids && strategy.signal_source_uids.length > 0) {
            document.getElementById('signalSources').value = strategy.signal_source_uids;
        }
        
        // strategy_type 字段已移除，因为 strategies 表中没有此字段
        document.getElementById('strategyEnabled').checked = strategy.enabled || false;
        
        // 设置客户选择
        if (strategy.customers && strategy.customers.length > 0) {
            const customerUids = strategy.customers.map(c => c.customer_uid);
            document.getElementById('strategyCustomers').value = customerUids;
        }
        
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
                max_leverage: parseFloat(document.getElementById('ruleMaxLeverage').value),
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
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/rules`, {
                method: 'POST',
                body: JSON.stringify(ruleData)
            });
            
            if (response && response.ok) {
                this.showToast('成功', '规则创建成功', 'success');
                // 关闭模态框
                const modal = bootstrap.Modal.getInstance(document.getElementById('addRuleModal'));
                if (modal) {
                    modal.hide();
                }
                // 刷新数据
                this.loadRulesData();
            } else {
                const errorData = response ? await response.json() : { message: '创建失败' };
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
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/rules/${ruleUid}`, {
                method: 'PUT',
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
        document.getElementById('ruleMaxLeverage').value = rule.max_leverage || '';
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
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/signal-trades?page=1&page_size=10`);
            if (response && response.ok) {
                const data = await response.json();
                
                if (data.data && data.data.trades) {
                    this.renderSignalTradesTable(data.data.trades);
                    this.updateSignalTradesPagination(data.data.pagination);
                } else {
                    console.error('信号源交易记录数据格式错误:', data.data);
                    this.renderSignalTradesTable([]);
                }
            } else {
                console.error('加载信号源交易记录失败:', response ? response.statusText : '网络错误');
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
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/signal-trades?page=1&page_size=10`);
            if (response && response.ok) {
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
            
            // 加载信号源持仓（使用apiRequest自动包含认证Token）
            const signalPositionsResponse = await this.apiRequest(`${this.apiBaseUrl}/signal-positions`);
            if (signalPositionsResponse && signalPositionsResponse.ok) {
                const signalData = await signalPositionsResponse.json();
                signalPositions = signalData.data || [];
                this.renderSignalPositionsTable(signalPositions);
                this.updatePositionsStats('signal', signalPositions.length);
            }

            // 加载客户持仓（使用apiRequest自动包含认证Token）
            const customerPositionsResponse = await this.apiRequest(`${this.apiBaseUrl}/customer-positions`);
            if (customerPositionsResponse && customerPositionsResponse.ok) {
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
            
            // 加载信号源持仓（使用apiRequest自动包含认证Token）
            const signalPositionsResponse = await this.apiRequest(`${this.apiBaseUrl}/signal-positions`);
            if (signalPositionsResponse && signalPositionsResponse.ok) {
                const signalData = await signalPositionsResponse.json();
                signalPositions = signalData.data || [];
                this.renderSignalPositionsTable(signalPositions);
                this.updatePositionsStats('signal', signalPositions.length);
            }

            // 加载客户持仓（使用apiRequest自动包含认证Token）
            const customerPositionsResponse = await this.apiRequest(`${this.apiBaseUrl}/customer-positions`);
            if (customerPositionsResponse && customerPositionsResponse.ok) {
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
    async viewSignalTradeDetails(tradeUid) {
        try {
            // 获取信号源交易详情（使用apiRequest自动包含认证Token）
            const response = await this.apiRequest(`${this.apiBaseUrl}/signal-trades/${tradeUid}`);
            if (response && response.ok) {
                const data = await response.json();
                const trade = data.data;
                
                // 显示信号源交易详情的模态框
                this.showSignalTradeDetailsModal(trade);
            } else {
                this.showToast('错误', '获取信号源交易详情失败', 'danger');
            }
        } catch (error) {
            console.error('获取信号源交易详情失败:', error);
            this.showToast('错误', '获取信号源交易详情失败', 'danger');
        }
    }

    showSignalTradeDetailsModal(trade) {
        // 创建信号源交易详情模态框
        const modalHtml = `
            <div class="modal fade" id="signalTradeDetailsModal" tabindex="-1" aria-labelledby="signalTradeDetailsModalLabel" aria-hidden="true">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="signalTradeDetailsModalLabel">信号源交易详情</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <div class="row">
                                <div class="col-md-6">
                                    <h6>基本信息</h6>
                                    <table class="table table-sm">
                                        <tr><td><strong>交易ID:</strong></td><td>${trade.trade_uid}</td></tr>
                                        <tr><td><strong>信号源:</strong></td><td>${trade.signal_source_uid || '未知'}</td></tr>
                                        <tr><td><strong>交易对:</strong></td><td>${trade.symbol || '未知'}</td></tr>
                                        <tr><td><strong>持仓方向:</strong></td><td>
                                            <span class="badge bg-${trade.pos_side === 'long' ? 'success' : 'danger'}">
                                                ${trade.pos_side === 'long' ? '多头' : '空头'}
                                            </span>
                                        </td></tr>
                                        <tr><td><strong>状态:</strong></td><td>
                                            <span class="badge bg-${trade.status === 'open' ? 'primary' : 'secondary'}">
                                                ${trade.status === 'open' ? '持仓中' : '已平仓'}
                                            </span>
                                        </td></tr>
                                    </table>
                                </div>
                                <div class="col-md-6">
                                    <h6>交易参数</h6>
                                    <table class="table table-sm">
                                        <tr><td><strong>合约数量:</strong></td><td>${trade.volume_contract || '0'}</td></tr>
                                        <tr><td><strong>开仓价格:</strong></td><td>${trade.open_px || '未知'}</td></tr>
                                        <tr><td><strong>平仓价格:</strong></td><td>${trade.close_px || '未平仓'}</td></tr>
                                        <tr><td><strong>已平仓数量:</strong></td><td>${trade.close_volume_contract || '0'}</td></tr>
                                        <tr><td><strong>盈亏:</strong></td><td>
                                            <span class="text-${trade.profit >= 0 ? 'success' : 'danger'}">
                                                ${trade.profit || '0'} USDT
                                            </span>
                                        </td></tr>
                                    </table>
                                </div>
                            </div>
                            <div class="row mt-3">
                                <div class="col-12">
                                    <h6>时间信息</h6>
                                    <table class="table table-sm">
                                        <tr><td><strong>创建时间:</strong></td><td>${trade.created_at || '未知'}</td></tr>
                                        <tr><td><strong>更新时间:</strong></td><td>${trade.updated_at || '未知'}</td></tr>
                                        <tr><td><strong>平仓时间:</strong></td><td>${trade.closed_at || '未平仓'}</td></tr>
                                    </table>
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                            ${trade.status === 'open' ? `<button type="button" class="btn btn-warning" onclick="app.closeSignalTrade('${trade.trade_uid}')" data-bs-dismiss="modal">平仓</button>` : ''}
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // 移除已存在的模态框
        const existingModal = document.getElementById('signalTradeDetailsModal');
        if (existingModal) {
            existingModal.remove();
        }
        
        // 添加新的模态框到页面
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // 显示模态框
        const modal = new bootstrap.Modal(document.getElementById('signalTradeDetailsModal'));
        modal.show();
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
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/${endpoint}?${uidParam}=${accountUid}&symbol=${symbol}&pos_side=${posSide}`);
            
            if (response && response.ok) {
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
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/${endpoint}?${uidParam}=${accountUid}&symbol=${symbol}&pos_side=${posSide}&status=open`);
            
            if (response && response.ok) {
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

            // 发送平仓请求（使用apiRequest自动包含认证Token）
            const endpoint = accountType === 'signal' ? '/manual/close_signal_position' : '/manual/close_position';
            const response = await this.apiRequest(`${this.apiBaseUrl}${endpoint}`, {
                method: 'POST',
                body: JSON.stringify(closeData)
            });

            if (!response || !response.ok) {
                this.showToast('错误', '平仓请求失败', 'danger');
                return;
            }

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

            // 获取持仓汇总信息（使用apiRequest自动包含认证Token）
            const summaryResponse = await this.apiRequest(`${this.apiBaseUrl}/${type === 'signal' ? 'signal-positions' : 'customer-positions'}`);
            if (summaryResponse && summaryResponse.ok) {
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

            // 获取交易记录（使用apiRequest自动包含认证Token）
            const tradesResponse = await this.apiRequest(`${this.apiBaseUrl}/${type === 'signal' ? 'signal-trades' : 'trades'}?${type === 'signal' ? 'signal_source_uid' : 'customer_uid'}=${accountId}&symbol=${symbol}&pos_side=${posSide}`);
            if (tradesResponse && tradesResponse.ok) {
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
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/signal-trades?${params}`);
            if (response && response.ok) {
                const data = await response.json();
                
                if (data.data && data.data.trades) {
                    this.renderSignalTradesTable(data.data.trades);
                    this.updateSignalTradesPagination(data.data.pagination);
                } else {
                    console.error('信号源交易记录数据格式错误:', data.data);
                    this.renderSignalTradesTable([]);
                }
            } else {
                console.error('加载信号源交易记录失败:', response ? response.statusText : '网络错误');
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
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/signal_sources`, {
                method: 'POST',
                body: JSON.stringify(signalSourceData)
            });
            
            if (response && response.ok) {
                this.showToast('成功', '信号源创建成功', 'success');
                // 关闭模态框
                const modal = bootstrap.Modal.getInstance(document.getElementById('addSignalSourceModal'));
                if (modal) {
                    modal.hide();
                }
                // 刷新数据
                this.loadSignalSourcesData();
            } else {
                const errorData = response ? await response.json() : { message: '创建失败' };
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
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/signal_sources/${sourceUid}`, {
                method: 'PUT',
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
                // 加载客户列表（使用apiRequest自动包含认证Token）
                const response = await this.apiRequest(`${this.apiBaseUrl}/customers`);
                if (response && response.ok) {
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
                // 加载信号源列表（使用apiRequest自动包含认证Token）
                const response = await this.apiRequest(`${this.apiBaseUrl}/signal_sources`);
                if (response && response.ok) {
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
                is_demo: this.getIsDemo({ elementId: 'manualIsDemo' }),
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
            // 使用后端代理，避免 CORS 问题
            const url = `${this.apiBaseUrl}/market/ticker?instId=${symbol}`;
            
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
        const isDemo = this.getIsDemo({ elementId: 'manualIsDemo' });
        
        if (!accountType || !accountUid) {
            this.showToast('错误', '请先选择账户类型和账户', 'danger');
            return;
        }
        
        try {
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/manual/orders?account_uid=${accountUid}&account_type=${accountType}&is_demo=${isDemo}&status=live`);
            
            if (response && response.ok) {
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
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/manual/cancel_order`, {
                method: 'POST',
                body: JSON.stringify({
                    order_id: orderId,
                    account_uid: accountUid,
                    account_type: accountType,
                    is_demo: isDemo
                })
            });
            
            if (response && response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.showToast('成功', '撤单成功', 'success');
                    this.refreshPendingOrders(); // 刷新订单列表
                } else {
                    console.error('撤单失败:', result);
                    this.showToast('错误', result.message || '撤单失败', 'danger');
                }
            } else {
                const errorMsg = response ? `撤单失败: ${response.status}` : '撤单失败: 网络错误';
                console.error('撤单请求失败:', errorMsg);
                this.showToast('错误', errorMsg, 'danger');
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
            const isDemo = this.getIsDemo({ elementId: 'manualIsDemo' });
            // 获取客户未成交订单
            const customersResponse = await this.apiRequest(`${this.apiBaseUrl}/customers?is_demo=${isDemo}`);
            if (customersResponse.ok) {
                const customersData = await customersResponse.json();
                const customers = customersData.data?.customers || [];
                
                for (const customer of customers) {
                    try {
                        const ordersResponse = await this.apiRequest(
                            `${this.apiBaseUrl}/manual/orders?account_uid=${customer.customer_uid}&account_type=customer&is_demo=${isDemo}&status=live`
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
            const signalSourcesResponse = await this.apiRequest(`${this.apiBaseUrl}/signal_sources?is_demo=${isDemo}`);
            if (signalSourcesResponse.ok) {
                const signalSourcesData = await signalSourcesResponse.json();
                const signalSources = signalSourcesData.data || [];
                
                for (const signalSource of signalSources) {
                    try {
                        const ordersResponse = await this.apiRequest(
                            `${this.apiBaseUrl}/manual/orders?account_uid=${signalSource.source_uid}&account_type=signal&is_demo=${isDemo}&status=live`
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
            
            const isDemo = this.getIsDemo({ elementId: 'manualIsDemo' });
            const response = await this.apiRequest(`${this.apiBaseUrl}/manual/cancel_order`, {
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
            const isDemo = this.getIsDemo({ elementId: 'manualIsDemo', defaultValue: 1 });
            
            // 获取所有客户和信号源
            const [customersResponse, signalSourcesResponse] = await Promise.all([
                this.apiRequest(`${this.apiBaseUrl}/customers?is_demo=${isDemo}`),
                this.apiRequest(`${this.apiBaseUrl}/signal_sources?is_demo=${isDemo}`)
            ]);
            
            const customers = customersResponse && customersResponse.ok ? (await customersResponse.json()).data?.customers || [] : [];
            const signalSources = signalSourcesResponse && signalSourcesResponse.ok ? (await signalSourcesResponse.json()).data || [] : [];
            
            
            // 检查所有账户的订单
            for (const customer of customers) {
                try {
                    const response = await this.apiRequest(
                        `${this.apiBaseUrl}/manual/orders?account_uid=${customer.customer_uid}&account_type=customer&is_demo=${isDemo}&status=all`
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
                    const response = await this.apiRequest(
                        `${this.apiBaseUrl}/manual/orders?account_uid=${signalSource.source_uid}&account_type=signal&is_demo=${isDemo}&status=all`
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
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/manual/check_order_status?order_id=${orderId}`);
            
            if (response && response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.showToast('调试', `订单状态: ${result.data.execution_status}`, 'info');
                } else {
                    console.error('检查失败:', result);
                    this.showToast('错误', result.message || '检查失败', 'danger');
                }
            } else {
                const errorMsg = response ? `检查失败: ${response.status}` : '检查失败: 网络错误';
                console.error('检查请求失败:', errorMsg);
                this.showToast('错误', errorMsg, 'danger');
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
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/manual/cleanup_duplicates`, {
                method: 'POST'
            });
            
            if (response && response.ok) {
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
                const errorMsg = response ? `清理失败: ${response.status}` : '清理失败: 网络错误';
                console.error('清理请求失败:', errorMsg);
                this.showToast('错误', errorMsg, 'danger');
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
            // 使用apiRequest自动包含认证Token
            const response = await this.apiRequest(`${this.apiBaseUrl}/manual/cleanup_invalid_positions`, {
                method: 'POST'
            });
            
            if (response && response.ok) {
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
                const errorMsg = response ? `清理失败: ${response.status}` : '清理失败: 网络错误';
                console.error('清理请求失败:', errorMsg);
                this.showToast('错误', errorMsg, 'danger');
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
                            const isDemo = this.getIsDemo({ elementId: 'manualIsDemo' });
                            const response = await this.apiRequest(`${this.apiBaseUrl}/manual/cancel_order`, {
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
            const isDemo = this.getIsDemo({ elementId: 'manualIsDemo' });
            const response = await this.apiRequest(`${this.apiBaseUrl}/manual/orders?account_uid=${accountUid}&account_type=${accountType}&is_demo=${isDemo}&status=live`);
            
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200 && result.data && result.data.length > 0) {
                    // 批量撤单
                    let successCount = 0;
                    let failCount = 0;
                    
                    for (const order of result.data) {
                        try {
                            const isDemo = this.getIsDemo({ elementId: 'manualIsDemo' });
                            const cancelResponse = await this.apiRequest(`${this.apiBaseUrl}/manual/cancel_order`, {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                },
                                body: JSON.stringify({
                                    order_id: order.order_id,
                                    account_uid: accountUid,
                                    account_type: accountType,
                                    is_demo: isDemo
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
                case 'message-forward':
                    // 静默刷新消息转发数据
                    await this.loadMessageForwardData();
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
            } else if (e.target.matches('#refreshPopularTradersBtn') || e.target.closest('#refreshPopularTradersBtn')) {
                self.loadPopularTraders();
            } else if (e.target.matches('.add-to-limit-follow') || e.target.closest('.add-to-limit-follow')) {
                const btn = e.target.closest('.add-to-limit-follow') || e.target;
                const traderData = JSON.parse(btn.dataset.trader);
                self.addPopularTraderToLimitFollow(traderData);
            }
        });
        
        // 热门带单员筛选变化事件
        const exchangeSelect = document.getElementById('popularTradersExchange');
        const sortBySelect = document.getElementById('popularTradersSortBy');
        const limitSelect = document.getElementById('popularTradersLimit');
        const fetchAllCheckbox = document.getElementById('popularTradersFetchAll');
        
        if (exchangeSelect) {
            exchangeSelect.addEventListener('change', () => self.loadPopularTraders());
        }
        if (sortBySelect) {
            sortBySelect.addEventListener('change', () => self.loadPopularTraders());
        }
        if (limitSelect) {
            limitSelect.addEventListener('change', () => self.loadPopularTraders());
        }
        if (fetchAllCheckbox) {
            fetchAllCheckbox.addEventListener('change', () => {
                // 当取消"获取全部数据"时，如果limit为空，自动设置为20
                if (!fetchAllCheckbox.checked && !limitSelect.value) {
                    limitSelect.value = '20';
                }
            });
        }
        
        // Hyperliquid筛选变化事件
        const hyperliquidSortBy = document.getElementById('hyperliquidSortBy');
        const hyperliquidLimit = document.getElementById('hyperliquidLimit');
        const refreshHyperliquidBtn = document.getElementById('refreshHyperliquidBtn');
        
        if (hyperliquidSortBy) {
            hyperliquidSortBy.addEventListener('change', () => self.loadHyperliquidTraders());
        }
        if (hyperliquidLimit) {
            hyperliquidLimit.addEventListener('change', () => self.loadHyperliquidTraders());
        }
        if (refreshHyperliquidBtn) {
            refreshHyperliquidBtn.addEventListener('click', () => self.loadHyperliquidTraders());
        }
        
        // Hyperliquid跟单按钮事件
        document.addEventListener('click', function(e) {
            if (e.target.matches('.add-hyperliquid-follow') || e.target.closest('.add-hyperliquid-follow')) {
                const btn = e.target.closest('.add-hyperliquid-follow') || e.target;
                const traderData = JSON.parse(btn.dataset.trader);
                self.addHyperliquidFollow(traderData);
            } else if (e.target.matches('#addHyperliquidFollowBtn')) {
                self.showAddHyperliquidFollowModal();
            }
        });
        
        // Echosync 排行榜标签页切换事件
        const pnlTab = document.getElementById('pnl-tab');
        const winrateTab = document.getElementById('winrate-tab');
        const recentTab = document.getElementById('recent-tab');
        
        // 时间筛选器变化事件
        const leaderboardPeriodFilter = document.getElementById('leaderboardPeriodFilter');
        if (leaderboardPeriodFilter) {
            leaderboardPeriodFilter.addEventListener('change', () => {
                // 获取当前活动的标签页
                const activeTab = document.querySelector('#leaderboardTabs .nav-link.active');
                if (activeTab) {
                    const sortBy = activeTab.id === 'pnl-tab' ? 'total_pnl' : 
                                   activeTab.id === 'winrate-tab' ? 'avg_win_rate' : 'updated_at';
                    const period = self.getLeaderboardPeriod();
                    self.loadEchosyncLeaderboard(sortBy, period);
                }
            });
        }
        
        // 刷新按钮
        const refreshLeaderboardBtn = document.getElementById('refreshLeaderboardBtn');
        if (refreshLeaderboardBtn) {
            refreshLeaderboardBtn.addEventListener('click', () => {
                const activeTab = document.querySelector('#leaderboardTabs .nav-link.active');
                if (activeTab) {
                    const sortBy = activeTab.id === 'pnl-tab' ? 'total_pnl' : 
                                   activeTab.id === 'winrate-tab' ? 'avg_win_rate' : 'updated_at';
                    const period = self.getLeaderboardPeriod();
                    self.loadEchosyncLeaderboard(sortBy, period);
                }
            });
        }
        
        if (pnlTab) {
            pnlTab.addEventListener('shown.bs.tab', () => {
                const period = self.getLeaderboardPeriod();
                self.loadEchosyncLeaderboard('total_pnl', period);
            });
        }
        if (winrateTab) {
            winrateTab.addEventListener('shown.bs.tab', () => {
                const period = self.getLeaderboardPeriod();
                self.loadEchosyncLeaderboard('avg_win_rate', period);
            });
        }
        if (recentTab) {
            recentTab.addEventListener('shown.bs.tab', () => {
                const period = self.getLeaderboardPeriod();
                self.loadEchosyncLeaderboard('updated_at', period);
            });
        }
        
        // 巨鲸订单刷新按钮
        const refreshWhaleOrdersBtn = document.getElementById('refreshWhaleOrdersBtn');
        if (refreshWhaleOrdersBtn) {
            refreshWhaleOrdersBtn.addEventListener('click', () => self.loadWhaleOrders());
        }
        
        // 巨鲸转移刷新按钮
        const refreshWhaleMovesBtn = document.getElementById('refreshWhaleMovesBtn');
        if (refreshWhaleMovesBtn) {
            refreshWhaleMovesBtn.addEventListener('click', () => self.loadWhaleMoves());
        }
        
        // 启动自动刷新
        self.startWhaleAutoRefresh();
        
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
            } else if (e.target.matches('#limitFollowMode')) {
                // 跟单模式切换，显示/隐藏相应区域
                self.handleFollowModeChange();
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
            const response = await this.apiRequest(`${this.apiBaseUrl}/limit-follow/strategies`);
            if (response && response.ok) {
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
            // 判断跟单模式并显示相应信息
            let followSourceDisplay = '';
            if (strategy.follow_mode === 'follow_signal_source' || strategy.signal_source_uid) {
                // 信号源模式
                const signalSourceUid = strategy.signal_source_uid || strategy.trader_unique_name;
                followSourceDisplay = `<span class="badge bg-info">信号源</span> ${strategy.signal_source_name || signalSourceUid}`;
            } else {
                // 跟单员模式
                followSourceDisplay = `<span class="badge bg-primary">跟单员</span> ${strategy.trader_name || strategy.trader_unique_name || '未知跟单员'}`;
            }
            
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>
                    ${strategy.strategy_name || strategy.name || '未命名策略'}
                    ${strategy.reverse_direction ? '<br><span class="badge bg-warning text-dark mt-1"><i class="bi bi-arrow-left-right"></i> 反向跟单</span>' : ''}
                </td>
                <td>${followSourceDisplay}</td>
                <td>
                    ${strategy.customers && strategy.customers.length > 0 
                        ? strategy.customers.map(c => 
                            `<span class="badge bg-primary me-1 mb-1">${c.customer_name || c.customer_uid}${c.custom_leverage ? ` (${c.custom_leverage}倍)` : ''}</span>`
                          ).join('')
                        : (strategy.customer_name || strategy.customer_uid || '未知客户')
                    }
                </td>
                <td>${strategy.symbol}</td>
                <td>
                    <span class="badge bg-${strategy.pos_side === 'both' ? 'info' : (strategy.pos_side === 'long' ? 'success' : 'danger')}">${strategy.pos_side === 'both' ? '双向' : (strategy.pos_side === 'long' ? '多仓' : '空仓')}</span>
                    ${strategy.reverse_direction ? '<br><small class="text-muted">（反向）</small>' : ''}
                </td>
                <td>${strategy.follow_type === 'percentage' ? '价格偏移' : '固定价格'}</td>
                <td>${strategy.follow_value}% (${strategy.min_follow_value}% - ${strategy.max_follow_value}%)</td>
                <td>
                    ${this.getFollowOrderTypeDisplay(strategy.follow_order_types)}
                </td>
                <td><span class="badge bg-${strategy.enabled ? 'success' : 'secondary'}">${strategy.enabled ? '启用' : '禁用'}</span></td>
                <td>
                    <button class="btn btn-sm btn-outline-primary" onclick="app.editLimitFollowStrategy(${strategy.id})" title="编辑策略">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-info" onclick="app.manageStrategyCustomers(${strategy.id})" title="管理客户">
                        <i class="bi bi-people"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="app.deleteLimitFollowStrategy(${strategy.id})" title="删除策略">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
    }
    
    getOrderTypeDisplay(orderType) {
        switch(orderType) {
            case 'market':
                return '<span class="badge bg-warning">市价单</span>';
            case 'limit':
                return '<span class="badge bg-primary">限价单</span>';
            default:
                return '<span class="badge bg-secondary">未知</span>';
        }
    }
    
    // 获取跟单订单类型显示
    getFollowOrderTypeDisplay(followOrderTypes) {
        if (!followOrderTypes) {
            return '<span class="badge bg-secondary">限价单</span>';
        }
        
        switch (followOrderTypes) {
            case 'limit_only':
                return '<span class="badge bg-warning">限价单</span>';
            case 'market_only':
                return '<span class="badge bg-success">市价单</span>';
            case 'both':
                return '<span class="badge bg-info">限价+市价</span>';
            default:
                return '<span class="badge bg-secondary">限价单</span>';
        }
    }

    // 加载限价跟单订单列表
    buildLimitFollowQuery(page = 1) {
        const params = new URLSearchParams();
        const orderType = document.getElementById('lfoOrderType')?.value?.trim();
        const status = document.getElementById('lfoStatus')?.value?.trim();
        const symbol = document.getElementById('lfoSymbol')?.value?.trim();
        const posSide = document.getElementById('lfoPosSide')?.value?.trim();
        const keyword = document.getElementById('lfoKeyword')?.value?.trim();
        const startTime = document.getElementById('lfoStartTime')?.value?.trim();
        const endTime = document.getElementById('lfoEndTime')?.value?.trim();
        const pageSize = document.getElementById('lfoPageSize')?.value?.trim() || '50';

        if (orderType) params.set('order_type', orderType);
        if (status) params.set('status', status);
        if (symbol) params.set('symbol', symbol);
        if (posSide) params.set('pos_side', posSide);
        if (keyword) params.set('keyword', keyword);
        if (startTime) {
            // 转换datetime-local格式为后端需要的格式
            const formattedTime = this.formatDateTimeLocal(startTime);
            params.set('start_time', formattedTime);
        }
        if (endTime) {
            const formattedTime = this.formatDateTimeLocal(endTime);
            params.set('end_time', formattedTime);
        }
        params.set('page', String(page));
        params.set('page_size', pageSize);

        return params.toString();
    }

    formatDateTimeLocal(datetimeLocal) {
        // 将datetime-local格式转换为 YYYY-MM-DD HH:MM:SS 格式
        if (!datetimeLocal) return '';
        const date = new Date(datetimeLocal);
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        const seconds = String(date.getSeconds()).padStart(2, '0');
        return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
    }

    formatDateTimeLocalForInput(datetimeStr) {
        // 将 YYYY-MM-DD HH:MM:SS 格式转换为 datetime-local 格式
        if (!datetimeStr) return '';
        const date = new Date(datetimeStr);
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${year}-${month}-${day}T${hours}:${minutes}`;
    }

    // 加载限价跟单订单列表
    async loadLimitFollowOrders(page = 1) {
        try {
            // 显示加载状态
            this.showLoadingState();
            
            const query = this.buildLimitFollowQuery(page);
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/orders?${query}`);
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.renderLimitFollowOrdersTable(result.data);
                    this.renderLimitFollowPagination(result.total || 0, result.page || 1, result.page_size || 50);
                } else {
                    console.error('获取订单列表失败:', result.message);
                    this.showErrorState('获取订单列表失败: ' + result.message);
                }
            } else {
                console.error('获取订单列表请求失败:', response.status);
                this.showErrorState('请求失败: ' + response.status);
            }
        } catch (error) {
            console.error('加载订单列表失败:', error);
            this.showErrorState('加载失败: ' + error.message);
        } finally {
            this.hideLoadingState();
        }
    }

    // 显示加载状态
    showLoadingState() {
        const tbody = document.querySelector('#limitFollowOrdersTable tbody');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-center"><div class="spinner-border spinner-border-sm me-2" role="status"></div>加载中...</td></tr>';
        }
        
        // 禁用查询按钮
        const searchBtn = document.getElementById('lfoSearchBtn');
        if (searchBtn) {
            searchBtn.disabled = true;
            searchBtn.innerHTML = '<i class="bi bi-hourglass-split me-1"></i>查询中...';
        }
    }

    // 隐藏加载状态
    hideLoadingState() {
        const searchBtn = document.getElementById('lfoSearchBtn');
        if (searchBtn) {
            searchBtn.disabled = false;
            searchBtn.innerHTML = '<i class="bi bi-search me-1"></i>查询';
        }
    }

    // 显示错误状态
    showErrorState(message) {
        const tbody = document.querySelector('#limitFollowOrdersTable tbody');
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="10" class="text-center text-danger"><i class="bi bi-exclamation-triangle me-2"></i>${message}</td></tr>`;
        }
    }
    
    // 渲染限价跟单订单表格
    renderLimitFollowOrdersTable(orders) {
        const tbody = document.querySelector('#limitFollowOrdersTable tbody');
        if (!tbody) return;
        
        // 使用 DocumentFragment 批量操作DOM
        const fragment = document.createDocumentFragment();
        
        if (!orders || orders.length === 0) {
            const emptyRow = document.createElement('tr');
            emptyRow.innerHTML = '<td colspan="10" class="text-center text-muted">暂无订单</td>';
            fragment.appendChild(emptyRow);
        } else {
            // 批量生成HTML字符串，减少DOM操作
            const rowsHTML = orders.map(order => this.generateOrderRowHTML(order)).join('');
            
            // 创建临时容器
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = `<table><tbody>${rowsHTML}</tbody></table>`;
            
            // 批量添加到fragment
            const tempTbody = tempDiv.querySelector('tbody');
            while (tempTbody.firstChild) {
                fragment.appendChild(tempTbody.firstChild);
            }
        }
        
        // 一次性更新DOM
        tbody.innerHTML = '';
        tbody.appendChild(fragment);
        
        // 批量绑定事件（使用事件委托）
        this.bindOrderTableEvents();
    }

    // 生成订单行HTML（优化版）
    generateOrderRowHTML(order) {
        const statusBadge = this.getOrderStatusBadge(order.status);
        const statusText = this.getOrderStatusText(order.status);
        const orderTypeHTML = this.getOrderTypeDisplay(order.order_type);
        const posSideBadge = order.pos_side === 'long' ? 'success' : 'danger';
        const posSideText = order.pos_side === 'long' ? '多头' : '空头';
        const isDisabled = order.status !== 'pending' && order.status !== 'live' ? 'disabled' : '';
        const formattedTime = this.formatDateTime(order.created_at);
        
        return `
            <tr data-order-uid="${order.order_uid}" data-status="${order.status}">
                <td><code class="small">${order.order_uid}</code></td>
                <td>${order.customer_name || order.customer_uid}</td>
                <td><span class="badge bg-info">${order.symbol}</span></td>
                <td><span class="badge bg-${posSideBadge}">${posSideText}</span></td>
                <td>${orderTypeHTML}</td>
                <td>${order.target_price || '-'}</td>
                <td>${order.order_size}</td>
                <td><span class="badge bg-${statusBadge}">${statusText}</span></td>
                <td><small>${formattedTime}</small></td>
                <td>
                    <button class="btn btn-sm btn-outline-warning cancel-order-btn" ${isDisabled}>
                        <i class="bi bi-x-circle"></i> 撤单
                    </button>
                </td>
            </tr>
        `;
    }
    
    // 批量绑定事件（事件委托）
    bindOrderTableEvents() {
        const tbody = document.querySelector('#limitFollowOrdersTable tbody');
        if (!tbody) return;
        
        // 移除旧的事件监听器
        tbody.removeEventListener('click', this.handleOrderTableClick);
        
        // 添加新的事件监听器
        this.handleOrderTableClick = (event) => {
            const target = event.target;
            const cancelBtn = target.closest('.cancel-order-btn');
            
            if (cancelBtn) {
                const row = cancelBtn.closest('tr');
                const orderUid = row.dataset.orderUid;
                const status = row.dataset.status;
                
                if (status === 'pending' || status === 'live') {
                    this.cancelLimitFollowOrder(orderUid);
                }
            }
        };
        
        tbody.addEventListener('click', this.handleOrderTableClick);
    }

    renderLimitFollowPagination(total, page, pageSize) {
        const ul = document.getElementById('lfoPagination');
        const summary = document.getElementById('lfoSummary');
        if (!ul || !summary) return;

        const totalPages = Math.max(1, Math.ceil(total / pageSize));
        summary.textContent = `共 ${total} 条，页 ${page}/${totalPages}`;

        // 使用 DocumentFragment 优化分页渲染
        const fragment = document.createDocumentFragment();
        
        const createItem = (label, targetPage, disabled = false, active = false) => {
            const li = document.createElement('li');
            li.className = `page-item ${disabled ? 'disabled' : ''} ${active ? 'active' : ''}`;
            const a = document.createElement('a');
            a.className = 'page-link';
            a.href = 'javascript:void(0)';
            a.textContent = label;
            if (!disabled) {
                a.addEventListener('click', () => this.loadLimitFollowOrders(targetPage));
            }
            li.appendChild(a);
            return li;
        };

        // 批量添加分页项
        fragment.appendChild(createItem('«', Math.max(1, page - 1), page === 1));

        const windowSize = 5;
        const start = Math.max(1, page - Math.floor(windowSize / 2));
        const end = Math.min(totalPages, start + windowSize - 1);
        const realStart = Math.max(1, end - windowSize + 1);

        for (let p = realStart; p <= end; p++) {
            fragment.appendChild(createItem(String(p), p, false, p === page));
        }

        fragment.appendChild(createItem('»', Math.min(totalPages, page + 1), page === totalPages));

        // 一次性更新DOM
        ul.innerHTML = '';
        ul.appendChild(fragment);
    }

    initLimitFollowOrdersUI() {
        const searchBtn = document.getElementById('lfoSearchBtn');
        const resetBtn = document.getElementById('lfoResetBtn');
        const exportBtn = document.getElementById('lfoExportBtn');
        const pageSizeSel = document.getElementById('lfoPageSize');

        if (searchBtn) {
            searchBtn.onclick = () => this.loadLimitFollowOrders(1);
        }
        if (resetBtn) {
            resetBtn.onclick = () => {
                ['lfoOrderType','lfoStatus','lfoSymbol','lfoPosSide','lfoKeyword','lfoStartTime','lfoEndTime']
                    .forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
                const ps = document.getElementById('lfoPageSize');
                if (ps) ps.value = '50';
                this.loadLimitFollowOrders(1);
            };
        }
        if (exportBtn) {
            exportBtn.onclick = () => this.exportLimitFollowOrders();
        }
        if (pageSizeSel) {
            pageSizeSel.onchange = () => this.loadLimitFollowOrders(1);
        }

        // 添加防抖搜索功能
        this.setupDebouncedSearch();
    }

    // 设置防抖搜索
    setupDebouncedSearch() {
        let searchTimeout;
        
        const debouncedSearch = () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                this.loadLimitFollowOrders(1);
            }, 500); // 500ms防抖
        };

        // 为输入框添加防抖搜索
        const searchInputs = ['lfoSymbol', 'lfoKeyword'];
        searchInputs.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.addEventListener('input', debouncedSearch);
                el.addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') {
                        clearTimeout(searchTimeout);
                        this.loadLimitFollowOrders(1);
                    }
                });
            }
        });

        // 为下拉框添加即时搜索
        const selectInputs = ['lfoOrderType', 'lfoStatus', 'lfoPosSide'];
        selectInputs.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.addEventListener('change', () => this.loadLimitFollowOrders(1));
            }
        });
    }

    quickFilter(type) {
        // 重置所有筛选条件
        ['lfoOrderType','lfoStatus','lfoSymbol','lfoPosSide','lfoKeyword','lfoStartTime','lfoEndTime']
            .forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });

        switch(type) {
            case 'market':
                document.getElementById('lfoOrderType').value = 'market';
                break;
            case 'filled':
                document.getElementById('lfoStatus').value = 'filled';
                break;
            case 'pending':
                document.getElementById('lfoStatus').value = 'pending';
                break;
            case 'canceled':
                document.getElementById('lfoStatus').value = 'canceled';
                break;
            case 'today':
                const today = new Date();
                const startOfDay = new Date(today.getFullYear(), today.getMonth(), today.getDate());
                const endOfDay = new Date(today.getFullYear(), today.getMonth(), today.getDate(), 23, 59, 59);
                
                document.getElementById('lfoStartTime').value = this.formatDateTimeLocalForInput(startOfDay.toISOString());
                document.getElementById('lfoEndTime').value = this.formatDateTimeLocalForInput(endOfDay.toISOString());
                break;
        }
        
        this.loadLimitFollowOrders(1);
    }

    async exportLimitFollowOrders() {
        try {
            const query = this.buildLimitFollowQuery(1);
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/orders?${query}&page_size=1000`);
            
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.downloadCSV(result.data, '限价跟单订单');
                } else {
                    alert('导出失败: ' + result.message);
                }
            } else {
                alert('导出请求失败: ' + response.status);
            }
        } catch (error) {
            console.error('导出失败:', error);
            alert('导出失败: ' + error.message);
        }
    }

    downloadCSV(data, filename) {
        if (!data || data.length === 0) {
            alert('没有数据可导出');
            return;
        }

        const headers = ['订单ID', '客户', '交易对', '方向', '目标价格', '数量', '状态', '创建时间'];
        const csvContent = [
            headers.join(','),
            ...data.map(row => [
                row.order_uid,
                row.customer_name || row.customer_uid,
                row.symbol,
                row.pos_side,
                row.target_price,
                row.order_size,
                row.status,
                this.formatDateTime(row.created_at)
            ].join(','))
        ].join('\n');

        const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', `${filename}_${new Date().toISOString().slice(0,10)}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
    
    // 加载限价跟单选项数据
    async loadLimitFollowOptions() {
        try {
            // 加载跟单员列表
            const tradersResponse = await this.apiRequest(`${this.apiBaseUrl}/limit-follow/traders`);
            if (tradersResponse && tradersResponse.ok) {
                const result = await tradersResponse.json();
                if (result.success === 200 && result.data) {
                    this.populateSelectOptions('limitFollowStrategyTrader', result.data, 'unique_name', 'name');
                } else {
                    console.warn('跟单员API返回失败:', result);
                }
            } else {
                console.warn('跟单员API请求失败:', tradersResponse.status);
            }
            
            // 加载客户列表 - 用于跟单员模式下的跟单账户
            // 获取所有客户数据（不分页）
            const customersResponse = await this.apiRequest(`${this.apiBaseUrl}/customers?page_size=100`);
            if (customersResponse && customersResponse.ok) {
                const result = await customersResponse.json();
                if (result.success === 200 && result.data && result.data.customers) {
                    // 存储客户数据，稍后根据模式分配
                    this.customersData = result.data.customers;
                } else {
                    console.warn('客户API返回失败:', result);
                }
            } else {
                console.warn('客户API请求失败:', customersResponse ? customersResponse.status : 'null');
            }
            
            // 加载信号源列表
            const signalSourcesResponse = await this.apiRequest(`${this.apiBaseUrl}/signal_sources`);
            if (signalSourcesResponse && signalSourcesResponse.ok) {
                const result = await signalSourcesResponse.json();
                if (result.success === 200 && result.data) {
                    // 存储信号源数据，稍后根据模式分配
                    this.signalSourcesData = result.data;
                    
                    // 直接填充信号源选择框（用于信号源模式）
                    this.populateSelectOptions('limitFollowStrategySignalSource', result.data, 'source_uid', 'name');
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
        
        if (data.length === 0) {
            console.warn(`populateSelectOptions: data数组为空`, data);
            return;
        }
        
        // 保留第一个选项
        const firstOption = select.options[0];
        select.innerHTML = '';
        if (firstOption) {
            select.appendChild(firstOption);
        }
        
        try {
            let addedCount = 0;
            data.forEach((item, index) => {
                if (item && item[valueField] !== undefined && item[textField] !== undefined) {
                    const option = document.createElement('option');
                    option.value = item[valueField];
                    option.textContent = item[textField];
                    select.appendChild(option);
                    addedCount++;
                } else {
                    console.warn(`跳过无效项:`, { item, valueField, textField, hasValue: item && item[valueField] !== undefined, hasText: item && item[textField] !== undefined });
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
                // 使用多客户API
                url = `${this.apiBaseUrl}/limit-follow/strategies/multi-customer`;
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

        // 设置默认模式并触发渲染（默认跟单员模式）
        const modeSelect = document.getElementById('limitFollowMode');
        if (modeSelect && !modeSelect.value) {
            modeSelect.value = 'trader';
        }
        // 立即根据模式显示对应区域
        if (typeof this.handleFollowModeChange === 'function') {
            this.handleFollowModeChange();
        }
    }
    
    // 生成策略UID
    generateStrategyUid() {
        const timestamp = Date.now();
        const random = Math.floor(Math.random() * 1000);
        return `LIMIT_FOLLOW_${timestamp}_${random}`;
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
            
            // 设置跟单模式 - 将后端的模式值转换为前端值
            let followMode = strategy.follow_mode;
            if (followMode === 'follow_trader') {
                followMode = 'trader';
            } else if (followMode === 'follow_signal_source') {
                followMode = 'signal';
            } else if (!followMode) {
                // 向后兼容：通过signal_source_uid字段判断模式
                if (strategy.signal_source_uid) {
                    followMode = 'signal';
                } else if (strategy.trader_unique_name) {
                    followMode = 'trader';
                } else {
                    followMode = 'trader'; // 默认为跟单员模式
                }
            }
            
            document.getElementById('limitFollowMode').value = followMode;
            
            // 触发模式切换处理
            this.handleFollowModeChange();
            
            // 根据模式设置相应的字段
            if (followMode === 'trader') {
                document.getElementById('limitFollowStrategyTrader').value = strategy.trader_unique_name || '';
                // 设置多客户选择
                if (strategy.customers && strategy.customers.length > 0) {
                    const customerUids = strategy.customers.map(c => c.customer_uid);
                    document.getElementById('limitFollowStrategyCustomers').value = customerUids;
                }
            } else if (followMode === 'signal') {
                // 直接使用signal_source_uid或trader_unique_name（它们现在是相同的）
                const signalSourceUid = strategy.signal_source_uid || strategy.trader_unique_name;
                document.getElementById('limitFollowStrategySignalSource').value = signalSourceUid || '';
                // 设置多客户选择
                if (strategy.customers && strategy.customers.length > 0) {
                    const customerUids = strategy.customers.map(c => c.customer_uid);
                    document.getElementById('limitFollowStrategyFollowCustomers').value = customerUids;
                }
            }
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
            document.getElementById('limitFollowStrategyLeverage').value = strategy.leverage || 10;
            document.getElementById('limitFollowStrategyMaxNetLeverage').value = strategy.max_net_leverage || 10.0;
            document.getElementById('limitFollowStrategyProportionalPosition').checked = strategy.proportional_position || false;
            document.getElementById('limitFollowStrategyMinFollowValue').value = strategy.min_follow_value || 0.5;
            document.getElementById('limitFollowStrategyMaxFollowValue').value = strategy.max_follow_value || 5.0;
            document.getElementById('limitFollowStrategyAutoCancelOnSignalClose').value = strategy.auto_cancel_on_signal_close ? 'true' : 'false';
            document.getElementById('limitFollowStrategyReverseDirection').checked = strategy.reverse_direction || false;  // 🆕 反向跟单
            
            // 设置跟单订单类型
            document.getElementById('followOrderTypes').value = strategy.follow_order_types || 'limit_only';
            
            // 设置限价市价比例
            document.getElementById('limitMarketRatio').value = strategy.limit_market_ratio || '1:1';
            
            // 根据订单类型显示/隐藏比例配置
            const limitMarketRatioRow = document.getElementById('limitMarketRatioRow');
            if (strategy.follow_order_types === 'both') {
                limitMarketRatioRow.style.display = 'block';
            } else {
                limitMarketRatioRow.style.display = 'none';
            }

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
            // 收集配置数据
            const configData = {};
            
            // 从页面中收集配置项
            const configElements = document.querySelectorAll('[data-config-key]');
            configElements.forEach(element => {
                const key = element.getAttribute('data-config-key');
                let value = element.value;
                
                // 根据元素类型处理值
                if (element.type === 'checkbox') {
                    value = element.checked;
                } else if (element.type === 'number') {
                    value = parseFloat(value) || 0;
                } else if (element.type === 'radio') {
                    if (element.checked) {
                        value = element.value;
                    }
                }
                
                if (key && value !== undefined && value !== '') {
                    configData[key] = value;
                }
            });
            
            // 如果没有找到配置元素，使用默认配置
            if (Object.keys(configData).length === 0) {
                // 从表单中收集配置
                const defaultConfig = {
                    max_orders_per_signal: 4,
                    default_follow_mode: 'follow_signal_source',
                    auto_execute_orders: true,
                    risk_control_enabled: true,
                    max_position_ratio: 0.1,
                    min_trade_interval: 60
                };
                
                // 尝试从常见的配置元素获取值
                const maxOrders = document.getElementById('maxOrdersPerSignal');
                if (maxOrders) configData.max_orders_per_signal = parseInt(maxOrders.value) || 4;
                
                const followMode = document.querySelector('input[name="followMode"]:checked');
                if (followMode) configData.default_follow_mode = followMode.value;
                
                const autoExecute = document.getElementById('autoExecuteOrders');
                if (autoExecute) configData.auto_execute_orders = autoExecute.checked;
                
                const riskControl = document.getElementById('riskControlEnabled');
                if (riskControl) configData.risk_control_enabled = riskControl.checked;
                
                const maxRatio = document.getElementById('maxPositionRatio');
                if (maxRatio) configData.max_position_ratio = parseFloat(maxRatio.value) || 0.1;
                
                const minInterval = document.getElementById('minTradeInterval');
                if (minInterval) configData.min_trade_interval = parseInt(minInterval.value) || 60;
                
                // 如果仍然没有配置，使用默认值
                if (Object.keys(configData).length === 0) {
                    Object.assign(configData, defaultConfig);
                }
            }
            
            // 发送配置到服务器
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/config`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(configData)
            });
            
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.showToast('成功', '限价跟单配置保存成功', 'success');
                } else {
                    this.showToast('错误', result.message || '保存配置失败', 'danger');
                }
            } else {
                const errorText = await response.text();
                console.error('保存配置失败:', response.status, errorText);
                this.showToast('错误', `保存配置失败: ${response.status}`, 'danger');
            }
            
        } catch (error) {
            console.error('保存配置失败:', error);
            this.showToast('错误', `保存配置失败: ${error.message}`, 'danger');
        }
    }

    // 重置限价跟单配置
    async resetLimitFollowConfig() {
        try {
            if (!confirm('确定要重置限价跟单配置吗？这将恢复所有配置到默认值。')) {
                return;
            }
            
            // 重置为默认配置
            const defaultConfig = {
                max_orders_per_signal: 4,
                default_follow_mode: 'follow_signal_source',
                auto_execute_orders: true,
                risk_control_enabled: true,
                max_position_ratio: 0.1,
                min_trade_interval: 60
            };
            
            // 发送重置配置到服务器
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/config`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(defaultConfig)
            });
            
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.showToast('成功', '限价跟单配置已重置为默认值', 'success');
                    
                    // 重新加载配置页面
                    this.loadLimitFollowConfig();
                } else {
                    this.showToast('错误', result.message || '重置配置失败', 'danger');
                }
            } else {
                const errorText = await response.text();
                console.error('重置配置失败:', response.status, errorText);
                this.showToast('错误', `重置配置失败: ${response.status}`, 'danger');
            }
            
        } catch (error) {
            console.error('重置配置失败:', error);
            this.showToast('错误', `重置配置失败: ${error.message}`, 'danger');
        }
    }
    
    // 加载限价跟单配置
    async loadLimitFollowConfig() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/config`);
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.populateLimitFollowConfig(result.data);
                } else {
                    console.error('加载配置失败:', result.message);
                }
            } else {
                console.error('加载配置失败:', response.status);
            }
        } catch (error) {
            console.error('加载限价跟单配置失败:', error);
        }
    }
    
    // 填充限价跟单配置到表单
    populateLimitFollowConfig(config) {
        // 填充配置到表单元素
        Object.keys(config).forEach(key => {
            const element = document.getElementById(key) || document.querySelector(`[data-config-key="${key}"]`);
            if (element) {
                if (element.type === 'checkbox') {
                    element.checked = config[key];
                } else if (element.type === 'radio') {
                    element.checked = element.value === config[key];
                } else {
                    element.value = config[key];
                }
            }
        });
    }

    // 显示执行跟单模态框
    async showExecuteLimitFollowModal() {
        try {
            // 加载客户列表
            await this.loadExecutionCustomers();
            
            // 加载信号源列表
            await this.loadExecutionSignalSources();
            
            // 显示模态框
            const modal = new bootstrap.Modal(document.getElementById('executeLimitFollowModal'));
            modal.show();
            
        } catch (error) {
            console.error('显示执行跟单模态框失败:', error);
            this.showToast('错误', `显示执行跟单模态框失败: ${error.message}`, 'danger');
        }
    }
    
    // 加载执行跟单的客户列表
    async loadExecutionCustomers() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/customers`);
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    const customers = result.data.customers || result.data;
                    const select = document.getElementById('executionCustomer');
                    if (select) {
                        select.innerHTML = '<option value="">选择客户</option>';
                        customers.forEach(customer => {
                            const option = document.createElement('option');
                            option.value = customer.customer_uid;
                            option.textContent = `${customer.name || customer.customer_uid} (${customer.customer_uid})`;
                            select.appendChild(option);
                        });
                    }
                }
            }
        } catch (error) {
            console.error('加载客户列表失败:', error);
        }
    }
    
    // 加载执行跟单的信号源列表
    async loadExecutionSignalSources() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/signal_sources`);
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    const sources = result.data;
                    const select = document.getElementById('executionSignalSource');
                    if (select) {
                        select.innerHTML = '<option value="">选择信号源</option>';
                        sources.forEach(source => {
                            const option = document.createElement('option');
                            option.value = source.source_uid;
                            option.textContent = `${source.name || source.source_uid} (${source.source_uid})`;
                            select.appendChild(option);
                        });
                    }
                }
            }
        } catch (error) {
            console.error('加载信号源列表失败:', error);
        }
    }

    // 提交执行跟单
    async submitLimitFollowExecution() {
        try {
            // 获取表单数据
            const customerUid = document.getElementById('executionCustomer').value;
            const signalSource = document.getElementById('executionSignalSource').value;
            const symbol = document.getElementById('executionSymbol').value;
            const posSide = document.getElementById('executionPosSide').value;
            const signalPrice = document.getElementById('executionSignalPrice').value;
            const signalVolume = document.getElementById('executionSignalVolume').value;
            const followPercentages = document.getElementById('executionFollowPercentages').value;
            
            // 验证必填字段
            if (!customerUid || !signalSource || !symbol || !posSide || !signalPrice || !signalVolume) {
                this.showToast('错误', '请填写所有必填字段', 'danger');
                return;
            }
            
            // 解析跟单百分比
            const percentages = followPercentages.split(',').map(p => parseFloat(p.trim())).filter(p => !isNaN(p));
            if (percentages.length === 0) {
                this.showToast('错误', '请输入有效的跟单百分比', 'danger');
                return;
            }
            
            // 准备请求数据
            const requestData = {
                trader_unique_name: signalSource, // 使用信号源作为跟单员
                customer_uid: customerUid,
                symbol: symbol,
                pos_side: posSide,
                signal_price: parseFloat(signalPrice),
                signal_volume: parseFloat(signalVolume),
                follow_percentages: percentages
            };
            
            // 显示加载状态
            this.showToast('信息', '正在执行限价跟单...', 'info');
            
            // 发送请求
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/execute`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData)
            });
            
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.showToast('成功', `成功创建 ${result.data.orders.length} 个跟单订单`, 'success');
                    
                    // 关闭模态框
                    const modal = bootstrap.Modal.getInstance(document.getElementById('executeLimitFollowModal'));
                    modal.hide();
                    
                    // 清空表单
                    document.getElementById('executeLimitFollowForm').reset();
                    
                    // 刷新相关数据
                    this.loadLimitFollowOrders();
                } else {
                    this.showToast('错误', result.message || '执行跟单失败', 'danger');
                }
            } else {
                const errorText = await response.text();
                console.error('执行跟单失败:', response.status, errorText);
                this.showToast('错误', `执行跟单失败: ${response.status}`, 'danger');
            }
            
        } catch (error) {
            console.error('提交执行跟单失败:', error);
            this.showToast('错误', `提交执行跟单失败: ${error.message}`, 'danger');
        }
    }

    // ==================== 跟单员管理 ====================
    
    async loadLimitFollowTraders() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/traders`);
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
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">暂无跟单员数据</td></tr>';
            return;
        }
        
        traders.forEach(trader => {
            const collectorType = trader.collector_type || 'okx';
            let collectorTypeBadge = '';
            if (collectorType === 'okx') {
                collectorTypeBadge = '<span class="badge bg-primary"><i class="bi bi-exchange"></i> OKX</span>';
            } else if (collectorType === 'binance') {
                collectorTypeBadge = '<span class="badge bg-warning text-dark"><i class="bi bi-currency-bitcoin"></i> Binance</span>';
            } else {
                collectorTypeBadge = `<span class="badge bg-secondary">${collectorType}</span>`;
            }
            
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><code>${trader.unique_name}</code></td>
                <td>${trader.name}</td>
                <td>${collectorTypeBadge}</td>
                <td>${trader.description || '-'}</td>
                <td>
                    <span class="badge ${trader.enabled ? 'bg-success' : 'bg-secondary'}">
                        ${trader.enabled ? '启用' : '禁用'}
                    </span>
                </td>
                <td>${this.formatDateTime(trader.created_at)}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary edit-limit-follow-trader" 
                            data-trader-id="${trader.id}" title="编辑">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-warning toggle-limit-follow-trader" 
                            data-trader-id="${trader.id}" title="${trader.enabled ? '禁用' : '启用'}">
                        <i class="bi bi-${trader.enabled ? 'pause' : 'play'}"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger delete-limit-follow-trader" 
                            data-trader-id="${trader.id}" title="删除">
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
        
        // 重置编辑状态
        this.editingTraderId = null;
        
        // 修改模态框标题
        document.querySelector('#addLimitFollowTraderModal .modal-title').innerHTML = '<i class="bi bi-person-plus"></i> 新建跟单员';
        
        // 初始化采集器类型（默认OKX）
        document.getElementById('traderCollectorType').value = 'okx';
        this.onTraderCollectorTypeChange();
        
        // 显示模态框
        const modal = new bootstrap.Modal(document.getElementById('addLimitFollowTraderModal'));
        modal.show();
    }
    
    async saveLimitFollowTrader() {
        try {
            const formData = this.getLimitFollowTraderFormData();
            
            let response;
            if (this.editingTraderId) {
                // 编辑模式
                response = await fetch(`${this.apiBaseUrl}/limit-follow/traders/${this.editingTraderId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(formData)
                });
            } else {
                // 创建模式
                response = await fetch(`${this.apiBaseUrl}/limit-follow/traders`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(formData)
                });
            }
            
            if (response.ok) {
                const result = await response.json();
                if (result.success || result.success === 200) {
                    const message = this.editingTraderId ? '跟单员更新成功' : '跟单员创建成功';
                    this.showToast('成功', message, 'success');
                    
                    // 关闭模态框
                    const modal = bootstrap.Modal.getInstance(document.getElementById('addLimitFollowTraderModal'));
                    modal.hide();
                    
                    // 重置编辑状态
                    this.editingTraderId = null;
                    
                    // 重新加载数据
                    this.loadLimitFollowTraders();
                } else {
                    this.showToast('错误', result.message, 'error');
                }
            } else {
                const errorData = await response.json();
                this.showToast('错误', errorData.message || '操作失败', 'error');
            }
        } catch (error) {
            console.error('保存跟单员失败:', error);
            this.showToast('错误', '保存跟单员失败', 'error');
        }
    }
    
    // 采集器类型改变时的处理
    onTraderCollectorTypeChange() {
        const collectorType = document.getElementById('traderCollectorType').value;
        const okxGroup = document.getElementById('okxIdentifierGroup');
        const binanceGroup = document.getElementById('binanceIdentifierGroup');
        const okxConfig = document.getElementById('okxCollectorConfig');
        const binanceConfig = document.getElementById('binanceCollectorConfig');
        
        // 显示/隐藏标识符输入框
        if (collectorType === 'okx') {
            okxGroup.style.display = 'block';
            binanceGroup.style.display = 'none';
            okxConfig.style.display = 'block';
            binanceConfig.style.display = 'none';
            
            // 设置必填属性
            document.getElementById('traderUniqueName').required = true;
            document.getElementById('traderPortfolioId').required = false;
        } else if (collectorType === 'binance') {
            okxGroup.style.display = 'none';
            binanceGroup.style.display = 'block';
            okxConfig.style.display = 'none';
            binanceConfig.style.display = 'block';
            
            // 设置必填属性
            document.getElementById('traderUniqueName').required = false;
            document.getElementById('traderPortfolioId').required = true;
        }
    }
    
    getLimitFollowTraderFormData() {
        const collectorType = document.getElementById('traderCollectorType').value;
        
        // 根据采集器类型获取标识符
        let uniqueName = '';
        if (collectorType === 'okx') {
            uniqueName = document.getElementById('traderUniqueName').value;
        } else if (collectorType === 'binance') {
            uniqueName = document.getElementById('traderPortfolioId').value;
        }
        
        // 构建采集器配置
        const collectorConfig = {};
        if (collectorType === 'okx') {
            const apiBaseUrl = document.getElementById('okxApiBaseUrl').value.trim();
            const timeout = document.getElementById('okxTimeout').value;
            if (apiBaseUrl) collectorConfig.api_base_url = apiBaseUrl;
            if (timeout) collectorConfig.timeout = parseInt(timeout);
        } else if (collectorType === 'binance') {
            const apiBaseUrl = document.getElementById('binanceApiBaseUrl').value.trim();
            const timeout = document.getElementById('binanceTimeout').value;
            const defaultDays = document.getElementById('binanceDefaultDays').value;
            if (apiBaseUrl) collectorConfig.api_base_url = apiBaseUrl;
            if (timeout) collectorConfig.timeout = parseInt(timeout);
            if (defaultDays) collectorConfig.default_days = parseInt(defaultDays);
        }
        
        return {
            unique_name: uniqueName,
            name: document.getElementById('traderName').value,
            description: document.getElementById('traderDescription').value,
            collector_type: collectorType,
            collector_config: Object.keys(collectorConfig).length > 0 ? collectorConfig : null,
            enabled: document.getElementById('traderEnabled').checked
        };
    }
    
    // 编辑限价跟单员
    async editLimitFollowTrader(traderId) {
        // 防止重复点击
        if (this.isEditingTrader) {
            this.showToast('提示', '正在处理中，请稍候...', 'info');
            return;
        }
        
        this.isEditingTrader = true;
        
        try {
            // 显示加载状态
            this.showToast('信息', '正在加载跟单员数据...', 'info');
            
            // 添加超时控制
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000); // 10秒超时
            
            // 获取跟单员数据
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/traders/${traderId}`, {
                signal: controller.signal,
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                this.showToast('错误', '获取跟单员数据失败', 'danger');
                return;
            }
            
            const result = await response.json();
            if (result.success !== 200) {
                this.showToast('错误', result.message || '获取跟单员数据失败', 'danger');
                return;
            }
            
            const trader = result.data;
            
            // 设置采集器类型
            const collectorType = trader.collector_type || 'okx';
            document.getElementById('traderCollectorType').value = collectorType;
            this.onTraderCollectorTypeChange();
            
            // 填充基础表单数据
            document.getElementById('traderName').value = trader.name || '';
            document.getElementById('traderDescription').value = trader.description || '';
            document.getElementById('traderEnabled').checked = trader.enabled !== false;
            
            // 根据采集器类型填充标识符
            if (collectorType === 'okx') {
                document.getElementById('traderUniqueName').value = trader.unique_name || '';
            } else if (collectorType === 'binance') {
                document.getElementById('traderPortfolioId').value = trader.unique_name || '';
            }
            
            // 填充采集器配置
            const collectorConfig = trader.collector_config || {};
            if (collectorType === 'okx') {
                if (collectorConfig.api_base_url) {
                    document.getElementById('okxApiBaseUrl').value = collectorConfig.api_base_url;
                }
                if (collectorConfig.timeout) {
                    document.getElementById('okxTimeout').value = collectorConfig.timeout;
                }
            } else if (collectorType === 'binance') {
                if (collectorConfig.api_base_url) {
                    document.getElementById('binanceApiBaseUrl').value = collectorConfig.api_base_url;
                }
                if (collectorConfig.timeout) {
                    document.getElementById('binanceTimeout').value = collectorConfig.timeout;
                }
                if (collectorConfig.default_days) {
                    document.getElementById('binanceDefaultDays').value = collectorConfig.default_days;
                }
            }
            
            // 修改模态框标题
            document.querySelector('#addLimitFollowTraderModal .modal-title').innerHTML = '<i class="bi bi-pencil"></i> 编辑跟单员';
            
            // 显示模态框
            const modal = new bootstrap.Modal(document.getElementById('addLimitFollowTraderModal'));
            modal.show();
            
            // 存储编辑的ID
            this.editingTraderId = traderId;
            
        } catch (error) {
            if (error.name === 'AbortError') {
                this.showToast('错误', '请求超时，请重试', 'error');
            } else {
                console.error('编辑跟单员失败:', error);
                this.showToast('错误', '编辑跟单员失败', 'error');
            }
        } finally {
            // 重置编辑状态
            this.isEditingTrader = false;
        }
    }
    
    // 切换限价跟单员启用状态
    async toggleLimitFollowTrader(traderId) {
        // 防止重复点击
        if (this.isTogglingTrader) {
            this.showToast('提示', '正在处理中，请稍候...', 'info');
            return;
        }
        
        this.isTogglingTrader = true;
        
        try {
            // 显示加载状态
            this.showToast('信息', '正在切换状态...', 'info');
            
            // 添加超时控制
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 8000); // 8秒超时
            
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/traders/${traderId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    enabled: 'toggle' // 特殊值，后端会切换状态
                }),
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.showToast('成功', '跟单员状态切换成功', 'success');
                    // 重新加载跟单员列表
                    this.loadLimitFollowTraders();
                } else {
                    console.error('切换跟单员状态失败:', result.message);
                    this.showToast('错误', result.message, 'error');
                }
            } else {
                const errorData = await response.json();
                console.error('切换跟单员状态失败:', errorData.message);
                this.showToast('错误', errorData.message, 'error');
            }
        } catch (error) {
            if (error.name === 'AbortError') {
                this.showToast('错误', '请求超时，请重试', 'error');
            } else {
                console.error('切换跟单员状态异常:', error);
                this.showToast('错误', '切换跟单员状态失败', 'error');
            }
        } finally {
            // 重置切换状态
            this.isTogglingTrader = false;
        }
    }
    
    // ==================== 热门带单员模块 ====================
    
    async loadPopularTraders() {
        try {
            const container = document.getElementById('popularTradersContainer');
            if (!container) return;
            
            // 显示加载状态
            container.innerHTML = `
                <div class="col-12">
                    <div class="text-center py-5">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">加载中...</span>
                        </div>
                        <p class="mt-3 text-muted">正在加载热门带单员...</p>
                    </div>
                </div>
            `;
            
            // 获取筛选参数
            const exchange = document.getElementById('popularTradersExchange')?.value || 'all';
            const sortBy = document.getElementById('popularTradersSortBy')?.value || 'yield_ratio';
            const limitValue = document.getElementById('popularTradersLimit')?.value || '';
            const limit = limitValue ? parseInt(limitValue) : undefined; // 如果为空字符串，则不传limit参数
            const fetchAll = document.getElementById('popularTradersFetchAll')?.checked !== false; // 默认获取所有数据
            
            // 更新加载提示
            if (fetchAll) {
                container.innerHTML = `
                    <div class="col-12">
                        <div class="text-center py-5">
                            <div class="spinner-border text-primary" role="status">
                                <span class="visually-hidden">加载中...</span>
                            </div>
                            <p class="mt-3 text-muted">正在获取所有热门带单员数据，请稍候...</p>
                            <small class="text-muted d-block mt-2">这可能需要几秒钟时间</small>
                        </div>
                    </div>
                `;
            }
            
            // 构建请求URL
            const params = new URLSearchParams({
                exchange: exchange,
                sort_by: sortBy,
                fetch_all: fetchAll ? 'true' : 'false'
            });
            
            // 只有当limit有值时才添加limit参数
            if (limit && limit > 0) {
                params.append('limit', limit);
            }
            
            const response = await this.apiRequest(`${this.apiBaseUrl}/popular-traders?${params}`);
            
            if (!response || !response.ok) {
                throw new Error('获取热门带单员失败');
            }
            
            const result = await response.json();
            
            if (result.success && result.data) {
                // 显示统计信息
                const totalCount = result.total || (Array.isArray(result.data) ? result.data.length : 
                    (result.data.okx?.length || 0) + (result.data.binance?.length || 0));
                
                // 更新页面标题显示总数
                const pageTitle = document.querySelector('#popular-traders-page h2');
                if (pageTitle && totalCount > 0) {
                    // 只保留原始的"热门带单员"文本，去掉之前可能添加的计数
                    const originalText = '热门带单员';
                    pageTitle.innerHTML = `<i class="bi bi-star-fill"></i> ${originalText} <small class="text-muted">(共 ${totalCount} 个)</small>`;
                }
                
                // 处理数据格式：如果是字典格式，需要合并成数组
                let tradersList = result.data;
                if (!Array.isArray(tradersList)) {
                    // 字典格式：{okx: [...], binance: [...]}
                    tradersList = [];
                    if (result.data.okx && Array.isArray(result.data.okx)) {
                        tradersList = tradersList.concat(result.data.okx);
                    }
                    if (result.data.binance && Array.isArray(result.data.binance)) {
                        tradersList = tradersList.concat(result.data.binance);
                    }
                }
                
                this.renderPopularTraders(tradersList);
            } else {
                throw new Error(result.message || '获取热门带单员失败');
            }
            
        } catch (error) {
            console.error('加载热门带单员失败:', error);
            const container = document.getElementById('popularTradersContainer');
            if (container) {
                container.innerHTML = `
                    <div class="col-12">
                        <div class="alert alert-danger">
                            <i class="bi bi-exclamation-triangle"></i> 加载热门带单员失败: ${error.message}
                        </div>
                    </div>
                `;
            }
            this.showToast('错误', '加载热门带单员失败', 'error');
        }
    }
    
    renderPopularTraders(traders) {
        const container = document.getElementById('popularTradersContainer');
        if (!container) return;
        
        if (!traders || traders.length === 0) {
            container.innerHTML = `
                <div class="col-12">
                    <div class="alert alert-info text-center">
                        <i class="bi bi-info-circle"></i> 暂无热门带单员数据
                    </div>
                </div>
            `;
            return;
        }
        
        container.innerHTML = '';
        
        traders.forEach((trader, index) => {
            const source = trader.source || 'unknown';
            const exchangeBadge = source === 'okx' 
                ? '<span class="badge bg-primary"><i class="bi bi-exchange"></i> OKX</span>'
                : source === 'binance'
                ? '<span class="badge bg-warning text-dark"><i class="bi bi-currency-bitcoin"></i> Binance</span>'
                : '<span class="badge bg-secondary">未知</span>';
            
            const tierInfo = trader.tier || {};
            const tierBadge = tierInfo.name 
                ? `<span class="badge bg-info">${tierInfo.name}</span>`
                : '';
            
            const yieldColor = trader.yield_ratio >= 0 ? 'text-success' : 'text-danger';
            const yieldIcon = trader.yield_ratio >= 0 ? '↑' : '↓';
            
            const instruments = trader.instruments || [];
            const instrumentsList = instruments.slice(0, 4).map(inst => {
                const name = inst.name || inst.instId || inst;
                return `<span class="badge bg-light text-dark me-1">${name}</span>`;
            }).join('');
            
            const traderCard = document.createElement('div');
            traderCard.className = 'col-md-6 col-lg-4 mb-4';
            traderCard.innerHTML = `
                <div class="card h-100 trader-card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <div class="d-flex align-items-center">
                            ${trader.portrait ? `<img src="${trader.portrait}" class="rounded-circle me-2" style="width: 40px; height: 40px; object-fit: cover;" onerror="this.style.display='none'">` : ''}
                            <div>
                                <h6 class="mb-0">${trader.nick_name || '未知'}</h6>
                                <small class="text-muted"><code>${trader.unique_name}</code></small>
                            </div>
                        </div>
                        ${exchangeBadge}
                    </div>
                    <div class="card-body">
                        <div class="row g-2 mb-3">
                            <div class="col-6">
                                <div class="text-center p-2 bg-light rounded">
                                    <div class="small text-muted">收益率</div>
                                    <div class="h5 mb-0 ${yieldColor}">
                                        ${yieldIcon} ${this.formatPercentage(trader.yield_ratio)}%
                                    </div>
                                </div>
                            </div>
                            <div class="col-6">
                                <div class="text-center p-2 bg-light rounded">
                                    <div class="small text-muted">胜率</div>
                                    <div class="h5 mb-0">${this.formatPercentage(trader.win_ratio, 1)}%</div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="mb-3">
                            <div class="d-flex justify-content-between mb-1">
                                <span class="small text-muted">管理资产 (AUM)</span>
                                <strong>${this.formatNumber(trader.aum)} USDT</strong>
                            </div>
                            <div class="d-flex justify-content-between mb-1">
                                <span class="small text-muted">总盈亏</span>
                                <strong class="${trader.pnl >= 0 ? 'text-success' : 'text-danger'}">
                                    ${trader.pnl >= 0 ? '+' : ''}${this.formatNumber(trader.pnl)} USDT
                                </strong>
                            </div>
                            <div class="d-flex justify-content-between mb-1">
                                <span class="small text-muted">跟单人数</span>
                                <strong>${trader.follower_num} / ${trader.follower_limit || '∞'}</strong>
                            </div>
                            ${trader.lever > 0 ? `
                            <div class="d-flex justify-content-between">
                                <span class="small text-muted">杠杆</span>
                                <strong>${trader.lever}x</strong>
                            </div>
                            ` : ''}
                        </div>
                        
                        ${instruments.length > 0 ? `
                        <div class="mb-3">
                            <div class="small text-muted mb-1">交易对</div>
                            <div>${instrumentsList}${instruments.length > 4 ? '...' : ''}</div>
                        </div>
                        ` : ''}
                        
                        ${tierBadge ? `
                        <div class="mb-3">
                            ${tierBadge}
                        </div>
                        ` : ''}
                    </div>
                    <div class="card-footer bg-transparent">
                        <div class="d-grid gap-2">
                            <button class="btn btn-primary btn-sm add-to-limit-follow" 
                                    data-trader="${JSON.stringify(trader).replace(/"/g, '&quot;')}">
                                <i class="bi bi-arrow-repeat"></i> 添加到跟单交易
                            </button>
                        </div>
                    </div>
                </div>
            `;
            
            container.appendChild(traderCard);
        });
    }
    
    async addPopularTraderToLimitFollow(trader) {
        try {
            // 检查带单员是否已存在
            const response = await this.apiRequest(`${this.apiBaseUrl}/limit-follow/traders`);
            if (response && response.ok) {
                const result = await response.json();
                if (result.success && result.data) {
                    const existing = result.data.find(t => t.unique_name === trader.unique_name);
                    if (existing) {
                        this.showToast('提示', '该带单员已存在，正在跳转到限价跟单页面...', 'info');
                        setTimeout(() => {
                            this.navigateToPage('limit-follow');
                        }, 1500);
                        return;
                    }
                }
            }
            
            // 构建带单员数据
            const traderData = {
                unique_name: trader.unique_name,
                name: trader.nick_name || `热门带单员-${trader.unique_name.substring(0, 8)}`,
                description: `来自${trader.source === 'okx' ? 'OKX' : 'Binance'}的热门带单员，收益率${(trader.yield_ratio * 100).toFixed(2)}%，胜率${(trader.win_ratio * 100).toFixed(1)}%`,
                collector_type: trader.source || 'okx',
                collector_config: null,
                enabled: true
            };
            
            // 创建带单员
            const createResponse = await this.apiRequest(`${this.apiBaseUrl}/limit-follow/traders`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(traderData)
            });
            
            if (createResponse && createResponse.ok) {
                const createResult = await createResponse.json();
                if (createResult.success || createResult.success === 200) {
                    this.showToast('成功', '已添加到跟单交易，正在跳转...', 'success');
                    setTimeout(() => {
                        this.navigateToPage('limit-follow');
                        // 刷新限价跟单数据
                        this.loadLimitFollowTraders();
                    }, 1000);
                } else {
                    throw new Error(createResult.message || '添加失败');
                }
            } else {
                throw new Error('添加带单员失败');
            }
            
        } catch (error) {
            console.error('添加到跟单交易失败:', error);
            this.showToast('错误', `添加到跟单交易失败: ${error.message}`, 'error');
        }
    }
    
    async addPopularTraderToMarketFollow(trader) {
        try {
            // 市价跟单功能（如果存在）
            // 这里可以调用市价跟单的API
            this.showToast('提示', '市价跟单功能开发中，将先添加到限价跟单...', 'info');
            
            // TODO: 实现市价跟单添加逻辑
            // 可以先添加到限价跟单，然后提示用户
            await this.addPopularTraderToLimitFollow(trader);
            
        } catch (error) {
            console.error('添加到市价跟单失败:', error);
            this.showToast('错误', `添加到市价跟单失败: ${error.message}`, 'error');
        }
    }
    
    formatNumber(num) {
        if (num === null || num === undefined) return '0.00';
        const n = parseFloat(num);
        if (isNaN(n)) return '0.00';
        if (Math.abs(n) >= 1000000) {
            return (n / 1000000).toFixed(2) + 'M';
        } else if (Math.abs(n) >= 1000) {
            return (n / 1000).toFixed(2) + 'K';
        }
        return n.toFixed(2);
    }
    
    formatPercentage(value, decimals = 2) {
        if (value === null || value === undefined) return '0.00';
        const num = parseFloat(value);
        if (isNaN(num)) return '0.00';
        
        // 如果数值大于1，说明已经是百分比形式（如1205.38），直接格式化
        // 如果数值小于等于1，说明是小数形式（如0.120538），需要乘以100
        if (Math.abs(num) > 1) {
            return num.toFixed(decimals);
        } else {
            return (num * 100).toFixed(decimals);
        }
    }

    // ==================== Hyperliquid跟单模块 ====================
    
    async loadHyperliquidTraders() {
        try {
            const container = document.getElementById('hyperliquidTradersContainer');
            if (!container) return;
            
            // 显示加载状态
            container.innerHTML = `
                <div class="col-12">
                    <div class="text-center py-5">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">加载中...</span>
                        </div>
                        <p class="mt-3 text-muted">正在加载Hyperliquid交易员...</p>
                    </div>
                </div>
            `;
            
            // 获取筛选参数
            const sortBy = document.getElementById('hyperliquidSortBy')?.value || 'pnl';
            const limitValue = document.getElementById('hyperliquidLimit')?.value || '';
            const limit = limitValue ? parseInt(limitValue) : undefined;
            const useCache = document.getElementById('hyperliquidUseCache')?.checked !== false;
            
            // 构建请求URL
            const params = new URLSearchParams({
                exchange: 'hyperliquid',
                sort_by: sortBy,
                use_cache: useCache ? 'true' : 'false'
            });
            
            if (limit && limit > 0) {
                params.append('limit', limit);
            }
            
            const response = await this.apiRequest(`${this.apiBaseUrl}/popular-traders?${params}`);
            
            if (!response || !response.ok) {
                throw new Error('获取Hyperliquid交易员失败');
            }
            
            const result = await response.json();
            
            if (result.success && result.data) {
                // 处理数据格式
                let tradersList = [];
                if (result.data.hyperliquid && Array.isArray(result.data.hyperliquid)) {
                    tradersList = result.data.hyperliquid;
                } else if (Array.isArray(result.data)) {
                    tradersList = result.data;
                }
                
                // 显示统计信息
                const totalCount = tradersList.length;
                const pageTitle = document.querySelector('#hyperliquid-discovery-page h2');
                if (pageTitle && totalCount > 0) {
                    pageTitle.innerHTML = `<i class="bi bi-compass"></i> Hyperliquid交易员发现 <small class="text-muted">(共 ${totalCount} 个)</small>`;
                }
                
                this.renderHyperliquidTraders(tradersList);
            } else {
                throw new Error(result.message || '获取Hyperliquid交易员失败');
            }
            
        } catch (error) {
            console.error('加载Hyperliquid交易员失败:', error);
            const container = document.getElementById('hyperliquidTradersContainer');
            if (container) {
                container.innerHTML = `
                    <div class="col-12">
                        <div class="alert alert-danger">
                            <i class="bi bi-exclamation-triangle"></i> 加载Hyperliquid交易员失败: ${error.message}
                        </div>
                    </div>
                `;
            }
            this.showToast('错误', '加载Hyperliquid交易员失败', 'error');
        }
    }
    
    renderHyperliquidTraders(traders) {
        const container = document.getElementById('hyperliquidTradersContainer');
        if (!container) return;
        
        if (!traders || traders.length === 0) {
            container.innerHTML = `
                <div class="col-12">
                    <div class="alert alert-info text-center">
                        <i class="bi bi-info-circle"></i> 暂无Hyperliquid交易员数据
                    </div>
                </div>
            `;
            return;
        }
        
        container.innerHTML = '';
        
        traders.forEach((trader, index) => {
            const exchangeBadge = '<span class="badge bg-info"><i class="bi bi-lightning-charge"></i> Hyperliquid</span>';
            
            const yieldColor = trader.yield_ratio >= 0 ? 'text-success' : 'text-danger';
            const yieldIcon = trader.yield_ratio >= 0 ? '↑' : '↓';
            
            const traderCard = document.createElement('div');
            traderCard.className = 'col-md-6 col-lg-4 mb-4';
            traderCard.innerHTML = `
                <div class="card h-100 trader-card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <div class="d-flex align-items-center">
                            ${trader.portrait ? `<img src="${trader.portrait}" class="rounded-circle me-2" style="width: 40px; height: 40px; object-fit: cover;" onerror="this.style.display='none'">` : ''}
                            <div>
                                <h6 class="mb-0">${trader.nick_name || '未知'}</h6>
                                <small class="text-muted"><code>${trader.unique_name.substring(0, 10)}...</code></small>
                            </div>
                        </div>
                        ${exchangeBadge}
                    </div>
                    <div class="card-body">
                        <div class="row g-2 mb-3">
                            <div class="col-6">
                                <div class="text-center p-2 bg-light rounded">
                                    <div class="small text-muted">收益率</div>
                                    <div class="h5 mb-0 ${yieldColor}">
                                        ${yieldIcon} ${this.formatPercentage(trader.yield_ratio)}%
                                    </div>
                                </div>
                            </div>
                            <div class="col-6">
                                <div class="text-center p-2 bg-light rounded">
                                    <div class="small text-muted">胜率</div>
                                    <div class="h5 mb-0">${this.formatPercentage(trader.win_ratio, 1)}%</div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="mb-3">
                            <div class="d-flex justify-content-between mb-1">
                                <span class="small text-muted">管理资产 (AUM)</span>
                                <strong>${this.formatNumber(trader.aum)} USDC</strong>
                            </div>
                            <div class="d-flex justify-content-between mb-1">
                                <span class="small text-muted">总盈亏</span>
                                <strong class="${trader.pnl >= 0 ? 'text-success' : 'text-danger'}">
                                    ${trader.pnl >= 0 ? '+' : ''}${this.formatNumber(trader.pnl)} USDC
                                </strong>
                            </div>
                            <div class="d-flex justify-content-between mb-1">
                                <span class="small text-muted">跟单人数</span>
                                <strong>${trader.follower_num} / ${trader.follower_limit || '∞'}</strong>
                            </div>
                            ${trader.lever > 0 ? `
                            <div class="d-flex justify-content-between">
                                <span class="small text-muted">杠杆</span>
                                <strong>${trader.lever}x</strong>
                            </div>
                            ` : ''}
                        </div>
                    </div>
                    <div class="card-footer bg-transparent">
                        <div class="d-grid gap-2">
                            <button class="btn btn-primary btn-sm add-hyperliquid-follow" 
                                    data-trader='${JSON.stringify(trader).replace(/"/g, '&quot;')}'>
                                <i class="bi bi-arrow-repeat"></i> 创建跟单
                            </button>
                        </div>
                    </div>
                </div>
            `;
            
            container.appendChild(traderCard);
        });
    }
    
    async loadHyperliquidFollow() {
        try {
            // TODO: 实现加载Hyperliquid跟单策略列表
            this.showToast('提示', 'Hyperliquid跟单管理功能开发中...', 'info');
        } catch (error) {
            console.error('加载Hyperliquid跟单失败:', error);
            this.showToast('错误', '加载Hyperliquid跟单失败', 'error');
        }
    }
    
    async addHyperliquidFollow(trader) {
        try {
            this.showToast('提示', 'Hyperliquid跟单功能开发中，正在跳转到跟单管理...', 'info');
            setTimeout(() => {
                this.navigateToPage('hyperliquid-follow');
            }, 1000);
        } catch (error) {
            console.error('添加Hyperliquid跟单失败:', error);
            this.showToast('错误', `添加Hyperliquid跟单失败: ${error.message}`, 'error');
        }
    }
    
    showAddHyperliquidFollowModal() {
        this.showToast('提示', 'Hyperliquid跟单功能开发中...', 'info');
    }

    // ==================== 限价跟单监控功能 ====================
    
    async loadLimitFollowHealth() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/health`);
            const result = await response.json();
            
            if (result.success === 200) {
                this.updateLimitFollowHealthStatus(result.data);
            } else {
                console.error('获取健康状态失败:', result.message);
            }
            
        } catch (error) {
            console.error('获取限价跟单健康状态失败:', error);
        }
    }

    updateLimitFollowHealthStatus(health) {
        // 更新健康状态显示
        const statusElement = document.getElementById('limitFollowHealthStatus');
        if (statusElement) {
            let statusClass = '';
            let statusIcon = '';
            
            switch (health.overall_status) {
                case 'healthy':
                    statusClass = 'text-success';
                    statusIcon = 'fas fa-check-circle';
                    break;
                case 'warning':
                    statusClass = 'text-warning';
                    statusIcon = 'fas fa-exclamation-triangle';
                    break;
                case 'error':
                    statusClass = 'text-danger';
                    statusIcon = 'fas fa-times-circle';
                    break;
                default:
                    statusClass = 'text-secondary';
                    statusIcon = 'fas fa-question-circle';
            }
            
            statusElement.innerHTML = `
                <div class="d-flex align-items-center">
                    <i class="${statusIcon} ${statusClass} me-2"></i>
                    <div>
                        <span class="${statusClass} fw-bold">${health.overall_status.toUpperCase()}</span>
                        <small class="d-block text-muted">
                            健康评分: ${health.health_score}/100 | 
                            异常订单: ${health.problematic_orders} | 
                            最近更新: ${health.recent_updates}
                        </small>
                    </div>
                </div>
            `;
        }
        
        // 更新监控指标
        this.updateLimitFollowMetrics(health);
        
        // 显示建议
        this.showLimitFollowRecommendations(health.recommendations);
    }

    updateLimitFollowMetrics(health) {
        // 更新服务状态
        const serviceStatusElement = document.getElementById('limitFollowServiceStatus');
        if (serviceStatusElement) {
            const statusText = health.service_running ? '运行中' : '已停止';
            const statusClass = health.service_running ? 'text-success' : 'text-danger';
            serviceStatusElement.innerHTML = `<span class="${statusClass}">${statusText}</span>`;
        }
        
        // 更新订单统计
        if (health.orders_summary) {
            this.updateElement('limitFollowTotal24h', health.orders_summary.total_24h || 0);
            this.updateElement('limitFollowLiveCount', health.orders_summary.live || 0);
            this.updateElement('limitFollowFilledCount', health.orders_summary.filled || 0);
            this.updateElement('limitFollowPendingCount', health.orders_summary.pending || 0);
        }
        
        // 更新监控指标
        if (health.metrics) {
            this.updateElement('limitFollowSuccessRate', `${health.metrics.success_rate.toFixed(1)}%`);
            this.updateElement('limitFollowOrdersChecked', health.metrics.orders_checked || 0);
            this.updateElement('limitFollowOrdersUpdated', health.metrics.orders_updated || 0);
            this.updateElement('limitFollowConsecutiveFailures', health.metrics.consecutive_failures || 0);
        }
    }

    showLimitFollowRecommendations(recommendations) {
        const recommendationsElement = document.getElementById('limitFollowRecommendations');
        if (recommendationsElement && recommendations && recommendations.length > 0) {
            const recommendationsList = recommendations.map(rec => 
                `<li class="list-group-item"><i class="fas fa-lightbulb text-warning me-2"></i>${rec}</li>`
            ).join('');
            
            recommendationsElement.innerHTML = `
                <div class="alert alert-warning">
                    <h6><i class="fas fa-exclamation-triangle me-2"></i>系统建议</h6>
                    <ul class="list-group list-group-flush">
                        ${recommendationsList}
                    </ul>
                </div>
            `;
            recommendationsElement.style.display = 'block';
        } else if (recommendationsElement) {
            recommendationsElement.style.display = 'none';
        }
    }

    async syncLimitFollowStatus(forceSync = false) {
        try {
            this.showToast('信息', '正在同步订单状态...', 'info');
            
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/sync-status`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    force_sync: forceSync,
                    max_orders: 100
                })
            });
            
            const result = await response.json();
            
            if (result.success === 200) {
                const data = result.data;
                this.showToast('成功', 
                    `订单状态同步完成！检查: ${data.total_checked}, 更新: ${data.updated_count}, 错误: ${data.error_count}, 耗时: ${data.duration.toFixed(2)}秒`, 
                    'success'
                );
                
                // 刷新相关数据
                await this.loadLimitFollowOrders();
                await this.loadLimitFollowHealth();
                
            } else {
                this.showToast('错误', result.message || '同步失败', 'error');
            }
            
        } catch (error) {
            console.error('同步订单状态失败:', error);
            this.showToast('错误', '同步订单状态失败', 'error');
        }
    }

    async loadLimitFollowMetrics() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/metrics`);
            const result = await response.json();
            
            if (result.success === 200) {
                this.displayLimitFollowMetrics(result.data);
            } else {
                console.error('获取监控指标失败:', result.message);
            }
            
        } catch (error) {
            console.error('获取限价跟单监控指标失败:', error);
        }
    }

    displayLimitFollowMetrics(metrics) {
        // 显示详细的监控指标
        if (metrics.order_statistics) {
            const stats = metrics.order_statistics;
            
            // 更新订单统计图表（如果有的话）
            if (window.limitFollowChart) {
                window.limitFollowChart.data.datasets[0].data = [
                    stats.filled_orders,
                    stats.canceled_orders,
                    stats.rejected_orders,
                    stats.live_orders,
                    stats.pending_orders
                ];
                window.limitFollowChart.update();
            }
            
            // 更新统计数据显示
            this.updateElement('metricsSuccessRate', `${stats.success_rate}%`);
            this.updateElement('metricsAvgFillPrice', `$${stats.average_fill_price.toFixed(2)}`);
            this.updateElement('metricsTotalVolume', stats.total_filled_volume.toFixed(4));
        }
        
        if (metrics.strategy_statistics) {
            const strategyStats = metrics.strategy_statistics;
            this.updateElement('metricsTotalStrategies', strategyStats.total_strategies);
            this.updateElement('metricsActiveStrategies', strategyStats.active_strategies);
        }
    }

    updateElement(elementId, value) {
        const element = document.getElementById(elementId);
        if (element) {
            element.textContent = value;
        }
    }

    initLimitFollowMonitoringChart() {
        // 初始化监控图表
        const chartCanvas = document.getElementById('limitFollowOrderChart');
        if (chartCanvas) {
            const ctx = chartCanvas.getContext('2d');
            window.limitFollowChart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['已成交', '已取消', '已拒绝', '活跃中', '待处理'],
                    datasets: [{
                        data: [0, 0, 0, 0, 0],
                        backgroundColor: [
                            '#28a745',
                            '#dc3545',
                            '#fd7e14',
                            '#007bff',
                            '#6c757d'
                        ]
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: {
                            position: 'bottom'
                        },
                        title: {
                            display: true,
                            text: '订单状态分布'
                        }
                    }
                }
            });
        }
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
    
    // 处理跟单模式切换
    handleFollowModeChange() {
        const followMode = document.getElementById('limitFollowMode').value;
        const traderModeConfig = document.getElementById('traderModeConfig');
        const signalModeConfig = document.getElementById('signalModeConfig');
        
        // 隐藏所有配置
        traderModeConfig.style.display = 'none';
        signalModeConfig.style.display = 'none';
        
        if (followMode === 'trader') {
            // 跟单员模式
            traderModeConfig.style.display = 'block';
            this.populateTraderModeOptions();
        } else if (followMode === 'signal') {
            // 信号源模式
            signalModeConfig.style.display = 'block';
            this.populateSignalModeOptions();
        }
    }
    
    // 填充跟单员模式的选项
    populateTraderModeOptions() {
        // 客户选择框：包含普通客户和信号源
        const customerSelect = document.getElementById('limitFollowStrategyCustomers');
        if (customerSelect) {
            // 清空现有选项
            customerSelect.innerHTML = '';
            
            // 添加普通客户
            if (this.customersData && this.customersData.length > 0) {
                // 添加分隔符
                const separator1 = document.createElement('option');
                separator1.disabled = true;
                separator1.textContent = '--- 普通客户账户 ---';
                customerSelect.appendChild(separator1);
                
                this.customersData.forEach(customer => {
                    const option = document.createElement('option');
                    option.value = customer.customer_uid;
                    option.textContent = `[客户] ${customer.name}`;
                    customerSelect.appendChild(option);
                });
            }
            
            // 添加信号源
            if (this.signalSourcesData && this.signalSourcesData.length > 0) {
                // 添加分隔符
                const separator2 = document.createElement('option');
                separator2.disabled = true;
                separator2.textContent = '--- 信号源账户 ---';
                customerSelect.appendChild(separator2);
                
                this.signalSourcesData.forEach(signalSource => {
                    const option = document.createElement('option');
                    option.value = signalSource.source_uid;
                    option.textContent = `[信号源] ${signalSource.name}`;
                    customerSelect.appendChild(option);
                });
            }
        }
    }
    
    // 填充信号源模式的选项
    populateSignalModeOptions() {
        // 跟单账户选择框：只包含普通客户
        const followCustomerSelect = document.getElementById('limitFollowStrategyFollowCustomers');
        if (followCustomerSelect && this.customersData) {
            followCustomerSelect.innerHTML = '';
            
            this.customersData.forEach(customer => {
                const option = document.createElement('option');
                option.value = customer.customer_uid;
                option.textContent = customer.name;
                followCustomerSelect.appendChild(option);
            });
        }
    }
    
    getLimitFollowFormData() {
        const followMode = document.getElementById('limitFollowMode').value;
        
        // 验证跟单模式
        if (!followMode) {
            this.showToast('错误', '请选择跟单模式', 'danger');
            return null;
        }
        
        // 将前端的模式值转换为后端期望的值
        const backendFollowMode = followMode === 'trader' ? 'follow_trader' : 'follow_signal_source';
        
        const formData = {
            strategy_name: document.getElementById('limitFollowStrategyName').value,
            follow_mode: backendFollowMode,
            follow_order_types: document.getElementById('followOrderTypes').value,
            limit_market_ratio: getLimitMarketRatio(), // 使用自定义函数获取比例
            pos_side: document.getElementById('limitFollowStrategyPosSide').value,
            follow_type: document.getElementById('limitFollowStrategyFollowType').value,
            follow_value: parseFloat(document.getElementById('limitFollowStrategyFollowValue').value),
            min_follow_value: parseFloat(document.getElementById('limitFollowStrategyMinFollowValue').value),
            max_follow_value: parseFloat(document.getElementById('limitFollowStrategyMaxFollowValue').value),
            max_orders_per_signal: parseInt(document.getElementById('limitFollowStrategyMaxOrdersPerSignal').value),
            leverage: parseInt(document.getElementById('limitFollowStrategyLeverage').value),
            max_net_leverage: parseFloat(document.getElementById('limitFollowStrategyMaxNetLeverage').value),
            proportional_position: document.getElementById('limitFollowStrategyProportionalPosition').checked,
            auto_cancel_on_signal_close: document.getElementById('limitFollowStrategyAutoCancelOnSignalClose').value === 'true',
            reverse_direction: document.getElementById('limitFollowStrategyReverseDirection').checked ?? false,  // 🆕 反向跟单
            enabled: document.getElementById('limitFollowStrategyEnabled').checked ?? true
        };
        
        // 根据跟单模式设置不同的字段
        if (followMode === 'trader') {
            // 跟单员模式
            formData.trader_unique_name = document.getElementById('limitFollowStrategyTrader').value;
            const customerSelect = document.getElementById('limitFollowStrategyCustomers');
            const selectedCustomers = Array.from(customerSelect.selectedOptions).map(option => option.value);
            
            if (!formData.trader_unique_name || selectedCustomers.length === 0) {
                this.showToast('错误', '跟单员模式下请选择跟单员和跟单账户', 'danger');
                return null;
            }
            
            formData.customer_uids = selectedCustomers;
        } else if (followMode === 'signal') {
            // 信号源模式 - 直接使用信号源UID作为trader_unique_name
            const signalSourceUid = document.getElementById('limitFollowStrategySignalSource').value;
            const customerSelect = document.getElementById('limitFollowStrategyFollowCustomers');
            const selectedCustomers = Array.from(customerSelect.selectedOptions).map(option => option.value);
            
            if (!signalSourceUid || selectedCustomers.length === 0) {
                this.showToast('错误', '信号源模式下请选择信号源和跟单账户', 'danger');
                return null;
            }
            
            // 直接使用信号源UID作为trader_unique_name，不添加前缀
            formData.trader_unique_name = signalSourceUid;
            formData.signal_source_uid = signalSourceUid; // 保留原始信号源UID用于前端识别
            formData.customer_uids = selectedCustomers;
        }
        
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
    
    // 管理策略客户
    async manageStrategyCustomers(strategyId) {
        try {
            this.currentStrategyId = strategyId;
            
            // 获取策略信息
            const strategyResponse = await fetch(`${this.apiBaseUrl}/limit-follow/strategies/${strategyId}`);
            if (!strategyResponse.ok) {
                console.error('[客户管理] 获取策略信息失败:', strategyResponse.status);
                this.showToast('错误', '获取策略信息失败', 'danger');
                return;
            }
            
            const strategyResult = await strategyResponse.json();
            
            if (strategyResult.success !== 200) {
                this.showToast('错误', strategyResult.message || '获取策略信息失败', 'danger');
                return;
            }
            
            const strategy = strategyResult.data;
            
            // 更新模态框标题
            document.querySelector('#manageStrategyCustomersModal .modal-title').textContent = 
                `管理策略客户 - ${strategy.strategy_name}`;
            
            // 加载策略客户列表
            await this.loadStrategyCustomers(strategyId);
            
            // 加载可添加的客户列表
            await this.loadAvailableCustomers(strategyId);
            
            // 显示模态框
            const modal = new bootstrap.Modal(document.getElementById('manageStrategyCustomersModal'));
            modal.show();
            
        } catch (error) {
            console.error('管理策略客户失败:', error);
            this.showToast('错误', '管理策略客户失败，请检查网络连接', 'danger');
        }
    }
    
    // 加载策略客户列表
    async loadStrategyCustomers(strategyId) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/strategies/${strategyId}/customers`);
            if (!response.ok) {
                console.error('获取策略客户列表失败:', response.status);
                return;
            }
            
            const result = await response.json();
            if (result.success === 200) {
                this.renderStrategyCustomersTable(result.data);
            } else {
                console.error('获取策略客户列表失败:', result.message);
            }
        } catch (error) {
            console.error('加载策略客户列表失败:', error);
        }
    }
    
    // 渲染策略客户表格
    renderStrategyCustomersTable(customers) {
        const tbody = document.querySelector('#strategyCustomersTable tbody');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        if (!customers || customers.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">暂无客户</td></tr>';
            return;
        }
        
        customers.forEach(customer => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${customer.customer_name || customer.customer_uid}</td>
                <td>
                    <span class="badge bg-${customer.enabled ? 'success' : 'secondary'}">
                        ${customer.enabled ? '启用' : '禁用'}
                    </span>
                </td>
                <td>${customer.custom_leverage || '使用默认'}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary" onclick="app.editStrategyCustomer(${this.currentStrategyId}, '${customer.customer_uid}')" title="编辑设置">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="app.removeCustomerFromStrategy(${this.currentStrategyId}, '${customer.customer_uid}')" title="移除客户">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
    }
    
    // 加载可添加的客户列表
    async loadAvailableCustomers(strategyId) {
        try {
            
            // 获取所有客户
            const customersResponse = await fetch(`${this.apiBaseUrl}/customers`);
            if (!customersResponse.ok) {
                console.error('获取客户列表失败:', customersResponse.status);
                this.showToast('错误', '获取客户列表失败', 'danger');
                return;
            }
            
            const customersResult = await customersResponse.json();
            
            if (customersResult.success !== 200) {
                console.error('获取客户列表失败:', customersResult.message);
                this.showToast('错误', customersResult.message || '获取客户列表失败', 'danger');
                return;
            }
            
            // 修复：客户数据在data.customers中
            const allCustomers = customersResult.data.customers || customersResult.data;
            
            if (!Array.isArray(allCustomers)) {
                console.error('[客户管理] 客户数据格式错误:', allCustomers);
                this.showToast('错误', '客户数据格式错误', 'danger');
                return;
            }
            
            // 获取策略已有客户
            const strategyCustomersResponse = await fetch(`${this.apiBaseUrl}/limit-follow/strategies/${strategyId}/customers`);
            if (!strategyCustomersResponse.ok) {
                console.error('获取策略客户失败:', strategyCustomersResponse.status);
                this.showToast('错误', '获取策略客户失败', 'danger');
                return;
            }
            
            const strategyCustomersResult = await strategyCustomersResponse.json();
            
            const existingCustomerUids = strategyCustomersResult.success === 200 
                ? strategyCustomersResult.data.map(c => c.customer_uid)
                : [];
            
            // 过滤掉已添加的客户
            const availableCustomers = allCustomers.filter(customer => 
                !existingCustomerUids.includes(customer.customer_uid)
            );
            
            
            // 填充下拉框
            const select = document.getElementById('addCustomerSelect');
            if (!select) {
                console.error('[客户管理] 找不到addCustomerSelect元素');
                return;
            }
            
            select.innerHTML = '<option value="">选择要添加的客户</option>';
            
            if (availableCustomers.length === 0) {
                const option = document.createElement('option');
                option.value = '';
                option.textContent = '没有可添加的客户';
                option.disabled = true;
                select.appendChild(option);
            } else {
                availableCustomers.forEach(customer => {
                    const option = document.createElement('option');
                    option.value = customer.customer_uid;
                    option.textContent = customer.name || customer.customer_uid;
                    select.appendChild(option);
                });
            }
            
        } catch (error) {
            console.error('加载可添加客户列表失败:', error);
            this.showToast('错误', '加载客户列表失败，请检查网络连接', 'danger');
        }
    }
    
    // 添加客户到策略
    async addCustomerToStrategy() {
        try {
            const customerUid = document.getElementById('addCustomerSelect').value;
            const customLeverage = document.getElementById('addCustomerLeverage').value;
            const customFollowValue = document.getElementById('addCustomerFollowValue').value;
            
            if (!customerUid) {
                this.showToast('错误', '请选择要添加的客户', 'danger');
                return;
            }
            
            const data = {
                customer_uid: customerUid
            };
            
            if (customLeverage) {
                data.custom_leverage = parseInt(customLeverage);
            }
            
            if (customFollowValue) {
                data.custom_follow_value = parseFloat(customFollowValue);
            }
            
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/strategies/${this.currentStrategyId}/customers`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data)
            });
            
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.showToast('成功', '客户添加成功', 'success');
                    
                    // 重新加载数据
                    await this.loadStrategyCustomers(this.currentStrategyId);
                    await this.loadAvailableCustomers(this.currentStrategyId);
                    
                    // 清空表单
                    document.getElementById('addCustomerSelect').value = '';
                    document.getElementById('addCustomerLeverage').value = '';
                    document.getElementById('addCustomerFollowValue').value = '';
                } else {
                    this.showToast('错误', result.message || '添加客户失败', 'danger');
                }
            } else {
                const errorText = await response.text();
                console.error('添加客户失败:', response.status, errorText);
                this.showToast('错误', `添加客户失败: ${response.status}`, 'danger');
            }
            
        } catch (error) {
            console.error('添加客户到策略失败:', error);
            this.showToast('错误', '添加客户失败，请检查网络连接', 'danger');
        }
    }
    
    // 编辑策略客户设置
    async editStrategyCustomer(strategyId, customerUid) {
        try {
            // 获取当前客户设置
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/strategies/${strategyId}/customers`);
            if (!response.ok) {
                this.showToast('错误', '获取客户设置失败', 'danger');
                return;
            }
            
            const result = await response.json();
            if (result.success !== 200) {
                this.showToast('错误', result.message || '获取客户设置失败', 'danger');
                return;
            }
            
            const customer = result.data.find(c => c.customer_uid === customerUid);
            if (!customer) {
                this.showToast('错误', '客户不存在', 'danger');
                return;
            }
            
            // 显示编辑对话框
            const enabled = confirm('是否启用此客户？');
            const customLeverage = prompt('自定义杠杆倍数（留空使用默认）:', customer.custom_leverage || '');
            const customFollowValue = prompt('自定义跟单值（留空使用默认）:', customer.custom_follow_value || '');
            
            const data = {
                enabled: enabled ? 1 : 0
            };
            
            if (customLeverage && customLeverage.trim() !== '') {
                data.custom_leverage = parseInt(customLeverage);
            }
            
            if (customFollowValue && customFollowValue.trim() !== '') {
                data.custom_follow_value = parseFloat(customFollowValue);
            }
            
            const updateResponse = await fetch(`${this.apiBaseUrl}/limit-follow/strategies/${strategyId}/customers/${customerUid}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data)
            });
            
            if (updateResponse.ok) {
                const updateResult = await updateResponse.json();
                if (updateResult.success === 200) {
                    this.showToast('成功', '客户设置更新成功', 'success');
                    // 重新加载数据
                    await this.loadStrategyCustomers(strategyId);
                } else {
                    this.showToast('错误', updateResult.message || '更新客户设置失败', 'danger');
                }
            } else {
                this.showToast('错误', '更新客户设置失败', 'danger');
            }
            
        } catch (error) {
            console.error('编辑策略客户设置失败:', error);
            this.showToast('错误', '编辑客户设置失败，请检查网络连接', 'danger');
        }
    }
    
    // 从策略中移除客户
    async removeCustomerFromStrategy(strategyId, customerUid) {
        try {
            if (!confirm('确定要从此策略中移除该客户吗？')) {
                return;
            }
            
            const response = await fetch(`${this.apiBaseUrl}/limit-follow/strategies/${strategyId}/customers/${customerUid}`, {
                method: 'DELETE'
            });
            
            if (response.ok) {
                const result = await response.json();
                if (result.success === 200) {
                    this.showToast('成功', '客户移除成功', 'success');
                    // 重新加载数据
                    await this.loadStrategyCustomers(strategyId);
                    await this.loadAvailableCustomers(strategyId);
                } else {
                    this.showToast('错误', result.message || '移除客户失败', 'danger');
                }
            } else {
                this.showToast('错误', '移除客户失败', 'danger');
            }
            
        } catch (error) {
            console.error('从策略中移除客户失败:', error);
            this.showToast('错误', '移除客户失败，请检查网络连接', 'danger');
        }
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
                        <button class="btn btn-outline-primary btn-sm" onclick="app.viewStrategyTradeDetail('${strategy.name || strategy.instance_name}')" title="查看详情">
                            <i class="bi bi-eye"></i>
                        </button>
                        <button class="btn btn-outline-secondary btn-sm" onclick="app.editStrategyTrade('${strategy.name || strategy.instance_name}')" title="编辑策略">
                            <i class="bi bi-pencil"></i>
                        </button>
                        ${strategy.status === 'STOPPED' ? 
                            `<button class="btn btn-outline-success btn-sm" onclick="app.startStrategyTrade('${strategy.name || strategy.instance_name}')" title="启动策略">
                                <i class="bi bi-play"></i>
                            </button>` :
                            `<button class="btn btn-outline-warning btn-sm" onclick="app.stopStrategyTrade('${strategy.name || strategy.instance_name}')" title="停止策略">
                                <i class="bi bi-pause"></i>
                            </button>`
                        }
                        <button class="btn btn-outline-info btn-sm" onclick="app.showBacktestModal('${strategy.name || strategy.instance_name}')" title="运行回测">
                            <i class="bi bi-graph-up"></i>
                        </button>
                        <button class="btn btn-outline-danger btn-sm" onclick="app.deleteStrategyTrade('${strategy.name || strategy.instance_name}')" title="删除策略">
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
                    <div class="btn-group" role="group">
                        <button class="btn btn-outline-primary btn-sm" onclick="app.viewBacktestDetail('${backtest.id}')" title="查看详情">
                            <i class="bi bi-eye"></i>
                        </button>
                        <button class="btn btn-outline-danger btn-sm" onclick="app.deleteBacktest('${backtest.id}')" title="删除回测">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
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
    
        // 删除回测
        async deleteBacktest(backtestId) {
            try {
                if (!confirm('确定要删除这个回测记录吗？此操作不可撤销。')) {
                    return;
                }
                
                const response = await fetch(`${this.apiBaseUrl}/strategy/backtests/${backtestId}`, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    const result = await response.json();
                    if (result.success) {
                        this.showToast('成功', '回测记录已删除', 'success');
                        this.loadBacktestHistory(); // 重新加载回测列表
                    } else {
                        this.showToast('错误', result.message || '删除失败', 'danger');
                    }
                } else {
                    this.showToast('错误', '删除回测记录失败', 'danger');
                }
            } catch (error) {
                console.error('删除回测失败:', error);
                this.showToast('错误', `删除回测失败: ${error.message}`, 'danger');
            }
        }

        // 清空所有回测记录
        async clearAllBacktests() {
            try {
                if (!confirm('确定要清空所有回测记录吗？此操作不可撤销，将删除所有历史回测数据。')) {
                    return;
                }
                
                const response = await fetch(`${this.apiBaseUrl}/strategy/backtests/clear`, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    const result = await response.json();
                    if (result.success) {
                        this.showToast('成功', '所有回测记录已清空', 'success');
                        this.loadBacktestHistory(); // 重新加载回测列表
                    } else {
                        this.showToast('错误', result.message || '清空失败', 'danger');
                    }
                } else {
                    this.showToast('错误', '清空回测记录失败', 'danger');
                }
            } catch (error) {
                console.error('清空回测失败:', error);
                this.showToast('错误', `清空回测失败: ${error.message}`, 'danger');
            }
        }
    
    // 查看策略详情
    async viewStrategyTradeDetail(strategyName) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/strategy/instances/${strategyName}`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.data) {
                    this.showStrategyTradeDetailModal(data.data);
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
    showStrategyTradeDetailModal(strategy) {
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
    
    // 启动策略（带权限控制）
    async startStrategyTrade(strategyName) {
        try {
            // 构建启动配置
            const config = {
                symbol: 'BTC-USDT-SWAP', // 默认值，实际应该从策略配置中获取
                initial_capital: 10000,
                max_position_value: 5000,
                is_demo: this.getIsDemo() ? 1 : 0
            };
            
            // 权限控制：只有管理员可以指定customer_id和signal_source_uid
            const isAdmin = this.currentUser && this.currentUser.role === 'admin';
            if (isAdmin) {
                // 管理员：可以从表单或模态框中选择账号和信号源
                const customerSelect = document.getElementById('createStrategyTradeCustomers');
                const signalSourceSelect = document.getElementById('createStrategyTradeSignalSources');
                
                if (customerSelect && customerSelect.selectedOptions.length > 0) {
                    // 使用第一个选中的客户账号
                    config.customer_id = customerSelect.selectedOptions[0].value;
                }
                
                if (signalSourceSelect && signalSourceSelect.selectedOptions.length > 0) {
                    // 使用第一个选中的信号源
                    config.signal_source_uid = signalSourceSelect.selectedOptions[0].value;
                }
            }
            // 普通用户：不传递customer_id和signal_source_uid，后端会自动选择用户的账号
            
            const response = await this.apiRequest(`${this.apiBaseUrl}/strategy-live/strategies/${strategyName}/start`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(config)
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
                const errorData = await response.json().catch(() => ({}));
                this.showToast('错误', errorData.message || '策略启动请求失败', 'danger');
            }
        } catch (error) {
            console.error('启动策略失败:', error);
            this.showToast('错误', '策略启动失败', 'danger');
        }
    }
    
    // 停止策略
    async stopStrategyTrade(strategyName) {
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
    async deleteStrategyTrade(strategyName) {
        
        if (!confirm(`确定要删除策略 "${strategyName}" 吗？此操作不可撤销。`)) {
            return;
        }
        
        try {
            const url = `${this.apiBaseUrl}/strategy/instances/${strategyName}`;
            
            const response = await fetch(url, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                
                if (data.success) {
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
                }
            }
            
            // 然后获取已创建的策略实例
            const instancesResponse = await fetch(`${this.apiBaseUrl}/strategy/instances`);
            const instances = [];
            
            if (instancesResponse.ok) {
                const instancesData = await instancesResponse.json();
                if (instancesData.success && Array.isArray(instancesData.data)) {
                    instances.push(...instancesData.data);
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
        
        // 显示参数配置区域
        if (paramsArea) paramsArea.style.display = 'block';
        
        // 使用动态参数生成
        await this.showBacktestStrategyParams(strategyType);
    }
    
    // 显示回测策略参数
    async showBacktestStrategyParams(strategyType) {
        try {
            
            const response = await fetch(`${this.apiBaseUrl}/strategy/templates/${strategyType}`);
            if (!response.ok) {
                throw new Error(`获取策略模板失败: ${response.status}`);
            }
            
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message);
            }
            
            const template = data.data;
            
            // 生成动态参数表单
            const paramsHtml = this.generateBacktestStrategyParamsForm(strategyType, template.default_config, template.validation_rules, template.parameters);
            
            // 更新HTML
            const paramsArea = document.getElementById('backtestStrategyParams');
            if (paramsArea) {
                paramsArea.innerHTML = paramsHtml;
            }
            
        } catch (error) {
            console.error('生成回测策略参数失败:', error);
            // 降级到硬编码参数
            this.generateLegacyBacktestParams(strategyType);
        }
    }
    
    // 生成回测策略参数表单（统一使用创建策略的参数生成方法）
    generateBacktestStrategyParamsForm(strategyType, config, validation, parameters) {
        // 直接使用统一的参数生成方法，传入 isBacktest=true 标记
        // 确保与创建策略使用完全相同的逻辑和参数，只是ID前缀不同
        return this.generateStrategyParamsForm(strategyType, config, validation, parameters, true);
    }
    
    // 生成回测参数输入框（已废弃，统一使用 generateParamInputFromTemplate）
    // 保留此方法仅用于向后兼容，实际应该使用 generateParamInputFromTemplate
    generateBacktestParamInput(paramName, paramInfo) {
        // 使用统一的参数生成方法，但需要添加 backtest_ 前缀到ID
        const label = this.getParamLabel(paramName);
        const description = this.getParamDescription(paramName);
        const inputType = paramInfo.input_type || (paramInfo.type === 'boolean' ? 'checkbox' : 'number');
        const step = paramInfo.step || (inputType === 'number' ? '0.001' : '');
        const min = paramInfo.min !== undefined ? paramInfo.min : '';
        const max = paramInfo.max !== undefined ? paramInfo.max : '';
        const defaultValue = paramInfo.default || '';
        
        // 处理对象类型
        if (inputType === 'object' || paramInfo.type === 'object') {
            const jsonValue = typeof defaultValue === 'object' ? JSON.stringify(defaultValue, null, 2) : defaultValue;
            return `
                <div class="col-md-6 mb-3">
                    <label for="backtest_${paramName}" class="form-label">${label}</label>
                    <textarea class="form-control" 
                              id="backtest_${paramName}" 
                              name="${paramName}"
                              rows="4"
                              readonly>${jsonValue}</textarea>
                    ${description ? `<div class="form-text">${description}（对象类型，使用默认配置）</div>` : ''}
                </div>
            `;
        }
        
        // 处理复选框
        if (inputType === 'checkbox' || paramInfo.type === 'boolean') {
            const checked = defaultValue === true || defaultValue === 'true' || defaultValue === 1 || defaultValue === '1';
            return `
                <div class="col-md-6 mb-3">
                    <div class="form-check form-switch">
                        <input class="form-check-input" type="checkbox" id="backtest_${paramName}" name="${paramName}" ${checked ? 'checked' : ''}>
                        <label class="form-check-label" for="backtest_${paramName}">${label}</label>
                    </div>
                    ${description ? `<div class="form-text">${description}</div>` : ''}
                </div>
            `;
        }
        
        // 处理数字输入
        const numValue = defaultValue !== undefined && defaultValue !== null ? defaultValue : '';
        return `
            <div class="col-md-6 mb-3">
                <label for="backtest_${paramName}" class="form-label">${label}</label>
                <input type="${inputType}" 
                       class="form-control" 
                       id="backtest_${paramName}" 
                       name="${paramName}"
                       value="${numValue}"
                       ${min !== '' && min !== undefined ? `min="${min}"` : ''}
                       ${max !== '' && max !== undefined ? `max="${max}"` : ''}
                       ${inputType === 'number' && step ? `step="${step}"` : ''}
                       ${paramInfo.required !== false ? 'required' : ''}>
                ${description ? `<div class="form-text">${description}</div>` : ''}
            </div>
        `;
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
                            <input type="number" class="form-control" id="backtest_short_period" name="short_period" value="10" min="5" max="50" required>
                            <div class="form-text">短期移动平均线的计算周期</div>
                        </div>
                        <div class="col-md-6">
                            <label for="backtest_long_period" class="form-label">长期均线周期</label>
                            <input type="number" class="form-control" id="backtest_long_period" name="long_period" value="20" min="10" max="100" required>
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
                            <input type="number" class="form-control" id="backtest_rsi_period" name="rsi_period" value="14" min="5" max="30" required>
                        </div>
                        <div class="col-md-4">
                            <label for="backtest_oversold" class="form-label">超卖线</label>
                            <input type="number" class="form-control" id="backtest_oversold" name="rsi_oversold" value="30" min="10" max="40" required>
                        </div>
                        <div class="col-md-4">
                            <label for="backtest_overbought" class="form-label">超买线</label>
                            <input type="number" class="form-control" id="backtest_overbought" name="rsi_overbought" value="70" min="60" max="90" required>
                        </div>
                    </div>
                `;
                break;
                
            case 'MACD_Strategy':
                paramsHtml = `
                    <div class="row">
                        <div class="col-md-4">
                            <label for="backtest_fast_period" class="form-label">快速EMA周期</label>
                            <input type="number" class="form-control" id="backtest_fast_period" name="fast_period" value="12" min="5" max="20" required>
                        </div>
                        <div class="col-md-4">
                            <label for="backtest_slow_period" class="form-label">慢速EMA周期</label>
                            <input type="number" class="form-control" id="backtest_slow_period" name="slow_period" value="26" min="20" max="50" required>
                        </div>
                        <div class="col-md-4">
                            <label for="backtest_signal_period" class="form-label">信号线周期</label>
                            <input type="number" class="form-control" id="backtest_signal_period" name="signal_period" value="9" min="5" max="15" required>
                        </div>
                    </div>
                `;
                break;
                
            case 'Bollinger_Strategy':
                paramsHtml = `
                    <div class="row">
                        <div class="col-md-6">
                            <label for="backtest_bb_period" class="form-label">布林带周期</label>
                            <input type="number" class="form-control" id="backtest_bb_period" name="bb_period" value="20" min="10" max="50" required>
                        </div>
                        <div class="col-md-6">
                            <label for="backtest_bb_std" class="form-label">标准差倍数</label>
                            <input type="number" class="form-control" id="backtest_bb_std" name="bb_std" value="2" min="1" max="3" step="0.1" required>
                        </div>
                    </div>
                `;
                break;
                
            case 'Grid_Strategy':
                paramsHtml = `
                    <div class="row">
                        <div class="col-md-4">
                            <label for="backtest_grid_size" class="form-label">网格大小 (%)</label>
                            <input type="number" class="form-control" id="backtest_grid_size" name="grid_spacing" value="1" min="0.1" max="5" step="0.1" required>
                        </div>
                        <div class="col-md-4">
                            <label for="backtest_max_grids" class="form-label">最大网格数</label>
                            <input type="number" class="form-control" id="backtest_max_grids" name="grid_levels" value="10" min="3" max="20" required>
                        </div>
                        <div class="col-md-4">
                            <label for="backtest_base_amount" class="form-label">基础下单金额</label>
                            <input type="number" class="form-control" id="backtest_base_amount" name="investment_per_grid" value="100" min="10" max="1000" required>
                        </div>
                    </div>
                `;
                break;
                
            case 'HighFrequency_Strategy':
            case 'High_Frequency_Strategy':
                paramsHtml = `
                    <div class="row">
                        <div class="col-md-6">
                            <label for="backtest_fast_ema_period" class="form-label">快线EMA周期</label>
                            <input type="number" class="form-control" id="backtest_fast_ema_period" name="fast_ema_period" value="5" min="3" max="20" required>
                            <div class="form-text">快线EMA的计算周期</div>
                        </div>
                        <div class="col-md-6">
                            <label for="backtest_slow_ema_period" class="form-label">慢线EMA周期</label>
                            <input type="number" class="form-control" id="backtest_slow_ema_period" name="slow_ema_period" value="10" min="5" max="50" required>
                            <div class="form-text">慢线EMA的计算周期</div>
                        </div>
                    </div>
                    <div class="row mt-3">
                        <div class="col-md-4">
                            <label for="backtest_rsi_period" class="form-label">RSI周期</label>
                            <input type="number" class="form-control" id="backtest_rsi_period" name="rsi_period" value="14" min="5" max="30" required>
                        </div>
                        <div class="col-md-4">
                            <label for="backtest_rsi_oversold" class="form-label">RSI超卖线</label>
                            <input type="number" class="form-control" id="backtest_rsi_oversold" name="rsi_oversold" value="30" min="10" max="40" required>
                        </div>
                        <div class="col-md-4">
                            <label for="backtest_rsi_overbought" class="form-label">RSI超买线</label>
                            <input type="number" class="form-control" id="backtest_rsi_overbought" name="rsi_overbought" value="70" min="60" max="90" required>
                        </div>
                    </div>
                    <div class="row mt-3">
                        <div class="col-md-6">
                            <label for="backtest_volume_threshold" class="form-label">成交量倍数阈值</label>
                            <input type="number" class="form-control" id="backtest_volume_threshold" name="volume_threshold" value="1.5" min="1.0" max="5.0" step="0.1" required>
                            <div class="form-text">成交量确认的倍数阈值</div>
                        </div>
                        <div class="col-md-6">
                            <label for="backtest_price_change_threshold" class="form-label">价格变化阈值</label>
                            <input type="number" class="form-control" id="backtest_price_change_threshold" name="price_change_threshold" value="0.01" min="0.001" max="0.05" step="0.001" required>
                            <div class="form-text">价格变化的最小阈值</div>
                        </div>
                    </div>
                    <div class="row mt-3">
                        <div class="col-md-6">
                            <label for="backtest_min_trade_interval" class="form-label">最小交易间隔(分钟)</label>
                            <input type="number" class="form-control" id="backtest_min_trade_interval" name="min_trade_interval" value="5" min="1" max="60" required>
                            <div class="form-text">两次交易之间的最小时间间隔</div>
                        </div>
                        <div class="col-md-6">
                            <label for="backtest_max_trades_per_day" class="form-label">每日最大交易次数</label>
                            <input type="number" class="form-control" id="backtest_max_trades_per_day" name="max_trades_per_day" value="50" min="10" max="200" required>
                            <div class="form-text">每日允许的最大交易次数</div>
                        </div>
                    </div>
                `;
                break;
                
            default:
                paramsHtml = '<p class="text-muted">该策略使用默认参数配置</p>';
        }
        
        // 获取参数容器并更新内容
        const paramsContainer = document.getElementById('backtestStrategyParams');
        if (paramsContainer) {
            paramsContainer.innerHTML = paramsHtml;
            paramsContainer.style.display = 'block';
        } else {
            console.error('未找到回测策略参数容器');
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
        
        // 显示策略参数
        this.displayStrategyParams(backtestData.config_json);
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

    // 显示策略参数
    displayStrategyParams(configJson) {
        const tableBody = document.getElementById('strategyParamsTableBody');
        if (!tableBody) return;
        
        tableBody.innerHTML = ''; // 清空现有内容
        
        if (!configJson) {
            tableBody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">无策略参数</td></tr>';
            return;
        }
        
        try {
            const config = JSON.parse(configJson);
            
            for (const key in config) {
                if (Object.hasOwnProperty.call(config, key)) {
                    const value = config[key];
                    let displayValue = value;
                    let valueType = typeof value;
                    let description = ''; // 可以从后端获取更详细的参数说明
                    
                    // 尝试更友好的显示
                    if (typeof value === 'number') {
                        if (key.includes('pct') || key.includes('ratio') || key.includes('rate')) {
                            displayValue = `${(value * 100).toFixed(2)}%`;
                            valueType = '百分比';
                        } else if (Number.isInteger(value)) {
                            valueType = '整数';
                        } else {
                            displayValue = value.toFixed(4); // 浮点数保留4位
                            valueType = '浮点数';
                        }
                    } else if (typeof value === 'boolean') {
                        displayValue = value ? '是' : '否';
                        valueType = '布尔值';
                    } else if (Array.isArray(value)) {
                        displayValue = `[${value.join(', ')}]`;
                        valueType = '数组';
                    } else if (typeof value === 'object' && value !== null) {
                        displayValue = JSON.stringify(value);
                        valueType = '对象';
                    }
                    
                    const row = `
                        <tr>
                            <td>${key}</td>
                            <td>${displayValue}</td>
                            <td>${valueType}</td>
                            <td>${description}</td>
                        </tr>
                    `;
                    tableBody.innerHTML += row;
                }
            }
        } catch (error) {
            console.error('解析策略参数失败:', error);
            tableBody.innerHTML = '<tr><td colspan="4" class="text-center text-danger">解析策略参数失败</td></tr>';
        }
    }

    // 初始化回测图表
    initBacktestCharts(backtestData) {

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

            // 添加买入卖出标记 - markers 需要设置到 series 上
            this.addTradeMarkers(candlestickSeries, results.trade_history || []);

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
            
            // 🔧 验证数据有效性
            if (!returnData || returnData.length === 0) {
                console.error('❌ 没有有效的收益率数据');
                chartContainer.innerHTML = '<div class="text-center p-4 text-muted">无收益率数据</div>';
                return;
            }
            
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
            
            // 🔧 确保baseline数据也经过验证
            const baselineData = returnData
                .filter(point => point && typeof point.time === 'number')
                .map(point => ({
                    time: point.time,
                    value: 0
                }));
            
            baselineSeries.setData(baselineData);

            // 标记交易点 - markers 需要设置到 series 上，不是 chart
            this.addTradeMarkersToChart(returnSeries, results.trade_history || []);

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
            console.error('❌ 初始化收益曲线图表失败:', error);
            console.error('❌ 错误堆栈:', error.stack);
            chartContainer.innerHTML = `<div class="text-center p-4 text-danger">
                收益曲线图表加载失败<br>
                <small>${error.message}</small>
            </div>`;
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
            
            // 🔧 验证数据有效性
            if (!drawdownData || drawdownData.length === 0) {
                console.error('❌ 没有有效的回撤数据');
                chartContainer.innerHTML = '<div class="text-center p-4 text-muted">无回撤数据</div>';
                return;
            }
            
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

    // 添加交易标记（用于价格图表）
    addTradeMarkers(series, tradeHistory) {
        const markers = [];
        
        tradeHistory.forEach(trade => {
            if (trade.type === 'BUY' || trade.type === 'SELL' || trade.type === 'CLOSE') {
                const timestamp = this.parseTradeTimestamp(trade.timestamp);
                
                // 🔧 验证时间戳有效性
                if (timestamp && typeof timestamp === 'number' && !isNaN(timestamp)) {
                    const isBuy = trade.type === 'BUY';
                    markers.push({
                        time: timestamp,
                        position: isBuy ? 'belowBar' : 'aboveBar',
                        color: isBuy ? '#26a69a' : '#ef5350',
                        shape: isBuy ? 'arrowUp' : 'arrowDown',
                        text: isBuy ? 'B' : 'S',
                        size: 1,
                    });
                } else {
                    console.warn('⚠️ 跳过无效交易标记时间戳:', trade);
                }
            }
        });
        
        if (markers.length > 0 && series && typeof series.setMarkers === 'function') {
            series.setMarkers(markers);
        }
    }

    // 解析交易时间戳
    parseTradeTimestamp(timestamp) {
        try {
            if (!timestamp) {
                console.warn('时间戳为空，使用当前时间');
                return Math.floor(Date.now() / 1000);
            }
            
            if (typeof timestamp === 'string') {
                // 处理ISO格式字符串
                if (timestamp.includes('T') || timestamp.includes('-')) {
                    const date = new Date(timestamp);
                    if (!isNaN(date.getTime())) {
                        return Math.floor(date.getTime() / 1000);
                    }
                }
                // 处理纯数字字符串
                const num = parseInt(timestamp);
                if (!isNaN(num)) {
                    return num > 1000000000000 ? Math.floor(num / 1000) : num;
                }
            } else if (typeof timestamp === 'number') {
                return timestamp > 1000000000000 ? Math.floor(timestamp / 1000) : timestamp;
            }
        } catch (e) {
            console.warn('解析时间戳失败:', timestamp, e);
        }
        
        console.warn('使用当前时间作为默认时间戳');
        return Math.floor(Date.now() / 1000);
    }

    // 生成资金曲线数据
    generateEquityCurve(results) {
        const equityData = [];
              
        if (results.equity_curve && Array.isArray(results.equity_curve)) {
            results.equity_curve.forEach((point, index) => {
                const timestamp = this.parseTradeTimestamp(point.timestamp || point.time);
                const value = point.equity || point.total_value || point.value || 0;
                
                // 严格验证：时间戳必须是有效数字，且value不能是NaN
                if (timestamp && typeof timestamp === 'number' && !isNaN(timestamp) && !isNaN(value)) {
                    equityData.push({
                        time: timestamp,
                        value: value
                    });
                } else {
                    console.warn(`⚠️ 跳过无效数据点 ${index}: time=${timestamp}, value=${value}`);
                }
            });
        } else {
            // 如果没有资金曲线数据，从交易历史生成
            let equity = results.initial_capital || 100000;
            equityData.push({
                time: Math.floor(Date.now() / 1000) - 30 * 24 * 3600,
                value: equity
            });
            
            const trades = results.trades || results.trade_history || [];
            trades.forEach(trade => {
                if (trade.type === 'CLOSE' || trade.side === 'SELL') {
                    equity += trade.pnl || 0;
                    equityData.push({
                        time: this.parseTradeTimestamp(trade.timestamp),
                        value: equity
                    });
                }
            });
        }
        
        // 确保至少有一个数据点
        if (equityData.length === 0) {
            equityData.push({
                time: Math.floor(Date.now() / 1000),
                value: results.initial_capital || 100000
            });
        }
        
        // 🔧 关键修复：按时间排序并去重
        equityData.sort((a, b) => a.time - b.time);
        
        // 去除重复时间戳，保留最后一个值
        const uniqueData = [];
        const timeSet = new Set();
        
        for (let i = equityData.length - 1; i >= 0; i--) {
            const point = equityData[i];
            if (!timeSet.has(point.time)) {
                timeSet.add(point.time);
                uniqueData.unshift(point);
            }
        }
        
        return uniqueData;
    }

    // 生成收益率曲线数据
    generateReturnCurve(equityData) {
        if (!equityData || equityData.length === 0) return [];
        
        const initialValue = equityData[0].value;
        if (!initialValue || initialValue === 0) {
            console.warn('⚠️ 初始资金为0，无法计算收益率');
            return [];
        }
        
        // 🔧 过滤并验证数据
        const returnData = equityData
            .filter(point => point && typeof point.time === 'number' && !isNaN(point.time) && !isNaN(point.value))
            .map(point => ({
                time: point.time,
                value: ((point.value - initialValue) / initialValue) * 100 // 转换为百分比
            }));
        
        return returnData;
    }

    // 生成回撤曲线数据
    generateDrawdownCurve(results) {
        const equityData = this.generateEquityCurve(results);
        if (equityData.length === 0) return [];
        
        const drawdownData = [];
        let peak = equityData[0].value;
        
        equityData.forEach(point => {
            // 🔧 验证数据有效性
            if (!point || typeof point.time !== 'number' || isNaN(point.time) || isNaN(point.value)) {
                console.warn('⚠️ 跳过无效的回撤数据点:', point);
                return;
            }
            
            // 更新最高点
            if (point.value > peak) {
                peak = point.value;
            }
            
            // 计算回撤百分比
            if (peak > 0) {
                const drawdown = ((point.value - peak) / peak) * 100;
                drawdownData.push({
                    time: point.time,
                    value: drawdown // 负数表示回撤
                });
            }
        });
        
        return drawdownData;
    }

    // 为图表添加交易标记
    addTradeMarkersToChart(series, tradeHistory) {
        const markers = [];
        
        tradeHistory.forEach(trade => {
            if (trade.type === 'BUY' || trade.type === 'SELL' || trade.type === 'CLOSE') {
                const timestamp = this.parseTradeTimestamp(trade.timestamp);
                
                // 🔧 验证时间戳有效性
                if (timestamp && typeof timestamp === 'number' && !isNaN(timestamp)) {
                    const isBuy = trade.type === 'BUY';
                    markers.push({
                        time: timestamp,
                        position: isBuy ? 'belowBar' : 'aboveBar',
                        color: isBuy ? '#26a69a' : '#ef5350',
                        shape: isBuy ? 'arrowUp' : 'arrowDown',
                        text: isBuy ? 'B' : 'S',
                        size: 1,
                    });
                } else {
                    console.warn('⚠️ 跳过无效交易标记时间戳:', trade);
                }
            }
        });
        
        if (markers.length > 0 && series && typeof series.setMarkers === 'function') {
            series.setMarkers(markers);
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
            // 只计算平仓记录的PnL
            if (trade.pnl && trade.type === 'CLOSE') {
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
    
    // 刷新策略列表（重新扫描策略文件）
    async refreshStrategies() {
        try {
            this.showToast('信息', '正在扫描策略文件...', 'info');
            
            // 调用策略扫描 API
            const response = await fetch(`${this.apiBaseUrl}/strategy/scan`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    const count = data.data.count || 0;
                    const strategies = data.data.strategies || [];
                    
                    this.showToast('成功', `扫描完成！发现 ${count} 个策略`, 'success');
                    
                    // 刷新策略交易页面（如果在策略交易页面）
                    const currentPage = document.querySelector('.page-content.active');
                    if (currentPage && currentPage.id === 'strategy-trade-page') {
                        await this.loadStrategyTradeData();
                    }
                    
                    // 刷新策略管理页面（如果在策略管理页面）
                    if (currentPage && currentPage.id === 'strategies-page') {
                        await this.loadStrategiesData();
                    }
                    
                    // 重新加载策略选项（用于创建策略时的下拉框）
                    await this.loadStrategiesOptions();
                    
                } else {
                    this.showToast('错误', data.message || '扫描策略失败', 'danger');
                }
            } else {
                this.showToast('错误', '扫描策略请求失败', 'danger');
            }
        } catch (error) {
            console.error('刷新策略失败:', error);
            this.showToast('错误', '刷新策略失败: ' + error.message, 'danger');
        }
    }
    
    // 加载策略模板列表
    async loadStrategyTemplates() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/strategy/templates`);
            if (response.ok) {
                const data = await response.json();
            }
        } catch (error) {
            console.error('加载策略模板失败:', error);
        }
    }
    
    // ==================== 消息转发模块 ====================
    
    // 加载消息转发数据
    async loadMessageForwardData() {
        try {
            // 加载服务状态
            await this.loadMessageForwardStatus();
            
            // 加载平台列表（会自动更新源平台下拉列表）
            await this.loadPlatformsList();
            
            // 加载转发规则
            await this.loadForwardRulesList();
            
            // 加载消息历史
            await this.loadMessageHistory();
            
        } catch (error) {
            console.error('加载消息转发数据失败:', error);
            this.showToast('错误', '加载消息转发数据失败', 'danger');
        }
    }
    
    // 启动消息转发服务
    async startMessageForwardService() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/message-forward/start`, {
                method: 'POST'
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast('成功', '服务启动成功', 'success');
                // 刷新状态
                await this.loadMessageForwardStatus();
                await this.loadPlatformsList();
            } else {
                this.showToast('错误', data.message || '服务启动失败', 'danger');
            }
        } catch (error) {
            console.error('启动服务失败:', error);
            this.showToast('错误', '启动服务失败', 'danger');
        }
    }
    
    // 停止消息转发服务
    async stopMessageForwardService() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/message-forward/stop`, {
                method: 'POST'
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast('成功', '服务已停止', 'success');
                // 刷新状态
                await this.loadMessageForwardStatus();
                await this.loadPlatformsList();
            } else {
                this.showToast('错误', data.message || '停止服务失败', 'danger');
            }
        } catch (error) {
            console.error('停止服务失败:', error);
            this.showToast('错误', '停止服务失败', 'danger');
        }
    }
    
    // 初始化转发规则模态框事件
    initForwardRuleModal() {
        const addForwardRuleModal = document.getElementById('addForwardRuleModal');
        if (addForwardRuleModal) {
            addForwardRuleModal.addEventListener('show.bs.modal', async () => {
                // 确保平台列表已加载
                await this.loadPlatformsList();
            });
        }
    }

    // 加载用户管理数据
    async loadUserManagementData() {
        try {
            // 加载用户列表
            await this.loadUsersList();
            
        } catch (error) {
            console.error('加载用户管理数据失败:', error);
            this.showToast('错误', '加载用户管理数据失败', 'danger');
        }
    }

    // 加载用户列表
    async loadUsersList() {
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/auth/users`);
            if (response && response.ok) {
                const data = await response.json();
                if (data.success && data.data && data.data.users) {
                    this.renderUsersTable(data.data.users);
                } else {
                    this.renderUsersTable([]);
                }
            } else {
                this.renderUsersTable([]);
            }
        } catch (error) {
            console.error('加载用户列表失败:', error);
            this.renderUsersTable([]);
        }
    }

    // 渲染用户表格
    renderUsersTable(users) {
        const tbody = document.querySelector('#usersTable tbody');
        if (!tbody) return;

        // 确保users是数组
        if (!Array.isArray(users)) {
            console.error('renderUsersTable: users不是数组:', users);
            tbody.innerHTML = '<tr><td colspan="9" class="text-center text-danger">数据格式错误</td></tr>';
            return;
        }

        if (users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted">暂无用户数据</td></tr>';
            return;
        }

        tbody.innerHTML = users.map(user => `
            <tr>
                <td>${user.id}</td>
                <td>${user.username}</td>
                <td>${user.full_name || '-'}</td>
                <td>${user.email || '-'}</td>
                <td>
                    <span class="badge ${user.role === 'admin' ? 'bg-danger' : 'bg-primary'}">
                        ${user.role === 'admin' ? '管理员' : '普通用户'}
                    </span>
                </td>
                <td>
                    <span class="badge ${user.status === 'active' ? 'bg-success' : 'bg-secondary'}">
                        ${user.status === 'active' ? '启用' : '禁用'}
                    </span>
                </td>
                <td>${user.created_at ? new Date(user.created_at).toLocaleString() : '-'}</td>
                <td>${user.last_login_at ? new Date(user.last_login_at).toLocaleString() : '从未登录'}</td>
                <td>
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-primary edit-user" data-user-id="${user.id}">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn btn-outline-success edit-user-permissions" data-user-id="${user.id}" title="编辑权限">
                            <i class="bi bi-shield-lock"></i>
                        </button>
                        <button class="btn btn-outline-warning toggle-user" data-user-id="${user.id}" data-status="${user.status}">
                            <i class="bi bi-${user.status === 'active' ? 'pause' : 'play'}"></i>
                        </button>
                        <button class="btn btn-outline-info reset-password" data-user-id="${user.id}">
                            <i class="bi bi-key"></i>
                        </button>
                        <button class="btn btn-outline-danger delete-user" data-user-id="${user.id}">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');

        // 绑定事件
        this.bindUserManagementEvents();
    }

    // 绑定用户管理事件
    bindUserManagementEvents() {
        // 添加用户按钮
        const addUserBtn = document.getElementById('addUserBtn');
        if (addUserBtn) {
            addUserBtn.addEventListener('click', () => this.showAddUserModal());
        }

        // 编辑用户按钮
        document.querySelectorAll('.edit-user').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const userId = e.target.closest('.edit-user').dataset.userId;
                this.showEditUserModal(userId);
            });
        });

        // 启用/禁用用户按钮
        document.querySelectorAll('.toggle-user').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const userId = e.target.closest('.toggle-user').dataset.userId;
                const currentStatus = e.target.closest('.toggle-user').dataset.status;
                this.toggleUserStatus(userId, currentStatus);
            });
        });

        // 重置密码按钮
        document.querySelectorAll('.reset-password').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const userId = e.target.closest('.reset-password').dataset.userId;
                this.showResetPasswordModal(userId);
            });
        });

        // 删除用户按钮
        document.querySelectorAll('.delete-user').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const userId = e.target.closest('.delete-user').dataset.userId;
                this.showDeleteUserModal(userId);
            });
        });

        // 编辑用户权限按钮
        document.querySelectorAll('.edit-user-permissions').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const userId = e.target.closest('.edit-user-permissions').dataset.userId;
                this.showEditUserPermissionsModal(userId);
            });
        });
    }

    // 显示添加用户模态框
    showAddUserModal() {
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">添加用户</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="addUserForm">
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label class="form-label">用户名 <span class="text-danger">*</span></label>
                                        <input type="text" class="form-control" name="username" required>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label class="form-label">姓名</label>
                                        <input type="text" class="form-control" name="full_name">
                                    </div>
                                </div>
                            </div>
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label class="form-label">邮箱</label>
                                        <input type="email" class="form-control" name="email">
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label class="form-label">角色 <span class="text-danger">*</span></label>
                                        <select class="form-select" name="role" required>
                                            <option value="">请选择角色</option>
                                            <option value="admin">管理员</option>
                                            <option value="user">普通用户</option>
                                        </select>
                                    </div>
                                </div>
                            </div>
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label class="form-label">密码 <span class="text-danger">*</span></label>
                                        <input type="password" class="form-control" name="password" required>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label class="form-label">确认密码 <span class="text-danger">*</span></label>
                                        <input type="password" class="form-control" name="confirm_password" required>
                                    </div>
                                </div>
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                        <button type="button" class="btn btn-primary" id="saveUserBtn">保存</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
        
        // 保存按钮事件
        document.getElementById('saveUserBtn').addEventListener('click', () => {
            this.saveUser();
        });
        
        // 模态框关闭后移除DOM元素
        modal.addEventListener('hidden.bs.modal', () => {
            document.body.removeChild(modal);
        });
    }

    // 显示编辑用户模态框
    async showEditUserModal(userId) {
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/auth/users/${userId}`);
            if (response && response.ok) {
                const data = await response.json();
                if (data.success && data.data) {
                    const user = data.data;
                    this.showEditUserForm(user);
                } else {
                    this.showToast('错误', '获取用户信息失败', 'danger');
                }
            } else {
                this.showToast('错误', '获取用户信息失败', 'danger');
            }
        } catch (error) {
            console.error('获取用户信息失败:', error);
            this.showToast('错误', '获取用户信息失败', 'danger');
        }
    }

    // 显示编辑用户表单
    showEditUserForm(user) {
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">编辑用户</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="editUserForm">
                            <input type="hidden" name="user_id" value="${user.id}">
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label class="form-label">用户名 <span class="text-danger">*</span></label>
                                        <input type="text" class="form-control" name="username" value="${user.username}" required>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label class="form-label">姓名</label>
                                        <input type="text" class="form-control" name="full_name" value="${user.full_name || ''}">
                                    </div>
                                </div>
                            </div>
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label class="form-label">邮箱</label>
                                        <input type="email" class="form-control" name="email" value="${user.email || ''}">
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label class="form-label">角色 <span class="text-danger">*</span></label>
                                        <select class="form-select" name="role" required>
                                            <option value="admin" ${user.role === 'admin' ? 'selected' : ''}>管理员</option>
                                            <option value="user" ${user.role === 'user' ? 'selected' : ''}>普通用户</option>
                                        </select>
                                    </div>
                                </div>
                            </div>
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label class="form-label">状态</label>
                                        <select class="form-select" name="status">
                                            <option value="active" ${user.status === 'active' ? 'selected' : ''}>启用</option>
                                            <option value="inactive" ${user.status === 'inactive' ? 'selected' : ''}>禁用</option>
                                        </select>
                                    </div>
                                </div>
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                        <button type="button" class="btn btn-primary" id="updateUserBtn">更新</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
        
        // 更新按钮事件
        document.getElementById('updateUserBtn').addEventListener('click', () => {
            this.updateUser();
        });
        
        // 模态框关闭后移除DOM元素
        modal.addEventListener('hidden.bs.modal', () => {
            document.body.removeChild(modal);
        });
    }

    // 显示重置密码模态框
    showResetPasswordModal(userId) {
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">重置密码</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <form id="resetPasswordForm">
                            <input type="hidden" name="user_id" value="${userId}">
                            <div class="mb-3">
                                <label class="form-label">新密码 <span class="text-danger">*</span></label>
                                <input type="password" class="form-control" name="password" required>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">确认密码 <span class="text-danger">*</span></label>
                                <input type="password" class="form-control" name="confirm_password" required>
                            </div>
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                        <button type="button" class="btn btn-warning" id="resetPasswordBtn">重置密码</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
        
        // 重置密码按钮事件
        document.getElementById('resetPasswordBtn').addEventListener('click', () => {
            this.resetPassword();
        });
        
        // 模态框关闭后移除DOM元素
        modal.addEventListener('hidden.bs.modal', () => {
            document.body.removeChild(modal);
        });
    }

    // 显示删除用户确认模态框
    showDeleteUserModal(userId) {
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">删除用户</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p>确定要删除这个用户吗？此操作不可撤销。</p>
                        <input type="hidden" name="user_id" value="${userId}">
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                        <button type="button" class="btn btn-danger" id="deleteUserBtn">删除</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
        
        // 删除按钮事件
        document.getElementById('deleteUserBtn').addEventListener('click', () => {
            this.deleteUser(userId);
        });
        
        // 模态框关闭后移除DOM元素
        modal.addEventListener('hidden.bs.modal', () => {
            document.body.removeChild(modal);
        });
    }

    // 保存用户
    async saveUser() {
        const form = document.getElementById('addUserForm');
        const formData = new FormData(form);
        const data = Object.fromEntries(formData);
        
        // 验证密码
        if (data.password !== data.confirm_password) {
            this.showToast('错误', '两次输入的密码不一致', 'danger');
            return;
        }
        
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/auth/users`, {
                method: 'POST',
                body: JSON.stringify(data)
            });
            
            if (response && response.ok) {
                const result = await response.json();
                if (result.success) {
                    this.showToast('成功', '用户创建成功', 'success');
                    this.loadUsersList(); // 重新加载用户列表
                    bootstrap.Modal.getInstance(document.querySelector('.modal')).hide();
                } else {
                    this.showToast('错误', result.message || '创建用户失败', 'danger');
                }
            } else {
                this.showToast('错误', '创建用户失败', 'danger');
            }
        } catch (error) {
            console.error('创建用户失败:', error);
            this.showToast('错误', '创建用户失败', 'danger');
        }
    }

    // 更新用户
    async updateUser() {
        const form = document.getElementById('editUserForm');
        const formData = new FormData(form);
        const data = Object.fromEntries(formData);
        
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/auth/users/${data.user_id}`, {
                method: 'PUT',
                body: JSON.stringify(data)
            });
            
            if (response && response.ok) {
                const result = await response.json();
                if (result.success) {
                    this.showToast('成功', '用户更新成功', 'success');
                    this.loadUsersList(); // 重新加载用户列表
                    bootstrap.Modal.getInstance(document.querySelector('.modal')).hide();
                } else {
                    this.showToast('错误', result.message || '更新用户失败', 'danger');
                }
            } else {
                this.showToast('错误', '更新用户失败', 'danger');
            }
        } catch (error) {
            console.error('更新用户失败:', error);
            this.showToast('错误', '更新用户失败', 'danger');
        }
    }

    // 重置密码
    async resetPassword() {
        const form = document.getElementById('resetPasswordForm');
        const formData = new FormData(form);
        const data = Object.fromEntries(formData);
        
        // 验证密码
        if (data.password !== data.confirm_password) {
            this.showToast('错误', '两次输入的密码不一致', 'danger');
            return;
        }
        
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/auth/users/${data.user_id}/reset-password`, {
                method: 'POST',
                body: JSON.stringify({ password: data.password })
            });
            
            if (response && response.ok) {
                const result = await response.json();
                if (result.success) {
                    this.showToast('成功', '密码重置成功', 'success');
                    bootstrap.Modal.getInstance(document.querySelector('.modal')).hide();
                } else {
                    this.showToast('错误', result.message || '重置密码失败', 'danger');
                }
            } else {
                this.showToast('错误', '重置密码失败', 'danger');
            }
        } catch (error) {
            console.error('重置密码失败:', error);
            this.showToast('错误', '重置密码失败', 'danger');
        }
    }

    // 切换用户状态
    async toggleUserStatus(userId, currentStatus) {
        const newStatus = currentStatus === 'active' ? 'inactive' : 'active';
        const action = newStatus === 'active' ? '启用' : '禁用';
        
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/auth/users/${userId}/toggle-status`, {
                method: 'POST',
                body: JSON.stringify({ status: newStatus })
            });
            
            if (response && response.ok) {
                const result = await response.json();
                if (result.success) {
                    this.showToast('成功', `用户${action}成功`, 'success');
                    this.loadUsersList(); // 重新加载用户列表
                } else {
                    this.showToast('错误', result.message || `${action}用户失败`, 'danger');
                }
            } else {
                this.showToast('错误', `${action}用户失败`, 'danger');
            }
        } catch (error) {
            console.error(`${action}用户失败:`, error);
            this.showToast('错误', `${action}用户失败`, 'danger');
        }
    }

    // 删除用户
    async deleteUser(userId) {
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/auth/users/${userId}`, {
                method: 'DELETE'
            });
            
            if (response && response.ok) {
                const result = await response.json();
                if (result.success) {
                    this.showToast('成功', '用户删除成功', 'success');
                    this.loadUsersList(); // 重新加载用户列表
                    bootstrap.Modal.getInstance(document.querySelector('.modal')).hide();
                } else {
                    this.showToast('错误', result.message || '删除用户失败', 'danger');
                }
            } else {
                this.showToast('错误', '删除用户失败', 'danger');
            }
        } catch (error) {
            console.error('删除用户失败:', error);
            this.showToast('错误', '删除用户失败', 'danger');
        }
    }

    // 加载权限管理数据
    async loadPermissionManagementData() {
        try {
            // 加载用户权限矩阵
            await this.loadUserPermissionsMatrix();
            
            // 加载权限模板
            await this.loadPermissionTemplates();
            
            // 加载用户列表用于权限管理
            await this.loadUsersForPermissionManagement();
            
        } catch (error) {
            console.error('加载权限管理数据失败:', error);
            this.showToast('错误', '加载权限管理数据失败', 'danger');
        }
    }

    // 加载用户权限矩阵
    async loadUserPermissionsMatrix() {
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/auth/permissions/matrix`);
            if (response && response.ok) {
                const data = await response.json();
                if (data.success && data.data) {
                    this.renderPermissionsMatrix(data.data);
                } else {
                    this.renderPermissionsMatrix([]);
                }
            } else {
                this.renderPermissionsMatrix([]);
            }
        } catch (error) {
            console.error('加载用户权限矩阵失败:', error);
            this.renderPermissionsMatrix([]);
        }
    }

    // 渲染权限矩阵
    renderPermissionsMatrix(matrixData) {
        const rolesTable = document.querySelector('#rolesTable tbody');
        if (!rolesTable) return;

        if (!matrixData || matrixData.length === 0) {
            rolesTable.innerHTML = '<tr><td colspan="3" class="text-center text-muted">暂无权限数据</td></tr>';
            return;
        }

        rolesTable.innerHTML = matrixData.map(role => `
            <tr>
                <td>${role.role_name}</td>
                <td>
                    <div class="d-flex flex-wrap gap-1">
                        ${role.permissions.map(perm => `
                            <span class="badge bg-success">${perm}</span>
                        `).join('')}
                    </div>
                </td>
                <td>
                    <button class="btn btn-sm btn-outline-primary edit-role-permissions" data-role="${role.role}">
                        <i class="bi bi-pencil"></i> 编辑
                    </button>
                </td>
            </tr>
        `).join('');

        // 绑定编辑权限事件
        document.querySelectorAll('.edit-role-permissions').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const role = e.target.closest('.edit-role-permissions').dataset.role;
                this.showEditRolePermissionsModal(role);
            });
        });
    }

    // 加载权限模板
    async loadPermissionTemplates() {
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/auth/permissions/templates`);
            if (response && response.ok) {
                const data = await response.json();
                if (data.success && data.data) {
                    this.renderPermissionTemplates(data.data);
                } else {
                    this.renderPermissionTemplates([]);
                }
            } else {
                this.renderPermissionTemplates([]);
            }
        } catch (error) {
            console.error('加载权限模板失败:', error);
            this.renderPermissionTemplates([]);
        }
    }

    // 加载用户列表用于权限管理
    async loadUsersForPermissionManagement() {
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/auth/users`);
            if (response && response.ok) {
                const data = await response.json();
                if (data.success && data.data && data.data.users) {
                    // 获取每个用户的权限信息
                    const usersWithPermissions = await Promise.all(
                        data.data.users.map(async (user) => {
                            try {
                                const permResponse = await this.apiRequest(`${this.apiBaseUrl}/auth/users/${user.id}/permissions`);
                                if (permResponse && permResponse.ok) {
                                    const permData = await permResponse.json();
                                    return {
                                        ...user,
                                        permissions: permData.success && permData.data && permData.data.permissions 
                                            ? permData.data.permissions 
                                            : [],
                                        hasCustomPermissions: permData.success && permData.data && permData.data.permissions
                                            ? permData.data.permissions.some(p => p.source === 'user')
                                            : false
                                    };
                                }
                            } catch (error) {
                                console.error(`获取用户 ${user.id} 权限失败:`, error);
                            }
                            return {
                                ...user,
                                permissions: [],
                                hasCustomPermissions: false
                            };
                        })
                    );
                    this.renderUsersPermissionTable(usersWithPermissions);
                } else {
                    this.renderUsersPermissionTable([]);
                }
            } else {
                this.renderUsersPermissionTable([]);
            }
        } catch (error) {
            console.error('加载用户列表失败:', error);
            this.renderUsersPermissionTable([]);
        }
    }

    // 渲染用户权限表格
    renderUsersPermissionTable(users) {
        const tbody = document.getElementById('usersPermissionTableBody');
        if (!tbody) return;

        if (!users || users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">暂无用户数据</td></tr>';
            return;
        }

        tbody.innerHTML = users.map(user => {
            // 统计权限数量
            const permissionCount = user.permissions ? user.permissions.length : 0;
            
            // 权限来源
            const permissionSource = user.hasCustomPermissions 
                ? '<span class="badge bg-warning text-dark">自定义</span>' 
                : '<span class="badge bg-secondary">角色</span>';
            
            // 状态
            const statusBadge = user.status === 'active' 
                ? '<span class="badge bg-success">启用</span>' 
                : '<span class="badge bg-danger">禁用</span>';
            
            // 角色
            const roleName = user.role === 'admin' ? '管理员' : '普通用户';
            const roleBadge = user.role === 'admin' 
                ? '<span class="badge bg-primary">管理员</span>' 
                : '<span class="badge bg-info">普通用户</span>';
            
            // 关联客户
            const customerInfo = user.customer_uid 
                ? `<span class="text-muted">${user.customer_uid}</span>` 
                : '<span class="text-muted">-</span>';
            
            return `
                <tr>
                    <td>${user.id}</td>
                    <td>${user.username || '-'}</td>
                    <td>${roleBadge}</td>
                    <td>${customerInfo}</td>
                    <td>${permissionSource}</td>
                    <td>
                        <span class="badge bg-info">${permissionCount} 个权限</span>
                    </td>
                    <td>${statusBadge}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary edit-user-permission-btn" data-user-id="${user.id}">
                            <i class="bi bi-pencil"></i> 编辑权限
                        </button>
                    </td>
                </tr>
            `;
        }).join('');

        // 绑定编辑权限按钮事件
        document.querySelectorAll('.edit-user-permission-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const userId = parseInt(e.target.closest('.edit-user-permission-btn').dataset.userId);
                this.showEditUserPermissionsModal(userId);
            });
        });
    }

    // 渲染权限模板
    renderPermissionTemplates(templates) {
        const permissionsList = document.getElementById('permissionsList');
        if (!permissionsList) return;

        if (!templates || templates.length === 0) {
            permissionsList.innerHTML = '<div class="list-group-item text-center text-muted">暂无权限模板</div>';
            return;
        }

        permissionsList.innerHTML = templates.map(template => `
            <div class="list-group-item d-flex justify-content-between align-items-center">
                <div>
                    <strong>${template.name}</strong>
                    <small class="text-muted d-block">${template.description}</small>
                </div>
                <div>
                    <span class="badge ${template.status === 'active' ? 'bg-success' : 'bg-secondary'}">
                        ${template.status === 'active' ? '已授权' : '未授权'}
                    </span>
                    <button class="btn btn-sm btn-outline-primary ms-2 apply-template" data-template-id="${template.id}">
                        <i class="bi bi-check-circle"></i> 应用
                    </button>
                </div>
            </div>
        `).join('');

        // 绑定应用模板事件
        document.querySelectorAll('.apply-template').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const templateId = e.target.closest('.apply-template').dataset.templateId;
                this.applyPermissionTemplate(templateId);
            });
        });
    }

    // 显示编辑角色权限模态框
    async showEditRolePermissionsModal(role) {
        // 先获取所有模块列表
        let modules = [];
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/auth/permissions`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.data && data.data.permissions) {
                    // 从权限数据中提取模块信息
                    const moduleMap = {};
                    data.data.permissions.forEach(perm => {
                        if (!moduleMap[perm.module_code]) {
                            moduleMap[perm.module_code] = {
                                code: perm.module_code,
                                name: perm.module_name,
                                description: perm.description
                            };
                        }
                    });
                    modules = Object.values(moduleMap);
                }
            }
        } catch (error) {
            console.error('获取模块列表失败，使用默认模块:', error);
        }
        
        // 如果获取失败，使用默认模块列表（与后端system_modules保持一致）
        if (modules.length === 0) {
            modules = [
                { code: 'signal_sources', name: '信号源管理', description: '信号源管理模块' },
                { code: 'customers', name: '客户管理', description: '客户管理模块' },
                { code: 'strategies', name: '策略管理', description: '策略管理模块' },
                { code: 'market_follow', name: '现价跟单', description: '现价跟单模块' },
                { code: 'limit_follow', name: '限价跟单', description: '限价跟单模块' },
                { code: 'backtest', name: '策略回测', description: '策略回测模块' },
                { code: 'strategy_live', name: '策略实盘', description: '策略实盘模块' },
                { code: 'message_forward', name: '消息转发', description: '消息转发模块' },
                { code: 'system_settings', name: '系统设置', description: '系统设置模块' },
                { code: 'users', name: '用户管理', description: '用户管理模块' }
            ];
        }
        
        // 生成权限表单HTML
        let permissionsHtml = '';
        modules.forEach((module, index) => {
            const colClass = index % 2 === 0 ? 'col-md-6' : 'col-md-6';
            const isNewRow = index % 2 === 0;
            
            if (isNewRow && index > 0) {
                permissionsHtml += '</div><div class="row mt-3">';
            } else if (isNewRow) {
                permissionsHtml += '<div class="row">';
            }
            
            permissionsHtml += `
                <div class="${colClass}">
                    <h6>${module.name}</h6>
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" name="permissions" value="${module.code}:read" id="${module.code}_read">
                        <label class="form-check-label" for="${module.code}_read">查看${module.name.replace('管理', '')}</label>
                    </div>
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" name="permissions" value="${module.code}:write" id="${module.code}_write">
                        <label class="form-check-label" for="${module.code}_write">编辑${module.name.replace('管理', '')}</label>
                    </div>
                </div>
            `;
        });
        
        // 确保最后一个row被关闭
        if (modules.length > 0) {
            permissionsHtml += '</div>';
        }
        
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.id = 'editRolePermissionsModal';
        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">编辑角色权限 - ${role}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body" style="max-height: 70vh; overflow-y: auto;">
                        <form id="editRolePermissionsForm">
                            <input type="hidden" name="role" value="${role}">
                            ${permissionsHtml}
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                        <button type="button" class="btn btn-primary" id="saveRolePermissionsBtn">保存权限</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        const bsModal = new bootstrap.Modal(modal);
        
        // 模态框显示后加载权限
        modal.addEventListener('shown.bs.modal', () => {
            this.loadRolePermissions(role);
        });
        
        bsModal.show();
        
        // 保存权限按钮事件
        document.getElementById('saveRolePermissionsBtn').addEventListener('click', () => {
            this.saveRolePermissions();
        });
        
        // 模态框关闭后移除DOM元素
        modal.addEventListener('hidden.bs.modal', () => {
            document.body.removeChild(modal);
        });
    }

    // 加载角色权限（用于编辑时预勾选）
    async loadRolePermissions(role) {
        try {
            // 获取权限矩阵
            const response = await this.apiRequest(`${this.apiBaseUrl}/auth/permissions/matrix`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.data) {
                    // 查找当前角色的权限
                    const roleData = data.data.find(r => r.role === role);
                    if (roleData && roleData.permissions) {
                        // 勾选对应的复选框
                        roleData.permissions.forEach(perm => {
                            const checkbox = document.getElementById(perm.replace(':', '_'));
                            if (checkbox) {
                                checkbox.checked = true;
                            }
                        });
                    }
                }
            }
        } catch (error) {
            console.error('加载角色权限失败:', error);
        }
    }

    // 显示编辑用户权限模态框
    async showEditUserPermissionsModal(userId) {
        // 先获取所有模块列表和用户权限
        let modules = [];
        let userPermissions = {};
        
        try {
            // 获取模块列表
            const modulesResponse = await this.apiRequest(`${this.apiBaseUrl}/auth/permissions`);
            if (modulesResponse.ok) {
                const modulesData = await modulesResponse.json();
                if (modulesData.success && modulesData.data && modulesData.data.permissions) {
                    const moduleMap = {};
                    modulesData.data.permissions.forEach(perm => {
                        if (!moduleMap[perm.module_code]) {
                            moduleMap[perm.module_code] = {
                                code: perm.module_code,
                                name: perm.module_name,
                                description: perm.description
                            };
                        }
                    });
                    modules = Object.values(moduleMap);
                }
            }
            
            // 如果获取失败，使用默认模块列表
            if (modules.length === 0) {
                modules = [
                    { code: 'signal_sources', name: '信号源管理', description: '信号源管理模块' },
                    { code: 'customers', name: '客户管理', description: '客户管理模块' },
                    { code: 'strategies', name: '策略管理', description: '策略管理模块' },
                    { code: 'market_follow', name: '现价跟单', description: '现价跟单模块' },
                    { code: 'limit_follow', name: '限价跟单', description: '限价跟单模块' },
                    { code: 'backtest', name: '策略回测', description: '策略回测模块' },
                    { code: 'strategy_live', name: '策略实盘', description: '策略实盘模块' },
                    { code: 'message_forward', name: '消息转发', description: '消息转发模块' },
                    { code: 'system_settings', name: '系统设置', description: '系统设置模块' },
                    { code: 'users', name: '用户管理', description: '用户管理模块' }
                ];
            }
            
            // 获取用户权限
            const userPermsResponse = await this.apiRequest(`${this.apiBaseUrl}/auth/users/${userId}/permissions`);
            if (userPermsResponse.ok) {
                const userPermsData = await userPermsResponse.json();
                if (userPermsData.success && userPermsData.data && userPermsData.data.permissions) {
                    userPermsData.data.permissions.forEach(perm => {
                        userPermissions[perm.module_code] = {
                            level: perm.permission_level,
                            source: perm.source
                        };
                    });
                }
            }
        } catch (error) {
            console.error('获取用户权限数据失败:', error);
        }
        
        // 生成权限表单HTML
        let permissionsHtml = '';
        modules.forEach((module, index) => {
            const colClass = 'col-md-6';
            const isNewRow = index % 2 === 0;
            
            if (isNewRow && index > 0) {
                permissionsHtml += '</div><div class="row mt-3">';
            } else if (isNewRow) {
                permissionsHtml += '<div class="row">';
            }
            
            const userPerm = userPermissions[module.code] || { level: 'none', source: 'role' };
            const sourceBadge = userPerm.source === 'user' 
                ? '<span class="badge bg-warning text-dark ms-2">自定义</span>' 
                : '<span class="badge bg-secondary ms-2">角色</span>';
            
            permissionsHtml += `
                <div class="${colClass}">
                    <h6>${module.name} ${sourceBadge}</h6>
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" name="permissions" value="${module.code}:read" id="user_${userId}_${module.code}_read" ${userPerm.level !== 'none' ? 'checked' : ''}>
                        <label class="form-check-label" for="user_${userId}_${module.code}_read">查看${module.name.replace('管理', '')}</label>
                    </div>
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" name="permissions" value="${module.code}:write" id="user_${userId}_${module.code}_write" ${['write', 'admin'].includes(userPerm.level) ? 'checked' : ''}>
                        <label class="form-check-label" for="user_${userId}_${module.code}_write">编辑${module.name.replace('管理', '')}</label>
                    </div>
                </div>
            `;
        });
        
        if (modules.length > 0) {
            permissionsHtml += '</div>';
        }
        
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.id = 'editUserPermissionsModal';
        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">编辑用户权限 - 用户ID: ${userId}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body" style="max-height: 70vh; overflow-y: auto;">
                        <div class="alert alert-info">
                            <i class="bi bi-info-circle"></i> 
                            <strong>说明：</strong>自定义权限会覆盖角色权限。如果某个模块没有自定义权限，将使用角色权限。
                        </div>
                        <form id="editUserPermissionsForm">
                            <input type="hidden" name="user_id" value="${userId}">
                            ${permissionsHtml}
                        </form>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                        <button type="button" class="btn btn-primary" id="saveUserPermissionsBtn">保存权限</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
        
        // 保存权限按钮事件
        document.getElementById('saveUserPermissionsBtn').addEventListener('click', () => {
            this.saveUserPermissions(userId);
        });
        
        // 模态框关闭后移除DOM元素
        modal.addEventListener('hidden.bs.modal', () => {
            document.body.removeChild(modal);
        });
    }

    // 保存用户权限
    async saveUserPermissions(userId) {
        try {
            const form = document.getElementById('editUserPermissionsForm');
            const formData = new FormData(form);
            const permissions = formData.getAll('permissions');
            
            const response = await this.apiRequest(`${this.apiBaseUrl}/auth/users/${userId}/permissions`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ permissions })
            });
            
            if (response && response.ok) {
                const result = await response.json();
                if (result.success) {
                    this.showToast('成功', '用户权限更新成功', 'success');
                    
                    // 如果在权限管理页面，重新加载用户权限列表
                    const currentPage = document.querySelector('.page-content.active');
                    if (currentPage && currentPage.id === 'permission-management-page') {
                        await this.loadUsersForPermissionManagement();
                    }
                    
                    // 如果在用户管理页面，重新加载用户列表
                    if (typeof this.loadUsersList === 'function') {
                        this.loadUsersList();
                    }
                    
                    // 关闭模态框
                    const modalElement = document.querySelector('#editUserPermissionsModal');
                    if (modalElement) {
                        const modalInstance = bootstrap.Modal.getInstance(modalElement);
                        if (modalInstance) {
                            modalInstance.hide();
                        }
                    }
                } else {
                    this.showToast('错误', result.message || '更新用户权限失败', 'danger');
                }
            } else {
                this.showToast('错误', '更新用户权限失败', 'danger');
            }
        } catch (error) {
            console.error('更新用户权限失败:', error);
            this.showToast('错误', '更新用户权限失败', 'danger');
        }
    }

    // 保存角色权限
    async saveRolePermissions() {
        const form = document.getElementById('editRolePermissionsForm');
        const formData = new FormData(form);
        const role = formData.get('role');
        const permissions = formData.getAll('permissions');
        
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/auth/permissions/roles/${role}`, {
                method: 'PUT',
                body: JSON.stringify({ permissions })
            });
            
            if (response && response.ok) {
                const result = await response.json();
                if (result.success) {
                    this.showToast('成功', '角色权限更新成功', 'success');
                    this.loadUserPermissionsMatrix(); // 重新加载权限矩阵
                    
                    // 安全地关闭模态框
                    const modalElement = document.querySelector('#editRolePermissionsModal');
                    if (modalElement) {
                        const modalInstance = bootstrap.Modal.getInstance(modalElement);
                        if (modalInstance) {
                            modalInstance.hide();
                        } else {
                            // 如果没有实例，直接移除模态框
                            modalElement.remove();
                        }
                    }
                } else {
                    this.showToast('错误', result.message || '更新角色权限失败', 'danger');
                }
            } else {
                this.showToast('错误', '更新角色权限失败', 'danger');
            }
        } catch (error) {
            console.error('更新角色权限失败:', error);
            this.showToast('错误', '更新角色权限失败', 'danger');
        }
    }

    // 应用权限模板
    async applyPermissionTemplate(templateId) {
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/auth/permissions/templates/${templateId}/apply`, {
                method: 'POST'
            });
            
            if (response && response.ok) {
                const result = await response.json();
                if (result.success) {
                    this.showToast('成功', '权限模板应用成功', 'success');
                    this.loadPermissionTemplates(); // 重新加载权限模板
                } else {
                    this.showToast('错误', result.message || '应用权限模板失败', 'danger');
                }
            } else {
                this.showToast('错误', '应用权限模板失败', 'danger');
            }
        } catch (error) {
            console.error('应用权限模板失败:', error);
            this.showToast('错误', '应用权限模板失败', 'danger');
        }
    }

    // 加载服务状态
    async loadMessageForwardStatus() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/message-forward/status`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.data) {
                    const status = data.data;
                    
                    // 更新服务状态
                    const statusBadge = document.getElementById('mf-service-status');
                    const startBtn = document.getElementById('startServiceBtn');
                    const stopBtn = document.getElementById('stopServiceBtn');
                    
                    if (statusBadge) {
                        if (status.running) {
                            statusBadge.innerHTML = '<span class="badge bg-success">运行中</span>';
                            if (startBtn) startBtn.style.display = 'none';
                            if (stopBtn) stopBtn.style.display = 'inline-block';
                        } else {
                            statusBadge.innerHTML = '<span class="badge bg-secondary">未启动</span>';
                            if (startBtn) startBtn.style.display = 'inline-block';
                            if (stopBtn) stopBtn.style.display = 'none';
                        }
                    }
                    
                    // 更新统计数据
                    document.getElementById('mf-connected-platforms').textContent = status.connected_platforms || 0;
                    document.getElementById('mf-active-rules').textContent = status.active_rules || 0;
                    document.getElementById('mf-today-forwarded').textContent = status.today_forwarded || 0;
                }
            }
        } catch (error) {
            console.error('加载服务状态失败:', error);
        }
    }

    // 加载平台列表
    async loadPlatformsList() {
        try {
            // 添加时间戳防止浏览器缓存
            const timestamp = new Date().getTime();
            const response = await fetch(`${this.apiBaseUrl}/message-forward/platforms?t=${timestamp}`, {
                method: 'GET',
                headers: {
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                }
            });
            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.renderPlatformsList(data.data || []);
                } else {
                    console.error('加载平台列表失败:', data.message);
                }
            } else {
                console.error('加载平台列表失败，HTTP状态码:', response.status);
            }
        } catch (error) {
            console.error('加载平台列表失败:', error);
        }
    }

    // 渲染平台列表
    renderPlatformsList(platforms) {
        const tbody = document.getElementById('platformsTableBody');
        if (!tbody) return;
        
        if (platforms.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">暂无平台配置</td></tr>';
            return;
        }
        
        tbody.innerHTML = '';
        platforms.forEach(platform => {
            const row = document.createElement('tr');
            
            // 平台图标
            let platformIcon = '';
            switch (platform.platform_type) {
                case 'telegram':
                case 'telegram_mtproto':
                    platformIcon = '<i class="bi bi-telegram text-primary"></i> Telegram';
                    break;
                case 'dingtalk':
                    platformIcon = '<i class="bi bi-chat-dots text-info"></i> 钉钉';
                    break;
                case 'wechat':
                    platformIcon = '<i class="bi bi-wechat text-success"></i> 微信';
                    break;
                case 'wechat_official':
                    platformIcon = '<i class="bi bi-wechat text-primary"></i> 微信公众号';
                    break;
                case 'bicoin':
                    platformIcon = '<i class="bi bi-coin text-warning"></i> 币coin';
                    break;
                case 'coinglass':
                    platformIcon = '<i class="bi bi-graph-up text-info"></i> CoinGlass';
                    break;
                case 'tradingview':
                    platformIcon = '<i class="bi bi-bar-chart text-success"></i> TradingView';
                    break;
                default:
                    platformIcon = this.getPlatformTypeName(platform.platform_type) || platform.platform_type;
            }
            
            // 状态徽章
            let statusBadge = '';
            if (platform.status === 'active' || platform.status === 'connected') {
                statusBadge = '<span class="badge bg-success">已连接</span>';
            } else if (platform.status === 'error') {
                statusBadge = `<span class="badge bg-danger" title="${platform.error_message || ''}">错误</span>`;
            } else if (platform.status === 'disconnected' || platform.status === 'inactive') {
                statusBadge = '<span class="badge bg-secondary">未连接</span>';
            } else {
                // 默认显示未连接
                statusBadge = '<span class="badge bg-secondary">未连接</span>';
            }
            
            // 格式化时间
            const lastConnected = platform.last_connected_at ? 
                new Date(platform.last_connected_at).toLocaleString('zh-CN') : 
                '从未连接';
            
            // 监听群组数量
            const monitoredChatsCount = Array.isArray(platform.monitored_chats) ? platform.monitored_chats.length : 0;
            const monitoredChatsBadge = monitoredChatsCount > 0 ? 
                `<span class="badge bg-info" title="已配置 ${monitoredChatsCount} 个监听群组">${monitoredChatsCount} 个群组</span>` : 
                '<span class="badge bg-secondary">未配置</span>';
            
            row.innerHTML = `
                <td>${platformIcon}</td>
                <td>${platform.platform_name}</td>
                <td>${statusBadge}</td>
                <td>${lastConnected}</td>
                <td>${monitoredChatsBadge}</td>
                <td>
                    <div class="btn-group btn-group-sm">
                        ${platform.platform_type === 'telegram' || platform.platform_type === 'telegram_mtproto' ? 
                            `<button class="btn btn-secondary" onclick="window.app.managePlatformChats(${platform.id})" title="管理监听群组">
                                <i class="bi bi-list-ul"></i> 群组
                            </button>` : ''
                        }
                        <button class="btn btn-primary" onclick="window.app.testPlatform(${platform.id})" title="测试监听功能">
                            <i class="bi bi-play-circle"></i> 测试
                        </button>
                        ${platform.enabled ? 
                            `<button class="btn btn-warning" onclick="window.app.disablePlatform(${platform.id})">
                                <i class="bi bi-pause-fill"></i> 禁用
                            </button>` :
                            `<button class="btn btn-success" onclick="window.app.enablePlatform(${platform.id})">
                                <i class="bi bi-play-fill"></i> 启用
                            </button>`
                        }
                        <button class="btn btn-info" onclick="window.app.editPlatform(${platform.id})">
                            <i class="bi bi-pencil"></i> 编辑
                        </button>
                        <button class="btn btn-danger" onclick="window.app.deletePlatform(${platform.id}, '${platform.platform_name}')">
                            <i class="bi bi-trash"></i> 删除
                        </button>
                    </div>
                </td>
            `;
            
            tbody.appendChild(row);
        });
        
        // 同时更新源平台下拉列表（用于转发规则）
        this.updateSourcePlatformSelect(platforms);
    }
    
    // 更新源平台下拉列表
    updateSourcePlatformSelect(platforms) {
        const select = document.getElementById('sourcePlatform');
        if (!select) return;
        
        // 保存当前选中的值
        const currentValue = select.value;
        
        // 清空并添加默认选项
        select.innerHTML = '<option value="">请选择源平台账户</option>';
        
        // 只添加已启用的平台
        platforms.filter(p => p.enabled).forEach(platform => {
            const option = document.createElement('option');
            option.value = platform.id;
            option.textContent = `${platform.platform_name} (${this.getPlatformTypeName(platform.platform_type)})`;
            select.appendChild(option);
        });
        
        // 恢复之前选中的值
        if (currentValue) {
            select.value = currentValue;
        }
    }
    
    // 获取平台类型名称
    getPlatformTypeName(platformType) {
        const typeMap = {
            'telegram': 'Telegram',
            'telegram_mtproto': 'Telegram',
            'dingtalk': '钉钉',
            'wechat': '微信',
            'wechat_official': '微信公众号',
            'bicoin': '币coin',
            'coinglass': 'CoinGlass',
            'tradingview': 'TradingView'
        };
        return typeMap[platformType] || platformType;
    }
    
    // 测试平台监听
    async testPlatform(platformId) {
        if (!confirm('确认测试平台监听功能？测试将持续30秒，期间会收集收到的消息。')) {
            return;
        }
        
        try {
            const response = await fetch(`${this.apiBaseUrl}/message-forward/platforms/${platformId}/test`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ duration: 30 })
            });
            
            const data = await response.json();
            
            if (data.success) {
                // 使用后端返回的 message（优先）
                let message = data.message || `测试完成！\n收到 ${data.data.messages_count} 条消息`;
                
                // 如果有消息详情，追加显示
                if (data.data.messages_count > 0 && data.data.messages && data.data.messages.length > 0) {
                    const msgPreview = data.data.messages.slice(0, 3).map(m => {
                        const content = m.content || '';
                        return `- ${content.substring(0, 50)}${content.length > 50 ? '...' : ''}`;
                    }).join('\n');
                    message += `\n\n${msgPreview}`;
                }
                
                alert(message);
                this.showToast('成功', data.message || `测试完成，收到 ${data.data.messages_count} 条消息`, 'success');
                
                // 刷新平台列表和消息历史
                await this.loadPlatformsList();
                await this.loadMessageHistory();
            } else {
                // 检查是否需要登录
                if (data.needs_login) {
                    // 显示登录模态框
                    this.showPlatformLoginModal(platformId, data);
                } else {
                    this.showToast('错误', data.message || '测试失败', 'danger');
                }
            }
        } catch (error) {
            console.error('测试平台失败:', error);
            this.showToast('错误', '测试失败: ' + error.message, 'danger');
        }
    }
    
    // 显示平台登录模态框
    showPlatformLoginModal(platformId, data) {
        // 获取模态框（HTML中已定义）
        let modal = document.getElementById('platformLoginModal');
        if (!modal) {
            console.error('登录模态框不存在');
            this.showToast('错误', '登录界面加载失败', 'danger');
            return;
        }
        
        // 确保验证按钮事件已绑定（只绑定一次）
        const verifyBtn = modal.querySelector('#verifyLoginBtn');
        if (verifyBtn && !verifyBtn.dataset.bound) {
            verifyBtn.addEventListener('click', () => {
                const currentPlatformId = modal.dataset.platformId;
                if (currentPlatformId) {
                    this.verifyPlatformLogin(parseInt(currentPlatformId));
                }
            });
            verifyBtn.dataset.bound = 'true';
        }
        
        // 显示相应的步骤
        const phoneCodeStep = modal.querySelector('#loginStepPhoneCode');
        const passwordStep = modal.querySelector('#loginStepPassword');
        const errorDiv = modal.querySelector('#loginError');
        const phoneNumberSpan = modal.querySelector('#loginPhoneNumber');
        
        // 隐藏错误信息
        errorDiv.style.display = 'none';
        
        // 根据步骤显示相应内容
        if (data.step === 'phone_code' || !data.step) {
            phoneCodeStep.style.display = 'block';
            passwordStep.style.display = 'none';
            if (data.phone) {
                phoneNumberSpan.textContent = data.phone;
            }
            modal.querySelector('#phoneCodeInput').value = '';
            modal.querySelector('#passwordInput').value = '';
        } else if (data.step === 'password') {
            phoneCodeStep.style.display = 'none';
            passwordStep.style.display = 'block';
            modal.querySelector('#phoneCodeInput').value = '';
            modal.querySelector('#passwordInput').value = '';
        }
        
        // 保存当前平台ID和步骤到模态框
        modal.dataset.platformId = platformId;
        modal.dataset.currentStep = data.step || 'phone_code';
        
        // 显示模态框
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    }
    
    // 验证平台登录
    async verifyPlatformLogin(platformId) {
        const modal = document.getElementById('platformLoginModal');
        if (!modal) return;
        
        const phoneCodeInput = modal.querySelector('#phoneCodeInput');
        const passwordInput = modal.querySelector('#passwordInput');
        const errorDiv = modal.querySelector('#loginError');
        const verifyBtn = modal.querySelector('#verifyLoginBtn');
        const currentStep = modal.dataset.currentStep || 'phone_code';
        
        // 获取输入值
        const phoneCode = phoneCodeInput.value.trim();
        const password = passwordInput.value.trim();
        
        // 验证输入
        if (currentStep === 'phone_code' && !phoneCode) {
            errorDiv.textContent = '请输入验证码';
            errorDiv.style.display = 'block';
            return;
        }
        
        if (currentStep === 'password' && !password) {
            errorDiv.textContent = '请输入两步验证密码';
            errorDiv.style.display = 'block';
            return;
        }
        
        // 禁用按钮
        verifyBtn.disabled = true;
        verifyBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 验证中...';
        errorDiv.style.display = 'none';
        
        try {
            const response = await fetch(`${this.apiBaseUrl}/message-forward/platforms/${platformId}/login/verify-code`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    phone_code: phoneCode || undefined,
                    password: password || undefined
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                // 登录成功
                this.showToast('成功', '登录成功，session已保存', 'success');
                
                // 关闭模态框
                const bsModal = bootstrap.Modal.getInstance(modal);
                bsModal.hide();
                
                // 刷新平台列表
                await this.loadPlatformsList();
                
                // 提示用户重新测试
                if (confirm('登录成功！是否立即测试平台监听功能？')) {
                    await this.testPlatform(platformId);
                }
            } else {
                // 检查是否需要重新发送验证码
                if (data.needs_resend) {
                    // 需要重新发送验证码
                    errorDiv.textContent = data.message || '验证码已过期，已重新发送验证码，请使用新的验证码';
                    errorDiv.style.display = 'block';
                    // 清空输入框，让用户输入新的验证码
                    phoneCodeInput.value = '';
                    // 更新手机号显示（如果有）
                    if (data.phone) {
                        const phoneNumberSpan = modal.querySelector('#loginPhoneNumber');
                        if (phoneNumberSpan) {
                            phoneNumberSpan.textContent = data.phone;
                        }
                    }
                    // 确保显示验证码输入步骤
                    modal.querySelector('#loginStepPhoneCode').style.display = 'block';
                    modal.querySelector('#loginStepPassword').style.display = 'none';
                    modal.dataset.currentStep = 'phone_code';
                } else if (data.step === 'password') {
                    // 需要输入两步验证密码
                    modal.dataset.currentStep = 'password';
                    modal.querySelector('#loginStepPhoneCode').style.display = 'none';
                    modal.querySelector('#loginStepPassword').style.display = 'block';
                    errorDiv.textContent = data.message || '需要两步验证密码';
                    errorDiv.style.display = 'block';
                } else {
                    // 验证码错误或其他错误
                    errorDiv.textContent = data.message || '验证失败';
                    errorDiv.style.display = 'block';
                }
            }
        } catch (error) {
            console.error('验证登录失败:', error);
            errorDiv.textContent = '验证失败: ' + error.message;
            errorDiv.style.display = 'block';
        } finally {
            // 恢复按钮
            verifyBtn.disabled = false;
            verifyBtn.innerHTML = '<i class="bi bi-check-circle"></i> 验证';
        }
    }
    
    // 管理平台监听群组
    async managePlatformChats(platformId) {
        try {
            // 显示加载提示
            this.showToast('提示', '正在获取群组列表，请稍候...', 'info');
            
            // 获取平台信息
            const platformResponse = await fetch(`${this.apiBaseUrl}/message-forward/platforms/${platformId}`);
            const platformData = await platformResponse.json();
            
            if (!platformData.success) {
                this.showToast('错误', '获取平台信息失败', 'danger');
                return;
            }
            
            const platform = platformData.data;
            
            // 只支持Telegram
            if (platform.platform_type !== 'telegram' && platform.platform_type !== 'telegram_mtproto') {
                this.showToast('提示', '当前仅支持Telegram平台管理群组', 'info');
                return;
            }
            
            // 获取群组列表（性能优化：使用已运行的实例）
            const startTime = Date.now();
            const chatsResponse = await fetch(`${this.apiBaseUrl}/message-forward/platforms/${platformId}/chats`);
            const chatsData = await chatsResponse.json();
            const duration = ((Date.now() - startTime) / 1000).toFixed(2);
            
            console.log(`获取群组列表耗时: ${duration}秒`);
            
            if (!chatsData.success) {
                this.showToast('错误', chatsData.message || '获取群组列表失败', 'danger');
                return;
            }
            
            // 保存群组数据到实例变量，供保存时使用
            this.currentPlatformChats = chatsData.data;
            
            // 显示管理群组模态框
            this.showManageChatsModal(platformId, platform, chatsData.data, platform.monitored_chats || []);
            
        } catch (error) {
            console.error('管理平台群组失败:', error);
            this.showToast('错误', '管理群组失败: ' + error.message, 'danger');
        }
    }
    
    // 显示管理群组模态框
    showManageChatsModal(platformId, platform, allChats, monitoredChats) {
        // 创建或更新模态框
        let modal = document.getElementById('manageChatsModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'manageChatsModal';
            modal.className = 'modal fade';
            modal.innerHTML = `
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">管理监听群组 - ${platform.platform_name}</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <p class="text-muted">选择要监听的群组/频道。只有选中的群组消息会被转发。</p>
                            
                            <div class="mb-3">
                                <input type="text" class="form-control" id="chatSearchInput" placeholder="搜索群组名称...">
                            </div>
                            
                            <div id="chatsListContainer" style="max-height: 400px; overflow-y: auto;">
                                <!-- 群组列表将在这里动态生成 -->
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-primary" id="saveChatsBtn">保存</button>
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
            
            // 绑定保存按钮
            document.getElementById('saveChatsBtn').addEventListener('click', () => {
                this.saveMonitoredChats(platformId);
            });
            
            // 绑定搜索
            document.getElementById('chatSearchInput').addEventListener('input', (e) => {
                this.filterChatsList(e.target.value);
            });
        }
        
        // 更新标题
        modal.querySelector('.modal-title').textContent = `管理监听群组 - ${platform.platform_name}`;
        
        // 渲染群组列表
        this.renderChatsList(allChats, monitoredChats);
        
        // 显示模态框
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
        
        // 保存platformId到模态框
        modal.dataset.platformId = platformId;
    }
    
    // 渲染群组列表
    renderChatsList(allChats, monitoredChats) {
        const container = document.getElementById('chatsListContainer');
        if (!container) return;
        
        // 获取已选中的群组ID集合
        const monitoredChatIds = new Set(
            monitoredChats.map(c => String(c.chat_id || c.id || ''))
        );
        
        if (allChats.length === 0) {
            container.innerHTML = '<p class="text-muted text-center">未找到群组或频道</p>';
            return;
        }
        
        container.innerHTML = allChats.map(chat => {
            const chatId = String(chat.chat_id || chat.id || '');
            const isChecked = monitoredChatIds.has(chatId);
            const chatType = chat.type === 'channel' ? '频道' : '群组';
            const usernameText = chat.username ? `(@${chat.username})` : '';
            
            return `
                <div class="form-check mb-2 chat-item" data-chat-id="${chatId}" data-chat-name="${chat.title}">
                    <input class="form-check-input" type="checkbox" value="${chatId}" 
                           id="chat_${chatId}" ${isChecked ? 'checked' : ''}>
                    <label class="form-check-label" for="chat_${chatId}">
                        <strong>${chat.title}</strong> ${usernameText}
                        <span class="badge bg-secondary">${chatType}</span>
                        ${chat.unread_count > 0 ? `<span class="badge bg-danger">${chat.unread_count}条未读</span>` : ''}
                    </label>
                </div>
            `;
        }).join('');
    }
    
    // 过滤群组列表
    filterChatsList(searchText) {
        const items = document.querySelectorAll('.chat-item');
        const searchLower = searchText.toLowerCase();
        
        items.forEach(item => {
            const chatName = item.dataset.chatName || '';
            if (chatName.toLowerCase().includes(searchLower)) {
                item.style.display = '';
            } else {
                item.style.display = 'none';
            }
        });
    }
    
    // 保存监听的群组
    async saveMonitoredChats(platformId) {
        try {
            const modal = document.getElementById('manageChatsModal');
            if (!modal) return;
            
            // 获取所有群组信息（从之前加载的数据中获取）
            const allChats = this.currentPlatformChats || [];
            
            // 获取选中的群组
            const selectedChatIds = new Set();
            modal.querySelectorAll('.chat-item input:checked').forEach(checkbox => {
                selectedChatIds.add(checkbox.value);
            });
            
            // 构建selectedChats列表
            const selectedChats = allChats
                .filter(chat => selectedChatIds.has(String(chat.chat_id || chat.id)))
                .map(chat => ({
                    chat_id: String(chat.chat_id || chat.id),
                    chat_name: chat.title || '',
                    chat_type: chat.type || (chat.is_channel ? 'channel' : 'group'),
                    username: chat.username || null
                }));
            
            // 更新平台的monitored_chats
            const updateResponse = await fetch(`${this.apiBaseUrl}/message-forward/platforms/${platformId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    monitored_chats: selectedChats
                })
            });
            
            const updateData = await updateResponse.json();
            
            if (updateData.success) {
                this.showToast('成功', `已更新监听群组配置（${selectedChats.length}个）`, 'success');
                
                // 关闭模态框
                const bsModal = bootstrap.Modal.getInstance(modal);
                if (bsModal) {
                    bsModal.hide();
                }
                
                // 刷新平台列表
                await this.loadPlatformsList();
            } else {
                this.showToast('错误', updateData.message || '保存失败', 'danger');
            }
            
        } catch (error) {
            console.error('保存监听群组失败:', error);
            this.showToast('错误', '保存失败: ' + error.message, 'danger');
        }
    }

    // 加载转发规则列表
    async loadForwardRulesList() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/message-forward/rules`);
            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.renderForwardRulesList(data.data || []);
                }
            }
        } catch (error) {
            console.error('加载转发规则失败:', error);
        }
    }

    // 渲染转发规则列表
    renderForwardRulesList(rules) {
        const tbody = document.getElementById('forwardRulesTableBody');
        if (!tbody) {
            console.error('找不到 forwardRulesTableBody 元素');
            return;
        }
        
        if (rules.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">暂无转发规则</td></tr>';
            return;
        }
        
        tbody.innerHTML = '';
        rules.forEach(rule => {
            const row = document.createElement('tr');
            
            // 目标平台
            const targetPlatforms = Array.isArray(rule.target_platforms) ? 
                rule.target_platforms.join(', ') : 
                (rule.target_platforms || '');
            
            // 状态
            const statusBadge = rule.enabled ? 
                '<span class="badge bg-success">启用</span>' : 
                '<span class="badge bg-secondary">禁用</span>';
            
            row.innerHTML = `
                <td>${rule.rule_name}</td>
                <td><span class="badge bg-primary">${rule.source_platform_name || rule.source_platform || '所有'}</span></td>
                <td>${targetPlatforms}</td>
                <td>${statusBadge}</td>
                <td>${rule.messages_forwarded || 0}</td>
                <td>
                    <div class="btn-group btn-group-sm">
                        ${rule.enabled ? 
                            `<button class="btn btn-warning" onclick="window.app.disableRule('${rule.rule_id}')">
                                <i class="bi bi-pause-fill"></i> 禁用
                            </button>` :
                            `<button class="btn btn-success" onclick="window.app.enableRule('${rule.rule_id}')">
                                <i class="bi bi-play-fill"></i> 启用
                            </button>`
                        }
                        <button class="btn btn-info" onclick="window.app.editRule('${rule.rule_id}')">
                            <i class="bi bi-pencil"></i> 编辑
                        </button>
                        <button class="btn btn-danger" onclick="window.app.deleteRule('${rule.rule_id}', '${rule.rule_name}')">
                            <i class="bi bi-trash"></i> 删除
                        </button>
                    </div>
                </td>
            `;
            
            tbody.appendChild(row);
        });
    }

    // 加载消息历史
    async loadMessageHistory() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/message-forward/history?limit=100`);
            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.renderMessageHistory(data.data || []);
                }
            }
        } catch (error) {
            console.error('加载消息历史失败:', error);
        }
    }

    // 渲染消息历史
    renderMessageHistory(messages) {
        const tbody = document.getElementById('historyTableBody');
        if (!tbody) return;
        
        if (messages.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">暂无消息历史</td></tr>';
            return;
        }
        
        tbody.innerHTML = '';
        messages.forEach(msg => {
            const row = document.createElement('tr');
            
            // 格式化时间：后端返回的是 ISO 格式的本地时间
            let timestamp;
            try {
                if (msg.timestamp) {
                    // ISO 格式: "2025-11-10T16:46:20"
                    // 手动解析，确保跨浏览器兼容
                    let date;
                    if (msg.timestamp.includes('T')) {
                        // ISO 格式，手动解析各个部分
                        const [datePart, timePart] = msg.timestamp.split('T');
                        const [year, month, day] = datePart.split('-').map(Number);
                        const [hours, minutes, seconds] = timePart.split(':').map(Number);
                        // 使用本地时区创建 Date 对象
                        date = new Date(year, month - 1, day, hours, minutes, seconds || 0);
                    } else {
                        // 其他格式，尝试直接解析
                        date = new Date(msg.timestamp);
                    }
                    
                    // 检查是否有效
                    if (isNaN(date.getTime())) {
                        timestamp = msg.timestamp;
                    } else {
                        // 手动格式化为 YYYY/MM/DD HH:MM:SS
                        const year = date.getFullYear();
                        const month = String(date.getMonth() + 1).padStart(2, '0');
                        const day = String(date.getDate()).padStart(2, '0');
                        const hours = String(date.getHours()).padStart(2, '0');
                        const minutes = String(date.getMinutes()).padStart(2, '0');
                        const seconds = String(date.getSeconds()).padStart(2, '0');
                        timestamp = `${year}/${month}/${day} ${hours}:${minutes}:${seconds}`;
                    }
                } else {
                    timestamp = '-';
                }
            } catch (e) {
                console.error('时间格式化失败:', e, msg.timestamp);
                timestamp = msg.timestamp || '-';
            }
            
            const content = msg.content.length > 50 ? msg.content.substring(0, 50) + '...' : msg.content;
            const forwardedTo = Array.isArray(msg.forwarded_to) ? msg.forwarded_to.join(', ') : (msg.forwarded_to || '-');
            const chatTitle = msg.source_chat_title || '-';
            
            row.innerHTML = `
                <td>${timestamp}</td>
                <td><span class="badge bg-primary">${msg.source_platform}</span></td>
                <td>${chatTitle}</td>
                <td>${content}</td>
                <td>${forwardedTo}</td>
            `;
            
            tbody.appendChild(row);
        });
    }

    // 保存新平台
    async savePlatform() {
        try {
            const platformType = document.getElementById('platformType').value;
            const platformName = document.getElementById('platformName').value;
            const platformEnabled = document.getElementById('platformEnabled').checked;
            
            if (!platformType || !platformName) {
                this.showToast('错误', '请填写所有必填项', 'warning');
                return;
            }
            
            // 构建配置对象
            let config = {};
            
            switch (platformType) {
                case 'telegram':
                    config.api_id = document.getElementById('telegramApiId').value;
                    config.api_hash = document.getElementById('telegramApiHash').value;
                    config.phone = document.getElementById('telegramPhone').value || '';
                    config.session_string = document.getElementById('telegramSessionString').value.trim() || '';
                    
                    if (!config.api_id || !config.api_hash) {
                        this.showToast('错误', '请填写 API ID 和 API Hash', 'warning');
                        return;
                    }
                    
                    if (!config.phone && !config.session_string) {
                        this.showToast('错误', '请填写手机号码或会话字符串', 'warning');
                        return;
                    }
                    break;
                
                case 'dingtalk':
                    config.webhook_url = document.getElementById('dingtalkWebhook').value;
                    config.secret = document.getElementById('dingtalkSecret').value || '';
                    if (!config.webhook_url) {
                        this.showToast('错误', '请填写 Webhook URL', 'warning');
                        return;
                    }
                    break;
                
                case 'wechat':
                    config.hot_reload = document.getElementById('wechatHotReload').checked;
                    break;
                
                case 'wechat_official':
                    config.app_id = document.getElementById('wechat_officialAppId').value;
                    config.app_secret = document.getElementById('wechat_officialAppSecret').value;
                    config.token = document.getElementById('wechat_officialToken').value || '';
                    
                    if (!config.app_id || !config.app_secret) {
                        this.showToast('错误', '请填写 AppID 和 AppSecret', 'warning');
                        return;
                    }
                    break;
                
                case 'coinglass':
                    config.api_key = document.getElementById('coinglassApiKey').value;
                    config.api_secret = document.getElementById('coinglassApiSecret').value || '';
                    config.enable_whale_alert = document.getElementById('coinglassEnableWhaleAlert').checked;
                    config.polling_interval = parseInt(document.getElementById('coinglassPollingInterval').value) || 10;
                    config.min_position_value = parseFloat(document.getElementById('coinglassMinPositionValue').value) || 1000000;
                    
                    if (!config.api_key) {
                        this.showToast('错误', '请填写 CoinGlass API Key', 'warning');
                        return;
                    }
                    break;
                
                case 'bicoin':
                    const connectionType = document.getElementById('bicoinConnectionType').value;
                    config.use_webhook = (connectionType === 'webhook');
                    config.use_websocket = (connectionType === 'websocket');
                    config.use_api = (connectionType === 'api');
                    config.use_crawler = (connectionType === 'crawler');
                    
                    if (config.use_webhook) {
                        config.webhook_port = parseInt(document.getElementById('bicoinWebhookPort').value) || 8080;
                        config.webhook_path = '/bicoin/webhook';
                    }
                    
                    if (config.use_api) {
                        config.api_token = document.getElementById('bicoinApiToken').value || '';
                    }
                    break;
                
                case 'tradingview':
                    config.use_webhook = true;  // TradingView仅支持Webhook
                    config.webhook_port = parseInt(document.getElementById('tradingviewWebhookPort').value) || 8080;
                    config.webhook_path = document.getElementById('tradingviewWebhookPath').value || '/tradingview/webhook';
                    config.secret_key = document.getElementById('tradingviewSecretKey').value || '';
                    
                    // 策略过滤器
                    const strategyFilterStr = document.getElementById('tradingviewStrategyFilter').value.trim();
                    config.strategy_filter = strategyFilterStr ? strategyFilterStr.split(',').map(s => s.trim()) : [];
                    
                    // 交易对过滤器
                    const symbolFilterStr = document.getElementById('tradingviewSymbolFilter').value.trim();
                    config.symbol_filter = symbolFilterStr ? symbolFilterStr.split(',').map(s => s.trim()) : [];
                    break;
            }
            
            // 发送请求
            const response = await fetch(`${this.apiBaseUrl}/message-forward/platforms`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    platform_type: platformType,
                    platform_name: platformName,
                    enabled: platformEnabled,
                    config: config
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast('成功', '平台添加成功', 'success');
                
                // 关闭模态框
                const modal = bootstrap.Modal.getInstance(document.getElementById('addPlatformModal'));
                modal.hide();
                
                // 重置表单
                document.getElementById('addPlatformForm').reset();
                
                // 刷新列表
                await this.loadPlatformsList();
                await this.loadMessageForwardStatus();
            } else {
                this.showToast('错误', data.message || '添加平台失败', 'danger');
            }
            
        } catch (error) {
            console.error('保存平台失败:', error);
            this.showToast('错误', '保存平台失败: ' + error.message, 'danger');
        }
    }

    // 启用/禁用平台
    async enablePlatform(platformId) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/message-forward/platforms/${platformId}/enable`, {
                method: 'POST'
            });
            
            const data = await response.json();
            if (data.success) {
                this.showToast('成功', '平台已启用', 'success');
                await this.loadPlatformsList();
                await this.loadMessageForwardStatus();
            } else {
                this.showToast('错误', data.message || '启用平台失败', 'danger');
            }
        } catch (error) {
            console.error('启用平台失败:', error);
            this.showToast('错误', '启用平台失败', 'danger');
        }
    }

    async disablePlatform(platformId) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/message-forward/platforms/${platformId}/disable`, {
                method: 'POST'
            });
            
            const data = await response.json();
            if (data.success) {
                this.showToast('成功', '平台已禁用', 'success');
                await this.loadPlatformsList();
                await this.loadMessageForwardStatus();
            } else {
                this.showToast('错误', data.message || '禁用平台失败', 'danger');
            }
        } catch (error) {
            console.error('禁用平台失败:', error);
            this.showToast('错误', '禁用平台失败', 'danger');
        }
    }

    // 删除平台
    async deletePlatform(platformId, platformName) {
        if (!confirm(`确定要删除平台"${platformName}"吗？此操作不可恢复。`)) {
            return;
        }
        
        try {
            const response = await fetch(`${this.apiBaseUrl}/message-forward/platforms/${platformId}`, {
                method: 'DELETE'
            });
            
            const data = await response.json();
            if (data.success) {
                this.showToast('成功', '平台已删除', 'success');
                await this.loadPlatformsList();
                await this.loadMessageForwardStatus();
            } else {
                this.showToast('错误', data.message || '删除平台失败', 'danger');
            }
        } catch (error) {
            console.error('删除平台失败:', error);
            this.showToast('错误', '删除平台失败', 'danger');
        }
    }

    // 加载目标平台列表
    async loadTargetPlatforms() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/message-forward/platforms`);
            const result = await response.json();
            
            if (!result.success) {
                console.error('加载平台列表失败:', result.message);
                return;
            }
            
            const platforms = result.data || [];
            
            // 过滤：只显示启用的、支持发送的平台
            const sendablePlatformTypes = ['telegram', 'dingtalk', 'wechat', 'bicoin', 'tradingview'];
            const targetPlatforms = platforms.filter(p => 
                p.enabled && sendablePlatformTypes.includes(p.platform_type)
            );
            
            this.renderTargetPlatforms(targetPlatforms);
            
        } catch (error) {
            console.error('加载目标平台列表失败:', error);
        }
    }
    
    // 渲染目标平台复选框
    renderTargetPlatforms(platforms) {
        const container = document.getElementById('targetPlatformsContainer');
        if (!container) return;
        
        if (platforms.length === 0) {
            container.innerHTML = '<div class="alert alert-warning">暂无可用的目标平台，请先在"平台管理"中添加并启用平台</div>';
            return;
        }
        
        // 按平台类型分组
        const platformsByType = {};
        platforms.forEach(platform => {
            if (!platformsByType[platform.platform_type]) {
                platformsByType[platform.platform_type] = [];
            }
            platformsByType[platform.platform_type].push(platform);
        });
        
        // 平台类型的中文名称
        const platformTypeNames = {
            'telegram': 'Telegram',
            'dingtalk': '钉钉',
            'wechat': '微信',
            'bicoin': '币coin',
            'tradingview': 'TradingView'
        };
        
        let html = '';
        
        // 渲染每个平台类型
        Object.keys(platformsByType).forEach(platformType => {
            const typePlatforms = platformsByType[platformType];
            const typeName = platformTypeNames[platformType] || platformType;
            
            typePlatforms.forEach(platform => {
                const platformId = `target_${platform.platform_type}_${platform.id}`;
                // 总是显示实例名称，让用户知道选择的是哪个具体实例
                const displayName = `${typeName} - ${platform.platform_name}`;
                
                html += `
                    <div class="form-check">
                        <input class="form-check-input target-platform" type="checkbox" 
                               id="${platformId}" 
                               value="${platform.id}" 
                               data-platform-type="${platform.platform_type}"
                               data-platform-name="${platform.platform_name}">
                        <label class="form-check-label" for="${platformId}">
                            ${displayName}
                        </label>
                    </div>
                `;
            });
        });
        
        container.innerHTML = html;
        
        // 为每个复选框添加事件监听器
        container.querySelectorAll('.target-platform').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                // 从 data-platform-type 获取平台类型（因为 value 现在是平台ID）
                const platformType = e.target.getAttribute('data-platform-type');
                const containerId = `${platformType}TargetContainer`;
                const containerEl = document.getElementById(containerId);
                if (containerEl) {
                    containerEl.style.display = e.target.checked ? 'block' : 'none';
                }
            });
        });
    }

    // 保存转发规则
    async saveForwardRule() {
        try {
            const ruleName = document.getElementById('forwardRuleName')?.value?.trim() || '';
            const ruleEnabled = document.getElementById('forwardRuleEnabled')?.checked || false;
            const sourcePlatform = document.getElementById('sourcePlatform')?.value?.trim() || '';
            const sourceChatIds = document.getElementById('sourceChatIds')?.value?.trim() || '';
            
            // 验证规则名称
            if (!ruleName) {
                this.showToast('错误', '请填写规则名称', 'warning');
                const ruleNameInput = document.getElementById('forwardRuleName');
                if (ruleNameInput) {
                    ruleNameInput.focus();
                }
                return;
            }
            
            // 验证源平台（现在使用平台ID）
            if (!sourcePlatform) {
                this.showToast('错误', '请选择源平台账户', 'warning');
                const sourcePlatformSelect = document.getElementById('sourcePlatform');
                if (sourcePlatformSelect) {
                    sourcePlatformSelect.focus();
                }
                return;
            }
            
            // 解析平台ID（格式：platform_id:platform_type）
            const sourcePlatformId = parseInt(sourcePlatform);
            if (isNaN(sourcePlatformId)) {
                this.showToast('错误', '无效的源平台账户', 'warning');
                return;
            }
            
            // 获取目标平台（现在保存的是平台实例ID，而不是平台类型）
            const targetPlatformIds = [];  // 平台实例ID列表
            const targetPlatformTypes = []; // 平台类型列表（用于兼容旧代码）
            const targetChatIds = {};
            
            document.querySelectorAll('.target-platform:checked').forEach(checkbox => {
                const platformId = parseInt(checkbox.value); // 平台实例ID
                const platformType = checkbox.getAttribute('data-platform-type'); // 平台类型
                
                targetPlatformIds.push(platformId);
                if (!targetPlatformTypes.includes(platformType)) {
                    targetPlatformTypes.push(platformType);
                }
                
                // 获取对应的chat_ids（使用平台类型作为key，因为可能有多个同类型实例）
                const chatIdsInput = document.getElementById(`${platformType}TargetChatIds`);
                if (chatIdsInput && chatIdsInput.value) {
                    // 如果该平台类型还没有chat_ids，则设置
                    if (!targetChatIds[platformType]) {
                        targetChatIds[platformType] = chatIdsInput.value.split(',').map(id => id.trim()).filter(id => id);
                    }
                } else if (!targetChatIds[platformType]) {
                    targetChatIds[platformType] = [];
                }
            });
            
            if (targetPlatformIds.length === 0) {
                this.showToast('错误', '请至少选择一个目标平台', 'warning');
                return;
            }
            
            // 构建规则对象（使用source_platform_id和target_platform_ids）
            const ruleData = {
                rule_name: ruleName,
                enabled: ruleEnabled,
                source_platform_id: sourcePlatformId,  // 使用平台ID
                source_chat_ids: sourceChatIds ? sourceChatIds.split(',').map(id => id.trim()).filter(id => id) : [],
                target_platform_ids: targetPlatformIds,  // 新增：保存平台实例ID列表
                target_platforms: targetPlatformTypes,  // 保留：平台类型列表（用于兼容）
                target_chat_ids: targetChatIds,
                keywords: document.getElementById('keywords').value ? 
                    document.getElementById('keywords').value.split(',').map(k => k.trim()).filter(k => k) : [],
                exclude_keywords: document.getElementById('excludeKeywords').value ? 
                    document.getElementById('excludeKeywords').value.split(',').map(k => k.trim()).filter(k => k) : [],
                add_prefix: document.getElementById('addPrefix').value || '',
                add_suffix: document.getElementById('addSuffix').value || '',
                enable_markdown: document.getElementById('enableMarkdown').checked
            };
            
            // 检查是更新还是新建
            const modal = document.getElementById('addForwardRuleModal');
            const ruleId = modal?.dataset?.ruleId;
            const isUpdate = !!ruleId;
            
            // 发送请求
            const url = isUpdate ? 
                `${this.apiBaseUrl}/message-forward/rules/${ruleId}` : 
                `${this.apiBaseUrl}/message-forward/rules`;
            const method = isUpdate ? 'PUT' : 'POST';
            
            const response = await fetch(url, {
                method: method,
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(ruleData)
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast('成功', isUpdate ? '转发规则更新成功' : '转发规则添加成功', 'success');
                
                // 关闭模态框
                const modalInstance = bootstrap.Modal.getInstance(modal);
                if (modalInstance) {
                    modalInstance.hide();
                }
                
                // 重置表单和状态
                document.getElementById('addForwardRuleForm').reset();
                if (modal) {
                    delete modal.dataset.ruleId;
                }
                
                // 恢复模态框标题和按钮文本
                const modalTitle = document.querySelector('#addForwardRuleModal .modal-title');
                if (modalTitle) {
                    modalTitle.textContent = '添加转发规则';
                }
                const saveButton = document.querySelector('#addForwardRuleModal .btn-primary[type="submit"]');
                if (saveButton) {
                    saveButton.textContent = '保存规则';
                }
                
                // 刷新列表
                await this.loadForwardRulesList();
                await this.loadMessageForwardStatus();
            } else {
                this.showToast('错误', data.message || (isUpdate ? '更新规则失败' : '添加规则失败'), 'danger');
            }
            
        } catch (error) {
            console.error('保存规则失败:', error);
            this.showToast('错误', '保存规则失败: ' + error.message, 'danger');
        }
    }

    // 启用/禁用规则
    async enableRule(ruleId) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/message-forward/rules/${ruleId}/enable`, {
                method: 'POST'
            });
            
            const data = await response.json();
            if (data.success) {
                this.showToast('成功', '规则已启用', 'success');
                await this.loadForwardRulesList();
                await this.loadMessageForwardStatus();
            } else {
                this.showToast('错误', data.message || '启用规则失败', 'danger');
            }
        } catch (error) {
            console.error('启用规则失败:', error);
            this.showToast('错误', '启用规则失败', 'danger');
        }
    }

    async disableRule(ruleId) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/message-forward/rules/${ruleId}/disable`, {
                method: 'POST'
            });
            
            const data = await response.json();
            if (data.success) {
                this.showToast('成功', '规则已禁用', 'success');
                await this.loadForwardRulesList();
                await this.loadMessageForwardStatus();
            } else {
                this.showToast('错误', data.message || '禁用规则失败', 'danger');
            }
        } catch (error) {
            console.error('禁用规则失败:', error);
            this.showToast('错误', '禁用规则失败', 'danger');
        }
    }

    // 删除规则
    async deleteRule(ruleId, ruleName) {
        if (!confirm(`确定要删除规则"${ruleName}"吗？此操作不可恢复。`)) {
            return;
        }
        
        try {
            const response = await fetch(`${this.apiBaseUrl}/message-forward/rules/${ruleId}`, {
                method: 'DELETE'
            });
            
            const data = await response.json();
            if (data.success) {
                this.showToast('成功', '规则已删除', 'success');
                await this.loadForwardRulesList();
                await this.loadMessageForwardStatus();
            } else {
                this.showToast('错误', data.message || '删除规则失败', 'danger');
            }
        } catch (error) {
            console.error('删除规则失败:', error);
            this.showToast('错误', '删除规则失败', 'danger');
        }
    }

    // 编辑平台
    async editPlatform(platformId) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/message-forward/platforms/${platformId}`);
            const result = await response.json();
            
            if (!result.success) {
                this.showToast('错误', result.message || '获取平台信息失败', 'danger');
                return;
            }
            
            const platform = result.data;
            
            // 填充基本信息
            document.getElementById('editPlatformId').value = platform.id;
            document.getElementById('editPlatformName').value = platform.platform_name;
            document.getElementById('editPlatformEnabled').checked = platform.enabled;
            
            // 根据平台类型生成配置字段
            this.renderEditPlatformConfigFields(platform.platform_type, platform.config || {});
            
            // 显示模态框
            const modal = new bootstrap.Modal(document.getElementById('editPlatformModal'));
            modal.show();
            
        } catch (error) {
            console.error('加载平台信息失败:', error);
            this.showToast('错误', '加载平台信息失败', 'danger');
        }
    }
    
    // 渲染编辑平台的配置字段
    renderEditPlatformConfigFields(platformType, config) {
        const container = document.getElementById('editPlatformConfigFields');
        container.innerHTML = '';
        
        let fieldsHtml = '';
        
        switch (platformType) {
            case 'telegram':
                fieldsHtml = `
                    <div class="mb-3">
                        <label for="editTelegramApiId" class="form-label">API ID</label>
                        <input type="text" class="form-control" id="editTelegramApiId" value="${config.api_id || ''}" required>
                    </div>
                    <div class="mb-3">
                        <label for="editTelegramApiHash" class="form-label">API Hash</label>
                        <input type="text" class="form-control" id="editTelegramApiHash" value="${config.api_hash || ''}" required>
                    </div>
                    <div class="mb-3">
                        <label for="editTelegramPhone" class="form-label">手机号码（+86开头）</label>
                        <input type="text" class="form-control" id="editTelegramPhone" value="${config.phone || ''}" placeholder="+8613800138000">
                    </div>
                    <div class="mb-3">
                        <label for="editTelegramSessionString" class="form-label">Session String（选填，如已登录）</label>
                        <textarea class="form-control" id="editTelegramSessionString" rows="3" placeholder="登录后获取的会话字符串">${config.session_string || ''}</textarea>
                        <small class="text-muted">如果为空，首次使用需要测试平台进行登录验证</small>
                    </div>
                `;
                break;
                
            case 'dingtalk':
                fieldsHtml = `
                    <div class="mb-3">
                        <label for="editDingtalkWebhook" class="form-label">Webhook URL</label>
                        <input type="text" class="form-control" id="editDingtalkWebhook" value="${config.webhook_url || ''}" required>
                    </div>
                    <div class="mb-3">
                        <label for="editDingtalkSecret" class="form-label">Secret（选填）</label>
                        <input type="text" class="form-control" id="editDingtalkSecret" value="${config.secret || ''}">
                    </div>
                `;
                break;
                
            case 'wechat':
                fieldsHtml = `
                    <div class="form-check mb-3">
                        <input class="form-check-input" type="checkbox" id="editWechatHotReload" ${config.hot_reload ? 'checked' : ''}>
                        <label class="form-check-label" for="editWechatHotReload">
                            启用热加载
                        </label>
                    </div>
                `;
                break;
                
            case 'wechat_official':
                fieldsHtml = `
                    <div class="alert alert-info mb-3">
                        <i class="bi bi-info-circle"></i> <strong>微信公众号配置</strong><br>
                        <small>配置微信公众号用于接收和发送消息。需要先在微信公众平台配置服务器URL。</small>
                    </div>
                    <div class="mb-3">
                        <label for="editWechatOfficialAppId" class="form-label">AppID <span class="text-danger">*</span></label>
                        <input type="text" class="form-control" id="editWechatOfficialAppId" value="${config.app_id || ''}" placeholder="wxca0a7ba829d1bd7b" required>
                        <small class="text-muted">从微信公众平台"开发" -> "基本配置"获取</small>
                    </div>
                    <div class="mb-3">
                        <label for="editWechatOfficialAppSecret" class="form-label">AppSecret <span class="text-danger">*</span></label>
                        <input type="password" class="form-control" id="editWechatOfficialAppSecret" value="${config.app_secret || ''}" placeholder="输入AppSecret" required>
                        <small class="text-muted">从微信公众平台"开发" -> "基本配置"获取，需要妥善保管</small>
                    </div>
                    <div class="mb-3">
                        <label for="editWechatOfficialToken" class="form-label">Token（服务器验证）</label>
                        <input type="text" class="form-control" id="editWechatOfficialToken" value="${config.token || ''}" placeholder="设置一个随机字符串用于验证">
                        <small class="text-muted">用于微信服务器验证，建议使用随机字符串。需要在微信公众平台"服务器配置"中填写相同的Token</small>
                    </div>
                    <div class="alert alert-warning">
                        <i class="bi bi-exclamation-triangle"></i> <strong>服务器配置步骤：</strong><br>
                        <small>
                            1. 保存配置后，在微信公众平台"开发" -> "基本配置" -> "服务器配置"中配置：<br>
                            &nbsp;&nbsp;&nbsp;&nbsp;URL: <code>https://your-domain.com/webhook/wechat_official</code><br>
                            &nbsp;&nbsp;&nbsp;&nbsp;Token: 与上面填写的Token一致<br>
                            &nbsp;&nbsp;&nbsp;&nbsp;消息加解密方式: 选择"明文模式"<br>
                            2. 点击"提交"进行验证<br>
                            3. 验证成功后，用户关注或发送消息时，系统会自动记录用户的openid
                        </small>
                    </div>
                `;
                break;
                
            case 'coinglass':
                fieldsHtml = `
                    <div class="mb-3">
                        <label for="editCoinglassApiKey" class="form-label">API Key</label>
                        <input type="text" class="form-control" id="editCoinglassApiKey" value="${config.api_key || ''}" required>
                    </div>
                    <div class="mb-3">
                        <label for="editCoinglassApiSecret" class="form-label">API Secret（选填）</label>
                        <input type="text" class="form-control" id="editCoinglassApiSecret" value="${config.api_secret || ''}">
                    </div>
                    <div class="form-check mb-3">
                        <input class="form-check-input" type="checkbox" id="editCoinglassEnableWhaleAlert" ${config.enable_whale_alert ? 'checked' : ''}>
                        <label class="form-check-label" for="editCoinglassEnableWhaleAlert">
                            启用巨鲸预警
                        </label>
                    </div>
                    <div class="mb-3">
                        <label for="editCoinglassPollingInterval" class="form-label">轮询间隔（秒）</label>
                        <input type="number" class="form-control" id="editCoinglassPollingInterval" value="${config.polling_interval || 10}" min="1">
                    </div>
                    <div class="mb-3">
                        <label for="editCoinglassMinPositionValue" class="form-label">最小持仓价值（USD）</label>
                        <input type="number" class="form-control" id="editCoinglassMinPositionValue" value="${config.min_position_value || 1000000}" min="0">
                    </div>
                `;
                break;
                
            case 'bicoin':
                const connectionType = config.use_webhook ? 'webhook' : 
                                      config.use_websocket ? 'websocket' : 
                                      config.use_api ? 'api' : 
                                      config.use_crawler ? 'crawler' : 'webhook';
                fieldsHtml = `
                    <div class="mb-3">
                        <label for="editBicoinConnectionType" class="form-label">连接类型</label>
                        <select class="form-select" id="editBicoinConnectionType">
                            <option value="webhook" ${connectionType === 'webhook' ? 'selected' : ''}>Webhook</option>
                            <option value="websocket" ${connectionType === 'websocket' ? 'selected' : ''}>WebSocket</option>
                            <option value="api" ${connectionType === 'api' ? 'selected' : ''}>API轮询</option>
                            <option value="crawler" ${connectionType === 'crawler' ? 'selected' : ''}>网页爬虫</option>
                        </select>
                    </div>
                    <div class="mb-3" id="editBicoinWebhookConfig" style="display: ${connectionType === 'webhook' ? 'block' : 'none'};">
                        <label for="editBicoinWebhookPort" class="form-label">Webhook 端口</label>
                        <input type="number" class="form-control" id="editBicoinWebhookPort" value="${config.webhook_port || 8080}" min="1" max="65535">
                    </div>
                    <div class="mb-3" id="editBicoinApiConfig" style="display: ${connectionType === 'api' ? 'block' : 'none'};">
                        <label for="editBicoinApiToken" class="form-label">API Token</label>
                        <input type="text" class="form-control" id="editBicoinApiToken" value="${config.api_token || ''}">
                    </div>
                `;
                break;
                
            case 'tradingview':
                fieldsHtml = `
                    <div class="mb-3">
                        <label for="editTradingviewWebhookPort" class="form-label">Webhook 端口</label>
                        <input type="number" class="form-control" id="editTradingviewWebhookPort" value="${config.webhook_port || 8080}" min="1" max="65535">
                    </div>
                    <div class="mb-3">
                        <label for="editTradingviewWebhookPath" class="form-label">Webhook 路径</label>
                        <input type="text" class="form-control" id="editTradingviewWebhookPath" value="${config.webhook_path || '/tradingview/webhook'}">
                    </div>
                    <div class="mb-3">
                        <label for="editTradingviewSecretKey" class="form-label">Secret Key（选填）</label>
                        <input type="text" class="form-control" id="editTradingviewSecretKey" value="${config.secret_key || ''}">
                    </div>
                    <div class="mb-3">
                        <label for="editTradingviewStrategyFilter" class="form-label">策略过滤器（逗号分隔）</label>
                        <input type="text" class="form-control" id="editTradingviewStrategyFilter" value="${(config.strategy_filter || []).join(', ')}" placeholder="策略1, 策略2">
                    </div>
                    <div class="mb-3">
                        <label for="editTradingviewSymbolFilter" class="form-label">交易对过滤器（逗号分隔）</label>
                        <input type="text" class="form-control" id="editTradingviewSymbolFilter" value="${(config.symbol_filter || []).join(', ')}" placeholder="BTCUSDT, ETHUSDT">
                    </div>
                `;
                break;
        }
        
        container.innerHTML = fieldsHtml;
        
        // 为 bicoin 添加连接类型切换事件
        if (platformType === 'bicoin') {
            const connectionTypeSelect = document.getElementById('editBicoinConnectionType');
            if (connectionTypeSelect) {
                connectionTypeSelect.addEventListener('change', (e) => {
                    document.getElementById('editBicoinWebhookConfig').style.display = e.target.value === 'webhook' ? 'block' : 'none';
                    document.getElementById('editBicoinApiConfig').style.display = e.target.value === 'api' ? 'block' : 'none';
                });
            }
        }
    }
    
    // 保存平台编辑
    async updatePlatform() {
        try {
            const platformId = document.getElementById('editPlatformId').value;
            const platformName = document.getElementById('editPlatformName').value;
            const platformEnabled = document.getElementById('editPlatformEnabled').checked;
            
            if (!platformName) {
                this.showToast('错误', '请填写平台名称', 'warning');
            return;
        }
        
            // 获取当前平台信息以确定平台类型
            const getResponse = await fetch(`${this.apiBaseUrl}/message-forward/platforms/${platformId}`);
            const getResult = await getResponse.json();
            
            if (!getResult.success) {
                this.showToast('错误', '获取平台信息失败', 'danger');
                return;
            }
            
            const platformType = getResult.data.platform_type;
            
            // 构建配置对象
            let config = {};
            
            switch (platformType) {
                case 'telegram':
                    config.api_id = document.getElementById('editTelegramApiId').value;
                    config.api_hash = document.getElementById('editTelegramApiHash').value;
                    config.phone = document.getElementById('editTelegramPhone').value || '';
                    config.session_string = document.getElementById('editTelegramSessionString').value.trim() || '';
                    
                    if (!config.api_id || !config.api_hash) {
                        this.showToast('错误', '请填写 API ID 和 API Hash', 'warning');
                        return;
                    }
                    break;
                
                case 'dingtalk':
                    config.webhook_url = document.getElementById('editDingtalkWebhook').value;
                    config.secret = document.getElementById('editDingtalkSecret').value || '';
                    if (!config.webhook_url) {
                        this.showToast('错误', '请填写 Webhook URL', 'warning');
                        return;
                    }
                    break;
                
                case 'wechat':
                    config.hot_reload = document.getElementById('editWechatHotReload').checked;
                    break;
                
                case 'wechat_official':
                    config.app_id = document.getElementById('editWechatOfficialAppId').value;
                    config.app_secret = document.getElementById('editWechatOfficialAppSecret').value;
                    config.token = document.getElementById('editWechatOfficialToken').value || '';
                    
                    if (!config.app_id || !config.app_secret) {
                        this.showToast('错误', '请填写 AppID 和 AppSecret', 'warning');
                        return;
                    }
                    break;
                
                case 'coinglass':
                    config.api_key = document.getElementById('editCoinglassApiKey').value;
                    config.api_secret = document.getElementById('editCoinglassApiSecret').value || '';
                    config.enable_whale_alert = document.getElementById('editCoinglassEnableWhaleAlert').checked;
                    config.polling_interval = parseInt(document.getElementById('editCoinglassPollingInterval').value) || 10;
                    config.min_position_value = parseFloat(document.getElementById('editCoinglassMinPositionValue').value) || 1000000;
                    
                    if (!config.api_key) {
                        this.showToast('错误', '请填写 CoinGlass API Key', 'warning');
            return;
        }
                    break;
                
                case 'bicoin':
                    const connectionType = document.getElementById('editBicoinConnectionType').value;
                    config.use_webhook = (connectionType === 'webhook');
                    config.use_websocket = (connectionType === 'websocket');
                    config.use_api = (connectionType === 'api');
                    config.use_crawler = (connectionType === 'crawler');
                    
                    if (config.use_webhook) {
                        config.webhook_port = parseInt(document.getElementById('editBicoinWebhookPort').value) || 8080;
                        config.webhook_path = '/bicoin/webhook';
                    }
                    
                    if (config.use_api) {
                        config.api_token = document.getElementById('editBicoinApiToken').value || '';
                    }
                    break;
                
                case 'tradingview':
                    config.use_webhook = true;
                    config.webhook_port = parseInt(document.getElementById('editTradingviewWebhookPort').value) || 8080;
                    config.webhook_path = document.getElementById('editTradingviewWebhookPath').value || '/tradingview/webhook';
                    config.secret_key = document.getElementById('editTradingviewSecretKey').value || '';
                    
                    const strategyFilterStr = document.getElementById('editTradingviewStrategyFilter').value.trim();
                    config.strategy_filter = strategyFilterStr ? strategyFilterStr.split(',').map(s => s.trim()) : [];
                    
                    const symbolFilterStr = document.getElementById('editTradingviewSymbolFilter').value.trim();
                    config.symbol_filter = symbolFilterStr ? symbolFilterStr.split(',').map(s => s.trim()) : [];
                    break;
            }
            
            // 发送更新请求
            const response = await fetch(`${this.apiBaseUrl}/message-forward/platforms/${platformId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    platform_name: platformName,
                    config: config,
                    enabled: platformEnabled
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showToast('成功', '平台更新成功', 'success');
                
                // 关闭模态框
                const modal = bootstrap.Modal.getInstance(document.getElementById('editPlatformModal'));
                modal.hide();
                
                // 刷新平台列表
                await this.loadPlatformsList();
            } else {
                this.showToast('错误', result.message || '更新失败', 'danger');
                }
            
        } catch (error) {
            console.error('更新平台失败:', error);
            this.showToast('错误', '更新平台失败', 'danger');
        }
    }

    // 编辑转发规则
    async editRule(ruleId) {
        try {
            // 获取规则数据
            const response = await fetch(`${this.apiBaseUrl}/message-forward/rules/${ruleId}`);
            const result = await response.json();
            
            if (!result.success) {
                this.showToast('错误', result.message || '获取规则失败', 'danger');
            return;
        }
        
            const rule = result.data;
            
            // 检查必要的表单元素是否存在
            const ruleNameInput = document.getElementById('forwardRuleName');
            const ruleEnabledInput = document.getElementById('forwardRuleEnabled');
            const sourcePlatformSelect = document.getElementById('sourcePlatform');
            const sourceChatIdsInput = document.getElementById('sourceChatIds');
            
            if (!ruleNameInput || !ruleEnabledInput || !sourcePlatformSelect || !sourceChatIdsInput) {
                this.showToast('错误', '表单元素未找到，请刷新页面重试', 'danger');
                console.error('缺少必要的表单元素:', {
                    ruleNameInput: !!ruleNameInput,
                    ruleEnabledInput: !!ruleEnabledInput,
                    sourcePlatformSelect: !!sourcePlatformSelect,
                    sourceChatIdsInput: !!sourceChatIdsInput
                });
                return;
            }
            
            // 填充表单
            ruleNameInput.value = rule.rule_name || '';
            ruleEnabledInput.checked = rule.enabled || false;
            
            // 设置源平台
            if (rule.source_platform_id) {
                document.getElementById('sourcePlatform').value = rule.source_platform_id;
            } else if (rule.source_platform) {
                // 兼容旧数据：根据平台类型找到对应的平台ID
                // 获取平台列表来匹配
                try {
                    const platformsResponse = await fetch(`${this.apiBaseUrl}/message-forward/platforms`);
                    if (platformsResponse.ok) {
                        const platformsData = await platformsResponse.json();
                        if (platformsData.success) {
                            const platforms = platformsData.data || [];
                            const matchingPlatform = platforms.find(p => p.platform_type === rule.source_platform);
                            if (matchingPlatform) {
                                document.getElementById('sourcePlatform').value = matchingPlatform.id;
                            }
                }
            }
        } catch (error) {
                    console.warn('获取平台列表失败，使用平台类型:', error);
                    // 如果获取失败，至少尝试设置平台类型（虽然可能不匹配）
                }
            }
            
            // 设置源聊天ID
            const sourceChatIds = Array.isArray(rule.source_chat_ids) ? 
                rule.source_chat_ids.join(', ') : 
                (rule.source_chat_ids || '');
            sourceChatIdsInput.value = sourceChatIds;
            
            // 加载目标平台列表
            await this.loadTargetPlatforms();
            
            // 等待目标平台列表渲染完成（使用轮询检查）
            const waitForTargetPlatforms = () => {
                return new Promise((resolve) => {
                    const checkInterval = setInterval(() => {
                        const container = document.getElementById('targetPlatformsContainer');
                        if (container && container.querySelector('.target-platform')) {
                            clearInterval(checkInterval);
                            resolve();
                        }
                    }, 100);
                    
                    // 最多等待3秒
                    setTimeout(() => {
                        clearInterval(checkInterval);
                        resolve();
                    }, 3000);
                });
            };
            
            await waitForTargetPlatforms();
            
            // 设置目标平台
            const targetPlatformIds = rule.target_platform_ids || [];
            if (targetPlatformIds.length > 0) {
                // 选中对应的平台实例
                targetPlatformIds.forEach(platformId => {
                    const checkbox = document.querySelector(`.target-platform[value="${platformId}"]`);
                    if (checkbox) {
                        checkbox.checked = true;
                        // 触发change事件以显示对应的配置
                        checkbox.dispatchEvent(new Event('change'));
                } else {
                        console.warn(`未找到平台实例复选框 (ID: ${platformId})`);
                    }
                });
            } else {
                // 兼容旧数据：使用target_platforms（平台类型）
                const targetPlatforms = Array.isArray(rule.target_platforms) ? 
                    rule.target_platforms : 
                    (rule.target_platforms ? [rule.target_platforms] : []);
                
                targetPlatforms.forEach(platformType => {
                    // 选中该类型的所有平台实例
                    const checkboxes = document.querySelectorAll(`.target-platform[data-platform-type="${platformType}"]`);
                    if (checkboxes.length > 0) {
                        checkboxes.forEach(checkbox => {
                            checkbox.checked = true;
                            checkbox.dispatchEvent(new Event('change'));
                        });
                    } else {
                        console.warn(`未找到平台类型复选框 (类型: ${platformType})`);
                    }
                });
            }
            
            // 设置目标聊天ID
            const targetChatIds = rule.target_chat_ids || {};
            Object.keys(targetChatIds).forEach(platformType => {
                const chatIdsInput = document.getElementById(`${platformType}TargetChatIds`);
                if (chatIdsInput) {
                    const chatIds = Array.isArray(targetChatIds[platformType]) ? 
                        targetChatIds[platformType].join(', ') : 
                        (targetChatIds[platformType] || '');
                    chatIdsInput.value = chatIds;
                }
            });
            
            // 设置关键词（安全检查）
            const keywordsInput = document.getElementById('keywords');
            if (keywordsInput) {
                const keywords = Array.isArray(rule.keywords) ? 
                    rule.keywords.join(', ') : 
                    (rule.keywords || '');
                keywordsInput.value = keywords;
            }
            
            // 设置排除关键词（安全检查）
            const excludeKeywordsInput = document.getElementById('excludeKeywords');
            if (excludeKeywordsInput) {
                const excludeKeywords = Array.isArray(rule.exclude_keywords) ? 
                    rule.exclude_keywords.join(', ') : 
                    (rule.exclude_keywords || '');
                excludeKeywordsInput.value = excludeKeywords;
            }
            
            // 设置前缀和后缀（安全检查）
            const addPrefixInput = document.getElementById('addPrefix');
            if (addPrefixInput) {
                addPrefixInput.value = rule.add_prefix || '';
            }
            
            const addSuffixInput = document.getElementById('addSuffix');
            if (addSuffixInput) {
                addSuffixInput.value = rule.add_suffix || '';
            }
            
            // 设置Markdown（安全检查）
            const enableMarkdownInput = document.getElementById('enableMarkdown');
            if (enableMarkdownInput) {
                enableMarkdownInput.checked = rule.enable_markdown || false;
            }
            
            // 保存规则ID用于更新
            const modal = document.getElementById('addForwardRuleModal');
            if (!modal) {
                this.showToast('错误', '找不到转发规则模态框，请刷新页面重试', 'danger');
                return;
            }
            
            modal.dataset.ruleId = ruleId;
            
            // 修改模态框标题
            const modalTitle = document.querySelector('#addForwardRuleModal .modal-title');
            if (modalTitle) {
                modalTitle.textContent = '编辑转发规则';
            }
            
            // 修改保存按钮文本
            const saveButton = document.querySelector('#addForwardRuleModal .btn-primary[type="submit"]');
            if (saveButton) {
                saveButton.textContent = '更新规则';
            }
            
            // 显示模态框
            const bootstrapModal = new bootstrap.Modal(modal);
            bootstrapModal.show();
            
        } catch (error) {
            console.error('编辑规则失败:', error);
            this.showToast('错误', '编辑规则失败: ' + error.message, 'danger');
        }
    }

    // ==================== Telegram监听服务（已移除，现在使用统一的消息转发服务） ====================
    
    // 创建策略交易
    async createStrategyTrade() {
        try {
            const form = document.getElementById('createStrategyTradeForm');
            if (!form) {
                this.showToast('错误', '表单不存在', 'danger');
                return;
            }
            
            const formData = new FormData(form);
            const strategyTypeSelect = document.getElementById('createStrategyTradeType');
            const strategyType = formData.get('strategyType') || strategyTypeSelect?.value;
            const strategyName = formData.get('strategyName') || document.getElementById('createStrategyTradeName')?.value;
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
            const selectedSignalSources = Array.from(document.getElementById('createStrategyTradeSignalSources')?.selectedOptions || [])
                .map(option => option.value);
            const selectedCustomers = Array.from(document.getElementById('createStrategyTradeCustomers')?.selectedOptions || [])
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
    async editStrategyTrade(strategyName) {
        try {
            
            // 获取策略详情
            const response = await fetch(`${this.apiBaseUrl}/strategy/instances/${strategyName}`);
            
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.data) {
                    this.showEditStrategyTradeModal(data.data);
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
    async showEditStrategyTradeModal(strategyData) {

        // 填充基本信息
        document.getElementById('editStrategyTradeId').value = strategyData.name || strategyData.instance_name;
        document.getElementById('editStrategyTradeName').value = strategyData.name || strategyData.instance_name;
        document.getElementById('editStrategyTradeType').value = strategyData.strategy_type || strategyData.type;
        document.getElementById('editStrategyTradeSymbol').value = strategyData.symbol || 'BTC-USDT-SWAP';
        document.getElementById('editStrategyTradeTimeframe').value = strategyData.timeframe || '1h';

        // 填充风险参数
        if (strategyData.config) {
            document.getElementById('editStrategyTradeRiskPerTrade').value = strategyData.config.risk_per_trade || 0.02;
            document.getElementById('editStrategyTradeMaxPositions').value = strategyData.config.max_positions || 3;
            document.getElementById('editStrategyTradeStopLossPct').value = strategyData.config.stop_loss_pct || 0.02;
            document.getElementById('editStrategyTradeTakeProfitPct').value = strategyData.config.take_profit_pct || 0.06;
        }
    
    
        // 加载客户和信号源列表
        await this.loadAccountsForStrategyTrade('edit');

        // 显示模态框
        const modal = new bootstrap.Modal(document.getElementById('editStrategyTradeModal'));
        modal.show();

        // 动态显示策略特定参数（使用统一的参数生成方法，传递现有配置）
        await this.showEditStrategyTradeParams(strategyData.strategy_type || strategyData.type, strategyData.config);
    }

    // 显示编辑策略的特定参数（统一使用模板参数定义）
    async showEditStrategyTradeParams(strategyType, config = {}) {
        const paramsContainer = document.getElementById('editStrategyTradeSpecificParams');
        if (!paramsContainer) return;
    
        paramsContainer.innerHTML = '<h6><i class="bi bi-gear"></i> 策略参数</h6><hr><div class="text-center">加载中...</div>';
    
        try {
            // 获取策略模板
            const response = await fetch(`${this.apiBaseUrl}/strategy/templates/${strategyType}`);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.message || '获取策略模板失败');
            }

            const template = data.data;
            const validation = template.validation_rules || {};

            // 使用统一的参数生成方法（传递现有配置）
            const formHtml = this.generateStrategyParamsForm(strategyType, config, validation, template.parameters);
            
            if (formHtml) {
                paramsContainer.innerHTML = `
                    <h6><i class="bi bi-gear"></i> 策略参数 - ${template.display_name}</h6>
                    <p class="text-muted small">${template.description}</p>
                    <hr>
                    ${formHtml}
                `;
            } else {
                paramsContainer.innerHTML = `
                    <h6><i class="bi bi-gear"></i> 策略参数 - ${template.display_name}</h6>
                    <p class="text-muted">该策略使用默认参数配置</p>
                `;
            }
        } catch (error) {
            console.error('❌ 显示编辑策略参数失败:', error);
            paramsContainer.innerHTML = `
                <h6><i class="bi bi-gear"></i> 策略参数</h6>
                <div class="alert alert-warning">无法加载策略参数: ${error.message}</div>
            `;
        }
    }

    // 填充策略交易表单
    async fillStrategyTradeForm(strategy, isEdit = false) {
        // 先加载信号源和客户选项
        await this.loadAccountsForStrategyTrade('edit');
        
        document.getElementById('editStrategyTradeId').value = strategy.strategy_uid || '';
        document.getElementById('editStrategyTradeName').value = strategy.name || '';
        document.getElementById('editStrategyTradeType').value = strategy.strategy_type || '';
        document.getElementById('editStrategyTradeSymbol').value = strategy.config?.symbol || 'BTC-USDT-SWAP';
        document.getElementById('editStrategyTradeTimeframe').value = strategy.config?.timeframe || '1h';
        document.getElementById('editStrategyTradeRiskPerTrade').value = strategy.config?.risk_per_trade || 0.02;
        document.getElementById('editStrategyTradeMaxPositions').value = strategy.config?.max_positions || 3;
        document.getElementById('editStrategyTradeStopLossPct').value = strategy.config?.stop_loss_pct || 0.05;
        document.getElementById('editStrategyTradeTakeProfitPct').value = strategy.config?.take_profit_pct || 0.1;
        
        // 如果是编辑模式，禁用某些字段
        if (isEdit) {
            document.getElementById('editStrategyTradeName').disabled = true;
        } else {
            document.getElementById('editStrategyTradeName').disabled = false;
        }
        
        // 加载策略特定参数
        this.showEditStrategyTradeParams(strategy.strategy_type || strategy.type, strategy.config);
    }
    // 加载账号列表用于策略关联
    async loadAccountsForStrategyTrade(mode = 'create') {
        try {
            let signalSourcesId, customersId;
            if (mode === 'edit') {
                signalSourcesId = 'editStrategyTradeSignalSources';
                customersId = 'editStrategyTradeCustomers';
            } else {
                signalSourcesId = 'createStrategyTradeSignalSources';
                customersId = 'createStrategyTradeCustomers';
            }
            
            const signalSourcesSelect = document.getElementById(signalSourcesId);
            const customersSelect = document.getElementById(customersId);

            if (!signalSourcesSelect || !customersSelect) return;

            // 加载信号源
            try {
                const signalSourcesResponse = await this.apiRequest(`${this.apiBaseUrl}/signal_sources`);
                if (signalSourcesResponse && signalSourcesResponse.ok) {
                const signalSourcesData = await signalSourcesResponse.json();
                
                if (signalSourcesData.success && Array.isArray(signalSourcesData.data)) {
                        if (signalSourcesData.data.length > 0) {
                    signalSourcesSelect.innerHTML = signalSourcesData.data.map(source => 
                                `<option value="${source.source_uid}">${source.name || source.source_uid} (${source.source_uid})</option>`
                    ).join('');
                } else {
                    signalSourcesSelect.innerHTML = '<option value="">暂无信号源数据</option>';
                            console.warn('⚠️ 信号源数据为空');
                }
            } else {
                        signalSourcesSelect.innerHTML = '<option value="">暂无信号源数据</option>';
                        console.warn('⚠️ 信号源API返回格式异常:', signalSourcesData);
                    }
                } else {
                    const status = signalSourcesResponse ? signalSourcesResponse.status : 'null';
                    console.error('❌ 信号源API调用失败:', status);
                    signalSourcesSelect.innerHTML = '<option value="">加载信号源失败</option>';
                }
            } catch (error) {
                console.error('❌ 加载信号源时发生异常:', error);
                signalSourcesSelect.innerHTML = '<option value="">加载信号源失败</option>';
            }

            // 加载客户
            try {
                const customersResponse = await this.apiRequest(`${this.apiBaseUrl}/customers?page_size=1000`);
                if (customersResponse && customersResponse.ok) {
                const customersData = await customersResponse.json();
                
                let customers = [];
                if (customersData.success) {
                    // 处理不同的数据结构
                    if (Array.isArray(customersData.data)) {
                        // 直接是数组
                        customers = customersData.data;
                    } else if (customersData.data && Array.isArray(customersData.data.customers)) {
                            // 嵌套结构: {data: {customers: [...]}}
                            customers = customersData.data.customers;
                        } else if (customersData.data && customersData.data.customers && Array.isArray(customersData.data.customers)) {
                            // 深度嵌套
                        customers = customersData.data.customers;
                    }
                }
                
                if (customers.length > 0) {
                    customersSelect.innerHTML = customers.map(customer => 
                            `<option value="${customer.customer_uid}">${customer.name || customer.customer_uid} (${customer.customer_uid})</option>`
                    ).join('');
                } else {
                    customersSelect.innerHTML = '<option value="">暂无客户数据</option>';
                        console.warn('⚠️ 客户数据为空，API响应:', customersData);
                }
            } else {
                    const status = customersResponse ? customersResponse.status : 'null';
                    console.error('❌ 客户API调用失败:', status);
                    customersSelect.innerHTML = '<option value="">加载客户失败</option>';
                }
            } catch (error) {
                console.error('❌ 加载客户时发生异常:', error);
                customersSelect.innerHTML = '<option value="">加载客户失败</option>';
            }
        } catch (error) {
            console.error('加载客户失败:', error);
            this.showToast('错误', '加载客户失败', 'danger');
        }
    }

    // 保存策略交易编辑
    async saveStrategyTradeEdit() {
        try {
            const form = document.getElementById('editStrategyTradeForm');
            if (!form) {
                this.showToast('错误', '编辑表单不存在', 'danger');
                return;
            }

            const strategyId = document.getElementById('editStrategyTradeId').value;
            const strategyName = document.getElementById('editStrategyTradeName').value;
            const tradingSymbol = document.getElementById('editStrategyTradeSymbol').value;
            const timeframe = document.getElementById('editStrategyTradeTimeframe').value;
            const riskPerTrade = document.getElementById('editStrategyTradeRiskPerTrade').value;
            const maxPositions = document.getElementById('editStrategyTradeMaxPositions').value;
            const stopLossPct = document.getElementById('editStrategyTradeStopLossPct').value;
            const takeProfitPct = document.getElementById('editStrategyTradeTakeProfitPct').value;

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
            const strategyType = document.getElementById('editStrategyTradeType').value;
            this.collectEditStrategyParams(strategyType, config);

            // 获取选中的客户和信号源
            const selectedSignalSources = Array.from(document.getElementById('editStrategyTradeSignalSources').selectedOptions)
                .map(option => option.value);
            const selectedCustomers = Array.from(document.getElementById('editStrategyTradeCustomers').selectedOptions)
                .map(option => option.value);

            const requestData = {
                name: strategyName,
                config: config,
                signal_sources: selectedSignalSources,
                customers: selectedCustomers
            };

            this.showToast('信息', '正在保存策略交易...', 'info');

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
                    this.showToast('成功', '策略交易更新成功', 'success');

                    // 关闭模态框
                    const modal = bootstrap.Modal.getInstance(document.getElementById('editStrategyTradeModal'));
                    if (modal) modal.hide();

                    // 刷新策略列表
                    this.loadStrategyTradeList();
                } else {
                    this.showToast('错误', data.message || '策略交易更新失败', 'danger');
                }
            } else {
                this.showToast('错误', '策略交易更新请求失败', 'danger');
            }
        } catch (error) {
            console.error('保存策略交易编辑失败:', error);
            this.showToast('错误', '保存策略交易失败', 'danger');
        }
    }

    // 收集编辑策略的特定参数
    collectEditStrategyParams(strategyType, config) {
        switch (strategyType) {
            case 'MA_Cross_Strategy':
                const shortPeriod = document.getElementById('editStrategyTradeShortPeriod')?.value;
                const longPeriod = document.getElementById('editStrategyTradeLongPeriod')?.value;
                if (shortPeriod) config.short_period = parseInt(shortPeriod);
                if (longPeriod) config.long_period = parseInt(longPeriod);
                break;
            case 'RSI_Strategy':
                const rsiPeriod = document.getElementById('editStrategyTradeRsiPeriod')?.value;
                const oversold = document.getElementById('editStrategyTradeOversold')?.value;
                const overbought = document.getElementById('editStrategyTradeOverbought')?.value;
                if (rsiPeriod) config.rsi_period = parseInt(rsiPeriod);
                if (oversold) config.rsi_oversold = parseInt(oversold);
                if (overbought) config.rsi_overbought = parseInt(overbought);
                break;
            case 'MACD_Strategy':
                const fastPeriod = document.getElementById('editStrategyTradeFastPeriod')?.value;
                const slowPeriod = document.getElementById('editStrategyTradeSlowPeriod')?.value;
                const signalPeriod = document.getElementById('editStrategyTradeSignalPeriod')?.value;
                if (fastPeriod) config.fast_period = parseInt(fastPeriod);
                if (slowPeriod) config.slow_period = parseInt(slowPeriod);
                if (signalPeriod) config.signal_period = parseInt(signalPeriod);
                break;
        }
    }
    
    // 策略类型变化处理
    async onStrategyTypeChangeTrade(strategyType) {
        await this.showStrategyTradeParams(strategyType);
    }

    // 加载策略模板到创建策略模态框
    async loadStrategyTemplatesForCreate() {
        try {
            // 专门获取策略交易模态框中的选择器
            const strategySelect = document.querySelector('#createStrategyTradeModal #strategyType');
            if (!strategySelect) {
                console.error('❌ 找不到策略交易模态框中的策略类型选择器');
                return;
            }

            // 清空现有选项，保留默认选项
            strategySelect.innerHTML = '<option value="">请选择策略类型</option>';

            // 获取所有策略（系统+用户）
            const [templatesResponse, allStrategiesResponse] = await Promise.all([
                this.apiRequest(`${this.apiBaseUrl}/strategy/templates`),
                this.apiRequest(`${this.apiBaseUrl}/strategy/all`)
            ]);
            
            if (!templatesResponse || !templatesResponse.ok) {
                throw new Error(`HTTP ${templatesResponse ? templatesResponse.status : 'null'}: ${templatesResponse ? templatesResponse.statusText : 'no response'}`);
            }
            
            const templatesData = await templatesResponse.json();
            
            // 如果有all策略接口，也获取用户策略
            let userStrategies = [];
            if (allStrategiesResponse && allStrategiesResponse.ok) {
                const allStrategiesData = await allStrategiesResponse.json();
                if (allStrategiesData.success && allStrategiesData.data && allStrategiesData.data.user) {
                    userStrategies = allStrategiesData.data.user;
                }
            }
            
            // 处理系统策略模板
            if (templatesData.success && templatesData.data) {
                const templates = templatesData.data;
                for (const [strategyId, template] of Object.entries(templates)) {
                    const option = document.createElement('option');
                    option.value = strategyId;
                    option.textContent = template.display_name || template.name || strategyId;
                    option.dataset.source = 'system';
                    strategySelect.appendChild(option);
                }
            }
            
            // 添加用户策略
            if (userStrategies.length > 0) {
                // 添加分隔符（如果已有系统策略）
                if (strategySelect.options.length > 1) {
                    const separator = document.createElement('option');
                    separator.disabled = true;
                    separator.textContent = '────────── 用户策略 ──────────';
                    strategySelect.appendChild(separator);
                }
                
                userStrategies.forEach(strategy => {
                    const option = document.createElement('option');
                    option.value = strategy.id;
                    option.textContent = `${strategy.name || strategy.id} (自定义)`;
                    option.dataset.source = 'user';
                    strategySelect.appendChild(option);
                });
            }
            
        } catch (error) {
            console.error('❌ 加载策略模板失败:', error);
            this.showToast('错误', `加载策略模板失败: ${error.message}`, 'danger');
        }
    }

    // 根据策略类型显示参数表单（支持传入现有配置）
    async showStrategyTradeParams(strategyType, existingConfig = null) {
        
        const paramsContainer = document.getElementById('strategySpecificParams');
        if (!paramsContainer) {
            console.error('❌ 找不到参数容器 strategySpecificParams');
            return;
        }

        paramsContainer.innerHTML = '';

        if (!strategyType) {
            return;
        }

        try {
            // 获取策略模板
            const response = await fetch(`${this.apiBaseUrl}/strategy/templates/${strategyType}`);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.message || '获取策略模板失败');
            }

            const template = data.data;
            // 如果提供了现有配置，使用它；否则使用默认配置
            const config = existingConfig || template.default_config;
            const validation = template.validation_rules || {};

            // 创建参数表单（传递parameters以统一参数生成）
            const formHtml = this.generateStrategyParamsForm(strategyType, config, validation, template.parameters);
            
            
            if (formHtml) {
                paramsContainer.innerHTML = `
                    <hr>
                    <h6>策略参数 - ${template.display_name}</h6>
                    <p class="text-muted small">${template.description}</p>
                    ${formHtml}
                `;
                
            } else {
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

    // 生成策略参数表单（统一使用模板参数定义，支持回测和创建策略）
    generateStrategyParamsForm(strategyType, config, validation, parameters = null, isBacktest = false) {
        let formHtml = '<div class="row">';
        const prefix = isBacktest ? 'backtest' : '';
        
        // 如果提供了parameters（来自模板），优先使用动态生成
        if (parameters && typeof parameters === 'object' && Object.keys(parameters).length > 0) {
            let hasParams = false;
            Object.entries(parameters).forEach(([paramName, paramInfo]) => {
                // 跳过symbol和timeframe（已在主表单中）
                if (paramName === 'symbol' || paramName === 'timeframe') {
                    return;
                }
                
                // 跳过嵌套参数中的 risk_config 对象（作为整体处理）
                if (paramName === 'risk_config' && paramInfo.type === 'object') {
                    return; // risk_config 作为整体对象，不展开
                }
                
                hasParams = true;
                
                // 使用配置中的值，如果没有则使用默认值
                // 支持嵌套路径（如 "risk_config.max_daily_loss"）
                let value = paramInfo.default;
                if (config) {
                    if (paramName.includes('.')) {
                        // 嵌套路径，需要递归查找
                        const keys = paramName.split('.');
                        let nestedValue = config;
                        for (const key of keys) {
                            if (nestedValue && typeof nestedValue === 'object' && key in nestedValue) {
                                nestedValue = nestedValue[key];
                            } else {
                                nestedValue = undefined;
                                break;
                            }
                        }
                        if (nestedValue !== undefined) {
                            value = nestedValue;
                        }
                    } else if (config.hasOwnProperty(paramName)) {
                        value = config[paramName];
                    }
                }
                
                formHtml += this.generateParamInputFromTemplate(paramName, paramInfo, value, validation?.[paramName], prefix);
            });
            
            if (hasParams) {
                formHtml += '</div>';
                return formHtml;
            }
            // 如果没有有效参数，降级到硬编码方式
            console.warn('⚠️ 参数对象为空或无效，降级到硬编码方式');
        }
        
        // 降级：使用硬编码的switch-case（向后兼容）
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
                ['grid_levels', 'grid_spacing', 'base_price', 'investment_per_grid'].forEach(param => {
                    if (config.hasOwnProperty(param)) {
                        formHtml += this.generateParamInput(param, config[param], validation[param]);
                    }
                });
                break;
                
            case 'FMZGrid_Strategy':
                ['ratio', 'grid_ratio', 'interval', 'price_precision', 'amount_precision'].forEach(param => {
                    if (config.hasOwnProperty(param)) {
                        formHtml += this.generateParamInput(param, config[param], validation[param]);
                    }
                });
                break;
                
            case 'HighFrequency_Strategy':
            case 'High_Frequency_Strategy':
                ['fast_ema_period', 'slow_ema_period', 'rsi_period', 'rsi_oversold', 'rsi_overbought', 
                 'volume_threshold', 'price_change_threshold', 'min_trade_interval', 'max_trades_per_day'].forEach(param => {
                    if (config.hasOwnProperty(param)) {
                        formHtml += this.generateParamInput(param, config[param], validation[param]);
                    }
                });
                break;
                
            case 'MarketMaker_Strategy':
                ['spread', 'quantity', 'max_orders'].forEach(param => {
                    if (config.hasOwnProperty(param)) {
                        formHtml += this.generateParamInput(param, config[param], validation[param]);
                    }
                });
                // 止损止盈开关和参数
                formHtml += `
                    <div class="col-md-6 mb-3">
                        <div class="form-check form-switch">
                            <input class="form-check-input" type="checkbox" id="enable_stop_loss" name="enable_stop_loss" ${config.enable_stop_loss ? 'checked' : ''}>
                            <label class="form-check-label" for="enable_stop_loss">启用止损</label>
                        </div>
                    </div>
                    <div class="col-md-6 mb-3">
                        <div class="form-check form-switch">
                            <input class="form-check-input" type="checkbox" id="enable_take_profit" name="enable_take_profit" ${config.enable_take_profit ? 'checked' : ''}>
                            <label class="form-check-label" for="enable_take_profit">启用止盈</label>
                        </div>
                    </div>
                `;
                ['stop_loss', 'take_profit'].forEach(param => {
                    if (config.hasOwnProperty(param)) {
                        formHtml += this.generateParamInput(param, config[param], validation[param]);
                    }
                });
                // 重平衡开关和参数
                formHtml += `
                    <div class="col-md-6 mb-3">
                        <div class="form-check form-switch">
                            <input class="form-check-input" type="checkbox" id="enable_rebalance" name="enable_rebalance" ${config.enable_rebalance ? 'checked' : ''}>
                            <label class="form-check-label" for="enable_rebalance">启用重平衡</label>
                        </div>
                    </div>
                `;
                ['base_asset_target', 'rebalance_threshold'].forEach(param => {
                    if (config.hasOwnProperty(param)) {
                        formHtml += this.generateParamInput(param, config[param], validation[param]);
                    }
                });
                break;
                
            case 'MarketMakerHedge_Strategy':
                // 继承做市商策略的所有参数
                ['spread', 'quantity', 'max_orders'].forEach(param => {
                    if (config.hasOwnProperty(param)) {
                        formHtml += this.generateParamInput(param, config[param], validation[param]);
                    }
                });
                // 止损止盈开关和参数
                formHtml += `
                    <div class="col-md-6 mb-3">
                        <div class="form-check form-switch">
                            <input class="form-check-input" type="checkbox" id="enable_stop_loss" name="enable_stop_loss" ${config.enable_stop_loss ? 'checked' : ''}>
                            <label class="form-check-label" for="enable_stop_loss">启用止损</label>
                        </div>
                    </div>
                    <div class="col-md-6 mb-3">
                        <div class="form-check form-switch">
                            <input class="form-check-input" type="checkbox" id="enable_take_profit" name="enable_take_profit" ${config.enable_take_profit ? 'checked' : ''}>
                            <label class="form-check-label" for="enable_take_profit">启用止盈</label>
                        </div>
                    </div>
                `;
                ['stop_loss', 'take_profit'].forEach(param => {
                    if (config.hasOwnProperty(param)) {
                        formHtml += this.generateParamInput(param, config[param], validation[param]);
                    }
                });
                // 重平衡开关和参数
                formHtml += `
                    <div class="col-md-6 mb-3">
                        <div class="form-check form-switch">
                            <input class="form-check-input" type="checkbox" id="enable_rebalance" name="enable_rebalance" ${config.enable_rebalance ? 'checked' : ''}>
                            <label class="form-check-label" for="enable_rebalance">启用重平衡</label>
                        </div>
                    </div>
                `;
                ['base_asset_target', 'rebalance_threshold'].forEach(param => {
                    if (config.hasOwnProperty(param)) {
                        formHtml += this.generateParamInput(param, config[param], validation[param]);
                    }
                });
                // 对冲参数
                formHtml += `
                    <div class="col-md-12 mb-3">
                        <div class="alert alert-info">
                            <h6>对冲参数配置</h6>
                        </div>
                    </div>
                    <div class="col-md-6 mb-3">
                        <div class="form-check form-switch">
                            <input class="form-check-input" type="checkbox" id="enable_hedge" name="enable_hedge" ${config.enable_hedge ? 'checked' : ''}>
                            <label class="form-check-label" for="enable_hedge">启用对冲</label>
                        </div>
                    </div>
                `;
                ['hedge_threshold', 'hedge_size_ratio', 'max_position_exposure'].forEach(param => {
                    if (config.hasOwnProperty(param)) {
                        formHtml += this.generateParamInput(param, config[param], validation[param]);
                    }
                });
                break;
        }

        formHtml += '</div>';
        return formHtml;
    }

    // 从模板生成参数输入框（统一方法，支持回测和创建策略）
    generateParamInputFromTemplate(paramName, paramInfo, defaultValue, validation, prefix = '') {
        const label = this.getParamLabel(paramName);
        const description = this.getParamDescription(paramName);
        const inputType = paramInfo.input_type || (paramInfo.type === 'boolean' ? 'checkbox' : 'number');
        const step = paramInfo.step || (inputType === 'number' ? '0.001' : '');
        const min = paramInfo.min !== undefined ? paramInfo.min : (validation?.min || '');
        const max = paramInfo.max !== undefined ? paramInfo.max : (validation?.max || '');
        
        // 生成ID和name（支持回测前缀）
        const fieldId = prefix ? `${prefix}_${paramName}` : paramName;
        const fieldName = paramName; // name保持原样，不添加前缀
        
        // 处理对象类型（如 risk_config）
        if (inputType === 'object' || paramInfo.type === 'object') {
            // 对象类型参数，显示为只读的JSON字符串
            const jsonValue = typeof defaultValue === 'object' ? JSON.stringify(defaultValue, null, 2) : defaultValue;
            return `
                <div class="col-md-12 mb-3">
                    <label for="${fieldId}" class="form-label">${label}</label>
                    <textarea class="form-control" 
                              id="${fieldId}" 
                              name="${fieldName}"
                              rows="4"
                              readonly>${jsonValue}</textarea>
                    ${description ? `<div class="form-text">${description}（对象类型，使用默认配置）</div>` : ''}
                </div>
            `;
        }
        
        // 处理复选框
        if (inputType === 'checkbox' || paramInfo.type === 'boolean') {
            const checked = defaultValue === true || defaultValue === 'true' || defaultValue === 1 || defaultValue === '1';
            return `
                <div class="col-md-6 mb-3">
                    <div class="form-check form-switch">
                        <input class="form-check-input" type="checkbox" id="${fieldId}" name="${fieldName}" ${checked ? 'checked' : ''}>
                        <label class="form-check-label" for="${fieldId}">${label}</label>
                    </div>
                    ${description ? `<div class="form-text">${description}</div>` : ''}
                </div>
            `;
        }
        
        // 处理数字输入
        const numValue = defaultValue !== undefined && defaultValue !== null ? defaultValue : '';
        return `
            <div class="col-md-6 mb-3">
                <label for="${fieldId}" class="form-label">${label}</label>
                <input type="${inputType}" 
                       class="form-control" 
                       id="${fieldId}" 
                       name="${fieldName}"
                       value="${numValue}"
                       ${min !== '' && min !== undefined ? `min="${min}"` : ''}
                       ${max !== '' && max !== undefined ? `max="${max}"` : ''}
                       ${inputType === 'number' && step ? `step="${step}"` : ''}
                       ${paramInfo.required !== false ? 'required' : ''}>
                ${description ? `<div class="form-text">${description}</div>` : ''}
            </div>
        `;
    }
    
    // 生成单个参数输入框（向后兼容）
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
            'base_price': '基准价格',
            'ratio': '目标币种比例',
            'grid_ratio': '网格密度',
            'interval': '更新间隔(毫秒)',
            'price_precision': '价格精度',
            'amount_precision': '数量精度',
            'fast_ema_period': '快线EMA周期',
            'slow_ema_period': '慢线EMA周期',
            'volume_threshold': '成交量倍数阈值',
            'price_change_threshold': '价格变化阈值',
            'min_trade_interval': '最小交易间隔(分钟)',
            'max_trades_per_day': '每日最大交易次数',
            // 网格策略参数
            'dynamic_grid': '动态网格',
            'enable_trend_following': '启用趋势跟踪',
            'grid_adjustment_threshold': '网格调整阈值',
            'investment_per_grid': '每网格投资金额',
            'max_grid_adjustments': '最大网格调整次数',
            'max_grid_positions': '最大网格持仓数',
            'position_sizing': '仓位大小',
            // 风险管理参数
            'risk_per_trade': '每笔交易风险',
            'stop_loss_pct': '止损百分比',
            'take_profit_pct': '止盈百分比',
            'max_positions': '最大持仓数',
            'risk_config': '风险配置',
            // 做市商策略参数
            'spread': '价差',
            'quantity': '每单数量',
            'max_orders': '每侧最大订单数',
            'enable_stop_loss': '启用止损',
            'enable_take_profit': '启用止盈',
            'stop_loss': '止损金额(USDC)',
            'take_profit': '止盈金额(USDC)',
            'enable_rebalance': '启用重平衡',
            'base_asset_target': '基础资产目标比例(%)',
            'rebalance_threshold': '重平衡触发阈值(%)',
            // 对冲策略参数
            'enable_hedge': '启用对冲',
            'hedge_threshold': '对冲触发阈值',
            'hedge_size_ratio': '对冲比例',
            'max_position_exposure': '最大持仓暴露倍数'
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
            'base_price': '网格中心价格',
            'ratio': '目标币种比例 (0.1-0.9，如0.5表示50%)',
            'grid_ratio': '网格密度 (0.0005-0.1，建议0.01即1%)',
            'interval': '策略更新间隔，单位毫秒 (建议1000)',
            'price_precision': '价格精度，小数点后位数 (2-8)',
            'amount_precision': '数量精度，小数点后位数 (2-8)',
            'fast_ema_period': '快线EMA周期 (建议3-20)',
            'slow_ema_period': '慢线EMA周期 (建议5-50)',
            'volume_threshold': '成交量倍数阈值 (建议1.0-5.0)',
            'price_change_threshold': '价格变化阈值 (建议0.001-0.05)',
            'min_trade_interval': '最小交易间隔分钟数 (建议1-60)',
            'max_trades_per_day': '每日最大交易次数 (建议10-200)',
            // 网格策略参数描述
            'dynamic_grid': '是否启用动态网格调整 (true/false)',
            'enable_trend_following': '是否启用趋势跟踪功能 (true/false)',
            'grid_adjustment_threshold': '网格调整的价格变化阈值 (0.01-0.1)',
            'investment_per_grid': '每个网格的投资金额 (建议100-10000)',
            'max_grid_adjustments': '最大网格调整次数 (建议1-10)',
            'max_grid_positions': '最大网格持仓数量 (建议3-20)',
            'position_sizing': '仓位大小计算方式 (fixed/percentage)',
            // 风险管理参数描述
            'risk_per_trade': '每笔交易的风险比例 (0.01-0.1)',
            'stop_loss_pct': '止损百分比 (0.01-0.2)',
            'take_profit_pct': '止盈百分比 (0.01-0.5)',
            'max_positions': '最大同时持仓数量 (1-50)',
            'risk_config': '风险配置对象 (包含详细风险参数)',
            // 做市商策略参数描述
            'spread': '买卖价差 (0.0001-0.1，如0.002表示0.2%)',
            'quantity': '每单数量 (0.001-1000)',
            'max_orders': '每侧最大订单数 (1-20)',
            'enable_stop_loss': '是否启用止损功能',
            'enable_take_profit': '是否启用止盈功能',
            'stop_loss': '止损金额，负数 (如-25表示亏损25 USDC时止损)',
            'take_profit': '止盈金额，正数 (如50表示盈利50 USDC时止盈)',
            'enable_rebalance': '是否启用资产重平衡功能',
            'base_asset_target': '基础资产目标比例 (0-100%，如30表示30%)',
            'rebalance_threshold': '重平衡触发阈值 (1-50%，如15表示当偏差超过15%时触发)',
            // 对冲策略参数描述
            'enable_hedge': '是否启用对冲功能 (降低方向性风险)',
            'hedge_threshold': '对冲触发阈值 (0.1-1.0，如0.5表示持仓暴露超过50%时触发)',
            'hedge_size_ratio': '对冲比例 (0.1-1.0，如0.8表示对冲80%的持仓)',
            'max_position_exposure': '最大持仓暴露倍数 (0.1-5.0，限制单边风险)'
        };
        return descriptions[paramName] || '';
    }

    // 动态收集策略参数
    collectDynamicStrategyParams(config) {
        const paramsContainer = document.getElementById('strategySpecificParams');
        if (!paramsContainer) return;

        // 获取所有参数输入框
        const inputs = paramsContainer.querySelectorAll('input[name], select[name]');
        inputs.forEach(input => {
            const paramName = input.name;
            let value = input.value;

            // 根据输入类型转换值
            if (input.type === 'checkbox') {
                value = input.checked;
            } else if (input.type === 'number') {
                if (paramName.includes('period') || paramName.includes('levels') || paramName.includes('oversold') || paramName.includes('overbought') || paramName.includes('max_orders') || paramName.includes('precision')) {
                    value = parseInt(value) || 0;
                } else {
                    value = parseFloat(value) || 0;
                }
            } else if (input.tagName === 'SELECT') {
                value = input.value;
            }

            // 添加到配置中
            config[paramName] = value;
        });
    }
    
    // 收集回测策略参数
    // ========== 用户策略管理功能 ==========
    
    /**
     * 初始化用户策略管理
     */
    initUserStrategyManagement() {
        // 在模态框显示时加载策略列表
        const modal = document.getElementById('userStrategyModal');
        if (modal) {
            modal.addEventListener('show.bs.modal', () => {
                this.loadUserStrategies();
            });
        }
    }
    
    /**
     * 加载用户策略列表
     */
    async loadUserStrategies() {
        try {
            // 使用 apiRequest 处理认证
            const response = await this.apiRequest(`${this.apiBaseUrl}/strategy/user/list`);
            if (!response.ok) {
                // 如果是401，返回空列表
                if (response.status === 401) {
                    const tbody = document.getElementById('userStrategiesTableBody');
                    if (tbody) {
                        tbody.innerHTML = `
                            <tr>
                                <td colspan="5" class="text-center text-muted">
                                    <i class="bi bi-inbox"></i> 请先登录以查看用户策略
                                </td>
                            </tr>
                        `;
                    }
                    return;
                }
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            const tbody = document.getElementById('userStrategiesTableBody');
            
            if (!tbody) return;
            
            if (data.success && data.data && data.data.length > 0) {
                tbody.innerHTML = data.data.map(strategy => `
                    <tr>
                        <td><code>${strategy.id}</code></td>
                        <td>${strategy.name || strategy.id}</td>
                        <td>${strategy.description || strategy.short_description || '-'}</td>
                        <td>${strategy.loaded_at ? this.formatDateTime(strategy.loaded_at) : '-'}</td>
                        <td>
                            <button class="btn btn-sm btn-outline-primary" onclick="window.app.viewUserStrategy('${strategy.id}')" title="查看">
                                <i class="bi bi-eye"></i>
                            </button>
                            <button class="btn btn-sm btn-outline-danger" onclick="window.app.deleteUserStrategy('${strategy.id}')" title="删除">
                                <i class="bi bi-trash"></i>
                            </button>
                            <button class="btn btn-sm btn-outline-info" onclick="window.app.reloadUserStrategy('${strategy.id}')" title="重新加载">
                                <i class="bi bi-arrow-clockwise"></i>
                            </button>
                        </td>
                    </tr>
                `).join('');
            } else {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="text-center text-muted">
                            <i class="bi bi-inbox"></i> 暂无用户策略，点击"上传策略"标签页添加
                        </td>
                    </tr>
                `;
            }
        } catch (error) {
            console.error('加载用户策略失败:', error);
            const tbody = document.getElementById('userStrategiesTableBody');
            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="text-center text-danger">
                            <i class="bi bi-exclamation-triangle"></i> 加载失败: ${error.message}
                        </td>
                    </tr>
                `;
            }
        }
    }
    
    /**
     * 上传用户策略
     */
    async uploadUserStrategy() {
        const strategyId = document.getElementById('strategyId')?.value;
        const strategyName = document.getElementById('uploadStrategyName')?.value;
        const strategyDescription = document.getElementById('strategyDescription')?.value;
        const strategyCode = document.getElementById('strategyCode')?.value;
        
        if (!strategyId || !strategyCode) {
            this.showToast('错误', '请填写策略ID和策略代码', 'danger');
            return;
        }
        
        // 验证策略ID格式
        if (!/^[a-zA-Z][a-zA-Z0-9_]*$/.test(strategyId)) {
            this.showToast('错误', '策略ID格式无效，只能包含字母、数字和下划线，且必须以字母开头', 'danger');
            return;
        }
        
        try {
            this.showToast('信息', '正在上传策略...', 'info');
            
            const response = await fetch(`${this.apiBaseUrl}/strategy/user/upload`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    strategy_id: strategyId,
                    code: strategyCode,
                    metadata: {
                        name: strategyName || strategyId,
                        description: strategyDescription || ''
                    }
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast('成功', '策略上传成功', 'success');
                
                // 清空表单
                document.getElementById('uploadStrategyForm')?.reset();
                
                // 切换到列表标签并刷新
                const listTab = document.getElementById('list-tab');
                if (listTab) {
                    listTab.click();
                }
                
                // 刷新策略列表
                await this.loadUserStrategies();
                
                // 刷新策略类型下拉列表（如果需要）
                if (window.app && typeof window.app.loadStrategyTemplatesForCreate === 'function') {
                    window.app.loadStrategyTemplatesForCreate();
                }
            } else {
                this.showToast('错误', data.message || '策略上传失败', 'danger');
            }
        } catch (error) {
            console.error('上传策略失败:', error);
            this.showToast('错误', `上传失败: ${error.message}`, 'danger');
        }
    }
    
    /**
     * 查看用户策略
     */
    async viewUserStrategy(strategyId) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/strategy/user/${strategyId}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.success && data.data) {
                // 创建一个新的模态框显示策略详情
                const modal = document.createElement('div');
                modal.className = 'modal fade';
                modal.innerHTML = `
                    <div class="modal-dialog modal-xl">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title">策略详情: ${data.data.strategy_id}</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body">
                                <div class="mb-3">
                                    <label class="form-label"><strong>策略名称:</strong></label>
                                    <p>${data.data.metadata?.name || data.data.strategy_id}</p>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label"><strong>策略描述:</strong></label>
                                    <p>${data.data.metadata?.description || '-'}</p>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label"><strong>策略代码:</strong></label>
                                    <pre class="bg-light p-3 rounded" style="max-height: 500px; overflow-y: auto;"><code>${this.escapeHtml(data.data.code)}</code></pre>
                                </div>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                            </div>
                        </div>
                    </div>
                `;
                
                document.body.appendChild(modal);
                const bsModal = new bootstrap.Modal(modal);
                bsModal.show();
                
                // 模态框关闭后移除DOM元素
                modal.addEventListener('hidden.bs.modal', () => {
                    document.body.removeChild(modal);
                });
            } else {
                this.showToast('错误', '获取策略详情失败', 'danger');
            }
        } catch (error) {
            console.error('查看策略失败:', error);
            this.showToast('错误', `获取失败: ${error.message}`, 'danger');
        }
    }
    
    /**
     * 删除用户策略
     */
    async deleteUserStrategy(strategyId) {
        if (!confirm(`确定要删除策略 "${strategyId}" 吗？此操作不可恢复。`)) {
            return;
        }
        
        try {
            const response = await fetch(`${this.apiBaseUrl}/strategy/user/${strategyId}`, {
                method: 'DELETE'
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast('成功', '策略删除成功', 'success');
                await this.loadUserStrategies();
                
                // 刷新策略类型下拉列表
                if (window.app && typeof window.app.loadStrategyTemplatesForCreate === 'function') {
                    window.app.loadStrategyTemplatesForCreate();
                }
            } else {
                this.showToast('错误', data.message || '策略删除失败', 'danger');
            }
        } catch (error) {
            console.error('删除策略失败:', error);
            this.showToast('错误', `删除失败: ${error.message}`, 'danger');
        }
    }
    
    /**
     * 重新加载用户策略
     */
    async reloadUserStrategy(strategyId) {
        try {
            this.showToast('信息', '正在重新加载策略...', 'info');
            
            const response = await fetch(`${this.apiBaseUrl}/strategy/user/${strategyId}/reload`, {
                method: 'POST'
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast('成功', '策略重新加载成功', 'success');
                await this.loadUserStrategies();
            } else {
                this.showToast('错误', data.message || '策略重新加载失败', 'danger');
            }
        } catch (error) {
            console.error('重新加载策略失败:', error);
            this.showToast('错误', `重新加载失败: ${error.message}`, 'danger');
        }
    }
    
    /**
     * 加载策略代码模板
     */
    loadStrategyTemplate() {
        const template = `from core.strategy_trade.base_strategy import BaseStrategy, MarketData, Signal
from utils.logger import get_logger

logger = get_logger(__name__)

class MyStrategy(BaseStrategy):
    """
    自定义策略示例
    请修改类名和策略逻辑
    """
    
    def __init__(self, name: str, symbol: str, config: dict):
        super().__init__(name, symbol, config)
        
        # 从配置中获取参数
        self.param1 = self.get_parameter('param1', 10)
        self.param2 = self.get_parameter('param2', 0.5)
        
        logger.info(f"策略初始化: {name}")
    
    def on_market_data(self, data: MarketData) -> None:
        """
        处理市场数据（必须实现）
        
        Args:
            data: 市场数据对象，包含 open, high, low, close, volume 等字段
        """
        current_price = data.close
        
        # 获取历史价格数据
        prices = self.get_price_data(length=20)  # 获取最近20个价格
        
        if len(prices) < 20:
            return  # 数据不足，等待更多数据
        
        # 示例：简单的移动平均策略
        ma_short = sum(prices[-5:]) / 5   # 5日均线
        ma_long = sum(prices[-20:]) / 20  # 20日均线
        
        # 生成买入信号
        if ma_short > ma_long and current_price > ma_short:
            self.create_signal(
                direction='BUY',
                price=current_price,
                volume=self.param2,
                strength=0.8,
                reason=f"短期均线上穿长期均线"
            )
        
        # 生成卖出信号
        elif ma_short < ma_long and current_price < ma_short:
            self.create_signal(
                direction='SELL',
                price=current_price,
                volume=self.param2,
                strength=0.8,
                reason=f"短期均线下穿长期均线"
            )
    
    def on_initialize(self) -> None:
        """策略初始化时调用（可选）"""
        logger.info(f"策略 {self.name} 初始化完成")
    
    def on_start(self) -> None:
        """策略启动时调用（可选）"""
        logger.info(f"策略 {self.name} 已启动")
    
    def on_stop(self) -> None:
        """策略停止时调用（可选）"""
        logger.info(f"策略 {self.name} 已停止")`;
        
        const codeTextarea = document.getElementById('strategyCode');
        if (codeTextarea) {
            codeTextarea.value = template;
            this.showToast('信息', '策略模板已加载', 'info');
        }
    }
    
    /**
     * 转义HTML（用于显示代码）
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    collectBacktestStrategyParams(strategyType, symbol) {
        // 获取时间周期
        const timeframe = document.getElementById('backtestTimeframe')?.value || '1h';
        
        const config = {
            symbol: symbol,
            timeframe: timeframe
        };
        
        try {
            
            // 使用动态参数收集而不是硬编码
            const paramsContainer = document.getElementById('backtestStrategyParams');
            if (paramsContainer) {
                const inputs = paramsContainer.querySelectorAll('input[name], select[name]');
                
                inputs.forEach(input => {
                    const paramName = input.name;
                    let value = input.value;
                    
                    // 跳过空值
                    if (!value || value.trim() === '') {
                        return;
                    }
                    
                    if (input.type === 'number') {
                        // 根据参数名判断是整数还是浮点数
                        if (paramName.includes('period') || paramName.includes('levels') || 
                            paramName.includes('oversold') || paramName.includes('overbought') ||
                            paramName.includes('interval') || paramName.includes('trades')) {
                            // 周期、层数、超买超卖、间隔、交易次数等应该是整数
                            value = parseInt(value);
                        } else if (paramName.includes('std') || paramName.includes('spacing') || 
                                   paramName.includes('amount') || paramName.includes('investment') ||
                                   paramName.includes('threshold') || paramName.includes('pct')) {
                            // 标准差、间距、金额、阈值、百分比等应该是浮点数
                            value = parseFloat(value);
                        } else {
                            // 默认尝试浮点数转换
                            value = parseFloat(value);
                        }
                        
                        // 检查转换结果
                        if (isNaN(value)) {
                            console.warn(`参数 ${paramName} 转换失败，跳过: ${input.value}`);
                            return;
                        }
                    } else if (input.type === 'checkbox') {
                        value = input.checked;
                    }
                    
                    config[paramName] = value;
                    
                    // 特别检查bb_std参数
                    if (paramName === 'bb_std') {
                        console.log(`🔍 bb_std 参数详情: 原始值="${input.value}", 转换后=${value}, 类型=${typeof value}`);
                    }
                });
            } else {
                console.warn('⚠️ 未找到动态参数容器，使用默认值');
            }
            
            // 验证必需参数
            this.validateStrategyParamsTrade(strategyType, config);
            
            return config;
            
        } catch (error) {
            console.error('策略参数收集失败:', error);
            this.showToast('错误', error.message, 'danger');
            return null;
        }
    }
    
    // 验证策略参数
    validateStrategyParamsTrade(strategyType, config) {
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
            
            // 获取时间周期
            const timeframe = document.getElementById('backtestTimeframe')?.value || '1h';
            
            // 收集策略参数
            let strategyConfig = {
                symbol: symbol,
                timeframe: timeframe
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
            
            if (strategyConfig.bb_std !== undefined) {
                console.log(`🔍 bb_std 最终值: ${strategyConfig.bb_std} (${typeof strategyConfig.bb_std})`);
            }
            
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

    // 搜索交易对
    async searchSymbols(query = '') {
        try {
            const response = await fetch(`${this.apiBaseUrl}/symbols?q=${encodeURIComponent(query)}&limit=50`);
            if (response.ok) {
                const data = await response.json();
                return data.data || [];
            } else {
                console.error('搜索交易对失败:', response.statusText);
                return [];
            }
        } catch (error) {
            console.error('搜索交易对失败:', error);
            return [];
        }
    }

    // 加载交易对到选择框
    async loadSymbolsToSelect(query = '') {
        const symbols = await this.searchSymbols(query);
        const selectElement = document.getElementById('limitFollowStrategySymbols');
        
        if (!selectElement) return;
        
        // 保存当前已选择的选项
        const selectedValues = Array.from(selectElement.selectedOptions).map(opt => opt.value);
        
        // 清空现有选项
        selectElement.innerHTML = '';
        
        if (symbols.length === 0) {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = query ? '未找到匹配的交易对' : '请输入搜索条件';
            option.disabled = true;
            selectElement.appendChild(option);
            return;
        }
        
        // 添加搜索结果
        symbols.forEach(symbol => {
            const option = document.createElement('option');
            option.value = symbol;
            option.textContent = symbol;
            
            // 如果这个选项之前被选中过，保持选中状态
            if (selectedValues.includes(symbol)) {
                option.selected = true;
            }
            
            selectElement.appendChild(option);
        });
        
        // 显示当前选择状态
        if (selectedValues.length > 0) {
            console.log(`当前已选择 ${selectedValues.length} 个交易对:`, selectedValues);
        }
    }

    // 初始化交易对搜索功能
    initSymbolSearch() {
        const searchInput = document.getElementById('symbolSearchInput');
        const searchBtn = document.getElementById('searchSymbolsBtn');
        const symbolsSelect = document.getElementById('limitFollowStrategySymbols');
        
        if (!searchInput || !searchBtn || !symbolsSelect) return;
        
        // 搜索按钮点击事件
        searchBtn.addEventListener('click', async () => {
            const query = searchInput.value.trim();
            await this.loadSymbolsToSelect(query);
        });
        
        // 输入框回车事件
        searchInput.addEventListener('keypress', async (e) => {
            if (e.key === 'Enter') {
                const query = searchInput.value.trim();
                await this.loadSymbolsToSelect(query);
            }
        });
        
        // 输入框实时搜索（防抖）
        let searchTimeout;
        searchInput.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(async () => {
                const query = searchInput.value.trim();
                if (query.length >= 2) { // 至少输入2个字符才开始搜索
                    await this.loadSymbolsToSelect(query);
                } else if (query.length === 0) {
                    // 清空搜索时显示提示
                    await this.loadSymbolsToSelect('');
                }
            }, 300); // 300ms防抖
        });
        
        // 选择框变化事件
        symbolsSelect.addEventListener('change', () => {
            const selectedOptions = Array.from(symbolsSelect.selectedOptions);
            if (selectedOptions.length > 0) {
                // 显示选择状态提示
                this.showSelectionStatus(selectedOptions.length);
            } else {
                this.hideSelectionStatus();
            }
        });
        
        // 初始加载一些热门交易对
        this.loadSymbolsToSelect('BTC');
    }

    // 显示选择状态
    showSelectionStatus(count) {
        let statusDiv = document.getElementById('symbolSelectionStatus');
        if (!statusDiv) {
            // 创建状态显示元素
            statusDiv = document.createElement('div');
            statusDiv.id = 'symbolSelectionStatus';
            statusDiv.className = 'alert alert-info mt-2';
            statusDiv.style.fontSize = '14px';
            
            // 插入到选择框后面
            const symbolsSelect = document.getElementById('limitFollowStrategySymbols');
            symbolsSelect.parentNode.insertBefore(statusDiv, symbolsSelect.nextSibling);
        }
        
        statusDiv.innerHTML = `
            <i class="bi bi-check-circle"></i> 
            <strong>已选择 ${count} 个交易对</strong> 
            <span class="text-muted">(按住Ctrl键可继续多选)</span>
        `;
        statusDiv.style.display = 'block';
    }

    // 隐藏选择状态
    hideSelectionStatus() {
        const statusDiv = document.getElementById('symbolSelectionStatus');
        if (statusDiv) {
            statusDiv.style.display = 'none';
        }
    }
    
    // 跳转到登录页面
    redirectToLogin() {
        // 清除本地存储的登录状态
        localStorage.removeItem('loginStatus');
        
        // 跳转到登录页面
        window.location.href = 'login.html';
    }
    
    // ==================== 做市模块 ====================
    
    // 显示添加做市账号模态框
    showAddMarketMakerModal() {
        const modal = new bootstrap.Modal(document.getElementById('addMarketMakerModal'));
        modal.show();
        // 初始化策略参数显示
        this.onMarketMakerStrategyChange();
    }
    
    // 策略类型改变时，显示/隐藏相应的参数字段
    onMarketMakerStrategyChange() {
        const strategy = document.getElementById('marketMakerStrategy').value;
        
        // 隐藏所有策略参数区域
        document.querySelectorAll('.strategy-params').forEach(el => {
            el.style.display = 'none';
        });
        
        // 根据策略类型显示相应的参数区域
        if (strategy === 'standard') {
            document.getElementById('standardStrategyParams').style.display = 'block';
        } else if (strategy === 'maker_hedge') {
            document.getElementById('makerHedgeStrategyParams').style.display = 'block';
        } else if (strategy === 'avellaneda_stoikov') {
            document.getElementById('avellanedaStoikovStrategyParams').style.display = 'block';
        }
    }
    
    // 加载做市账号列表
    async loadMarketMakers() {
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/market-maker/accounts`);
            if (!response || !response.ok) {
                throw new Error('加载做市账号失败');
            }
            const result = await response.json();
            const accounts = result.data || [];
            
            this.renderMarketMakers(accounts);
            this.updateMarketMakerStats(accounts);
        } catch (error) {
            console.error('加载做市账号失败:', error);
            this.showToast('加载做市账号失败', 'error');
        }
    }
    
    // 渲染做市账号列表
    renderMarketMakers(accounts) {
        const tbody = document.getElementById('marketMakerTableBody');
        if (!tbody) return;
        
        if (accounts.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted">暂无做市账号</td></tr>';
            return;
        }
        
        tbody.innerHTML = accounts.map(account => {
            const status = account.status || 'stopped';
            const statusBadge = status === 'running' 
                ? '<span class="badge bg-success">运行中</span>'
                : '<span class="badge bg-secondary">已停止</span>';
            
            const runtime = account.runtime || '0:00:00';
            const volume = account.volume || '0';
            const profit = account.profit || '0.00';
            
            return `
                <tr>
                    <td>${account.name || '-'}</td>
                    <td>${account.exchange || '-'}</td>
                    <td>${(account.symbols || []).join(', ') || '-'}</td>
                    <td>${account.spread || '-'}%</td>
                    <td>${account.quantity || '-'}</td>
                    <td>${statusBadge}</td>
                    <td>${runtime}</td>
                    <td>${volume}</td>
                    <td class="${parseFloat(profit) >= 0 ? 'text-success' : 'text-danger'}">${profit}</td>
                    <td>
                        <button class="btn btn-sm btn-primary" onclick="window.app.startMarketMaker('${account.name}')" ${status === 'running' ? 'disabled' : ''}>
                            <i class="bi bi-play-circle"></i> 启动
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="window.app.stopMarketMaker('${account.name}')" ${status === 'stopped' ? 'disabled' : ''}>
                            <i class="bi bi-stop-circle"></i> 停止
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="window.app.deleteMarketMaker('${account.name}')">
                            <i class="bi bi-trash"></i> 删除
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    }
    
    // 更新做市统计
    updateMarketMakerStats(accounts) {
        const running = accounts.filter(a => a.status === 'running').length;
        const total = accounts.length;
        
        document.getElementById('market-maker-running-count').textContent = `运行中: ${running}`;
        document.getElementById('market-maker-total-count').textContent = `总计: ${total}`;
    }
    
    // 添加做市账号
    async addMarketMaker() {
        const form = document.getElementById('addMarketMakerForm');
        if (!form.checkValidity()) {
            form.reportValidity();
            return;
        }
        
        const symbols = document.getElementById('marketMakerSymbols').value
            .split('\n')
            .map(s => s.trim())
            .filter(s => s);
        
        const strategy = document.getElementById('marketMakerStrategy').value;
        
        // 根据策略类型构建不同的参数
        let params = {
            strategy: strategy
        };
        
        if (strategy === 'standard') {
            params = {
                ...params,
                spread: parseFloat(document.getElementById('marketMakerSpread').value) || 0.03,
                quantity: document.getElementById('marketMakerQuantity').value ? parseFloat(document.getElementById('marketMakerQuantity').value) : null,
                max_orders: parseInt(document.getElementById('marketMakerMaxOrders').value) || 2,
                target_position: parseFloat(document.getElementById('marketMakerTargetPosition').value) || 0,
                max_position: parseFloat(document.getElementById('marketMakerMaxPosition').value) || 0.5,
                position_threshold: parseFloat(document.getElementById('marketMakerPositionThreshold').value) || 0.4,
                inventory_skew: parseFloat(document.getElementById('marketMakerInventorySkew').value) || 0,
                stop_loss: parseFloat(document.getElementById('marketMakerStopLoss').value) || -25,
                take_profit: parseFloat(document.getElementById('marketMakerTakeProfit').value) || 50,
                interval: parseInt(document.getElementById('marketMakerInterval').value) || 10,
                duration: parseInt(document.getElementById('marketMakerDuration').value) || 9999999,
                enable_rebalance: document.getElementById('marketMakerEnableRebalance').checked
            };
        } else if (strategy === 'maker_hedge') {
            params = {
                ...params,
                spread: parseFloat(document.getElementById('marketMakerHedgeSpread').value) || 0.5,
                quantity: document.getElementById('marketMakerHedgeQuantity').value ? parseFloat(document.getElementById('marketMakerHedgeQuantity').value) : null,
                max_orders: parseInt(document.getElementById('marketMakerHedgeMaxOrders').value) || 3,
                target_position: parseFloat(document.getElementById('marketMakerHedgeTargetPosition').value) || 0,
                max_position: parseFloat(document.getElementById('marketMakerHedgeMaxPosition').value) || 0.5,
                position_threshold: parseFloat(document.getElementById('marketMakerHedgePositionThreshold').value) || 0.4,
                inventory_skew: parseFloat(document.getElementById('marketMakerHedgeInventorySkew').value) || 0,
                stop_loss: parseFloat(document.getElementById('marketMakerHedgeStopLoss').value) || -25,
                take_profit: parseFloat(document.getElementById('marketMakerHedgeTakeProfit').value) || 50,
                interval: parseInt(document.getElementById('marketMakerHedgeInterval').value) || 60,
                duration: parseInt(document.getElementById('marketMakerHedgeDuration').value) || 3600
            };
        } else if (strategy === 'avellaneda_stoikov') {
            params = {
                ...params,
                risk_factor: parseFloat(document.getElementById('marketMakerASRiskFactor').value) || 5.0,
                inventory_target: parseFloat(document.getElementById('marketMakerASInventoryTarget').value) || 0.0,
                order_amount_shape_factor: parseFloat(document.getElementById('marketMakerASOrderAmountShape').value) || 1.0,
                min_spread: parseFloat(document.getElementById('marketMakerASMinSpread').value) || 0.01,
                maker_fee: parseFloat(document.getElementById('marketMakerASMakerFee').value) || 0.1,
                taker_fee: parseFloat(document.getElementById('marketMakerASTakerFee').value) || 0.1,
                interval: parseInt(document.getElementById('marketMakerASInterval').value) || 10,
                duration: parseInt(document.getElementById('marketMakerASDuration').value) || 9999999,
                add_transaction_costs: document.getElementById('marketMakerASAddTransactionCosts').checked
            };
        }
        
        // 根据交易对判断市场类型（如果包含_PERP则为永续合约，否则为现货）
        const marketType = symbols.some(s => s.includes('_PERP') || s.includes('PERP')) ? 'perp' : 'spot';
        
        const data = {
            name: document.getElementById('marketMakerAccountName').value,
            exchange: document.getElementById('marketMakerExchange').value,
            market_type: marketType,
            api_key: document.getElementById('marketMakerApiKey').value,
            api_secret: document.getElementById('marketMakerApiSecret').value,
            symbols: symbols,
            params: params
        };
        
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/market-maker/accounts`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            
            if (!response || !response.ok) {
                throw new Error('添加做市账号失败');
            }
            
            const result = await response.json();
            if (result.success) {
                this.showToast('添加做市账号成功', 'success');
                bootstrap.Modal.getInstance(document.getElementById('addMarketMakerModal')).hide();
                form.reset();
                this.loadMarketMakers();
            } else {
                this.showToast(result.message || '添加做市账号失败', 'error');
            }
        } catch (error) {
            console.error('添加做市账号失败:', error);
            this.showToast('添加做市账号失败', 'error');
        }
    }
    
    // 启动做市账号
    async startMarketMaker(accountName) {
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/market-maker/accounts/${encodeURIComponent(accountName)}/start`, {
                method: 'POST'
            });
            
            if (!response || !response.ok) {
                throw new Error('启动做市账号失败');
            }
            
            const result = await response.json();
            if (result.success) {
                this.showToast('启动做市账号成功', 'success');
                this.loadMarketMakers();
            } else {
                this.showToast(result.message || '启动做市账号失败', 'error');
            }
        } catch (error) {
            console.error('启动做市账号失败:', error);
            this.showToast('启动做市账号失败', 'error');
        }
    }
    
    // 停止做市账号
    async stopMarketMaker(accountName) {
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/market-maker/accounts/${encodeURIComponent(accountName)}/stop`, {
                method: 'POST'
            });
            
            if (!response || !response.ok) {
                throw new Error('停止做市账号失败');
            }
            
            const result = await response.json();
            if (result.success) {
                this.showToast('停止做市账号成功', 'success');
                this.loadMarketMakers();
            } else {
                this.showToast(result.message || '停止做市账号失败', 'error');
            }
        } catch (error) {
            console.error('停止做市账号失败:', error);
            this.showToast('停止做市账号失败', 'error');
        }
    }
    
    // 删除做市账号
    async deleteMarketMaker(accountName) {
        if (!confirm(`确定要删除做市账号 "${accountName}" 吗？`)) {
            return;
        }
        
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/market-maker/accounts/${encodeURIComponent(accountName)}`, {
                method: 'DELETE'
            });
            
            if (!response || !response.ok) {
                throw new Error('删除做市账号失败');
            }
            
            const result = await response.json();
            if (result.success) {
                this.showToast('删除做市账号成功', 'success');
                this.loadMarketMakers();
            } else {
                this.showToast(result.message || '删除做市账号失败', 'error');
            }
        } catch (error) {
            console.error('删除做市账号失败:', error);
            this.showToast('删除做市账号失败', 'error');
        }
    }
    
    // 加载做市统计
    async loadMarketMakerStats() {
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/market-maker/stats`);
            if (!response || !response.ok) {
                throw new Error('加载做市统计失败');
            }
            const result = await response.json();
            const stats = result.data || {};
            
            // 格式化数字，保留4位小数
            const formatNumber = (value) => {
                const num = parseFloat(value) || 0;
                return num.toFixed(4);
            };
            
            document.getElementById('market-maker-total-volume').textContent = formatNumber(stats.total_volume || '0');
            document.getElementById('market-maker-total-profit').textContent = formatNumber(stats.total_profit || '0');
            document.getElementById('market-maker-total-fees').textContent = formatNumber(stats.total_fees || '0');
            document.getElementById('market-maker-net-profit').textContent = formatNumber(stats.net_profit || '0');
            
            // 渲染详细统计表格
            const details = stats.details || [];
            const tbody = document.getElementById('marketMakerStatsTableBody');
            if (tbody) {
                if (details.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="11" class="text-center text-muted">暂无统计数据</td></tr>';
                } else {
                    // 格式化数字，保留4位小数
                    const formatNumber = (value) => {
                        const num = parseFloat(value) || 0;
                        return num.toFixed(4);
                    };
                    
                    tbody.innerHTML = details.map(detail => `
                        <tr>
                            <td>${detail.account_name || '-'}</td>
                            <td>${detail.symbol || '-'}</td>
                            <td>${formatNumber(detail.buy_volume || '0')}</td>
                            <td>${formatNumber(detail.sell_volume || '0')}</td>
                            <td>${formatNumber(detail.maker_buy_volume || '0')}</td>
                            <td>${formatNumber(detail.maker_sell_volume || '0')}</td>
                            <td>${formatNumber(detail.taker_buy_volume || '0')}</td>
                            <td>${formatNumber(detail.taker_sell_volume || '0')}</td>
                            <td class="${parseFloat(detail.realized_profit || 0) >= 0 ? 'text-success' : 'text-danger'}">${formatNumber(detail.realized_profit || '0')}</td>
                            <td>${formatNumber(detail.fees || '0')}</td>
                            <td class="${parseFloat(detail.net_profit || 0) >= 0 ? 'text-success' : 'text-danger'}">${formatNumber(detail.net_profit || '0')}</td>
                        </tr>
                    `).join('');
                }
            }
        } catch (error) {
            console.error('加载做市统计失败:', error);
            this.showToast('加载做市统计失败', 'error');
        }
    }
    
    // ==================== Echosync 排行榜功能 ====================
    
    // 获取时间筛选器的值
    getLeaderboardPeriod() {
        const filter = document.getElementById('leaderboardPeriodFilter');
        if (filter) {
            return parseInt(filter.value) || 180;
        }
        return 180; // 默认180天
    }
    
    async loadEchosyncLeaderboard(sortBy = 'total_pnl', periodDays = null) {
        // 如果没有指定时间范围，从筛选器获取
        if (periodDays === null) {
            periodDays = this.getLeaderboardPeriod();
        }
        try {
            let containerId;
            if (sortBy === 'total_pnl') {
                containerId = 'pnlLeaderboardContainer';
            } else if (sortBy === 'avg_win_rate') {
                containerId = 'winrateLeaderboardContainer';
            } else if (sortBy === 'updated_at') {
                containerId = 'recentLeaderboardContainer';
            }
            
            const container = document.getElementById(containerId);
            if (!container) return;
            
            // 显示加载状态
            container.innerHTML = `
                <div class="col-12">
                    <div class="text-center py-5">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">加载中...</span>
                        </div>
                        <p class="mt-3 text-muted">正在加载排行榜...</p>
                    </div>
                </div>
            `;
            
            const response = await this.apiRequest(
                `${this.apiBaseUrl}/echosync/leaderboard?sort_by=${sortBy}&period_days=${periodDays}&page_size=100&use_cache=true`
            );
            
            if (!response || !response.ok) {
                throw new Error('获取排行榜失败');
            }
            
            const result = await response.json();
            
            if (result.success && result.data) {
                this.renderLeaderboard(result.data, containerId, sortBy);
            } else {
                throw new Error(result.message || '获取排行榜失败');
            }
            
        } catch (error) {
            console.error('加载排行榜失败:', error);
            const containerId = sortBy === 'total_pnl' ? 'pnlLeaderboardContainer' : 
                               sortBy === 'avg_win_rate' ? 'winrateLeaderboardContainer' : 
                               'recentLeaderboardContainer';
            const container = document.getElementById(containerId);
            if (container) {
                container.innerHTML = `
                    <div class="col-12">
                        <div class="alert alert-danger">
                            <i class="bi bi-exclamation-triangle"></i> 加载排行榜失败: ${error.message}
                        </div>
                    </div>
                `;
            }
            this.showToast('错误', '加载排行榜失败', 'error');
        }
    }
    
    renderLeaderboard(traders, containerId, sortBy) {
        const container = document.getElementById(containerId);
        if (!container) return;
        
        if (!traders || traders.length === 0) {
            container.innerHTML = `
                <div class="col-12">
                    <div class="alert alert-info text-center">
                        <i class="bi bi-info-circle"></i> 暂无排行榜数据
                    </div>
                </div>
            `;
            return;
        }
        
        container.innerHTML = '';
        
        // 创建表格
        const card = document.createElement('div');
        card.className = 'card';
        card.innerHTML = `
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table table-hover">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>交易员地址</th>
                                <th>总盈亏 (USDC)</th>
                                <th>胜率</th>
                                <th>总交易数</th>
                                <th>总成交量 (USDC)</th>
                                <th>最大回撤</th>
                                <th>夏普比率</th>
                                <th>最新操作</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>
        `;
        
        const tbody = card.querySelector('tbody');
        traders.forEach((trader, index) => {
            const row = document.createElement('tr');
            
            // 地址格式化
            const address = trader.user_address || '';
            const shortAddress = address ? `${address.slice(0, 6)}...${address.slice(-4)}` : 'N/A';
            
            // 数据格式化
            const totalPnl = this.formatNumber(parseFloat(trader.total_pnl || 0), 2);
            const netPnl = this.formatNumber(parseFloat(trader.net_pnl || 0), 2);
            const winRate = this.formatPercentage(parseFloat(trader.avg_win_rate || 0), 2);
            const totalTrades = parseInt(trader.total_trades || 0);
            const winningTrades = parseInt(trader.total_winning_trades || 0);
            const totalVolume = this.formatNumber(parseFloat(trader.total_volume || 0), 0);
            const maxDrawdown = this.formatPercentage(parseFloat(trader.max_drawdown || 0) * 100, 2);
            const sharpeRatio = this.formatNumber(parseFloat(trader.sharpe_ratio || 0), 2);
            const updatedAt = trader.updated_at ? new Date(trader.updated_at).toLocaleString('zh-CN') : 'N/A';
            
            // 排名徽章
            let rankBadge = '';
            if (index === 0) rankBadge = '<span class="badge bg-warning text-dark"><i class="bi bi-trophy-fill"></i> 1</span>';
            else if (index === 1) rankBadge = '<span class="badge bg-secondary"><i class="bi bi-trophy"></i> 2</span>';
            else if (index === 2) rankBadge = '<span class="badge bg-info"><i class="bi bi-trophy"></i> 3</span>';
            else rankBadge = `<span class="badge bg-light text-dark">${index + 1}</span>`;
            
            row.innerHTML = `
                <td>${rankBadge}</td>
                <td>
                    <a href="#" class="trader-address-link" data-address="${address}" style="font-family: monospace;">
                        ${shortAddress}
                    </a>
                </td>
                <td>
                    <div>
                        <div class="fw-bold ${parseFloat(trader.total_pnl) >= 0 ? 'text-success' : 'text-danger'}">
                            ${parseFloat(trader.total_pnl) >= 0 ? '+' : ''}${totalPnl}
                        </div>
                        <small class="text-muted">净盈亏: ${netPnl}</small>
                    </div>
                </td>
                <td>
                    <div class="fw-bold ${parseFloat(trader.avg_win_rate) >= 50 ? 'text-success' : 'text-danger'}">
                        ${winRate}
                    </div>
                    <small class="text-muted">${winningTrades}/${totalTrades}</small>
                </td>
                <td class="text-center">${totalTrades}</td>
                <td>${totalVolume}</td>
                <td class="text-center">${maxDrawdown}</td>
                <td class="text-center">${sharpeRatio}</td>
                <td><small class="text-muted">${updatedAt}</small></td>
                <td>
                    <button class="btn btn-sm btn-primary add-whale-to-limit-follow" 
                            data-trader="${JSON.stringify(trader).replace(/"/g, '&quot;')}">
                        <i class="bi bi-arrow-repeat"></i> 跟单交易
                    </button>
                </td>
            `;
            
            tbody.appendChild(row);
        });
        
        container.appendChild(card);
        
        // 添加事件监听器
        const self = this;
        container.querySelectorAll('.trader-address-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const address = e.currentTarget.getAttribute('data-address');
                self.viewUserPortfolio(address);
            });
        });
        
        // 跟单交易事件监听
        container.querySelectorAll('.add-whale-to-limit-follow').forEach(btn => {
            btn.addEventListener('click', () => {
                const traderData = JSON.parse(btn.getAttribute('data-trader').replace(/&quot;/g, '"'));
                self.addWhaleTraderToLimitFollow(traderData);
            });
        });
    }
    
    async viewUserPortfolio(address) {
        try {
            const response = await this.apiRequest(`${this.apiBaseUrl}/echosync/user-portfolio/${address}`);
            
            if (!response || !response.ok) {
                throw new Error('获取用户详情失败');
            }
            
            const result = await response.json();
            
            if (result.success && result.data) {
                // 确保数据格式正确
                const portfolioData = result.data;

                this.showUserPortfolioModal(portfolioData, address);
            } else {
                throw new Error(result.message || '获取用户详情失败');
            }
            
        } catch (error) {
            this.showToast('错误', '获取用户详情失败', 'error');
        }
    }
    
    // 添加巨鲸交易员到限价跟单
    async addWhaleTraderToMarketFollow(trader) {
        try {
            // 市价跟单功能：直接调用限价跟单接口（底层逻辑相同）
            this.showToast('提示', '市价跟单功能将先添加到限价跟单...', 'info');
            
            // TODO: 实际实现市价跟单逻辑（需要后端支持）
            // 暂时先调用限价跟单功能
            await this.addWhaleTraderToLimitFollow(trader);
            
        } catch (error) {
            console.error('添加到市价跟单失败:', error);
            this.showToast('错误', `添加到市价跟单失败: ${error.message}`, 'error');
        }
    }
    
    async addWhaleTraderToLimitFollow(trader) {
        try {
            const address = trader.user_address || '';
            if (!address) {
                throw new Error('交易员地址为空');
            }
            
            // 检查带单员是否已存在（使用地址作为唯一标识）
            const response = await this.apiRequest(`${this.apiBaseUrl}/limit-follow/traders`);
            if (response && response.ok) {
                const result = await response.json();
                if (result.success && result.data) {
                    // 检查是否已存在相同地址的带单员
                    const existing = result.data.find(t => {
                        // 检查 collector_config 中是否包含该地址
                        if (t.collector_config) {
                            try {
                                const config = typeof t.collector_config === 'string' 
                                    ? JSON.parse(t.collector_config) 
                                    : t.collector_config;
                                return config.address === address || config.user_address === address;
                            } catch (e) {
                                return false;
                            }
                        }
                        return false;
                    });
                    
                    if (existing) {
                        this.showToast('提示', '该交易员已存在，正在跳转到限价跟单页面...', 'info');
                        setTimeout(() => {
                            this.navigateToPage('limit-follow');
                        }, 1500);
                        return;
                    }
                }
            }
            
            // 构建带单员数据
            // 注意：Hyperliquid 使用地址作为唯一标识，而不是 unique_name
            const traderData = {
                unique_name: `hyperliquid_${address.slice(2, 10)}`, // 使用地址的一部分作为 unique_name
                name: `Hyperliquid巨鲸-${address.slice(0, 6)}...${address.slice(-4)}`,
                description: `来自Hyperliquid的巨鲸交易员，总盈亏${this.formatNumber(parseFloat(trader.total_pnl || 0), 2)} USDC，胜率${this.formatPercentage(parseFloat(trader.avg_win_rate || 0), 2)}%，总交易数${trader.total_trades || 0}`,
                collector_type: 'hyperliquid', // 使用 hyperliquid 作为 collector_type
                collector_config: JSON.stringify({
                    address: address,
                    user_address: address,
                    source: 'echosync'
                }),
                enabled: true
            };
            
            // 创建带单员
            const createResponse = await this.apiRequest(`${this.apiBaseUrl}/limit-follow/traders`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(traderData)
            });
            
            if (createResponse && createResponse.ok) {
                const createResult = await createResponse.json();
                if (createResult.success || createResult.success === 200) {
                    this.showToast('成功', '已添加到跟单交易，正在跳转...', 'success');
                    setTimeout(() => {
                        this.navigateToPage('limit-follow');
                        // 刷新限价跟单数据
                        this.loadLimitFollowTraders();
                    }, 1000);
                } else {
                    throw new Error(createResult.message || '添加失败');
                }
            } else {
                const errorResult = await createResponse.json().catch(() => ({}));
                throw new Error(errorResult.message || '添加带单员失败');
            }
            
        } catch (error) {
            console.error('添加到跟单交易失败:', error);
            this.showToast('错误', `添加到跟单交易失败: ${error.message}`, 'error');
        }
    }
    
    showUserPortfolioModal(portfolio, address) {
        // 创建模态框
        let modal = document.getElementById('userPortfolioModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'userPortfolioModal';
            modal.className = 'modal fade';
            modal.setAttribute('tabindex', '-1');
            document.body.appendChild(modal);
        }
        
        // 调试：记录接收到的数据
        // console.log('[用户详情] 接收到的portfolio数据:', portfolio);
        // console.log('[用户详情] portfolio类型:', typeof portfolio);
        // console.log('[用户详情] portfolio键:', portfolio ? Object.keys(portfolio) : 'null');
        
        // 处理数据格式：Hyperliquid API 可能返回不同的数据结构
        let marginSummary = {};
        let assetPositions = [];
        let withdrawable = '0';
        
        if (portfolio) {
            // 如果 portfolio 是数组，需要处理嵌套数组的情况
            if (Array.isArray(portfolio)) {
                
                // 首先尝试查找包含 marginSummary 的字典元素
                const portfolioWithMargin = portfolio.find(item => 
                    item && typeof item === 'object' && !Array.isArray(item) && 'marginSummary' in item
                );
                
                if (portfolioWithMargin) {
                    portfolio = portfolioWithMargin;
                } else if (portfolio.length > 0) {
                    const firstItem = portfolio[0];
                    
                    // 如果第一个元素也是数组，说明是嵌套数组格式
                    // Hyperliquid API 可能返回: [[marginSummary], [assetPositions], ...]
                    if (Array.isArray(firstItem)) {
                        // 尝试从嵌套数组中提取数据
                        const extracted = {};
                        
                        // 第一个数组通常是 marginSummary
                        if (portfolio[0] && Array.isArray(portfolio[0]) && portfolio[0].length > 0) {
                            if (typeof portfolio[0][0] === 'object' && !Array.isArray(portfolio[0][0])) {
                                extracted.marginSummary = portfolio[0][0];
                            }
                        }
                        
                        // 第二个数组通常是 assetPositions
                        if (portfolio[1] && Array.isArray(portfolio[1])) {
                            extracted.assetPositions = portfolio[1];
                        }
                        
                        // 第三个可能是 withdrawable
                        if (portfolio[2] !== undefined) {
                            extracted.withdrawable = String(portfolio[2]);
                        }
                        
                        portfolio = extracted;
                    } else if (typeof firstItem === 'object' && firstItem !== null) {
                        // 如果第一个元素是对象，直接使用
                        portfolio = firstItem;
                    } else {
                        console.warn('[用户详情] 数组格式未知，无法解析');
                        portfolio = null;
                    }
                } else {
                    portfolio = null;
                }
            }
            
            // 提取数据
            if (portfolio && typeof portfolio === 'object') {
                marginSummary = portfolio.marginSummary || portfolio.margin || {};
                assetPositions = portfolio.assetPositions || portfolio.positions || [];
                withdrawable = portfolio.withdrawable || portfolio.withdrawableBalance || '0';
            }
        }
        
        const accountValue = this.formatNumber(parseFloat(marginSummary.accountValue || 0), 2);
        const withdrawableFormatted = this.formatNumber(parseFloat(withdrawable || 0), 2);
        const totalNtlPos = this.formatNumber(parseFloat(marginSummary.totalNtlPos || 0), 2);
        
        // 计算总持仓价值
        let totalPositionValue = 0;
        assetPositions.forEach(pos => {
            const posValue = parseFloat(pos.position?.positionValue || 0);
            totalPositionValue += Math.abs(posValue);
        });
        const positionValue = this.formatNumber(totalPositionValue, 2);
        
        // 计算杠杆率
        const leverage = parseFloat(marginSummary.accountValue) > 0 ? 
            (totalPositionValue / parseFloat(marginSummary.accountValue)).toFixed(2) : '0.00';
        
        modal.innerHTML = `
            <div class="modal-dialog modal-xl">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">
                            <i class="bi bi-person-circle"></i> 用户详情 
                            <span class="badge bg-secondary" style="font-family: monospace;">${address.slice(0, 10)}...${address.slice(-8)}</span>
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <!-- 账户概览 -->
                        <div class="row mb-4">
                            <div class="col-md-3">
                                <div class="card text-center">
                                    <div class="card-body">
                                        <h6 class="text-muted">账户总价值</h6>
                                        <h4 class="mb-0">$${accountValue}</h4>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-3">
                                <div class="card text-center">
                                    <div class="card-body">
                                        <h6 class="text-muted">可提取余额</h6>
                                        <h4 class="mb-0">$${withdrawableFormatted}</h4>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-3">
                                <div class="card text-center">
                                    <div class="card-body">
                                        <h6 class="text-muted">持仓价值</h6>
                                        <h4 class="mb-0">$${positionValue}</h4>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-3">
                                <div class="card text-center">
                                    <div class="card-body">
                                        <h6 class="text-muted">杠杆率</h6>
                                        <h4 class="mb-0">${leverage}x</h4>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- 持仓列表 -->
                        <h6 class="mb-3"><i class="bi bi-list-ul"></i> 当前持仓</h6>
                        <div class="table-responsive">
                            <table class="table table-sm table-hover">
                                <thead>
                                    <tr>
                                        <th>币种</th>
                                        <th>持仓数量</th>
                                        <th>持仓价值</th>
                                        <th>未实现盈亏</th>
                                        <th>杠杆</th>
                                        <th>清算价格</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${assetPositions.length > 0 ? assetPositions.map(pos => {
                                        const position = pos.position || {};
                                        const coin = position.coin || 'N/A';
                                        const szi = position.szi || '0';
                                        const posVal = this.formatNumber(Math.abs(parseFloat(position.positionValue || 0)), 2);
                                        const unrealizedPnl = this.formatNumber(parseFloat(position.unrealizedPnl || 0), 2);
                                        const lev = position.leverage?.value || '0';
                                        const liquidationPx = position.liquidationPx || 'N/A';
                                        const pnlColor = parseFloat(position.unrealizedPnl) >= 0 ? 'text-success' : 'text-danger';
                                        
                                        return `
                                            <tr>
                                                <td><strong>${coin}</strong></td>
                                                <td>${szi}</td>
                                                <td>$${posVal}</td>
                                                <td class="${pnlColor}">${parseFloat(position.unrealizedPnl) >= 0 ? '+' : ''}$${unrealizedPnl}</td>
                                                <td>${lev}x</td>
                                                <td>${liquidationPx}</td>
                                            </tr>
                                        `;
                                    }).join('') : '<tr><td colspan="6" class="text-center text-muted">暂无持仓</td></tr>'}
                                </tbody>
                            </table>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                        <a href="https://hypurrscan.io/address/${address}" target="_blank" class="btn btn-primary">
                            <i class="bi bi-box-arrow-up-right"></i> 在 Hypurrscan 查看
                        </a>
                    </div>
                </div>
            </div>
        `;
        
        const bootstrapModal = new bootstrap.Modal(modal);
        bootstrapModal.show();
    }
    
    // ==================== 巨鲸订单功能 ====================
    
    async loadWhaleOrders() {
        try {
            const tbody = document.getElementById('whaleOrdersTableBody');
            if (!tbody) return;
            
            // 显示加载状态
            tbody.innerHTML = `
                <tr>
                    <td colspan="9" class="text-center py-5">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">加载中...</span>
                        </div>
                        <p class="mt-3 text-muted">正在加载巨鲸订单...</p>
                    </td>
                </tr>
            `;
            
            // 获取筛选参数
            const minAmount = parseFloat(document.getElementById('whaleOrdersMinAmount')?.value || '100000');
            const tradeType = document.getElementById('whaleOrdersType')?.value || 'perpetual';
            
            // 最近24小时
            const endDate = Date.now();
            const startDate = endDate - (24 * 60 * 60 * 1000);
            
            const response = await this.apiRequest(
                `${this.apiBaseUrl}/echosync/whale-orders?min_trade_amount=${minAmount}&start_date=${startDate}&end_date=${endDate}&trade_type=${tradeType}&page_size=100`
            );
            
            if (!response || !response.ok) {
                throw new Error('获取巨鲸订单失败');
            }
            
            const result = await response.json();
            
            if (result.success && result.data) {
                this.renderWhaleOrders(result.data);
            } else {
                throw new Error(result.message || '获取巨鲸订单失败');
            }
            
        } catch (error) {
            console.error('加载巨鲸订单失败:', error);
            const tbody = document.getElementById('whaleOrdersTableBody');
            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="9" class="text-center">
                            <div class="alert alert-danger mb-0">
                                <i class="bi bi-exclamation-triangle"></i> 加载巨鲸订单失败: ${error.message}
                            </div>
                        </td>
                    </tr>
                `;
            }
            this.showToast('错误', '加载巨鲸订单失败', 'error');
        }
    }
    
    renderWhaleOrders(orders) {
        const tbody = document.getElementById('whaleOrdersTableBody');
        if (!tbody) return;
        
        if (!orders || orders.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="9" class="text-center">
                        <div class="alert alert-info mb-0">
                            <i class="bi bi-info-circle"></i> 暂无巨鲸订单数据
                        </div>
                    </td>
                </tr>
            `;
            return;
        }
        
        tbody.innerHTML = '';
        
        orders.forEach(order => {
            const row = document.createElement('tr');
            
            // 数据格式化
            const time = order.time ? new Date(order.time).toLocaleString('zh-CN') : 'N/A';
            const address = order.user_address || '';
            const shortAddress = address ? `${address.slice(0, 6)}...${address.slice(-4)}` : 'N/A';
            const coin = order.coin || 'N/A';
            const side = order.side === 'B' ? '<span class="badge bg-success">买入</span>' : '<span class="badge bg-danger">卖出</span>';
            const px = this.formatNumber(parseFloat(order.px || 0), 2);
            const sz = this.formatNumber(parseFloat(order.sz || 0), 4);
            const notionalValue = this.formatNumber(parseFloat(order.notional_value || 0), 0);
            const tradeType = order.trade_type === 'perpetual' ? '<span class="badge bg-primary">永续</span>' : '<span class="badge bg-info">现货</span>';
            
            row.innerHTML = `
                <td><small>${time}</small></td>
                <td>
                    <a href="#" class="trader-address-link" data-address="${address}" style="font-family: monospace;">
                        ${shortAddress}
                    </a>
                </td>
                <td><strong>${coin}</strong></td>
                <td>${side}</td>
                <td>$${px}</td>
                <td>${sz}</td>
                <td><strong>$${notionalValue}</strong></td>
                <td>${tradeType}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary view-portfolio-btn" 
                            data-address="${address}">
                        <i class="bi bi-eye"></i>
                    </button>
                </td>
            `;
            
            tbody.appendChild(row);
        });
        
        // 添加事件监听器
        const self = this;
        tbody.querySelectorAll('.trader-address-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const address = e.currentTarget.getAttribute('data-address');
                self.viewUserPortfolio(address);
            });
        });
        
        tbody.querySelectorAll('.view-portfolio-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const address = btn.getAttribute('data-address');
                self.viewUserPortfolio(address);
            });
        });
    }
    
    // ==================== 巨鲸转移功能 ====================
    
    async loadWhaleMoves() {
        try {
            const tbody = document.getElementById('whaleMovesTableBody');
            if (!tbody) return;
            
            // 显示加载状态
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center py-5">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">加载中...</span>
                        </div>
                        <p class="mt-3 text-muted">正在加载巨鲸资金转移...</p>
                    </td>
                </tr>
            `;
            
            // 获取筛选参数
            const minAmount = parseFloat(document.getElementById('whaleMovesMinAmount')?.value || '10000');
            
            // 根据 Echosync API，deposits 接口不需要时间戳参数
            // 它会返回所有符合金额条件的数据，按 event_time 排序
            const response = await this.apiRequest(
                `${this.apiBaseUrl}/echosync/whale-moves?min_amount=${minAmount}&page_size=100`
            );
            
            if (!response || !response.ok) {
                throw new Error('获取巨鲸资金转移失败');
            }
            
            const result = await response.json();
            
            if (result.success && result.data) {
                this.renderWhaleMoves(result.data);
            } else {
                throw new Error(result.message || '获取巨鲸资金转移失败');
            }
            
        } catch (error) {
            console.error('加载巨鲸资金转移失败:', error);
            const tbody = document.getElementById('whaleMovesTableBody');
            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="6" class="text-center">
                            <div class="alert alert-danger mb-0">
                                <i class="bi bi-exclamation-triangle"></i> 加载巨鲸资金转移失败: ${error.message}
                            </div>
                        </td>
                    </tr>
                `;
            }
            this.showToast('错误', '加载巨鲸资金转移失败', 'error');
        }
    }
    
    renderWhaleMoves = (moves) => {
        const tbody = document.getElementById('whaleMovesTableBody');
        if (!tbody) return;
        
        if (!moves || moves.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center">
                        <div class="alert alert-info mb-0">
                            <i class="bi bi-info-circle"></i> 暂无巨鲸资金转移数据
                        </div>
                    </td>
                </tr>
            `;
            return;
        }
        
        tbody.innerHTML = '';
        
        moves.forEach(move => {
            const row = document.createElement('tr');
            
            // 数据格式化
            // event_time 是 ISO 字符串格式，如 "2025-11-07T03:35:37.243009"
            let time = 'N/A';
            if (move.event_time) {
                try {
                    // 尝试解析 ISO 字符串
                    time = new Date(move.event_time).toLocaleString('zh-CN');
                } catch (e) {
                    // 如果失败，尝试作为时间戳解析
                    try {
                        time = new Date(parseInt(move.event_time) * 1000).toLocaleString('zh-CN');
                    } catch (e2) {
                        time = move.event_time; // 直接显示原始值
                    }
                }
            }
            
            const address = move.user_address || '';
            const shortAddress = address ? `${address.slice(0, 6)}...${address.slice(-4)}` : 'N/A';
            
            // deposits API 返回的都是存入，没有 event_type 字段
            const eventType = '<span class="badge bg-success"><i class="bi bi-arrow-down-circle"></i> 存入</span>';
            
            // 使用 usdc_amount 字段
            const amount = this.formatNumber(parseFloat(move.usdc_amount || 0), 2);
            
            // 使用 transaction_hash 字段
            const hash = move.transaction_hash || '';
            const shortHash = hash ? `${hash.slice(0, 8)}...${hash.slice(-6)}` : 'N/A';
            
            row.innerHTML = `
                <td><small>${time}</small></td>
                <td>
                    <a href="#" class="trader-address-link" data-address="${address}" style="font-family: monospace;">
                        ${shortAddress}
                    </a>
                </td>
                <td>${eventType}</td>
                <td><strong>$${amount}</strong></td>
                <td>
                    ${hash ? `<a href="https://hypurrscan.io/tx/${hash}" target="_blank" style="font-family: monospace;">
                        ${shortHash}
                    </a>` : 'N/A'}
                </td>
                <td>
                    <button class="btn btn-sm btn-outline-primary view-portfolio-btn" 
                            data-address="${address}">
                        <i class="bi bi-eye"></i>
                    </button>
                </td>
            `;
            
            tbody.appendChild(row);
        });
        
        // 添加事件监听器
        const self = this;
        tbody.querySelectorAll('.trader-address-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const address = e.currentTarget.getAttribute('data-address');
                self.viewUserPortfolio(address);
            });
        });
        
        tbody.querySelectorAll('.view-portfolio-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const address = btn.getAttribute('data-address');
                self.viewUserPortfolio(address);
            });
        });
    }
    
    // 启动自动刷新（巨鲸订单和转移）
    startWhaleAutoRefresh = () => {
        // 清除之前的定时器
        if (this.whaleOrdersInterval) {
            clearInterval(this.whaleOrdersInterval);
        }
        if (this.whaleMovesInterval) {
            clearInterval(this.whaleMovesInterval);
        }
        
        // 每分钟刷新巨鲸订单
        this.whaleOrdersInterval = setInterval(() => {
            const currentPage = document.querySelector('.page-content:not([style*="display: none"])');
            if (currentPage && currentPage.id === 'echosync-whale-orders-page') {
                this.loadWhaleOrders();
            }
        }, 60000); // 60秒
        
        // 每分钟刷新巨鲸转移
        this.whaleMovesInterval = setInterval(() => {
            const currentPage = document.querySelector('.page-content:not([style*="display: none"])');
            if (currentPage && currentPage.id === 'echosync-whale-moves-page') {
                this.loadWhaleMoves();
            }
        }, 60000); // 60秒
    }
}

// 页面加载完成后初始化应用
document.addEventListener('DOMContentLoaded', () => {
    window.app = new OKXTradingApp();
    
        // 为全局资产更新按钮添加事件监听器
        const updateAllAssetsBtn = document.getElementById('updateAllAssetsBtn');
        if (updateAllAssetsBtn) {
            updateAllAssetsBtn.addEventListener('click', () => {
                window.app.forceUpdateAllCustomerAssets();
            });
        }
        // 跟单订单类型变化事件监听器
        const followOrderTypesSelect = document.getElementById('followOrderTypes');
        const limitMarketRatioRow = document.getElementById('limitMarketRatioRow');
        
        if (followOrderTypesSelect && limitMarketRatioRow) {
            followOrderTypesSelect.addEventListener('change', function() {
                if (this.value === 'both') {
                    limitMarketRatioRow.style.display = 'block';
                } else {
                    limitMarketRatioRow.style.display = 'none';
                }
            });
        }
        
        // 自定义比例输入框变化事件监听器
        const customLimitRatio = document.getElementById('customLimitRatio');
        const customMarketRatio = document.getElementById('customMarketRatio');
        
        if (customLimitRatio && customMarketRatio) {
            customLimitRatio.addEventListener('input', updateRatioPreview);
            customMarketRatio.addEventListener('input', updateRatioPreview);
        }

        // 客户页面大小选择事件监听器
        const pageSize10Btn = document.getElementById('customersPageSize10');
        const pageSize20Btn = document.getElementById('customersPageSize20');
        const pageSize50Btn = document.getElementById('customersPageSize50');
        
        if (pageSize10Btn) {
            pageSize10Btn.addEventListener('click', () => {
                window.app.setCustomersPageSize(10);
            });
        }
        if (pageSize20Btn) {
            pageSize20Btn.addEventListener('click', () => {
                window.app.setCustomersPageSize(20);
            });
        }
        if (pageSize50Btn) {
            pageSize50Btn.addEventListener('click', () => {
                window.app.setCustomersPageSize(50);
            });
        }
});

// 全局错误处理
window.addEventListener('error', (event) => {
    console.error('全局错误:', event.error);
    if (window.app) {
        window.app.showToast('错误', '系统发生错误，请查看控制台', 'danger');
    }
});

// 未处理的Promise拒绝
window.addEventListener('unhandledrejection', (event) => {
    console.error('未处理的Promise拒绝:', event.reason);
    if (window.app) {
        window.app.showToast('错误', '网络请求失败，请检查网络连接', 'danger');
    }
}); 

// 自定义比例相关函数
function toggleCustomRatio() {
    const ratioSelect = document.getElementById('limitMarketRatio');
    const customInput = document.getElementById('customRatioInput');
    
    if (ratioSelect && customInput) {
        if (ratioSelect.value === 'custom') {
            customInput.style.display = 'block';
            updateRatioPreview(); // 初始化预览
        } else {
            customInput.style.display = 'none';
        }
    }
}

function updateRatioPreview() {
    const limitRatio = document.getElementById('customLimitRatio');
    const marketRatio = document.getElementById('customMarketRatio');
    const preview = document.getElementById('ratioPreview');
    
    if (limitRatio && marketRatio && preview) {
        const limit = parseInt(limitRatio.value) || 1;
        const market = parseInt(marketRatio.value) || 1;
        
        if (limit > 0 && market > 0) {
            const total = limit + market;
            const limitPercent = Math.round((limit / total) * 100);
            const marketPercent = Math.round((market / total) * 100);
            
            preview.textContent = `限价占${limitPercent}%，市价占${marketPercent}%`;
        } else {
            preview.textContent = '请输入有效的比例';
        }
    }
}

function getLimitMarketRatio() {
    const ratioSelect = document.getElementById('limitMarketRatio');
    
    if (ratioSelect && ratioSelect.value === 'custom') {
        const limitRatio = document.getElementById('customLimitRatio');
        const marketRatio = document.getElementById('customMarketRatio');
        
        if (limitRatio && marketRatio) {
            const limit = parseInt(limitRatio.value) || 1;
            const market = parseInt(marketRatio.value) || 1;
            return `${limit}:${market}`;
        }
    }
    
    return ratioSelect ? ratioSelect.value : '1:1';
} 

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
    
    // 刷新策略按钮
    const refreshStrategiesBtn = document.getElementById('refreshStrategiesBtn');
    if (refreshStrategiesBtn) {
        refreshStrategiesBtn.addEventListener('click', () => {
            if (window.app) {
                window.app.refreshStrategies();
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
    
    // 用户策略模态框事件
    const userStrategyModal = document.getElementById('userStrategyModal');
    if (userStrategyModal) {
        userStrategyModal.addEventListener('show.bs.modal', () => {
            if (window.app) {
                window.app.loadUserStrategies();
            }
        });
        
        // Tab切换时显示/隐藏上传按钮
        const tabButtons = userStrategyModal.querySelectorAll('[data-bs-toggle="tab"]');
        const uploadBtn = document.getElementById('uploadStrategyBtn');
        tabButtons.forEach(btn => {
            btn.addEventListener('shown.bs.tab', (e) => {
                if (e.target.id === 'upload-tab') {
                    uploadBtn.style.display = 'block';
                } else {
                    uploadBtn.style.display = 'none';
                }
            });
        });
        
        // 上传策略按钮
        if (uploadBtn) {
            uploadBtn.addEventListener('click', () => {
                if (window.app) {
                    window.app.uploadUserStrategy();
                }
            });
        }
    }
    
    // 策略类型变化事件 - 使用事件委托，专门针对策略交易模态框
    document.addEventListener('change', (e) => {
        if (e.target && e.target.id === 'strategyType' && e.target.closest('#createStrategyTradeModal')) {
            
            if (window.app) {
                window.app.onStrategyTypeChangeTrade(e.target.value);
            } else {
                console.error('❌ window.app 不存在');
            }
        }
    });
    
    
    // 创建策略模态框显示事件
    const createStrategyModal = document.getElementById('createStrategyTradeModal');
    if (createStrategyModal) {
        createStrategyModal.addEventListener('show.bs.modal', () => {
            if (window.app) {
                window.app.loadAccountsForStrategyTrade('create');
                window.app.loadStrategyTemplatesForCreate();
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
    // 策略交易编辑保存按钮事件
    const saveStrategyTradeBtn = document.getElementById('saveStrategyTradeBtn');
    if (saveStrategyTradeBtn) {
        saveStrategyTradeBtn.addEventListener('click', () => {
            if (window.app) {
                window.app.saveStrategyTradeEdit();
            }
        });
    }
    
    // ==================== 消息转发事件监听 ====================
    
    // 平台类型切换
    const platformTypeSelect = document.getElementById('platformType');
    if (platformTypeSelect) {
        platformTypeSelect.addEventListener('change', function(e) {
            // 隐藏所有配置
            document.querySelectorAll('.platform-config').forEach(el => el.style.display = 'none');
            
            // 显示对应的配置
            const platformType = e.target.value;
            if (platformType) {
                const configDiv = document.getElementById(`${platformType}Config`);
                if (configDiv) {
                    configDiv.style.display = 'block';
                }
            }
        });
    }
    
    // 目标平台复选框切换
    document.querySelectorAll('.target-platform').forEach(checkbox => {
        checkbox.addEventListener('change', function(e) {
            const platform = e.target.value;
            const container = document.getElementById(`${platform}TargetContainer`);
            if (container) {
                container.style.display = e.target.checked ? 'block' : 'none';
            }
        });
    });
    
    // 保存平台按钮
    const savePlatformBtn = document.getElementById('savePlatformBtn');
    if (savePlatformBtn) {
        savePlatformBtn.addEventListener('click', () => {
            if (window.app) {
                window.app.savePlatform();
            }
        });
    }
    
    // 更新平台按钮
    const updatePlatformBtn = document.getElementById('updatePlatformBtn');
    if (updatePlatformBtn) {
        updatePlatformBtn.addEventListener('click', () => {
            if (window.app) {
                window.app.updatePlatform();
            }
        });
    }
    
    // 保存规则按钮
    // 转发规则模态框打开时重置表单并加载目标平台
    const addForwardRuleModal = document.getElementById('addForwardRuleModal');
    if (addForwardRuleModal) {
        addForwardRuleModal.addEventListener('show.bs.modal', async () => {
            // 检查是否是编辑模式（通过检查是否有ruleId）
            const modal = document.getElementById('addForwardRuleModal');
            const isEditMode = modal?.dataset?.ruleId;
            
            // 如果不是编辑模式，重置表单
            if (!isEditMode) {
                const form = document.getElementById('addForwardRuleForm');
                if (form) {
                    form.reset();
                    // 确保规则名称和源平台字段为空
                    const ruleNameInput = document.getElementById('forwardRuleName');
                    const sourcePlatformSelect = document.getElementById('sourcePlatform');
                    if (ruleNameInput) {
                        ruleNameInput.value = '';
                    }
                    if (sourcePlatformSelect) {
                        sourcePlatformSelect.value = '';
                    }
                }
                
                // 恢复模态框标题和按钮文本
                const modalTitle = document.querySelector('#addForwardRuleModal .modal-title');
                if (modalTitle) {
                    modalTitle.textContent = '添加转发规则';
                }
                const saveButton = document.querySelector('#addForwardRuleModal .btn-primary[type="submit"]');
                if (saveButton) {
                    saveButton.textContent = '保存规则';
                }
            }
            
            // 加载目标平台列表
            if (window.app) {
                await window.app.loadTargetPlatforms();
            }
        });
    }
    
    const saveForwardRuleBtn = document.getElementById('saveForwardRuleBtn');
    if (saveForwardRuleBtn) {
        saveForwardRuleBtn.addEventListener('click', () => {
            if (window.app) {
                window.app.saveForwardRule();
            }
        });
    }
    
    // 转发规则标签页切换事件
    const rulesTab = document.getElementById('rules-tab');
    if (rulesTab) {
        rulesTab.addEventListener('shown.bs.tab', async () => {
            // 确保数据已加载
            if (window.app) {
                try {
                    await window.app.loadForwardRulesList();
                } catch (error) {
                    console.error('加载转发规则列表失败:', error);
                }
            }
        });
    }
    
    // 刷新按钮
    const refreshMessageForwardBtn = document.getElementById('refreshMessageForwardBtn');
    if (refreshMessageForwardBtn) {
        refreshMessageForwardBtn.addEventListener('click', () => {
            if (window.app) {
                window.app.loadMessageForwardData();
            }
        });
    }
    
    // Telegram监听服务已移除，现在使用统一的消息转发服务
    
    // 初始化转发规则模态框
            if (window.app) {
        window.app.initForwardRuleModal();
    }
});

// 未处理的Promise拒绝
window.addEventListener('unhandledrejection', (event) => {
    console.error('未处理的Promise拒绝:', event.reason);
    if (window.app) {
        window.app.showToast('错误', '网络请求失败，请检查网络连接', 'danger');
    }
}); 