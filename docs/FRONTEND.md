# 🎨 前端界面文档

> 跟单交易系统的前端界面使用说明和技术实现

## 📋 目录

- [🎯 界面概述](#-界面概述)
- [🏠 主控制台](#-主控制台)
- [👥 客户管理](#-客户管理)
- [📡 信号源监控](#-信号源监控)
- [💰 限价单管理](#-限价单管理)
- [🛡️ 风险控制](#-风险控制)
- [📊 数据分析](#-数据分析)
- [⚙️ 系统设置](#-系统设置)
- [🔧 技术实现](#-技术实现)
- [🎨 界面定制](#-界面定制)
- [🐛 常见问题](#-常见问题)

## 🎯 界面概述

跟单交易系统提供了完整的Web管理界面，采用响应式设计，支持桌面端和移动端访问。

### 🌟 设计特点

- **现代化UI**: 基于Bootstrap 5的现代化界面设计
- **响应式布局**: 自适应不同屏幕尺寸
- **实时数据**: WebSocket实时数据推送
- **交互友好**: 直观的操作流程和反馈
- **主题支持**: 支持明暗主题切换

### 📱 兼容性

- **浏览器**: Chrome 80+, Firefox 75+, Safari 13+, Edge 80+
- **设备**: 桌面端、平板、手机
- **分辨率**: 1920x1080, 1366x768, 375x667等

## 🏠 主控制台

主控制台是系统的核心界面，提供系统概览和快速操作入口。

### 📊 系统概览

- **关键指标**: 显示系统运行状态、客户数量、订单数量等
- **实时监控**: 连接状态、系统健康度、错误统计
- **快速操作**: 一键启动/停止服务、系统重启等

### 🎛️ 快速操作

```javascript
// 启动所有服务
function startAllServices() {
    fetch('/api/v1/system/start', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showNotification('所有服务已启动', 'success');
                refreshDashboard();
            }
        });
}

// 停止所有服务
function stopAllServices() {
    fetch('/api/v1/system/stop', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showNotification('所有服务已停止', 'warning');
                refreshDashboard();
            }
        });
}
```

### 📈 实时图表

主控制台包含多个实时更新的图表：

- **系统状态图**: 显示各模块运行状态
- **连接状态图**: 实时连接数量统计
- **性能监控图**: CPU、内存使用率等

## 👥 客户管理

客户管理界面提供完整的客户账户管理功能。

### 📋 客户列表

显示所有客户的基本信息：

| 字段 | 说明 | 示例 |
|------|------|------|
| 客户ID | 唯一标识符 | c001 |
| 客户名称 | 客户显示名称 | 张三 |
| 交易所 | 使用的交易所 | OKX |
| 账户类型 | 演示/实盘 | 演示账户 |
| 状态 | 启用/禁用 | 启用 |
| 初始资金 | 账户初始资金 | $10,000 |
| 当前资产 | 实时资产价值 | $10,500 |

### ➕ 添加客户

点击"添加客户"按钮，填写客户信息：

```html
<form id="addCustomerForm">
    <div class="row">
        <div class="col-md-6">
            <label class="form-label">客户名称 *</label>
            <input type="text" class="form-control" name="name" required>
        </div>
        <div class="col-md-6">
            <label class="form-label">交易所 *</label>
            <select class="form-select" name="exchange" required>
                <option value="">选择交易所</option>
                <option value="okx">OKX</option>
                <option value="binance">Binance</option>
            </select>
        </div>
    </div>
    <div class="row">
        <div class="col-md-6">
            <label class="form-label">API密钥 *</label>
            <input type="password" class="form-control" name="api_key" required>
        </div>
        <div class="col-md-6">
            <label class="form-label">API密钥 *</label>
            <input type="password" class="form-control" name="api_secret" required>
        </div>
    </div>
    <div class="row">
        <div class="col-md-6">
            <label class="form-label">初始资金</label>
            <input type="number" class="form-control" name="init_asset" step="0.01">
        </div>
        <div class="col-md-6">
            <label class="form-label">账户类型</label>
            <div class="form-check form-switch">
                <input class="form-check-input" type="checkbox" name="is_demo" checked>
                <label class="form-check-label">演示账户</label>
            </div>
        </div>
    </div>
</form>
```

### ✏️ 编辑客户

点击客户行的"编辑"按钮，修改客户信息：

```javascript
function editCustomer(customerUid) {
    // 获取客户信息
    fetch(`/api/v1/customers/${customerUid}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                fillCustomerForm(data.data);
                showEditModal();
            }
        });
}

function fillCustomerForm(customer) {
    document.getElementById('editCustomerForm').name.value = customer.name;
    document.getElementById('editCustomerForm').exchange.value = customer.exchange;
    document.getElementById('editCustomerForm').init_asset.value = customer.init_asset;
    document.getElementById('editCustomerForm').is_demo.checked = customer.is_demo;
}
```

### 🗑️ 删除客户

删除客户前会进行确认：

```javascript
function deleteCustomer(customerUid) {
    if (confirm('确定要删除这个客户吗？此操作不可恢复！')) {
        fetch(`/api/v1/customers/${customerUid}`, { method: 'DELETE' })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showNotification('客户删除成功', 'success');
                    refreshCustomerList();
                } else {
                    showNotification('删除失败: ' + data.message, 'error');
                }
            });
    }
}
```

## 📡 信号源监控

信号源监控界面实时显示所有信号源的连接状态和交易活动。

### 🔌 连接状态

每个信号源显示以下状态信息：

- **连接状态**: 在线/离线/重连中
- **最后活动**: 最后收到数据的时间
- **健康度**: 连接质量评分
- **错误统计**: 连接错误次数

### 📊 实时数据

```javascript
// 建立WebSocket连接
function connectSignalSourceWebSocket() {
    const ws = new WebSocket('ws://localhost:5000/ws/signal-sources');
    
    ws.onmessage = function(event) {
        const data = JSON.parse(event.data);
        
        switch(data.type) {
            case 'connection_status':
                updateConnectionStatus(data.data);
                break;
            case 'trade_signal':
                handleTradeSignal(data.data);
                break;
            case 'position_update':
                updatePositionDisplay(data.data);
                break;
        }
    };
    
    ws.onerror = function(error) {
        console.error('WebSocket错误:', error);
        showNotification('信号源连接失败', 'error');
    };
}

// 更新连接状态显示
function updateConnectionStatus(statusData) {
    statusData.forEach(source => {
        const statusElement = document.getElementById(`status-${source.source_uid}`);
        if (statusElement) {
            statusElement.className = `status-badge ${getStatusClass(source.status)}`;
            statusElement.textContent = getStatusText(source.status);
        }
    });
}
```

### 🚨 异常处理

当信号源出现异常时，系统会：

1. **自动重连**: 尝试重新建立连接
2. **状态标记**: 在界面上标记异常状态
3. **通知提醒**: 发送钉钉或邮件通知
4. **日志记录**: 记录详细的错误信息

## 💰 限价单管理

限价单管理是系统的核心功能，提供专业的跟单策略管理界面。

### 📋 策略列表

显示所有限价单策略：

| 字段 | 说明 | 示例 |
|------|------|------|
| 策略名称 | 策略显示名称 | BTC跟单策略 |
| 跟单员 | 被跟随的交易员 | trader001 |
| 客户 | 执行跟单的客户 | c001 |
| 交易对 | 交易品种 | BTC-USDT-SWAP |
| 持仓方向 | 多/空/双向 | 双向 |
| 跟单类型 | 百分比/固定 | 百分比 |
| 跟单值 | 跟单参数 | 2.5% |
| 风险等级 | 低/中/高 | 中等 |
| 状态 | 启用/禁用 | 启用 |

### ➕ 创建策略

创建新的限价单策略：

```html
<form id="createStrategyForm">
    <div class="row">
        <div class="col-md-6">
            <label class="form-label">策略名称 *</label>
            <input type="text" class="form-control" name="strategy_name" required>
        </div>
        <div class="col-md-6">
            <label class="form-label">跟单员 *</label>
            <select class="form-select" name="trader_unique_name" required>
                <option value="">选择跟单员</option>
                <!-- 动态加载跟单员列表 -->
            </select>
        </div>
    </div>
    <div class="row">
        <div class="col-md-6">
            <label class="form-label">客户 *</label>
            <select class="form-select" name="customer_uid" required>
                <option value="">选择客户</option>
                <!-- 动态加载客户列表 -->
            </select>
        </div>
        <div class="col-md-6">
            <label class="form-label">交易对 *</label>
            <input type="text" class="form-control" name="symbol" placeholder="如: BTC-USDT-SWAP" required>
        </div>
    </div>
    <div class="row">
        <div class="col-md-6">
            <label class="form-label">持仓方向</label>
            <select class="form-select" name="pos_side">
                <option value="both">双向跟随</option>
                <option value="long">仅多仓</option>
                <option value="short">仅空仓</option>
            </select>
        </div>
        <div class="col-md-6">
            <label class="form-label">跟单类型</label>
            <select class="form-select" name="follow_type">
                <option value="percentage">百分比</option>
                <option value="fixed">固定数量</option>
            </select>
        </div>
    </div>
    <div class="row">
        <div class="col-md-6">
            <label class="form-label">跟单值 *</label>
            <input type="number" class="form-control" name="follow_value" step="0.1" required>
        </div>
        <div class="col-md-6">
            <label class="form-label">最大订单数</label>
            <input type="number" class="form-control" name="max_orders_per_signal" min="1" max="10" value="4">
        </div>
    </div>
    <div class="row">
        <div class="col-md-6">
            <label class="form-label">最大净杠杆</label>
            <input type="number" class="form-control" name="max_net_leverage" min="1" max="50" step="0.5" value="10">
        </div>
        <div class="col-md-6">
            <label class="form-label">风险等级</label>
            <select class="form-select" name="risk_level">
                <option value="low">低风险</option>
                <option value="medium" selected>中等风险</option>
                <option value="high">高风险</option>
            </select>
        </div>
    </div>
    <div class="row">
        <div class="col-md-6">
            <label class="form-label">止损百分比</label>
            <input type="number" class="form-control" name="stop_loss_percentage" min="0" max="50" step="0.5" value="5">
        </div>
        <div class="col-md-6">
            <label class="form-label">止盈百分比</label>
            <input type="number" class="form-control" name="take_profit_percentage" min="0" max="100" step="0.5" value="10">
        </div>
    </div>
    <div class="row">
        <div class="col-md-6">
            <div class="form-check form-switch">
                <input class="form-check-input" type="checkbox" name="proportional_position" checked>
                <label class="form-check-label">启用按比例开仓</label>
            </div>
        </div>
        <div class="col-md-6">
            <div class="form-check form-switch">
                <input class="form-check-input" type="checkbox" name="auto_cancel_on_signal_close" checked>
                <label class="form-check-label">信号平仓时自动撤单</label>
            </div>
        </div>
    </div>
</form>
```

### 📊 订单监控

实时监控限价单订单状态：

```javascript
// 获取订单列表
function loadOrders(filters = {}) {
    const queryString = new URLSearchParams(filters).toString();
    
    fetch(`/api/v1/limit-follow/orders?${queryString}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                renderOrdersTable(data.data);
            }
        });
}

// 渲染订单表格
function renderOrdersTable(orders) {
    const tbody = document.getElementById('ordersTableBody');
    tbody.innerHTML = '';
    
    orders.forEach(order => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${order.order_uid}</td>
            <td>${order.strategy_name || '-'}</td>
            <td>${order.customer_name || '-'}</td>
            <td>${order.symbol}</td>
            <td><span class="badge ${getPosSideClass(order.pos_side)}">${getPosSideText(order.pos_side)}</span></td>
            <td>$${order.target_price}</td>
            <td>${order.order_size}</td>
            <td><span class="badge ${getStatusClass(order.status)}">${getStatusText(order.status)}</span></td>
            <td><span class="risk-score ${getRiskClass(order.risk_score)}">${order.risk_score || '-'}</span></td>
            <td>${formatDateTime(order.created_at)}</td>
            <td>
                <button class="btn btn-sm btn-outline-primary" onclick="viewOrder('${order.order_uid}')">查看</button>
                ${order.status === 'pending' ? `<button class="btn btn-sm btn-outline-danger" onclick="cancelOrder('${order.order_uid}')">撤销</button>` : ''}
            </td>
        `;
        tbody.appendChild(row);
    });
}
```

### 🎯 策略配置

策略配置支持多种参数设置：

- **基础配置**: 策略名称、跟单员、客户、交易对
- **跟单参数**: 跟单类型、跟单值、最大订单数
- **风险控制**: 最大杠杆、风险等级、止损止盈
- **高级选项**: 按比例开仓、自动撤单等

## 🛡️ 风险控制

风险控制界面提供全面的风险管理功能。

### 📊 风险概览

显示系统整体风险状况：

- **风险分布**: 低/中/高风险策略数量
- **杠杆使用**: 当前杠杆使用情况
- **持仓集中度**: 各资产持仓分布
- **风险评分**: 整体风险评分

### 🚨 风险警报

实时显示风险警报：

```javascript
// 获取风险警报
function loadRiskAlerts() {
    fetch('/api/v1/limit-follow/risk/alerts')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                renderRiskAlerts(data.data);
            }
        });
}

// 渲染风险警报
function renderRiskAlerts(alerts) {
    const container = document.getElementById('riskAlerts');
    container.innerHTML = '';
    
    if (alerts.length === 0) {
        container.innerHTML = '<div class="alert alert-success">当前没有风险警报</div>';
        return;
    }
    
    alerts.forEach(alert => {
        const alertElement = document.createElement('div');
        alertElement.className = `alert alert-${getAlertLevelClass(alert.alert_type)}`;
        alertElement.innerHTML = `
            <h6 class="alert-heading">${alert.message}</h6>
            <p class="mb-1"><strong>策略:</strong> ${alert.strategy_name}</p>
            <p class="mb-1"><strong>客户:</strong> ${alert.customer_name}</p>
            <p class="mb-1"><strong>风险等级:</strong> <span class="badge ${getRiskLevelClass(alert.risk_level)}">${alert.risk_level}</span></p>
            <p class="mb-1"><strong>最大杠杆:</strong> ${alert.max_leverage}</p>
            <small class="text-muted">${formatDateTime(alert.created_at)}</small>
        `;
        container.appendChild(alertElement);
    });
}
```

### 📈 风险评估

对特定策略进行风险评估：

```javascript
// 评估策略风险
function assessStrategyRisk(strategyId, customerUid) {
    fetch('/api/v1/limit-follow/risk/assessment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy_id: strategyId, customer_uid: customerUid })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showRiskAssessmentResult(data.data);
        }
    });
}

// 显示风险评估结果
function showRiskAssessmentResult(assessment) {
    const modal = new bootstrap.Modal(document.getElementById('riskAssessmentModal'));
    
    document.getElementById('riskScore').textContent = assessment.risk_score;
    document.getElementById('riskLevel').textContent = assessment.risk_level;
    document.getElementById('riskFactors').innerHTML = assessment.risk_factors.map(factor => `<li>${factor}</li>`).join('');
    document.getElementById('recommendations').innerHTML = assessment.recommendations.map(rec => `<li>${rec}</li>`).join('');
    
    modal.show();
}
```

## 📊 数据分析

数据分析界面提供丰富的交易数据分析和可视化。

### 📈 性能分析

分析限价单执行性能：

```javascript
// 加载性能分析数据
function loadPerformanceAnalysis(days = 30, customerUid = null) {
    const params = new URLSearchParams({ days });
    if (customerUid) params.append('customer_uid', customerUid);
    
    fetch(`/api/v1/limit-follow/analytics/performance?${params}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                renderPerformanceCharts(data.data);
            }
        });
}

// 渲染性能图表
function renderPerformanceCharts(data) {
    // 订单状态分布图
    const orderStatusCtx = document.getElementById('orderStatusChart').getContext('2d');
    new Chart(orderStatusCtx, {
        type: 'doughnut',
        data: {
            labels: ['已成交', '待处理', '活跃', '已撤销', '部分成交'],
            datasets: [{
                data: [
                    data.filled_orders,
                    data.pending_orders,
                    data.live_orders,
                    data.canceled_orders,
                    data.partially_filled_orders
                ],
                backgroundColor: ['#28a745', '#ffc107', '#17a2b8', '#6c757d', '#fd7e14']
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false
        }
    });
    
    // 风险等级分布图
    const riskLevelCtx = document.getElementById('riskLevelChart').getContext('2d');
    new Chart(riskLevelCtx, {
        type: 'pie',
        data: {
            labels: ['低风险', '中等风险', '高风险'],
            datasets: [{
                data: [
                    data.risk_distribution.find(r => r.risk_level === 'low')?.count || 0,
                    data.risk_distribution.find(r => r.risk_level === 'medium')?.count || 0,
                    data.risk_distribution.find(r => r.risk_level === 'high')?.count || 0
                ],
                backgroundColor: ['#28a745', '#ffc107', '#dc3545']
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false
        }
    });
}
```

### 📊 趋势分析

分析交易趋势变化：

```javascript
// 加载趋势分析数据
function loadTrendAnalysis(days = 30, customerUid = null) {
    const params = new URLSearchParams({ days });
    if (customerUid) params.append('customer_uid', customerUid);
    
    fetch(`/api/v1/limit-follow/analytics/trends?${params}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                renderTrendCharts(data.data);
            }
        });
}

// 渲染趋势图表
function renderTrendCharts(data) {
    // 每日订单数量趋势
    const dailyOrdersCtx = document.getElementById('executionTrendChart').getContext('2d');
    new Chart(dailyOrdersCtx, {
        type: 'line',
        data: {
            labels: data.daily_orders.map(d => d.date),
            datasets: [{
                label: '订单数量',
                data: data.daily_orders.map(d => d.order_count),
                borderColor: '#007bff',
                backgroundColor: 'rgba(0, 123, 255, 0.1)',
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true }
            }
        }
    });
    
    // 每日成功率趋势
    const successRateCtx = document.getElementById('profitLossChart').getContext('2d');
    new Chart(successRateCtx, {
        type: 'line',
        data: {
            labels: data.daily_success_rate.map(d => d.date),
            datasets: [{
                label: '成功率 (%)',
                data: data.daily_success_rate.map(d => d.success_rate),
                borderColor: '#28a745',
                backgroundColor: 'rgba(40, 167, 69, 0.1)',
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { 
                    beginAtZero: true,
                    max: 100
                }
            }
        }
    });
}
```

## ⚙️ 系统设置

系统设置界面提供各种配置选项。

### 🔧 基本设置

配置系统基本参数：

```javascript
// 加载系统设置
function loadSystemSettings() {
    fetch('/api/v1/limit-follow/config')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                fillSettingsForm(data.data.config);
            }
        });
}

// 填充设置表单
function fillSettingsForm(config) {
    document.getElementById('maxOrdersPerSignal').value = config.max_orders_per_signal || 4;
    document.getElementById('checkInterval').value = config.check_interval || 1;
    document.getElementById('maxRetryAttempts').value = config.max_retry_attempts || 3;
    document.getElementById('retryDelay').value = config.retry_delay || 5;
    document.getElementById('minFollowPercentage').value = config.min_follow_percentage || 0.5;
    document.getElementById('maxFollowPercentage').value = config.max_follow_percentage || 10.0;
    document.getElementById('maxNetLeverage').value = config.max_net_leverage || 10.0;
    document.getElementById('riskControlEnabled').checked = config.risk_control_enabled !== false;
}

// 保存系统设置
function saveSystemSettings() {
    const formData = new FormData(document.getElementById('settingsForm'));
    const settings = {};
    
    for (let [key, value] of formData.entries()) {
        if (key === 'riskControlEnabled') {
            settings[key] = value === 'on';
        } else {
            settings[key] = parseFloat(value) || value;
        }
    }
    
    fetch('/api/v1/limit-follow/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('设置保存成功', 'success');
        } else {
            showNotification('保存失败: ' + data.message, 'error');
        }
    });
}
```

### 🎨 界面设置

自定义界面显示：

- **主题切换**: 明暗主题切换
- **语言设置**: 多语言支持
- **布局调整**: 自定义界面布局
- **通知设置**: 配置通知方式

## 🔧 技术实现

### 🏗️ 架构设计

前端采用模块化架构：

```
frontend/
├── index.html          # 主页面
├── app.js             # 主应用逻辑
├── styles.css         # 主样式文件
├── limit_follow.html  # 限价单页面
├── components/        # 组件模块
│   ├── customer.js    # 客户管理
│   ├── signal.js      # 信号源监控
│   ├── strategy.js    # 策略管理
│   └── analytics.js   # 数据分析
└── utils/             # 工具函数
    ├── api.js         # API调用
    ├── websocket.js   # WebSocket管理
    └── charts.js      # 图表组件
```

### 📡 数据通信

#### RESTful API

```javascript
// API调用封装
class APIClient {
    constructor(baseURL = '/api/v1') {
        this.baseURL = baseURL;
    }
    
    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const config = {
            headers: { 'Content-Type': 'application/json' },
            ...options
        };
        
        try {
            const response = await fetch(url, config);
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.message || '请求失败');
            }
            
            return data;
        } catch (error) {
            console.error('API请求错误:', error);
            throw error;
        }
    }
    
    async get(endpoint, params = {}) {
        const queryString = new URLSearchParams(params).toString();
        const url = queryString ? `${endpoint}?${queryString}` : endpoint;
        return this.request(url, { method: 'GET' });
    }
    
    async post(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }
    
    async put(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }
    
    async delete(endpoint) {
        return this.request(endpoint, { method: 'DELETE' });
    }
}

// 全局API客户端实例
const api = new APIClient();
```

#### WebSocket实时通信

```javascript
// WebSocket连接管理
class WebSocketManager {
    constructor(url) {
        this.url = url;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.handlers = new Map();
    }
    
    connect() {
        try {
            this.ws = new WebSocket(this.url);
            this.setupEventHandlers();
        } catch (error) {
            console.error('WebSocket连接失败:', error);
            this.scheduleReconnect();
        }
    }
    
    setupEventHandlers() {
        this.ws.onopen = () => {
            console.log('WebSocket连接已建立');
            this.reconnectAttempts = 0;
        };
        
        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            } catch (error) {
                console.error('消息解析失败:', error);
            }
        };
        
        this.ws.onclose = () => {
            console.log('WebSocket连接已关闭');
            this.scheduleReconnect();
        };
        
        this.ws.onerror = (error) => {
            console.error('WebSocket错误:', error);
        };
    }
    
    handleMessage(data) {
        const { type, payload } = data;
        
        if (this.handlers.has(type)) {
            this.handlers.get(type).forEach(handler => {
                try {
                    handler(payload);
                } catch (error) {
                    console.error(`处理消息类型 ${type} 失败:`, error);
                }
            });
        }
    }
    
    on(type, handler) {
        if (!this.handlers.has(type)) {
            this.handlers.set(type, []);
        }
        this.handlers.get(type).push(handler);
    }
    
    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }
    
    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
            
            setTimeout(() => {
                console.log(`尝试重连 (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
                this.connect();
            }, delay);
        } else {
            console.error('达到最大重连次数，停止重连');
        }
    }
    
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}

// 创建WebSocket管理器实例
const wsManager = new WebSocketManager('ws://localhost:5000/ws');
wsManager.connect();
```

### 🎨 UI组件

#### 通知组件

```javascript
// 通知管理器
class NotificationManager {
    constructor() {
        this.container = this.createContainer();
    }
    
    createContainer() {
        const container = document.createElement('div');
        container.id = 'notification-container';
        container.className = 'notification-container';
        document.body.appendChild(container);
        return container;
    }
    
    show(message, type = 'info', duration = 5000) {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <div class="notification-content">
                <span class="notification-message">${message}</span>
                <button class="notification-close" onclick="this.parentElement.parentElement.remove()">×</button>
            </div>
        `;
        
        this.container.appendChild(notification);
        
        // 自动消失
        if (duration > 0) {
            setTimeout(() => {
                if (notification.parentElement) {
                    notification.remove();
                }
            }, duration);
        }
        
        return notification;
    }
    
    success(message, duration) {
        return this.show(message, 'success', duration);
    }
    
    error(message, duration) {
        return this.show(message, 'error', duration);
    }
    
    warning(message, duration) {
        return this.show(message, 'warning', duration);
    }
    
    info(message, duration) {
        return this.show(message, 'info', duration);
    }
}

// 全局通知管理器
const notifications = new NotificationManager();
```

#### 模态框组件

```javascript
// 模态框管理器
class ModalManager {
    constructor() {
        this.activeModals = new Map();
    }
    
    show(modalId, options = {}) {
        const modalElement = document.getElementById(modalId);
        if (!modalElement) {
            console.error(`模态框 ${modalId} 不存在`);
            return null;
        }
        
        const modal = new bootstrap.Modal(modalElement, options);
        modal.show();
        
        this.activeModals.set(modalId, modal);
        return modal;
    }
    
    hide(modalId) {
        const modal = this.activeModals.get(modalId);
        if (modal) {
            modal.hide();
            this.activeModals.delete(modalId);
        }
    }
    
    hideAll() {
        this.activeModals.forEach(modal => modal.hide());
        this.activeModals.clear();
    }
}

// 全局模态框管理器
const modals = new ModalManager();
```

## 🎨 界面定制

### 🎨 主题定制

系统支持自定义主题：

```css
/* 自定义主题变量 */
:root {
    --primary-color: #007bff;
    --secondary-color: #6c757d;
    --success-color: #28a745;
    --warning-color: #ffc107;
    --danger-color: #dc3545;
    --info-color: #17a2b8;
    --light-color: #f8f9fa;
    --dark-color: #343a40;
}

/* 深色主题 */
[data-theme="dark"] {
    --bg-primary: #1a1a1a;
    --bg-secondary: #2d2d2d;
    --text-primary: #ffffff;
    --text-secondary: #cccccc;
    --border-color: #404040;
}
```

### 📱 响应式设计

```css
/* 移动端适配 */
@media (max-width: 768px) {
    .sidebar {
        position: fixed;
        left: -100%;
        transition: left 0.3s ease;
    }
    
    .sidebar.show {
        left: 0;
    }
    
    .main-content {
        margin-left: 0;
    }
    
    .table-responsive {
        font-size: 0.875rem;
    }
    
    .btn {
        padding: 0.375rem 0.75rem;
        font-size: 0.875rem;
    }
}

/* 平板端适配 */
@media (min-width: 769px) and (max-width: 1024px) {
    .col-xl-3 {
        flex: 0 0 50%;
        max-width: 50%;
    }
}
```

## 🐛 常见问题

### ❓ 常见问题解答

#### 1. 页面无法加载

**问题**: 访问前端页面时显示空白或错误

**解决方案**:
1. 检查后端服务是否启动
2. 确认API接口是否正常
3. 查看浏览器控制台错误信息
4. 检查网络连接

#### 2. WebSocket连接失败

**问题**: 实时数据无法更新

**解决方案**:
1. 检查WebSocket服务是否启动
2. 确认防火墙设置
3. 检查网络代理配置
4. 查看后端日志

#### 3. 图表显示异常

**问题**: 数据图表无法正常显示

**解决方案**:
1. 检查Chart.js库是否正确加载
2. 确认数据格式是否正确
3. 检查浏览器兼容性
4. 清除浏览器缓存

#### 4. 表单提交失败

**问题**: 无法保存配置或创建记录

**解决方案**:
1. 检查必填字段是否完整
2. 确认数据格式是否正确
3. 查看API响应错误信息
4. 检查后端服务状态

### 🔧 调试技巧

#### 浏览器开发者工具

```javascript
// 开启调试模式
localStorage.setItem('debug', 'true');

// 查看API请求
console.log('API请求:', endpoint, data);

// 查看WebSocket消息
wsManager.on('*', (type, payload) => {
    console.log('WebSocket消息:', type, payload);
});
```

#### 日志记录

```javascript
// 自定义日志记录
class Logger {
    static log(level, message, data = null) {
        const timestamp = new Date().toISOString();
        const logEntry = { timestamp, level, message, data };
        
        console.log(`[${timestamp}] ${level.toUpperCase()}: ${message}`, data);
        
        // 保存到本地存储
        this.saveToStorage(logEntry);
    }
    
    static info(message, data) {
        this.log('info', message, data);
    }
    
    static warn(message, data) {
        this.log('warn', message, data);
    }
    
    static error(message, data) {
        this.log('error', message, data);
    }
    
    static saveToStorage(logEntry) {
        const logs = JSON.parse(localStorage.getItem('app_logs') || '[]');
        logs.push(logEntry);
        
        // 只保留最近100条日志
        if (logs.length > 100) {
            logs.splice(0, logs.length - 100);
        }
        
        localStorage.setItem('app_logs', JSON.stringify(logs));
    }
}
```

---

**📖 [返回主文档 →](../README.md)**

**🔧 [查看API文档 →](API_DOCS.md)** 