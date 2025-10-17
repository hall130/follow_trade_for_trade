# 合约配置文件
# 包含合约张数精度和最小合约张数的配置
# 供signal_service和trade_service共同使用

# 合约张数精度（OKX官方同步）
CONTRACT_SZ_PRECISION = {
    '1INCH-USDT-SWAP': 0,      # 0位小数
    'A-USDT-SWAP': 0,      # 0位小数
    'AAVE-USDT-SWAP': 1,      # 1位小数
    'ACE-USDT-SWAP': 0,      # 0位小数
    'ACH-USDT-SWAP': 0,      # 0位小数
    'ACT-USDT-SWAP': 0,      # 0位小数
    'ADA-USDT-SWAP': 1,      # 1位小数
    'AERO-USDT-SWAP': 0,      # 0位小数
    'AEVO-USDT-SWAP': 0,      # 0位小数
    'AGLD-USDT-SWAP': 0,      # 0位小数
    'AI16Z-USDT-SWAP': 0,      # 0位小数
    'AIDOGE-USDT-SWAP': 0,      # 0位小数
    'AIXBT-USDT-SWAP': 0,      # 0位小数
    'ALCH-USDT-SWAP': 0,      # 0位小数
    'ALGO-USDT-SWAP': 0,      # 0位小数
    'ANIME-USDT-SWAP': 0,      # 0位小数
    'APE-USDT-SWAP': 0,      # 0位小数
    'API3-USDT-SWAP': 0,      # 0位小数
    'APT-USDT-SWAP': 0,      # 0位小数
    'AR-USDT-SWAP': 0,      # 0位小数
    'ARB-USDT-SWAP': 1,      # 1位小数
    'ARC-USDT-SWAP': 0,      # 0位小数
    'ARKM-USDT-SWAP': 0,      # 0位小数
    'ATH-USDT-SWAP': 0,      # 0位小数
    'ATOM-USDT-SWAP': 0,      # 0位小数
    'AUCTION-USDT-SWAP': 0,      # 0位小数
    'AVAAI-USDT-SWAP': 0,      # 0位小数
    'AVAX-USDT-SWAP': 1,      # 1位小数
    'AXS-USDT-SWAP': 0,      # 0位小数
    'BABY-USDT-SWAP': 0,      # 0位小数
    'BAND-USDT-SWAP': 0,      # 0位小数
    'BAT-USDT-SWAP': 0,      # 0位小数
    'BCH-USDT-SWAP': 1,      # 1位小数
    'BERA-USDT-SWAP': 0,      # 0位小数
    'BICO-USDT-SWAP': 0,      # 0位小数
    'BIGTIME-USDT-SWAP': 0,      # 0位小数
    'BIO-USDT-SWAP': 0,      # 0位小数
    'BLUR-USDT-SWAP': 0,      # 0位小数
    'BNB-USDT-SWAP': 0,      # 0位小数
    'BNT-USDT-SWAP': 0,      # 0位小数
    'BOME-USDT-SWAP': 0,      # 0位小数
    'BONK-USDT-SWAP': 0,      # 0位小数
    'BRETT-USDT-SWAP': 0,      # 0位小数
    'BTC-USDT-SWAP': 2,      # 2位小数
    'CAT-USDT-SWAP': 0,      # 0位小数
    'CATI-USDT-SWAP': 0,      # 0位小数
    'CELO-USDT-SWAP': 0,      # 0位小数
    'CETUS-USDT-SWAP': 0,      # 0位小数
    'CFX-USDT-SWAP': 0,      # 0位小数
    'CHZ-USDT-SWAP': 0,      # 0位小数
    'COMP-USDT-SWAP': 0,      # 0位小数
    'COOKIE-USDT-SWAP': 0,      # 0位小数
    'CORE-USDT-SWAP': 0,      # 0位小数
    'CRO-USDT-SWAP': 0,      # 0位小数
    'CRV-USDT-SWAP': 0,      # 0位小数
    'CSPR-USDT-SWAP': 0,      # 0位小数
    'CTC-USDT-SWAP': 0,      # 0位小数
    'CVC-USDT-SWAP': 0,      # 0位小数
    'CVX-USDT-SWAP': 0,      # 0位小数
    'DEGEN-USDT-SWAP': 0,      # 0位小数
    'DGB-USDT-SWAP': 0,      # 0位小数
    'DOG-USDT-SWAP': 0,      # 0位小数
    'DOGE-USDT-SWAP': 2,      # 2位小数
    'DOGS-USDT-SWAP': 0,      # 0位小数
    'DOOD-USDT-SWAP': 0,      # 0位小数
    'DOT-USDT-SWAP': 0,      # 0位小数
    'DUCK-USDT-SWAP': 0,      # 0位小数
    'DYDX-USDT-SWAP': 0,      # 0位小数
    'EGLD-USDT-SWAP': 0,      # 0位小数
    'EIGEN-USDT-SWAP': 0,      # 0位小数
    'ENJ-USDT-SWAP': 0,      # 0位小数
    'ENS-USDT-SWAP': 0,      # 0位小数
    'ETC-USDT-SWAP': 2,      # 2位小数
    'ETH-USDT-SWAP': 2,      # 2位小数
    'ETHFI-USDT-SWAP': 0,      # 0位小数
    'ETHW-USDT-SWAP': 0,      # 0位小数
    'FARTCOIN-USDT-SWAP': 0,      # 0位小数
    'FIL-USDT-SWAP': 0,      # 0位小数
    'FLM-USDT-SWAP': 0,      # 0位小数
    'FLOKI-USDT-SWAP': 0,      # 0位小数
    'FLOW-USDT-SWAP': 0,      # 0位小数
    'FXS-USDT-SWAP': 0,      # 0位小数
    'GALA-USDT-SWAP': 0,      # 0位小数
    'GAS-USDT-SWAP': 0,      # 0位小数
    'GLM-USDT-SWAP': 0,      # 0位小数
    'GMT-USDT-SWAP': 0,      # 0位小数
    'GMX-USDT-SWAP': 0,      # 0位小数
    'GOAT-USDT-SWAP': 0,      # 0位小数
    'GODS-USDT-SWAP': 0,      # 0位小数
    'GPS-USDT-SWAP': 0,      # 0位小数
    'GRASS-USDT-SWAP': 0,      # 0位小数
    'GRIFFAIN-USDT-SWAP': 0,      # 0位小数
    'GRT-USDT-SWAP': 0,      # 0位小数
    'H-USDT-SWAP': 0,      # 0位小数
    'HBAR-USDT-SWAP': 1,      # 1位小数
    'HMSTR-USDT-SWAP': 0,      # 0位小数
    'HOME-USDT-SWAP': 0,      # 0位小数
    'HUMA-USDT-SWAP': 0,      # 0位小数
    'HYPE-USDT-SWAP': 0,      # 0位小数
    'ICP-USDT-SWAP': 0,      # 0位小数
    'ICX-USDT-SWAP': 0,      # 0位小数
    'ID-USDT-SWAP': 0,      # 0位小数
    'IMX-USDT-SWAP': 0,      # 0位小数
    'INIT-USDT-SWAP': 0,      # 0位小数
    'INJ-USDT-SWAP': 0,      # 0位小数
    'IOST-USDT-SWAP': 0,      # 0位小数
    'IOTA-USDT-SWAP': 0,      # 0位小数
    'IP-USDT-SWAP': 0,      # 0位小数
    'JELLYJELLY-USDT-SWAP': 0,      # 0位小数
    'JOE-USDT-SWAP': 0,      # 0位小数
    'JST-USDT-SWAP': 0,      # 0位小数
    'JTO-USDT-SWAP': 0,      # 0位小数
    'JUP-USDT-SWAP': 0,      # 0位小数
    'KAITO-USDT-SWAP': 0,      # 0位小数
    'KMNO-USDT-SWAP': 0,      # 0位小数
    'KSM-USDT-SWAP': 0,      # 0位小数
    'LA-USDT-SWAP': 0,      # 0位小数
    'LAUNCHCOIN-USDT-SWAP': 0,      # 0位小数
    'LAYER-USDT-SWAP': 0,      # 0位小数
    'LDO-USDT-SWAP': 0,      # 0位小数
    'LINK-USDT-SWAP': 1,      # 1位小数
    'LPT-USDT-SWAP': 0,      # 0位小数
    'LQTY-USDT-SWAP': 0,      # 0位小数
    'LRC-USDT-SWAP': 0,      # 0位小数
    'LTC-USDT-SWAP': 1,      # 1位小数
    'LUNA-USDT-SWAP': 0,      # 0位小数
    'LUNC-USDT-SWAP': 0,      # 0位小数
    'MAGIC-USDT-SWAP': 0,      # 0位小数
    'MAJOR-USDT-SWAP': 0,      # 0位小数
    'MANA-USDT-SWAP': 0,      # 0位小数
    'MASK-USDT-SWAP': 0,      # 0位小数
    'ME-USDT-SWAP': 0,      # 0位小数
    'MEME-USDT-SWAP': 0,      # 0位小数
    'MERL-USDT-SWAP': 0,      # 0位小数
    'METIS-USDT-SWAP': 0,      # 0位小数
    'MEW-USDT-SWAP': 0,      # 0位小数
    'MINA-USDT-SWAP': 0,      # 0位小数
    'MKR-USDT-SWAP': 1,      # 1位小数
    'MOG-USDT-SWAP': 0,      # 0位小数
    'MOODENG-USDT-SWAP': 0,      # 0位小数
    'MORPHO-USDT-SWAP': 0,      # 0位小数
    'MOVE-USDT-SWAP': 0,      # 0位小数
    'MUBARAK-USDT-SWAP': 0,      # 0位小数
    'NEAR-USDT-SWAP': 1,      # 1位小数
    'NEIRO-USDT-SWAP': 0,      # 0位小数
    'NEIROETH-USDT-SWAP': 0,      # 0位小数
    'NEO-USDT-SWAP': 0,      # 0位小数
    'NEWT-USDT-SWAP': 0,      # 0位小数
    'NMR-USDT-SWAP': 0,      # 0位小数
    'NOT-USDT-SWAP': 0,      # 0位小数
    'NXPC-USDT-SWAP': 0,      # 0位小数
    'OL-USDT-SWAP': 0,      # 0位小数
    'OM-USDT-SWAP': 1,      # 1位小数
    'ONDO-USDT-SWAP': 0,      # 0位小数
    'ONE-USDT-SWAP': 0,      # 0位小数
    'ONT-USDT-SWAP': 0,      # 0位小数
    'OP-USDT-SWAP': 0,      # 0位小数
    'ORBS-USDT-SWAP': 0,      # 0位小数
    'ORDI-USDT-SWAP': 0,      # 0位小数
    'PARTI-USDT-SWAP': 0,      # 0位小数
    'PENGU-USDT-SWAP': 0,      # 0位小数
    'PEOPLE-USDT-SWAP': 0,      # 0位小数
    'PEPE-USDT-SWAP': 1,      # 1位小数
    'PERP-USDT-SWAP': 0,      # 0位小数
    'PI-USDT-SWAP': 0,      # 0位小数
    'PLUME-USDT-SWAP': 0,      # 0位小数
    'PNUT-USDT-SWAP': 0,      # 0位小数
    'POL-USDT-SWAP': 0,      # 0位小数
    'POPCAT-USDT-SWAP': 0,      # 0位小数
    'PRCL-USDT-SWAP': 0,      # 0位小数
    'PROMPT-USDT-SWAP': 0,      # 0位小数
    'PUMP-USDT-SWAP': 0,      # 0位小数
    'PYTH-USDT-SWAP': 0,      # 0位小数
    'QTUM-USDT-SWAP': 0,      # 0位小数
    'RAY-USDT-SWAP': 0,      # 0位小数
    'RDNT-USDT-SWAP': 0,      # 0位小数
    'RENDER-USDT-SWAP': 0,      # 0位小数
    'RESOLV-USDT-SWAP': 0,      # 0位小数
    'RSR-USDT-SWAP': 0,      # 0位小数
    'RVN-USDT-SWAP': 0,      # 0位小数
    'S-USDT-SWAP': 0,      # 0位小数
    'SAHARA-USDT-SWAP': 0,      # 0位小数
    'SAND-USDT-SWAP': 0,      # 0位小数
    'SATS-USDT-SWAP': 0,      # 0位小数
    'SCR-USDT-SWAP': 0,      # 0位小数
    'SHELL-USDT-SWAP': 0,      # 0位小数
    'SHIB-USDT-SWAP': 1,      # 1位小数
    'SIGN-USDT-SWAP': 0,      # 0位小数
    'SLP-USDT-SWAP': 0,      # 0位小数
    'SNX-USDT-SWAP': 0,      # 0位小数
    'SOL-USDT-SWAP': 2,      # 2位小数
    'SOLV-USDT-SWAP': 0,      # 0位小数
    'SONIC-USDT-SWAP': 0,      # 0位小数
    'SOON-USDT-SWAP': 0,      # 0位小数
    'SOPH-USDT-SWAP': 0,      # 0位小数
    'SPK-USDT-SWAP': 0,      # 0位小数
    'SPX-USDT-SWAP': 0,      # 0位小数
    'SSV-USDT-SWAP': 0,      # 0位小数
    'STORJ-USDT-SWAP': 0,      # 0位小数
    'STRK-USDT-SWAP': 0,      # 0位小数
    'STX-USDT-SWAP': 1,      # 1位小数
    'SUI-USDT-SWAP': 0,      # 0位小数
    'SUSHI-USDT-SWAP': 0,      # 0位小数
    'SWARMS-USDT-SWAP': 0,      # 0位小数
    'SYRUP-USDT-SWAP': 0,      # 0位小数
    'T-USDT-SWAP': 0,      # 0位小数
    'TAO-USDT-SWAP': 0,      # 0位小数
    'THETA-USDT-SWAP': 1,      # 1位小数
    'TIA-USDT-SWAP': 0,      # 0位小数
    'TNSR-USDT-SWAP': 0,      # 0位小数
    'TON-USDT-SWAP': 0,      # 0位小数
    'TRB-USDT-SWAP': 0,      # 0位小数
    'TREE-USDT-SWAP': 0,      # 0位小数
    'TRUMP-USDT-SWAP': 0,      # 0位小数
    'TRX-USDT-SWAP': 2,      # 2位小数
    'TURBO-USDT-SWAP': 1,      # 1位小数
    'UMA-USDT-SWAP': 0,      # 0位小数
    'UNI-USDT-SWAP': 0,      # 0位小数
    'USDC-USDT-SWAP': 0,      # 0位小数
    'USELESS-USDT-SWAP': 0,      # 0位小数
    'USTC-USDT-SWAP': 0,      # 0位小数
    'UXLINK-USDT-SWAP': 0,      # 0位小数
    'VANA-USDT-SWAP': 0,      # 0位小数
    'VINE-USDT-SWAP': 0,      # 0位小数
    'VIRTUAL-USDT-SWAP': 0,      # 0位小数
    'W-USDT-SWAP': 0,      # 0位小数
    'WAL-USDT-SWAP': 0,      # 0位小数
    'WAXP-USDT-SWAP': 0,      # 0位小数
    'WCT-USDT-SWAP': 0,      # 0位小数
    'WIF-USDT-SWAP': 0,      # 0位小数
    'WLD-USDT-SWAP': 0,      # 0位小数
    'WOO-USDT-SWAP': 0,      # 0位小数
    'XAUT-USDT-SWAP': 0,      # 0位小数
    'XCH-USDT-SWAP': 0,      # 0位小数
    'XLM-USDT-SWAP': 1,      # 1位小数
    'XRP-USDT-SWAP': 2,      # 2位小数
    'XTZ-USDT-SWAP': 0,      # 0位小数
    'YFI-USDT-SWAP': 0,      # 0位小数
    'YGG-USDT-SWAP': 0,      # 0位小数
    'ZENT-USDT-SWAP': 0,      # 0位小数
    'ZEREBRO-USDT-SWAP': 0,      # 0位小数
    'ZETA-USDT-SWAP': 0,      # 0位小数
    'ZIL-USDT-SWAP': 0,      # 0位小数
    'ZK-USDT-SWAP': 0,      # 0位小数
    'ZRO-USDT-SWAP': 0,      # 0位小数
    'ZRX-USDT-SWAP': 0,      # 0位小数
}

# 合约最小下单张数（OKX官方同步）
CONTRACT_MIN_SZ = {
    '1INCH-USDT-SWAP': 1.0,      # 最小1.0张
    'A-USDT-SWAP': 1.0,      # 最小1.0张
    'AAVE-USDT-SWAP': 0.1,      # 最小0.1张
    'ACE-USDT-SWAP': 1.0,      # 最小1.0张
    'ACH-USDT-SWAP': 1.0,      # 最小1.0张
    'ACT-USDT-SWAP': 1.0,      # 最小1.0张
    'ADA-USDT-SWAP': 0.1,      # 最小0.1张
    'AERO-USDT-SWAP': 1.0,      # 最小1.0张
    'AEVO-USDT-SWAP': 1.0,      # 最小1.0张
    'AGLD-USDT-SWAP': 1.0,      # 最小1.0张
    'AI16Z-USDT-SWAP': 1.0,      # 最小1.0张
    'AIDOGE-USDT-SWAP': 1.0,      # 最小1.0张
    'AIXBT-USDT-SWAP': 1.0,      # 最小1.0张
    'ALCH-USDT-SWAP': 1.0,      # 最小1.0张
    'ALGO-USDT-SWAP': 1.0,      # 最小1.0张
    'ANIME-USDT-SWAP': 1.0,      # 最小1.0张
    'APE-USDT-SWAP': 1.0,      # 最小1.0张
    'API3-USDT-SWAP': 1.0,      # 最小1.0张
    'APT-USDT-SWAP': 1.0,      # 最小1.0张
    'AR-USDT-SWAP': 1.0,      # 最小1.0张
    'ARB-USDT-SWAP': 0.1,      # 最小0.1张
    'ARC-USDT-SWAP': 1.0,      # 最小1.0张
    'ARKM-USDT-SWAP': 1.0,      # 最小1.0张
    'ATH-USDT-SWAP': 1.0,      # 最小1.0张
    'ATOM-USDT-SWAP': 1.0,      # 最小1.0张
    'AUCTION-USDT-SWAP': 1.0,      # 最小1.0张
    'AVAAI-USDT-SWAP': 1.0,      # 最小1.0张
    'AVAX-USDT-SWAP': 0.1,      # 最小0.1张
    'AXS-USDT-SWAP': 1.0,      # 最小1.0张
    'BABY-USDT-SWAP': 1.0,      # 最小1.0张
    'BAND-USDT-SWAP': 1.0,      # 最小1.0张
    'BAT-USDT-SWAP': 1.0,      # 最小1.0张
    'BCH-USDT-SWAP': 0.1,      # 最小0.1张
    'BERA-USDT-SWAP': 1.0,      # 最小1.0张
    'BICO-USDT-SWAP': 1.0,      # 最小1.0张
    'BIGTIME-USDT-SWAP': 1.0,      # 最小1.0张
    'BIO-USDT-SWAP': 1.0,      # 最小1.0张
    'BLUR-USDT-SWAP': 1.0,      # 最小1.0张
    'BNB-USDT-SWAP': 1.0,      # 最小1.0张
    'BNT-USDT-SWAP': 1.0,      # 最小1.0张
    'BOME-USDT-SWAP': 1.0,      # 最小1.0张
    'BONK-USDT-SWAP': 1.0,      # 最小1.0张
    'BRETT-USDT-SWAP': 1.0,      # 最小1.0张
    'BTC-USDT-SWAP': 0.01,      # 最小0.01张
    'CAT-USDT-SWAP': 1.0,      # 最小1.0张
    'CATI-USDT-SWAP': 1.0,      # 最小1.0张
    'CELO-USDT-SWAP': 1.0,      # 最小1.0张
    'CETUS-USDT-SWAP': 1.0,      # 最小1.0张
    'CFX-USDT-SWAP': 1.0,      # 最小1.0张
    'CHZ-USDT-SWAP': 1.0,      # 最小1.0张
    'COMP-USDT-SWAP': 1.0,      # 最小1.0张
    'COOKIE-USDT-SWAP': 1.0,      # 最小1.0张
    'CORE-USDT-SWAP': 1.0,      # 最小1.0张
    'CRO-USDT-SWAP': 1.0,      # 最小1.0张
    'CRV-USDT-SWAP': 1.0,      # 最小1.0张
    'CSPR-USDT-SWAP': 1.0,      # 最小1.0张
    'CTC-USDT-SWAP': 1.0,      # 最小1.0张
    'CVC-USDT-SWAP': 1.0,      # 最小1.0张
    'CVX-USDT-SWAP': 1.0,      # 最小1.0张
    'DEGEN-USDT-SWAP': 1.0,      # 最小1.0张
    'DGB-USDT-SWAP': 1.0,      # 最小1.0张
    'DOG-USDT-SWAP': 1.0,      # 最小1.0张
    'DOGE-USDT-SWAP': 0.01,      # 最小0.01张
    'DOGS-USDT-SWAP': 1.0,      # 最小1.0张
    'DOOD-USDT-SWAP': 1.0,      # 最小1.0张
    'DOT-USDT-SWAP': 1.0,      # 最小1.0张
    'DUCK-USDT-SWAP': 1.0,      # 最小1.0张
    'DYDX-USDT-SWAP': 1.0,      # 最小1.0张
    'EGLD-USDT-SWAP': 1.0,      # 最小1.0张
    'EIGEN-USDT-SWAP': 1.0,      # 最小1.0张
    'ENJ-USDT-SWAP': 1.0,      # 最小1.0张
    'ENS-USDT-SWAP': 1.0,      # 最小1.0张
    'ETC-USDT-SWAP': 0.01,      # 最小0.01张
    'ETH-USDT-SWAP': 0.01,      # 最小0.01张
    'ETHFI-USDT-SWAP': 1.0,      # 最小1.0张
    'ETHW-USDT-SWAP': 1.0,      # 最小1.0张
    'FARTCOIN-USDT-SWAP': 1.0,      # 最小1.0张
    'FIL-USDT-SWAP': 1.0,      # 最小1.0张
    'FLM-USDT-SWAP': 1.0,      # 最小1.0张
    'FLOKI-USDT-SWAP': 1.0,      # 最小1.0张
    'FLOW-USDT-SWAP': 1.0,      # 最小1.0张
    'FXS-USDT-SWAP': 1.0,      # 最小1.0张
    'GALA-USDT-SWAP': 1.0,      # 最小1.0张
    'GAS-USDT-SWAP': 1.0,      # 最小1.0张
    'GLM-USDT-SWAP': 1.0,      # 最小1.0张
    'GMT-USDT-SWAP': 1.0,      # 最小1.0张
    'GMX-USDT-SWAP': 1.0,      # 最小1.0张
    'GOAT-USDT-SWAP': 1.0,      # 最小1.0张
    'GODS-USDT-SWAP': 1.0,      # 最小1.0张
    'GPS-USDT-SWAP': 1.0,      # 最小1.0张
    'GRASS-USDT-SWAP': 1.0,      # 最小1.0张
    'GRIFFAIN-USDT-SWAP': 1.0,      # 最小1.0张
    'GRT-USDT-SWAP': 1.0,      # 最小1.0张
    'H-USDT-SWAP': 1.0,      # 最小1.0张
    'HBAR-USDT-SWAP': 0.1,      # 最小0.1张
    'HMSTR-USDT-SWAP': 1.0,      # 最小1.0张
    'HOME-USDT-SWAP': 1.0,      # 最小1.0张
    'HUMA-USDT-SWAP': 1.0,      # 最小1.0张
    'HYPE-USDT-SWAP': 1.0,      # 最小1.0张
    'ICP-USDT-SWAP': 1.0,      # 最小1.0张
    'ICX-USDT-SWAP': 1.0,      # 最小1.0张
    'ID-USDT-SWAP': 1.0,      # 最小1.0张
    'IMX-USDT-SWAP': 1.0,      # 最小1.0张
    'INIT-USDT-SWAP': 1.0,      # 最小1.0张
    'INJ-USDT-SWAP': 1.0,      # 最小1.0张
    'IOST-USDT-SWAP': 1.0,      # 最小1.0张
    'IOTA-USDT-SWAP': 1.0,      # 最小1.0张
    'IP-USDT-SWAP': 1.0,      # 最小1.0张
    'JELLYJELLY-USDT-SWAP': 1.0,      # 最小1.0张
    'JOE-USDT-SWAP': 1.0,      # 最小1.0张
    'JST-USDT-SWAP': 1.0,      # 最小1.0张
    'JTO-USDT-SWAP': 1.0,      # 最小1.0张
    'JUP-USDT-SWAP': 1.0,      # 最小1.0张
    'KAITO-USDT-SWAP': 1.0,      # 最小1.0张
    'KMNO-USDT-SWAP': 1.0,      # 最小1.0张
    'KSM-USDT-SWAP': 1.0,      # 最小1.0张
    'LA-USDT-SWAP': 1.0,      # 最小1.0张
    'LAUNCHCOIN-USDT-SWAP': 1.0,      # 最小1.0张
    'LAYER-USDT-SWAP': 1.0,      # 最小1.0张
    'LDO-USDT-SWAP': 1.0,      # 最小1.0张
    'LINK-USDT-SWAP': 0.1,      # 最小0.1张
    'LPT-USDT-SWAP': 1.0,      # 最小1.0张
    'LQTY-USDT-SWAP': 1.0,      # 最小1.0张
    'LRC-USDT-SWAP': 1.0,      # 最小1.0张
    'LTC-USDT-SWAP': 0.1,      # 最小0.1张
    'LUNA-USDT-SWAP': 1.0,      # 最小1.0张
    'LUNC-USDT-SWAP': 1.0,      # 最小1.0张
    'MAGIC-USDT-SWAP': 1.0,      # 最小1.0张
    'MAJOR-USDT-SWAP': 1.0,      # 最小1.0张
    'MANA-USDT-SWAP': 1.0,      # 最小1.0张
    'MASK-USDT-SWAP': 1.0,      # 最小1.0张
    'ME-USDT-SWAP': 1.0,      # 最小1.0张
    'MEME-USDT-SWAP': 1.0,      # 最小1.0张
    'MERL-USDT-SWAP': 1.0,      # 最小1.0张
    'METIS-USDT-SWAP': 1.0,      # 最小1.0张
    'MEW-USDT-SWAP': 1.0,      # 最小1.0张
    'MINA-USDT-SWAP': 1.0,      # 最小1.0张
    'MKR-USDT-SWAP': 0.1,      # 最小0.1张
    'MOG-USDT-SWAP': 1.0,      # 最小1.0张
    'MOODENG-USDT-SWAP': 1.0,      # 最小1.0张
    'MORPHO-USDT-SWAP': 1.0,      # 最小1.0张
    'MOVE-USDT-SWAP': 1.0,      # 最小1.0张
    'MUBARAK-USDT-SWAP': 1.0,      # 最小1.0张
    'NEAR-USDT-SWAP': 0.1,      # 最小0.1张
    'NEIRO-USDT-SWAP': 1.0,      # 最小1.0张
    'NEIROETH-USDT-SWAP': 1.0,      # 最小1.0张
    'NEO-USDT-SWAP': 1.0,      # 最小1.0张
    'NEWT-USDT-SWAP': 1.0,      # 最小1.0张
    'NMR-USDT-SWAP': 1.0,      # 最小1.0张
    'NOT-USDT-SWAP': 1.0,      # 最小1.0张
    'NXPC-USDT-SWAP': 1.0,      # 最小1.0张
    'OL-USDT-SWAP': 1.0,      # 最小1.0张
    'OM-USDT-SWAP': 0.1,      # 最小0.1张
    'ONDO-USDT-SWAP': 1.0,      # 最小1.0张
    'ONE-USDT-SWAP': 1.0,      # 最小1.0张
    'ONT-USDT-SWAP': 1.0,      # 最小1.0张
    'OP-USDT-SWAP': 1.0,      # 最小1.0张
    'ORBS-USDT-SWAP': 1.0,      # 最小1.0张
    'ORDI-USDT-SWAP': 1.0,      # 最小1.0张
    'PARTI-USDT-SWAP': 1.0,      # 最小1.0张
    'PENGU-USDT-SWAP': 1.0,      # 最小1.0张
    'PEOPLE-USDT-SWAP': 1.0,      # 最小1.0张
    'PEPE-USDT-SWAP': 0.1,      # 最小0.1张
    'PERP-USDT-SWAP': 1.0,      # 最小1.0张
    'PI-USDT-SWAP': 1.0,      # 最小1.0张
    'PLUME-USDT-SWAP': 1.0,      # 最小1.0张
    'PNUT-USDT-SWAP': 1.0,      # 最小1.0张
    'POL-USDT-SWAP': 1.0,      # 最小1.0张
    'POPCAT-USDT-SWAP': 1.0,      # 最小1.0张
    'PRCL-USDT-SWAP': 1.0,      # 最小1.0张
    'PROMPT-USDT-SWAP': 1.0,      # 最小1.0张
    'PUMP-USDT-SWAP': 1.0,      # 最小1.0张
    'PYTH-USDT-SWAP': 1.0,      # 最小1.0张
    'QTUM-USDT-SWAP': 1.0,      # 最小1.0张
    'RAY-USDT-SWAP': 1.0,      # 最小1.0张
    'RDNT-USDT-SWAP': 1.0,      # 最小1.0张
    'RENDER-USDT-SWAP': 1.0,      # 最小1.0张
    'RESOLV-USDT-SWAP': 1.0,      # 最小1.0张
    'RSR-USDT-SWAP': 1.0,      # 最小1.0张
    'RVN-USDT-SWAP': 1.0,      # 最小1.0张
    'S-USDT-SWAP': 1.0,      # 最小1.0张
    'SAHARA-USDT-SWAP': 1.0,      # 最小1.0张
    'SAND-USDT-SWAP': 1.0,      # 最小1.0张
    'SATS-USDT-SWAP': 1.0,      # 最小1.0张
    'SCR-USDT-SWAP': 1.0,      # 最小1.0张
    'SHELL-USDT-SWAP': 1.0,      # 最小1.0张
    'SHIB-USDT-SWAP': 0.1,      # 最小0.1张
    'SIGN-USDT-SWAP': 1.0,      # 最小1.0张
    'SLP-USDT-SWAP': 1.0,      # 最小1.0张
    'SNX-USDT-SWAP': 1.0,      # 最小1.0张
    'SOL-USDT-SWAP': 0.01,      # 最小0.01张
    'SOLV-USDT-SWAP': 1.0,      # 最小1.0张
    'SONIC-USDT-SWAP': 1.0,      # 最小1.0张
    'SOON-USDT-SWAP': 1.0,      # 最小1.0张
    'SOPH-USDT-SWAP': 1.0,      # 最小1.0张
    'SPK-USDT-SWAP': 1.0,      # 最小1.0张
    'SPX-USDT-SWAP': 1.0,      # 最小1.0张
    'SSV-USDT-SWAP': 1.0,      # 最小1.0张
    'STORJ-USDT-SWAP': 1.0,      # 最小1.0张
    'STRK-USDT-SWAP': 1.0,      # 最小1.0张
    'STX-USDT-SWAP': 0.1,      # 最小0.1张
    'SUI-USDT-SWAP': 1.0,      # 最小1.0张
    'SUSHI-USDT-SWAP': 1.0,      # 最小1.0张
    'SWARMS-USDT-SWAP': 1.0,      # 最小1.0张
    'SYRUP-USDT-SWAP': 1.0,      # 最小1.0张
    'T-USDT-SWAP': 1.0,      # 最小1.0张
    'TAO-USDT-SWAP': 1.0,      # 最小1.0张
    'THETA-USDT-SWAP': 0.1,      # 最小0.1张
    'TIA-USDT-SWAP': 1.0,      # 最小1.0张
    'TNSR-USDT-SWAP': 1.0,      # 最小1.0张
    'TON-USDT-SWAP': 1.0,      # 最小1.0张
    'TRB-USDT-SWAP': 1.0,      # 最小1.0张
    'TREE-USDT-SWAP': 1.0,      # 最小1.0张
    'TRUMP-USDT-SWAP': 1.0,      # 最小1.0张
    'TRX-USDT-SWAP': 0.01,      # 最小0.01张
    'TURBO-USDT-SWAP': 0.1,      # 最小0.1张
    'UMA-USDT-SWAP': 1.0,      # 最小1.0张
    'UNI-USDT-SWAP': 1.0,      # 最小1.0张
    'USDC-USDT-SWAP': 1.0,      # 最小1.0张
    'USELESS-USDT-SWAP': 1.0,      # 最小1.0张
    'USTC-USDT-SWAP': 1.0,      # 最小1.0张
    'UXLINK-USDT-SWAP': 1.0,      # 最小1.0张
    'VANA-USDT-SWAP': 1.0,      # 最小1.0张
    'VINE-USDT-SWAP': 1.0,      # 最小1.0张
    'VIRTUAL-USDT-SWAP': 1.0,      # 最小1.0张
    'W-USDT-SWAP': 1.0,      # 最小1.0张
    'WAL-USDT-SWAP': 1.0,      # 最小1.0张
    'WAXP-USDT-SWAP': 1.0,      # 最小1.0张
    'WCT-USDT-SWAP': 1.0,      # 最小1.0张
    'WIF-USDT-SWAP': 1.0,      # 最小1.0张
    'WLD-USDT-SWAP': 1.0,      # 最小1.0张
    'WOO-USDT-SWAP': 1.0,      # 最小1.0张
    'XAUT-USDT-SWAP': 1.0,      # 最小1.0张
    'XCH-USDT-SWAP': 1.0,      # 最小1.0张
    'XLM-USDT-SWAP': 0.1,      # 最小0.1张
    'XRP-USDT-SWAP': 0.01,      # 最小0.01张
    'XTZ-USDT-SWAP': 1.0,      # 最小1.0张
    'YFI-USDT-SWAP': 1.0,      # 最小1.0张
    'YGG-USDT-SWAP': 1.0,      # 最小1.0张
    'ZENT-USDT-SWAP': 1.0,      # 最小1.0张
    'ZEREBRO-USDT-SWAP': 1.0,      # 最小1.0张
    'ZETA-USDT-SWAP': 1.0,      # 最小1.0张
    'ZIL-USDT-SWAP': 1.0,      # 最小1.0张
    'ZK-USDT-SWAP': 1.0,      # 最小1.0张
    'ZRO-USDT-SWAP': 1.0,      # 最小1.0张
    'ZRX-USDT-SWAP': 1.0,      # 最小1.0张
}

# 合约乘数（张数->币数量），OKX U本位永续合约
CONTRACT_MULTIPLIERS = {
    '1INCH-USDT-SWAP': 1.0,      # 1张=1.0 1INCH
    'A-USDT-SWAP': 10.0,      # 1张=10.0 A
    'AAVE-USDT-SWAP': 0.1,      # 1张=0.1 AAVE
    'ACE-USDT-SWAP': 1.0,      # 1张=1.0 ACE
    'ACH-USDT-SWAP': 100.0,      # 1张=100.0 ACH
    'ACT-USDT-SWAP': 1.0,      # 1张=1.0 ACT
    'ADA-USDT-SWAP': 100.0,      # 1张=100.0 ADA
    'AERO-USDT-SWAP': 10.0,      # 1张=10.0 AERO
    'AEVO-USDT-SWAP': 1.0,      # 1张=1.0 AEVO
    'AGLD-USDT-SWAP': 1.0,      # 1张=1.0 AGLD
    'AI16Z-USDT-SWAP': 1.0,      # 1张=1.0 AI16Z
    'AIDOGE-USDT-SWAP': 10000000000.0,      # 1张=10000000000.0 AIDOGE
    'AIXBT-USDT-SWAP': 10.0,      # 1张=10.0 AIXBT
    'ALCH-USDT-SWAP': 10.0,      # 1张=10.0 ALCH
    'ALGO-USDT-SWAP': 10.0,      # 1张=10.0 ALGO
    'ANIME-USDT-SWAP': 10.0,      # 1张=10.0 ANIME
    'APE-USDT-SWAP': 0.1,      # 1张=0.1 APE
    'API3-USDT-SWAP': 1.0,      # 1张=1.0 API3
    'APT-USDT-SWAP': 1.0,      # 1张=1.0 APT
    'AR-USDT-SWAP': 0.1,      # 1张=0.1 AR
    'ARB-USDT-SWAP': 10.0,      # 1张=10.0 ARB
    'ARC-USDT-SWAP': 10.0,      # 1张=10.0 ARC
    'ARKM-USDT-SWAP': 1.0,      # 1张=1.0 ARKM
    'ATH-USDT-SWAP': 100.0,      # 1张=100.0 ATH
    'ATOM-USDT-SWAP': 1.0,      # 1张=1.0 ATOM
    'AUCTION-USDT-SWAP': 0.1,      # 1张=0.1 AUCTION
    'AVAAI-USDT-SWAP': 10.0,      # 1张=10.0 AVAAI
    'AVAX-USDT-SWAP': 1.0,      # 1张=1.0 AVAX
    'AXS-USDT-SWAP': 0.1,      # 1张=0.1 AXS
    'BABY-USDT-SWAP': 10.0,      # 1张=10.0 BABY
    'BAND-USDT-SWAP': 1.0,      # 1张=1.0 BAND
    'BAT-USDT-SWAP': 10.0,      # 1张=10.0 BAT
    'BCH-USDT-SWAP': 0.1,      # 1张=0.1 BCH
    'BERA-USDT-SWAP': 0.1,      # 1张=0.1 BERA
    'BICO-USDT-SWAP': 1.0,      # 1张=1.0 BICO
    'BIGTIME-USDT-SWAP': 10.0,      # 1张=10.0 BIGTIME
    'BIO-USDT-SWAP': 1.0,      # 1张=1.0 BIO
    'BLUR-USDT-SWAP': 10.0,      # 1张=10.0 BLUR
    'BNB-USDT-SWAP': 0.01,      # 1张=0.01 BNB
    'BNT-USDT-SWAP': 10.0,      # 1张=10.0 BNT
    'BOME-USDT-SWAP': 1000.0,      # 1张=1000.0 BOME
    'BONK-USDT-SWAP': 100000.0,      # 1张=100000.0 BONK
    'BRETT-USDT-SWAP': 100.0,      # 1张=100.0 BRETT
    'BTC-USDT-SWAP': 0.01,      # 1张=0.01 BTC
    'CAT-USDT-SWAP': 100000.0,      # 1张=100000.0 CAT
    'CATI-USDT-SWAP': 1.0,      # 1张=1.0 CATI
    'CELO-USDT-SWAP': 1.0,      # 1张=1.0 CELO
    'CETUS-USDT-SWAP': 10.0,      # 1张=10.0 CETUS
    'CFX-USDT-SWAP': 10.0,      # 1张=10.0 CFX
    'CHZ-USDT-SWAP': 10.0,      # 1张=10.0 CHZ
    'COMP-USDT-SWAP': 0.1,      # 1张=0.1 COMP
    'COOKIE-USDT-SWAP': 10.0,      # 1张=10.0 COOKIE
    'CORE-USDT-SWAP': 1.0,      # 1张=1.0 CORE
    'CRO-USDT-SWAP': 10.0,      # 1张=10.0 CRO
    'CRV-USDT-SWAP': 1.0,      # 1张=1.0 CRV
    'CSPR-USDT-SWAP': 1.0,      # 1张=1.0 CSPR
    'CTC-USDT-SWAP': 10.0,      # 1张=10.0 CTC
    'CVC-USDT-SWAP': 100.0,      # 1张=100.0 CVC
    'CVX-USDT-SWAP': 1.0,      # 1张=1.0 CVX
    'DEGEN-USDT-SWAP': 100.0,      # 1张=100.0 DEGEN
    'DGB-USDT-SWAP': 100.0,      # 1张=100.0 DGB
    'DOG-USDT-SWAP': 1000.0,      # 1张=1000.0 DOG
    'DOGE-USDT-SWAP': 1000.0,      # 1张=1000.0 DOGE
    'DOGS-USDT-SWAP': 1000.0,      # 1张=1000.0 DOGS
    'DOOD-USDT-SWAP': 1000.0,      # 1张=1000.0 DOOD
    'DOT-USDT-SWAP': 1.0,      # 1张=1.0 DOT
    'DUCK-USDT-SWAP': 100.0,      # 1张=100.0 DUCK
    'DYDX-USDT-SWAP': 1.0,      # 1张=1.0 DYDX
    'EGLD-USDT-SWAP': 0.1,      # 1张=0.1 EGLD
    'EIGEN-USDT-SWAP': 1.0,      # 1张=1.0 EIGEN
    'ENJ-USDT-SWAP': 10.0,      # 1张=10.0 ENJ
    'ENS-USDT-SWAP': 0.1,      # 1张=0.1 ENS
    'ETC-USDT-SWAP': 10.0,      # 1张=10.0 ETC
    'ETH-USDT-SWAP': 0.1,      # 1张=0.1 ETH
    'ETHFI-USDT-SWAP': 1.0,      # 1张=1.0 ETHFI
    'ETHW-USDT-SWAP': 0.1,      # 1张=0.1 ETHW
    'FARTCOIN-USDT-SWAP': 1.0,      # 1张=1.0 FARTCOIN
    'FIL-USDT-SWAP': 0.1,      # 1张=0.1 FIL
    'FLM-USDT-SWAP': 10.0,      # 1张=10.0 FLM
    'FLOKI-USDT-SWAP': 100000.0,      # 1张=100000.0 FLOKI
    'FLOW-USDT-SWAP': 10.0,      # 1张=10.0 FLOW
    'FXS-USDT-SWAP': 1.0,      # 1张=1.0 FXS
    'GALA-USDT-SWAP': 10.0,      # 1张=10.0 GALA
    'GAS-USDT-SWAP': 1.0,      # 1张=1.0 GAS
    'GLM-USDT-SWAP': 10.0,      # 1张=10.0 GLM
    'GMT-USDT-SWAP': 1.0,      # 1张=1.0 GMT
    'GMX-USDT-SWAP': 0.1,      # 1张=0.1 GMX
    'GOAT-USDT-SWAP': 10.0,      # 1张=10.0 GOAT
    'GODS-USDT-SWAP': 1.0,      # 1张=1.0 GODS
    'GPS-USDT-SWAP': 10.0,      # 1张=10.0 GPS
    'GRASS-USDT-SWAP': 1.0,      # 1张=1.0 GRASS
    'GRIFFAIN-USDT-SWAP': 10.0,      # 1张=10.0 GRIFFAIN
    'GRT-USDT-SWAP': 10.0,      # 1张=10.0 GRT
    'H-USDT-SWAP': 100.0,      # 1张=100.0 H
    'HBAR-USDT-SWAP': 100.0,      # 1张=100.0 HBAR
    'HMSTR-USDT-SWAP': 100.0,      # 1张=100.0 HMSTR
    'HOME-USDT-SWAP': 100.0,      # 1张=100.0 HOME
    'HUMA-USDT-SWAP': 100.0,      # 1张=100.0 HUMA
    'HYPE-USDT-SWAP': 0.1,      # 1张=0.1 HYPE
    'ICP-USDT-SWAP': 0.01,      # 1张=0.01 ICP
    'ICX-USDT-SWAP': 10.0,      # 1张=10.0 ICX
    'ID-USDT-SWAP': 10.0,      # 1张=10.0 ID
    'IMX-USDT-SWAP': 1.0,      # 1张=1.0 IMX
    'INIT-USDT-SWAP': 10.0,      # 1张=10.0 INIT
    'INJ-USDT-SWAP': 0.1,      # 1张=0.1 INJ
    'IOST-USDT-SWAP': 1000.0,      # 1张=1000.0 IOST
    'IOTA-USDT-SWAP': 10.0,      # 1张=10.0 IOTA
    'IP-USDT-SWAP': 1.0,      # 1张=1.0 IP
    'JELLYJELLY-USDT-SWAP': 100.0,      # 1张=100.0 JELLYJELLY
    'JOE-USDT-SWAP': 10.0,      # 1张=10.0 JOE
    'JST-USDT-SWAP': 100.0,      # 1张=100.0 JST
    'JTO-USDT-SWAP': 1.0,      # 1张=1.0 JTO
    'JUP-USDT-SWAP': 10.0,      # 1张=10.0 JUP
    'KAITO-USDT-SWAP': 1.0,      # 1张=1.0 KAITO
    'KMNO-USDT-SWAP': 100.0,      # 1张=100.0 KMNO
    'KSM-USDT-SWAP': 0.1,      # 1张=0.1 KSM
    'LA-USDT-SWAP': 10.0,      # 1张=10.0 LA
    'LAUNCHCOIN-USDT-SWAP': 10.0,      # 1张=10.0 LAUNCHCOIN
    'LAYER-USDT-SWAP': 1.0,      # 1张=1.0 LAYER
    'LDO-USDT-SWAP': 1.0,      # 1张=1.0 LDO
    'LINK-USDT-SWAP': 1.0,      # 1张=1.0 LINK
    'LPT-USDT-SWAP': 0.1,      # 1张=0.1 LPT
    'LQTY-USDT-SWAP': 1.0,      # 1张=1.0 LQTY
    'LRC-USDT-SWAP': 10.0,      # 1张=10.0 LRC
    'LTC-USDT-SWAP': 1.0,      # 1张=1.0 LTC
    'LUNA-USDT-SWAP': 1.0,      # 1张=1.0 LUNA
    'LUNC-USDT-SWAP': 10000.0,      # 1张=10000.0 LUNC
    'MAGIC-USDT-SWAP': 1.0,      # 1张=1.0 MAGIC
    'MAJOR-USDT-SWAP': 1.0,      # 1张=1.0 MAJOR
    'MANA-USDT-SWAP': 10.0,      # 1张=10.0 MANA
    'MASK-USDT-SWAP': 1.0,      # 1张=1.0 MASK
    'ME-USDT-SWAP': 1.0,      # 1张=1.0 ME
    'MEME-USDT-SWAP': 100.0,      # 1张=100.0 MEME
    'MERL-USDT-SWAP': 1.0,      # 1张=1.0 MERL
    'METIS-USDT-SWAP': 0.1,      # 1张=0.1 METIS
    'MEW-USDT-SWAP': 1000.0,      # 1张=1000.0 MEW
    'MINA-USDT-SWAP': 1.0,      # 1张=1.0 MINA
    'MKR-USDT-SWAP': 0.01,      # 1张=0.01 MKR
    'MOG-USDT-SWAP': 1000000.0,      # 1张=1000000.0 MOG
    'MOODENG-USDT-SWAP': 10.0,      # 1张=10.0 MOODENG
    'MORPHO-USDT-SWAP': 1.0,      # 1张=1.0 MORPHO
    'MOVE-USDT-SWAP': 10.0,      # 1张=10.0 MOVE
    'MUBARAK-USDT-SWAP': 100.0,      # 1张=100.0 MUBARAK
    'NEAR-USDT-SWAP': 10.0,      # 1张=10.0 NEAR
    'NEIRO-USDT-SWAP': 1000.0,      # 1张=1000.0 NEIRO
    'NEIROETH-USDT-SWAP': 100.0,      # 1张=100.0 NEIROETH
    'NEO-USDT-SWAP': 1.0,      # 1张=1.0 NEO
    'NEWT-USDT-SWAP': 10.0,      # 1张=10.0 NEWT
    'NMR-USDT-SWAP': 0.1,      # 1张=0.1 NMR
    'NOT-USDT-SWAP': 100.0,      # 1张=100.0 NOT
    'NXPC-USDT-SWAP': 1.0,      # 1张=1.0 NXPC
    'OL-USDT-SWAP': 10.0,      # 1张=10.0 OL
    'OM-USDT-SWAP': 10.0,      # 1张=10.0 OM
    'ONDO-USDT-SWAP': 10.0,      # 1张=10.0 ONDO
    'ONE-USDT-SWAP': 100.0,      # 1张=100.0 ONE
    'ONT-USDT-SWAP': 10.0,      # 1张=10.0 ONT
    'OP-USDT-SWAP': 1.0,      # 1张=1.0 OP
    'ORBS-USDT-SWAP': 100.0,      # 1张=100.0 ORBS
    'ORDI-USDT-SWAP': 0.1,      # 1张=0.1 ORDI
    'PARTI-USDT-SWAP': 10.0,      # 1张=10.0 PARTI
    'PENGU-USDT-SWAP': 100.0,      # 1张=100.0 PENGU
    'PEOPLE-USDT-SWAP': 100.0,      # 1张=100.0 PEOPLE
    'PEPE-USDT-SWAP': 10000000.0,      # 1张=10000000.0 PEPE
    'PERP-USDT-SWAP': 1.0,      # 1张=1.0 PERP
    'PI-USDT-SWAP': 1.0,      # 1张=1.0 PI
    'PLUME-USDT-SWAP': 10.0,      # 1张=10.0 PLUME
    'PNUT-USDT-SWAP': 10.0,      # 1张=10.0 PNUT
    'POL-USDT-SWAP': 10.0,      # 1张=10.0 POL
    'POPCAT-USDT-SWAP': 10.0,      # 1张=10.0 POPCAT
    'PRCL-USDT-SWAP': 1.0,      # 1张=1.0 PRCL
    'PROMPT-USDT-SWAP': 10.0,      # 1张=10.0 PROMPT
    'PUMP-USDT-SWAP': 1000.0,      # 1张=1000.0 PUMP
    'PYTH-USDT-SWAP': 10.0,      # 1张=10.0 PYTH
    'QTUM-USDT-SWAP': 1.0,      # 1张=1.0 QTUM
    'RAY-USDT-SWAP': 1.0,      # 1张=1.0 RAY
    'RDNT-USDT-SWAP': 10.0,      # 1张=10.0 RDNT
    'RENDER-USDT-SWAP': 1.0,      # 1张=1.0 RENDER
    'RESOLV-USDT-SWAP': 10.0,      # 1张=10.0 RESOLV
    'RSR-USDT-SWAP': 100.0,      # 1张=100.0 RSR
    'RVN-USDT-SWAP': 10.0,      # 1张=10.0 RVN
    'S-USDT-SWAP': 10.0,      # 1张=10.0 S
    'SAHARA-USDT-SWAP': 10.0,      # 1张=10.0 SAHARA
    'SAND-USDT-SWAP': 10.0,      # 1张=10.0 SAND
    'SATS-USDT-SWAP': 10000000.0,      # 1张=10000000.0 SATS
    'SCR-USDT-SWAP': 1.0,      # 1张=1.0 SCR
    'SHELL-USDT-SWAP': 10.0,      # 1张=10.0 SHELL
    'SHIB-USDT-SWAP': 1000000.0,      # 1张=1000000.0 SHIB
    'SIGN-USDT-SWAP': 100.0,      # 1张=100.0 SIGN
    'SLP-USDT-SWAP': 10.0,      # 1张=10.0 SLP
    'SNX-USDT-SWAP': 1.0,      # 1张=1.0 SNX
    'SOL-USDT-SWAP': 1.0,      # 1张=1.0 SOL
    'SOLV-USDT-SWAP': 100.0,      # 1张=100.0 SOLV
    'SONIC-USDT-SWAP': 1.0,      # 1张=1.0 SONIC
    'SOON-USDT-SWAP': 10.0,      # 1张=10.0 SOON
    'SOPH-USDT-SWAP': 100.0,      # 1张=100.0 SOPH
    'SPK-USDT-SWAP': 100.0,      # 1张=100.0 SPK
    'SPX-USDT-SWAP': 1.0,      # 1张=1.0 SPX
    'SSV-USDT-SWAP': 0.1,      # 1张=0.1 SSV
    'STORJ-USDT-SWAP': 10.0,      # 1张=10.0 STORJ
    'STRK-USDT-SWAP': 1.0,      # 1张=1.0 STRK
    'STX-USDT-SWAP': 10.0,      # 1张=10.0 STX
    'SUI-USDT-SWAP': 1.0,      # 1张=1.0 SUI
    'SUSHI-USDT-SWAP': 1.0,      # 1张=1.0 SUSHI
    'SWARMS-USDT-SWAP': 10.0,      # 1张=10.0 SWARMS
    'SYRUP-USDT-SWAP': 10.0,      # 1张=10.0 SYRUP
    'T-USDT-SWAP': 100.0,      # 1张=100.0 T
    'TAO-USDT-SWAP': 0.01,      # 1张=0.01 TAO
    'THETA-USDT-SWAP': 10.0,      # 1张=10.0 THETA
    'TIA-USDT-SWAP': 1.0,      # 1张=1.0 TIA
    'TNSR-USDT-SWAP': 1.0,      # 1张=1.0 TNSR
    'TON-USDT-SWAP': 1.0,      # 1张=1.0 TON
    'TRB-USDT-SWAP': 0.1,      # 1张=0.1 TRB
    'TREE-USDT-SWAP': 1.0,      # 1张=1.0 TREE
    'TRUMP-USDT-SWAP': 0.1,      # 1张=0.1 TRUMP
    'TRX-USDT-SWAP': 1000.0,      # 1张=1000.0 TRX
    'TURBO-USDT-SWAP': 10000.0,      # 1张=10000.0 TURBO
    'UMA-USDT-SWAP': 0.1,      # 1张=0.1 UMA
    'UNI-USDT-SWAP': 1.0,      # 1张=1.0 UNI
    'USDC-USDT-SWAP': 10.0,      # 1张=10.0 USDC
    'USELESS-USDT-SWAP': 10.0,      # 1张=10.0 USELESS
    'USTC-USDT-SWAP': 100.0,      # 1张=100.0 USTC
    'UXLINK-USDT-SWAP': 10.0,      # 1张=10.0 UXLINK
    'VANA-USDT-SWAP': 0.1,      # 1张=0.1 VANA
    'VINE-USDT-SWAP': 10.0,      # 1张=10.0 VINE
    'VIRTUAL-USDT-SWAP': 1.0,      # 1张=1.0 VIRTUAL
    'W-USDT-SWAP': 1.0,      # 1张=1.0 W
    'WAL-USDT-SWAP': 10.0,      # 1张=10.0 WAL
    'WAXP-USDT-SWAP': 100.0,      # 1张=100.0 WAXP
    'WCT-USDT-SWAP': 10.0,      # 1张=10.0 WCT
    'WIF-USDT-SWAP': 1.0,      # 1张=1.0 WIF
    'WLD-USDT-SWAP': 1.0,      # 1张=1.0 WLD
    'WOO-USDT-SWAP': 10.0,      # 1张=10.0 WOO
    'XAUT-USDT-SWAP': 0.001,      # 1张=0.001 XAUT
    'XCH-USDT-SWAP': 0.01,      # 1张=0.01 XCH
    'XLM-USDT-SWAP': 100.0,      # 1张=100.0 XLM
    'XRP-USDT-SWAP': 100.0,      # 1张=100.0 XRP
    'XTZ-USDT-SWAP': 1.0,      # 1张=1.0 XTZ
    'YFI-USDT-SWAP': 0.0001,      # 1张=0.0001 YFI
    'YGG-USDT-SWAP': 1.0,      # 1张=1.0 YGG
    'ZENT-USDT-SWAP': 100.0,      # 1张=100.0 ZENT
    'ZEREBRO-USDT-SWAP': 10.0,      # 1张=10.0 ZEREBRO
    'ZETA-USDT-SWAP': 10.0,      # 1张=10.0 ZETA
    'ZIL-USDT-SWAP': 100.0,      # 1张=100.0 ZIL
    'ZK-USDT-SWAP': 10.0,      # 1张=10.0 ZK
    'ZRO-USDT-SWAP': 1.0,      # 1张=1.0 ZRO
    'ZRX-USDT-SWAP': 10.0,      # 1张=10.0 ZRX
}

# 合约价格精度
CONTRACT_TICK_SZ = {
    "1INCH-USDT-SWAP": 0.0001,
    "A-USDT-SWAP": 0.0001,    
    "AAVE-USDT-SWAP": 0.01,   
    "ACE-USDT-SWAP": 0.0001,  
    "ACH-USDT-SWAP": 0.00001,   
    "ACT-USDT-SWAP": 0.00001,   
    "ADA-USD-SWAP": 0.0001,   
    "ADA-USDT-SWAP": 0.0001,  
    "AERO-USDT-SWAP": 0.0001, 
    "AEVO-USDT-SWAP": 0.00001,  
    "AGLD-USDT-SWAP": 0.0001, 
    "AI16Z-USDT-SWAP": 0.00001, 
    "AIXBT-USDT-SWAP": 0.00001, 
    "ALGO-USDT-SWAP": 0.0001, 
    "ANIME-USDT-SWAP": 0.00001,
    "APE-USDT-SWAP": 0.0001,
    "API3-USDT-SWAP": 0.0001,
    "APT-USDT-SWAP": 0.001,
    "AR-USDT-SWAP": 0.001,
    "ARB-USDT-SWAP": 0.0001,
    "ARC-USDT-SWAP": 0.00001,
    "ARKM-USDT-SWAP": 0.0001,
    "ATH-USDT-SWAP": 0.00001,
    "ATOM-USDT-SWAP": 0.001,
    "AUCTION-USDT-SWAP": 0.001,
    "AVAAI-USDT-SWAP": 0.00001,
    "AVAX-USD-SWAP": 0.001,
    "AVAX-USDT-SWAP": 0.001,
    "AXS-USDT-SWAP": 0.001,
    "BABY-USDT-SWAP": 0.00001,
    "BAND-USDT-SWAP": 0.0001,
    "BAT-USDT-SWAP": 0.0001,
    "BCH-USD-SWAP": 0.1,
    "BCH-USDT-SWAP": 0.1,
    "BERA-USDT-SWAP": 0.001,
    "BICO-USDT-SWAP": 0.00001,
    "BIGTIME-USDT-SWAP": 0.00001,
    "BIO-USDT-SWAP": 0.00001,
    "BLUR-USDT-SWAP": 0.00001,
    "BNB-USDT-SWAP": 0.1,
    "BNT-USDT-SWAP": 0.0001,
    "BOME-USDT-SWAP": 0.000001,
    "BONK-USDT-SWAP": 0.000000001,
    "BRETT-USDT-SWAP": 0.00001,
    "BTC-USD-SWAP": 0.1,
    "BTC-USDC-SWAP": 0.1,
    "BTC-USDT-SWAP": 0.1,
    "CAT-USDT-SWAP": 0.000000001,
    "CATI-USDT-SWAP": 0.00001,
    "CELO-USDT-SWAP": 0.0001,
    "CETUS-USDT-SWAP": 0.00001,
    "CFX-USDT-SWAP": 0.00001,
    "CHZ-USDT-SWAP": 0.00001,
    "COMP-USDT-SWAP": 0.01,
    "COOKIE-USDT-SWAP": 0.00001,
    "CORE-USDT-SWAP": 0.0001,
    "CRO-USDT-SWAP": 0.00001,
    "CRV-USDT-SWAP": 0.0001,
    "CTC-USDT-SWAP": 0.0001,
    "CVC-USDT-SWAP": 0.00001,
    "CVX-USDT-SWAP": 0.001,
    "DEGEN-USDT-SWAP": 0.000001,
    "DOGE-USD-SWAP": 0.00001,
    "DOGE-USDT-SWAP": 0.00001,
    "DOGS-USDT-SWAP": 0.0000001,
    "DOOD-USDT-SWAP": 0.000001,
    "DOT-USD-SWAP": 0.001,
    "DOT-USDT-SWAP": 0.001,
    "DUCK-USDT-SWAP": 0.000001,
    "DYDX-USDT-SWAP": 0.0001,
    "EGLD-USDT-SWAP": 0.01,
    "EIGEN-USDT-SWAP": 0.0001,
    "ENJ-USDT-SWAP": 0.00001,
    "ENS-USDT-SWAP": 0.001,
    "ETC-USD-SWAP": 0.01,
    "ETC-USDT-SWAP": 0.01,
    "ETH-USD-SWAP": 0.01,
    "ETH-USDC-SWAP": 0.01,
    "ETH-USDT-SWAP": 0.01,
    "ETHFI-USDT-SWAP": 0.0001,
    "ETHW-USDT-SWAP": 0.001,
    "FARTCOIN-USDT-SWAP": 0.0001,
    "FIL-USD-SWAP": 0.001,
    "FIL-USDT-SWAP": 0.001,
    "FLM-USDT-SWAP": 0.00001,
    "FLOKI-USDT-SWAP": 0.00000001,
    "FLOW-USDT-SWAP": 0.0001,
    "FXS-USDT-SWAP": 0.001,
    "GALA-USDT-SWAP": 0.00001,
    "GAS-USDT-SWAP": 0.001,
    "GLM-USDT-SWAP": 0.0001,
    "GMT-USDT-SWAP": 0.00001,
    "GMX-USDT-SWAP": 0.01,
    "GOAT-USDT-SWAP": 0.00001,
    "GODS-USDT-SWAP": 0.00001,
    "GPS-USDT-SWAP": 0.000001,
    "GRASS-USDT-SWAP": 0.0001,
    "GRIFFAIN-USDT-SWAP": 0.00001,
    "GRT-USDT-SWAP": 0.00001,
    "H-USDT-SWAP": 0.00001,
    "HBAR-USDT-SWAP": 0.00001,
    "HMSTR-USDT-SWAP": 0.0000001,
    "HOME-USDT-SWAP": 0.00001,
    "HUMA-USDT-SWAP": 0.00001,
    "HYPE-USDT-SWAP": 0.001,
    "ICP-USDT-SWAP": 0.001,
    "ICX-USDT-SWAP": 0.00001,
    "IMX-USDT-SWAP": 0.0001,
    "INIT-USDT-SWAP": 0.0001,
    "INJ-USDT-SWAP": 0.001,
    "IOST-USDT-SWAP": 0.000001,
    "IOTA-USDT-SWAP": 0.0001,
    "IP-USDT-SWAP": 0.0001,
    "JELLYJELLY-USDT-SWAP": 0.00001,
    "JOE-USDT-SWAP": 0.0001,
    "JTO-USDT-SWAP": 0.001,
    "JUP-USDT-SWAP": 0.0001,
    "KAITO-USDT-SWAP": 0.0001,
    "KMNO-USDT-SWAP": 0.00001,
    "KSM-USDT-SWAP": 0.01,
    "LA-USDT-SWAP": 0.0001,
    "LAUNCHCOIN-USDT-SWAP": 0.00001,
    "LAYER-USDT-SWAP": 0.0001,
    "LDO-USDT-SWAP": 0.0001,
    "LINEA-USDT-SWAP": 0.00001,
    "LINK-USD-SWAP": 0.001,
    "LINK-USDT-SWAP": 0.001,
    "LPT-USDT-SWAP": 0.001,
    "LQTY-USDT-SWAP": 0.0001,
    "LRC-USDT-SWAP": 0.00001,
    "LTC-USD-SWAP": 0.01,
    "LTC-USDT-SWAP": 0.01,
    "LUNA-USDT-SWAP": 0.0001,
    "LUNC-USDT-SWAP": 0.00000001,
    "MAGIC-USDT-SWAP": 0.00001,
    "MAJOR-USDT-SWAP": 0.0001,
    "MANA-USDT-SWAP": 0.0001,
    "MASK-USDT-SWAP": 0.001,
    "ME-USDT-SWAP": 0.0001,
    "MEME-USDT-SWAP": 0.000001,
    "MERL-USDT-SWAP": 0.00001,
    "METIS-USDT-SWAP": 0.01,
    "MEW-USDT-SWAP": 0.000001,
    "MINA-USDT-SWAP": 0.0001,
    "MOG-USDT-SWAP": 0.0000000001,
    "MOODENG-USDT-SWAP": 0.00001,
    "MORPHO-USDT-SWAP": 0.0001,
    "MOVE-USDT-SWAP": 0.00001,
    "MUBARAK-USDT-SWAP": 0.00001,
    "NEAR-USDT-SWAP": 0.001,
    "NEIRO-USDT-SWAP": 0.0000001,
    "NEO-USDT-SWAP": 0.001,
    "NEWT-USDT-SWAP": 0.0001,
    "NMR-USDT-SWAP": 0.001,
    "NOT-USDT-SWAP": 0.000001,
    "NXPC-USDT-SWAP": 0.0001,
    "OKB-USDT-SWAP": 0.01,
    "OL-USDT-SWAP": 0.00001,
    "OM-USDT-SWAP": 0.0001,
    "ONDO-USDT-SWAP": 0.0001,
    "ONE-USDT-SWAP": 0.000001,
    "ONT-USDT-SWAP": 0.0001,
    "OP-USDT-SWAP": 0.0001,
    "ORBS-USDT-SWAP": 0.00001,
    "ORDI-USDT-SWAP": 0.001,
    "PARTI-USDT-SWAP": 0.0001,
    "PENGU-USDT-SWAP": 0.000001,
    "PEOPLE-USDT-SWAP": 0.00001,
    "PEPE-USDT-SWAP": 0.000000001,
    "PERP-USDT-SWAP": 0.0001,
    "PI-USDT-SWAP": 0.0001,
    "PLUME-USDT-SWAP": 0.00001,
    "PNUT-USDT-SWAP": 0.0001,
    "POL-USDT-SWAP": 0.0001,
    "POPCAT-USDT-SWAP": 0.0001,
    "PRCL-USDT-SWAP": 0.00001,
    "PROMPT-USDT-SWAP": 0.00001,
    "PUMP-USDT-SWAP": 0.000001,
    "PYTH-USDT-SWAP": 0.00001,
    "QTUM-USDT-SWAP": 0.001,
    "RAY-USDT-SWAP": 0.0001,
    "RENDER-USDT-SWAP": 0.001,
    "RESOLV-USDT-SWAP": 0.0001,
    "RSR-USDT-SWAP": 0.000001,
    "RVN-USDT-SWAP": 0.00001,
    "S-USDT-SWAP": 0.0001,
    "SAHARA-USDT-SWAP": 0.00001,
    "SAND-USDT-SWAP": 0.0001,
    "SATS-USDT-SWAP": 0.00000000001,
    "SCR-USDT-SWAP": 0.0001,
    "SHELL-USDT-SWAP": 0.0001,
    "SHIB-USDT-SWAP": 0.000000001,
    "SIGN-USDT-SWAP": 0.00001,
    "SKY-USDT-SWAP": 0.00001,
    "SLP-USDT-SWAP": 0.000001,
    "SNX-USDT-SWAP": 0.0001,
    "SOL-USD-SWAP": 0.01,
    "SOL-USDT-SWAP": 0.01,
    "SOLV-USDT-SWAP": 0.000001,
    "SONIC-USDT-SWAP": 0.00001,
    "SOON-USDT-SWAP": 0.00001,
    "SOPH-USDT-SWAP": 0.00001,
    "SPK-USDT-SWAP": 0.00001,
    "SPX-USDT-SWAP": 0.0001,
    "SSV-USDT-SWAP": 0.001,
    "STORJ-USDT-SWAP": 0.0001,
    "STRK-USDT-SWAP": 0.0001,
    "STX-USDT-SWAP": 0.0001,
    "SUI-USD-SWAP": 0.0001,
    "SUI-USDT-SWAP": 0.0001,
    "SUSHI-USDT-SWAP": 0.0001,
    "SWARMS-USDT-SWAP": 0.00001,
    "SYRUP-USDT-SWAP": 0.0001,
    "T-USDT-SWAP": 0.00001,
    "TAO-USDT-SWAP": 0.1,
    "THETA-USDT-SWAP": 0.0001,
    "TIA-USDT-SWAP": 0.001,
    "TNSR-USDT-SWAP": 0.0001,
    "TON-USDT-SWAP": 0.001,
    "TRB-USDT-SWAP": 0.01,
    "TREE-USDT-SWAP": 0.0001,
    "TRUMP-USDT-SWAP": 0.001,
    "TRX-USDT-SWAP": 0.00001,
    "TURBO-USDT-SWAP": 0.000001,
    "UMA-USDT-SWAP": 0.001,
    "UNI-USD-SWAP": 0.001,
    "UNI-USDT-SWAP": 0.001,
    "USDC-USDT-SWAP": 0.00001,
    "USELESS-USDT-SWAP": 0.0001,
    "USTC-USDT-SWAP": 0.00001,
    "UXLINK-USDT-SWAP": 0.0001,
    "VANA-USDT-SWAP": 0.001,
    "VINE-USDT-SWAP": 0.00001,
    "VIRTUAL-USDT-SWAP": 0.0001,
    "W-USDT-SWAP": 0.00001,
    "WAL-USDT-SWAP": 0.0001,
    "WCT-USDT-SWAP": 0.0001,
    "WIF-USDT-SWAP": 0.0001,
    "WLD-USDT-SWAP": 0.0001,
    "WLFI-USDT-SWAP": 0.0001,
    "WOO-USDT-SWAP": 0.00001,
    "XAUT-USDT-SWAP": 0.1,
    "XLM-USDT-SWAP": 0.00001,
    "XPL-USDT-SWAP": 0.0001,
    "XRP-USD-SWAP": 0.0001,
    "XRP-USDT-SWAP": 0.0001,
    "XTZ-USDT-SWAP": 0.0001,
    "YFI-USDT-SWAP": 1.0,
    "YGG-USDT-SWAP": 0.0001,
    "ZENT-USDT-SWAP": 0.000001,
    "ZETA-USDT-SWAP": 0.0001,
    "ZIL-USDT-SWAP": 0.00001,
    "ZK-USDT-SWAP": 0.00001,
    "ZRO-USDT-SWAP": 0.001,
    "ZRX-USDT-SWAP": 0.0001,
}

# ============================================================================
# 币本位合约配置（OKX官方同步）
# ============================================================================

# 币本位合约张数精度（OKX官方同步）
INVERSE_CONTRACT_SZ_PRECISION = {
    'BTC-USD-SWAP': 1,      # 1位小数
    'ETH-USD-SWAP': 1,      # 1位小数
    'SOL-USD-SWAP': 1,      # 1位小数
    'DOGE-USD-SWAP': 1,      # 1位小数
    'XRP-USD-SWAP': 1,      # 1位小数
    'ADA-USD-SWAP': 1,      # 1位小数
    'AVAX-USD-SWAP': 1,      # 1位小数
    'BCH-USD-SWAP': 1,      # 1位小数
    'DOT-USD-SWAP': 1,      # 1位小数
    'ETC-USD-SWAP': 1,      # 1位小数
    'FIL-USD-SWAP': 1,      # 1位小数
    'LINK-USD-SWAP': 1,      # 1位小数
    'LTC-USD-SWAP': 1,      # 1位小数
    'SUI-USD-SWAP': 1,      # 1位小数
    'UNI-USD-SWAP': 1,      # 1位小数
}

# 币本位合约最小下单张数（OKX官方同步）
INVERSE_CONTRACT_MIN_SZ = {
    'BTC-USD-SWAP': 1.0,      # 最小1.0张
    'ETH-USD-SWAP': 1.0,      # 最小1.0张
    'SOL-USD-SWAP': 1.0,      # 最小1.0张
    'DOGE-USD-SWAP': 1.0,      # 最小1.0张
    'XRP-USD-SWAP': 1.0,      # 最小1.0张
    'ADA-USD-SWAP': 1.0,      # 最小1.0张
    'AVAX-USD-SWAP': 1.0,      # 最小1.0张
    'BCH-USD-SWAP': 1.0,      # 最小1.0张
    'DOT-USD-SWAP': 1.0,      # 最小1.0张
    'ETC-USD-SWAP': 1.0,      # 最小1.0张
    'FIL-USD-SWAP': 1.0,      # 最小1.0张
    'LINK-USD-SWAP': 1.0,      # 最小1.0张
    'LTC-USD-SWAP': 1.0,      # 最小1.0张
    'SUI-USD-SWAP': 1.0,      # 最小1.0张
    'UNI-USD-SWAP': 1.0,      # 最小1.0张
}

# 币本位合约乘数（张数->USDT价值），OKX币本位永续合约
INVERSE_CONTRACT_MULTIPLIERS = {
    'BTC-USD-SWAP': 100.0,      # 1张=100.0 USDT
    'ETH-USD-SWAP': 10.0,      # 1张=10.0 USDT
    'SOL-USD-SWAP': 10.0,      # 1张=10.0 USDT
    'DOGE-USD-SWAP': 10.0,      # 1张=10.0 USDT
    'XRP-USD-SWAP': 10.0,      # 1张=10.0 USDT
    'ADA-USD-SWAP': 10.0,      # 1张=10.0 USDT
    'AVAX-USD-SWAP': 10.0,      # 1张=10.0 USDT
    'BCH-USD-SWAP': 10.0,      # 1张=10.0 USDT
    'DOT-USD-SWAP': 10.0,      # 1张=10.0 USDT
    'ETC-USD-SWAP': 10.0,      # 1张=10.0 USDT
    'FIL-USD-SWAP': 10.0,      # 1张=10.0 USDT
    'LINK-USD-SWAP': 10.0,      # 1张=10.0 USDT
    'LTC-USD-SWAP': 10.0,      # 1张=10.0 USDT
    'SUI-USD-SWAP': 10.0,      # 1张=10.0 USDT
    'UNI-USD-SWAP': 10.0,      # 1张=10.0 USDT
}

# 币本位合约价格精度（OKX官方同步）
INVERSE_CONTRACT_TICK_SZ = {
    'BTC-USD-SWAP': 0.1,      # 价格精度0.1
    'ETH-USD-SWAP': 0.01,      # 价格精度0.01
    'SOL-USD-SWAP': 0.01,      # 价格精度0.01
    'DOGE-USD-SWAP': 0.00001,      # 价格精度0.00001
    'XRP-USD-SWAP': 0.0001,      # 价格精度0.0001
    'ADA-USD-SWAP': 0.0001,      # 价格精度0.0001
    'AVAX-USD-SWAP': 0.001,      # 价格精度0.001
    'BCH-USD-SWAP': 0.1,      # 价格精度0.1
    'DOT-USD-SWAP': 0.001,      # 价格精度0.001
    'ETC-USD-SWAP': 0.01,      # 价格精度0.01
    'FIL-USD-SWAP': 0.001,      # 价格精度0.001
    'LINK-USD-SWAP': 0.001,      # 价格精度0.001
    'LTC-USD-SWAP': 0.01,      # 价格精度0.01
    'SUI-USD-SWAP': 0.0001,      # 价格精度0.0001
    'UNI-USD-SWAP': 0.001,      # 价格精度0.001
}

# ============================================================================
# 智能识别函数
# ============================================================================

def is_inverse_contract(symbol):
    """判断是否为币本位合约"""
    return symbol in INVERSE_CONTRACT_MULTIPLIERS

def get_contract_sz_precision(symbol):
    """获取合约张数精度（智能识别合约类型）"""
    if is_inverse_contract(symbol):
        return INVERSE_CONTRACT_SZ_PRECISION.get(symbol, 1)
    else:
        return CONTRACT_SZ_PRECISION.get(symbol, 0)

def get_contract_min_sz(symbol):
    """获取合约最小张数（智能识别合约类型）"""
    if is_inverse_contract(symbol):
        return INVERSE_CONTRACT_MIN_SZ.get(symbol, 1.0)
    else:
        return CONTRACT_MIN_SZ.get(symbol, 1)

def get_contract_multiplier(symbol):
    """获取合约乘数（智能识别合约类型）"""
    if is_inverse_contract(symbol):
        return INVERSE_CONTRACT_MULTIPLIERS.get(symbol, 10.0)
    else:
        return CONTRACT_MULTIPLIERS.get(symbol, 1)

def get_contract_tick_sz(symbol):
    """获取合约价格精度（智能识别合约类型）"""
    if is_inverse_contract(symbol):
        return INVERSE_CONTRACT_TICK_SZ.get(symbol, 0.01)
    else:
        return CONTRACT_TICK_SZ.get(symbol, 0.01)  # U本位默认价格精度

def get_contract_value_in_usdt(symbol, sz):
    """计算合约张数对应的USDT价值（智能识别合约类型）"""
    if is_inverse_contract(symbol):
        # 币本位合约：张数 × 乘数
        return sz * get_contract_multiplier(symbol)
    else:
        # U本位合约：张数 × 乘数
        return sz * get_contract_multiplier(symbol)

def get_contract_sz_from_usdt_value(symbol, usdt_value):
    """根据USDT价值计算需要的合约张数（智能识别合约类型）"""
    if is_inverse_contract(symbol):
        # 币本位合约：USDT价值 ÷ 乘数
        return usdt_value / get_contract_multiplier(symbol)
    else:
        # U本位合约：USDT价值 ÷ 乘数
        return usdt_value / get_contract_multiplier(symbol)

def get_contract_tick_sz_from_usdt_value(symbol):
    """根据USDT价值计算需要的合约价格精度（智能识别合约类型）"""
    if is_inverse_contract(symbol):
        return INVERSE_CONTRACT_TICK_SZ.get(symbol, 0.01)
    else:
        return get_contract_tick_sz(symbol)  # U本位默认价格精度

def list_inverse_contracts():
    """列出所有币本位合约"""
    return list(INVERSE_CONTRACT_MULTIPLIERS.keys())

def list_all_contracts():
    """列出所有合约（U本位 + 币本位）"""
    u_contracts = list(CONTRACT_MULTIPLIERS.keys())
    inverse_contracts = list(INVERSE_CONTRACT_MULTIPLIERS.keys())
    return u_contracts + inverse_contracts

def get_contract_info(symbol):
    """获取合约完整信息（智能识别合约类型）"""
    if is_inverse_contract(symbol):
        return {
            'symbol': symbol,
            'type': 'inverse',  # 币本位
            'min_sz': get_contract_min_sz(symbol),
            'sz_precision': get_contract_sz_precision(symbol),
            'multiplier': get_contract_multiplier(symbol),
            'tick_sz': get_contract_tick_sz(symbol),
            'description': f"1张 = {get_contract_multiplier(symbol)} USDT"
        }
    else:
        return {
            'symbol': symbol,
            'type': 'linear',  # U本位
            'min_sz': get_contract_min_sz(symbol),
            'sz_precision': get_contract_sz_precision(symbol),
            'multiplier': get_contract_multiplier(symbol),
            'tick_sz': get_contract_tick_sz(symbol),
            'description': f"1张 = {get_contract_multiplier(symbol)} {symbol.split('-')[0]}"
        }