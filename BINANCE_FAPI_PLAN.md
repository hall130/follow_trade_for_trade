# 计划：Binance USDT-M 合约(fapi)跟单 + 动态合约规格 + 对账动态缩短

## 目标（用户确认）
1. Binance 以 **USDT-M 永续合约(fapi)** 跟单，与 OKX 并存；做到"本地量与交易所量一致"。
2. **动态合约规格**：启动时从交易所拉 minSz/lotSz/ctVal/tickSz 覆盖静态表，修掉未知品种回退错误。
3. **对账动态缩短**：把 30 分钟固定周期改为可配置、更短，并在成交后主动触发。

## 关键约束（调研已确认）
- 所有 `contract_config` 调用点传的都是 OKX 格式 `XXX-USDT-SWAP`；Binance 数据已被 `binance_collector.py` 归一化成该格式。→ 动态规格表必须用 **OKX 格式符号做 key**。
- Binance U 本位下单量就是**币数量**，等效 multiplier=1.0（OKX 是张×ctVal）。
- `WebSocketClientManager.get_client` 在 [unified_ws_client.py:490] **硬编码 `exchange='okx'`**，客户 WS 路径当前永远建 OKX。
- Binance 现有 REST/WS 都是**现货**：`api/v3`、`stream.binance.com`、`get_positions` 读现货余额、无 `connect()`、listenKey 管理未实现、有一段悬空 stub。
- 下单深度耦合 OKX：参数(`tdMode/posSide/tag`)、返回解析(`data[0].ordId`、`sCode 51016`)。
- 对账循环 `periodic_position_check` 目前**被注释掉**（trade_server.py:515），根本没跑。
- 无全局设置表；配置走 `config/*.py` getter 函数。
- 归一化 `symbol[:-4]` 假设 4 位报价，`1000PEPE` 等会错位（本计划会处理映射）。

---

## 阶段 1：动态合约规格（低风险，先做，OKX/Binance 都受益）

新增 `config/contract_spec_manager.py`：
- 内存缓存 `_DYNAMIC_SPECS: dict[str, {min_sz, sz_precision, multiplier, tick_sz, source_exchange}]`，key 为 OKX 格式符号。
- `async refresh_from_okx(rest_client)`：调 `get_instruments_legacy("SWAP")` + `"SWAP"`(inverse 由 instId 后缀区分)，解析原始 `minSz/lotSz/ctVal/tickSz`（`get_instruments` 现有 dataclass 丢了 ctVal/lotSz，故用 `*_legacy` 拿原始字段）。precision 由 lotSz 推导。
- `async refresh_from_binance(fapi_rest_client)`：调 fapi `exchangeInfo`，把 `BTCUSDT→BTC-USDT-SWAP`（含 `1000XXX`/`USDC` 特例映射表），`LOT_SIZE.stepSize→min_sz`、由 stepSize 推 precision、`PRICE_FILTER.tickSize→tick_sz`、**multiplier=1.0**。
- 启动时在 `trade_server.main()` 调用一次刷新（OKX 用任一公共客户端；Binance 用 fapi 公共客户端）。失败则保留静态表兜底 + 告警日志。

改 `config/contract_config.py` 的 8 个 getter：**先查动态缓存，未命中再查静态表**（保持函数签名不变，40+ 调用点零改动）。未知品种：若能拉到就用真实值，仍未知则保留现有默认但打 `WARNING`（不再静默）。

顺带记录（不在本阶段擅自改，列为待确认）：
- 预存 bug：`limit_follow_executor.py:1061` 导入不存在的 `get_min_order_size/get_size_precision`；`trade_service.py:6619` 读错 key `min_size`；`api_server.py:7532` `round(x, min_sz)` 用 float 当 ndigits。
- `get_contract_value_in_usdt` 在净杠杆场景(7695/7727/7896/7929)未乘价、语义脆弱，Binance multiplier=1 会低估。

## 阶段 2：对账动态缩短 + 成交后触发

- `config/config.py`（或新增小配置）增 `RECONCILE_INTERVAL_SECONDS`（默认 300，可调）与 `RECONCILE_ON_FILL=True`。
- 取消 [trade_server.py:515] 注释，重新启用 `periodic_position_check`，`sleep(1800)` → 读配置（默认 300）。
- `check_position_anomalies` 增加可选参数 `only_customer_uid/only_symbol`，支持定向对账（复用现有全量逻辑）。
- 在 `_handle_customer_order_update` 末尾（trade_service.py:2998 前）成交处理完后，若 `RECONCILE_ON_FILL`，用 `asyncio.create_task` 延迟(如 3s)对该 customer+symbol 做一次定向对账，带去重/节流（避免连续成交刷屏）。
- 顺带：把 `_processed_close_orders/_updated_trades/_pending_total_close` 移入 `__init__` 并加容量上界（防无限增长）。

## 阶段 3：Binance fapi REST 客户端

- `config/binance_config.py` 增 fapi URL：live `https://fapi.binance.com`、testnet `https://testnet.binancefuture.com`；WS live `wss://fstream.binance.com`、testnet `wss://stream.binancefuture.com`。
- 新增 `exchange/binance/binance_fapi_rest_client.py`(或给现有 client 加 `market_type='futures'` 分支)，实现 BaseRESTClient：
  - `place_order`：`POST /fapi/v1/order`，映射 side(BUY/SELL)、type(MARKET/LIMIT)、quantity、`newClientOrderId←clOrdId`、`positionSide←posSide`(LONG/SHORT/BOTH)、`reduceOnly`。
  - `cancel_order`：`DELETE /fapi/v1/order`。
  - `get_order`：`GET /fapi/v1/order`，映射 `executedQty→filled`、status。
  - `get_positions`：`GET /fapi/v2/positionRisk`，映射 `positionAmt→size`、`entryPrice`、posSide。**返回结构对齐 OKX 消费格式**（`check_position_anomalies` 读 `positions['positions']` 里的 `instId/posSide/pos`）。
  - `get_instruments`：`GET /fapi/v1/exchangeInfo` 供阶段 1 使用。
  - `create_listen_key/extend_listen_key`：`POST/PUT /fapi/v1/listenKey`（WS 用户流依赖）。
  - 签名：HMAC-SHA256 query，`X-MBX-APIKEY` 头。

## 阶段 4：Binance fapi WS 客户端 + 成交回报翻译

- 新增 `exchange/binance/binance_fapi_ws_client.py`，实现 BaseWebSocketClient：
  - 真正的 `connect()`：走状态机(对齐 OKX 生命周期)，用 REST `create_listen_key` 建单一用户流 `wss://fstream/ws/<listenKey>`，定时 keepalive。
  - `subscribe(channel, callback, **kwargs)`：接受与 OKX 相同的 `"account"`/`"orders"`(带 `instType="SWAP"`)频道名；因 Binance 只有单条用户流，把两个回调都挂到 `ORDER_TRADE_UPDATE`/`ACCOUNT_UPDATE`。
  - **回报翻译**：把 Binance `ORDER_TRADE_UPDATE.o{i,c,X,z,l,ap,S,ps,s,R}` 翻译成 OKX 形状 dict(`ordId,clOrdId,state,accFillSz,fillSz,fillPx,avgPx,reduceOnly,posSide,instId,side`)，symbol 转回 OKX 格式，再喂给共享的 `_handle_customer_order_update`。→ 复用现有回补逻辑，量一致自动成立。

## 阶段 5：按交易所路由（打通端到端）

- 修 [unified_ws_client.py:490] 硬编码：`get_client` 透传 `exchange`（来自 customer）。
- 下单参数与返回解析按交易所分流：
  - 方案：在 **UnifiedRESTClient.place_order** 里为 Binance 也产出 OKX 形状返回(`{"code":"0","data":[{"ordId","clOrdId"}]}`)，让 trade_service 现有解析(1553)零改动；OKX 专属参数(tag/tdMode)对 Binance 忽略。
  - `sCode 51016`(clOrdId 冲突)等 OKX 错误码，给 Binance 映射等价判断或跳过。
- **符号翻译**在 client 边界完成：进 client 时 OKX 格式→Binance 原生(`BTC-USDT-SWAP→BTCUSDT`)，出 client 时翻回。集中在 fapi client 内部，trade_service 全程只见 OKX 格式。
- 持仓模式：确保 Binance 账户为**双向持仓(Hedge)**以匹配 posSide 语义（下单前检测/设置 `POST /fapi/v1/positionSide/dual`，或文档提示用户预先设置）。

## 阶段 6：验证（用户确认：mock 单测为主，暂不跑 testnet）

- `py_compile` 全部改动文件。
- 单测(mock)：
  - 动态规格：OKX 拉取覆盖静态、Binance `1000PEPE`/`USDC` 映射、未知品种告警。
  - 回报翻译：Binance 部分成交 `ORDER_TRADE_UPDATE`→OKX dict→`_handle_customer_order_update` 正确回补 `volume_contract`。
  - 下单：mock fapi client，验证 UnifiedRESTClient 为 Binance 也产出 OKX 形状返回、trade_service 解析(1553)零改动通过。
  - 符号翻译：`BTC-USDT-SWAP↔BTCUSDT` 双向、`1000PEPE`/`USDC` 特例。
  - 对账：定向对账只查目标 customer+symbol；成交后触发节流生效。
- testnet 冒烟由用户后续自行验证；本轮说明哪些逻辑只能静态/mock 验证、哪些需真实 testnet 才能确认（下单撮合、listenKey 用户流、双向持仓设置）。

---

## 风险与取舍
- 工作量集中在阶段 3–5（新建两套 fapi 客户端 + 路由）。阶段 1、2 独立可用、可先落地验证。
- Binance 需账户开启双向持仓，否则 posSide 语义不符。
- 净杠杆 `get_contract_value_in_usdt` 语义问题是既有隐患，本计划仅标注、不擅自改动（改动会影响 OKX 现有杠杆判断，需单独确认）。
- 现货 spot 那套 Binance 客户端保持不动，避免影响其他模块。
