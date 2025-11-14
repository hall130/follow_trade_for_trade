# 部署方案推荐

## 方案对比

### 方案 1：Gunicorn + systemd（推荐 ⭐⭐⭐⭐⭐）

**优点：**
- ✅ 生产级 WSGI 服务器，性能好、稳定性高
- ✅ 多进程处理，支持高并发
- ✅ systemd 自动重启，进程崩溃自动恢复
- ✅ 更好的错误处理和日志管理

**适用场景：**
- 生产环境
- 需要高并发处理
- 需要长期稳定运行

**部署步骤：**
```bash
# 1. 安装 Gunicorn
pip install gunicorn gevent

# 2. 复制 systemd 服务文件
sudo cp systemd/follow-trade-api.service /etc/systemd/system/

# 3. 创建日志目录
sudo mkdir -p /var/log/follow-trade

# 4. 重载 systemd
sudo systemctl daemon-reload

# 5. 启动服务
sudo systemctl start follow-trade-api

# 6. 设置开机自启
sudo systemctl enable follow-trade-api

# 7. 查看状态
sudo systemctl status follow-trade-api
```

### 方案 2：直接使用 systemd（简单方案 ⭐⭐⭐）

**优点：**
- ✅ 简单，无需额外配置
- ✅ systemd 自动重启
- ✅ 适合小规模应用

**缺点：**
- ⚠️ 使用 Flask 开发服务器，性能有限
- ⚠️ 单线程处理，高并发可能崩溃
- ⚠️ 不适合生产环境

**适用场景：**
- 开发/测试环境
- 低并发场景
- 快速部署

**部署步骤：**
```bash
# 1. 复制 systemd 服务文件（使用 all 模式）
sudo cp systemd/follow-trade-all.service /etc/systemd/system/

# 2. 修改 ExecStart 为直接运行 Python
# ExecStart=/root/follow_trade_for_trade/venv/bin/python /root/follow_trade_for_trade/main.py api

# 3. 重载并启动
sudo systemctl daemon-reload
sudo systemctl start follow-trade-all
sudo systemctl enable follow-trade-all
```

## 推荐方案

### 🏆 最佳实践：Gunicorn + systemd

**为什么推荐：**

1. **性能优势**
   - Gunicorn 多进程处理，可以充分利用多核 CPU
   - 支持异步 worker（gevent），处理 I/O 密集型请求更高效
   - 比 Flask 开发服务器性能提升 10-100 倍

2. **稳定性优势**
   - Gunicorn 有完善的错误处理机制
   - 自动重启 worker 进程，防止内存泄漏
   - systemd 监控主进程，确保服务始终运行

3. **生产就绪**
   - 这是业界标准的生产环境部署方案
   - 支持优雅重启、日志轮转等高级功能
   - 易于监控和运维

### 配置说明

**Gunicorn 配置（gunicorn_config.py）：**
- `workers = CPU核心数 * 2 + 1`：自动计算最优 worker 数量
- `worker_class = "gevent"`：使用异步 worker，提高并发能力
- `max_requests = 1000`：每个 worker 处理 1000 个请求后重启，防止内存泄漏
- `timeout = 120`：请求超时时间

**systemd 配置（follow-trade-api.service）：**
- `Restart=always`：进程退出后自动重启
- `RestartSec=10`：重启前等待 10 秒
- `Type=notify`：Gunicorn 支持 systemd 通知

## 监控和维护

### 查看服务状态
```bash
sudo systemctl status follow-trade-api
```

### 查看日志
```bash
# systemd 日志
sudo journalctl -u follow-trade-api -f

# Gunicorn 日志
tail -f /var/log/follow-trade/gunicorn_error.log
tail -f /var/log/follow-trade/gunicorn_access.log
```

### 重启服务
```bash
sudo systemctl restart follow-trade-api
```

### 优雅重启（不中断请求）
```bash
sudo systemctl reload follow-trade-api
```

## 总结

**推荐使用：Gunicorn + systemd**

这是生产环境的标准配置，既保证了性能，又确保了稳定性。即使 Flask 应用出现错误，Gunicorn 和 systemd 的双重保护机制也能确保服务快速恢复。

