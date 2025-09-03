# 📊 API接口文档

> 跟单交易系统的完整API接口文档

## 📋 快速导航

- [🏠 返回主文档](../README.md)
- [🎨 查看前端文档](FRONTEND.md)

## 🔗 API文档位置

详细的API接口文档请参考主README文档中的 [📊 API接口](../README.md#-api接口) 部分。

### 核心接口概览

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/v1/customers` | GET/POST | 客户管理 |
| `/api/v1/signal-sources` | GET/POST | 信号源管理 |
| `/api/v1/limit-follow/strategies` | GET/POST | 限价单策略 |
| `/api/v1/limit-follow/orders` | GET | 限价单订单 |
| `/api/v1/limit-follow/status` | GET | 系统状态 |

### 限价单专用接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/v1/limit-follow/risk/assessment` | POST | 风险评估 |
| `/api/v1/limit-follow/analytics/performance` | GET | 性能分析 |
| `/api/v1/limit-follow/batch/update-strategies` | POST | 批量更新策略 |

---

**📖 [返回主文档 →](../README.md)**

**🎨 [查看前端文档 →](FRONTEND.md)** 