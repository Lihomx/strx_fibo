"""
assets.py — 全球超级品种库 v5
yfinance / Yahoo Finance 支持的全球所有主要市场
40 组，1500+ 精选品种，覆盖 36 个交易所

yfinance 交易所后缀对照：
  美国无后缀  A股.SS/.SZ  港股.HK   日本.T    韩国.KS
  台湾.TW     印度.NS     澳洲.AX   英国.L    德国.DE
  法国.PA     瑞士.SW     荷兰.AS   意大利.MI 西班牙.MC
  北欧.ST/.CO/.OL/.HE     加拿大.TO 巴西.SA   墨西哥.MX
  新加坡.SI   马来西亚.KL 泰国.BK   印尼.JK   菲律宾.PS
  南非.JO     沙特.SR     以色列.TA 新西兰.NZ
  期货=F      外汇=X      加密-USD
"""
from typing import Dict, Tuple


_TV_MAP: Dict[str, str] = {
    "GC=F":"COMEX:GC1!","SI=F":"COMEX:SI1!","PL=F":"NYMEX:PL1!","PA=F":"NYMEX:PA1!",
    "HG=F":"COMEX:HG1!","ALI=F":"COMEX:ALI1!","CL=F":"NYMEX:CL1!","BZ=F":"NYMEX:BB1!",
    "NG=F":"NYMEX:NG1!","RB=F":"NYMEX:RB1!","HO=F":"NYMEX:HO1!",
    "ZW=F":"CBOT:ZW1!","ZC=F":"CBOT:ZC1!","ZS=F":"CBOT:ZS1!","ZL=F":"CBOT:ZL1!",
    "ZM=F":"CBOT:ZM1!","KC=F":"ICEUS:KC1!","CT=F":"ICEUS:CT1!","SB=F":"ICEUS:SB1!",
    "CC=F":"ICEUS:CC1!","OJ=F":"ICEUS:OJ1!","LE=F":"CME:LE1!","HE=F":"CME:HE1!",
    "ES=F":"CME:ES1!","NQ=F":"CME:NQ1!","YM=F":"CBOT:YM1!","RTY=F":"CME:RTY1!",
    "ZB=F":"CBOT:ZB1!","ZN=F":"CBOT:ZN1!","ZF=F":"CBOT:ZF1!","VX=F":"CBOE:VX1!",
    "6E=F":"CME:6E1!","6J=F":"CME:6J1!","6B=F":"CME:6B1!","6A=F":"CME:6A1!",
    "6C=F":"CME:6C1!","6S=F":"CME:6S1!",
    "XAUUSD=X":"TVC:GOLD","XAGUSD=X":"TVC:SILVER",
    "^GSPC":"SP:SPX","^NDX":"NASDAQ:NDX","^DJI":"DJ:DJI","^RUT":"TVC:RUT",
    "^VIX":"TVC:VIX","^N225":"TVC:NI225","^FTSE":"TVC:UKX","^GDAXI":"TVC:DAX",
    "^FCHI":"EURONEXT:PX1","^STOXX50E":"TVC:SX5E","^AXJO":"ASX:XJO",
    "^KS11":"KRX:KOSPI","^TWII":"TWSE:TAIEX","^HSI":"TVC:HSI",
    "^BSESN":"BSE:SENSEX","^NSEI":"NSE:NIFTY",
    "000001.SS":"SSE:000001","399001.SZ":"SZSE:399001","000300.SS":"SSE:000300",
    "9988.HK":"HKEX:9988","0700.HK":"HKEX:700","3690.HK":"HKEX:3690",
    "BTC-USD":"BINANCE:BTCUSDT","ETH-USD":"BINANCE:ETHUSDT",
    "SOL-USD":"BINANCE:SOLUSDT","BNB-USD":"BINANCE:BNBUSDT",
    "XRP-USD":"BINANCE:XRPUSDT",
}

def tv_symbol(ticker: str) -> str:
    if ticker in _TV_MAP:
        return _TV_MAP[ticker]
    exch = {
        ".SS":"SSE",".SZ":"SZSE",".HK":"HKEX",".L":"LSE",".DE":"XETRA",
        ".PA":"EURONEXT",".MI":"MIL",".MC":"BME",".SW":"SIX",".AS":"EURONEXT",
        ".ST":"NASDAQ",".CO":"NASDAQ",".OL":"OSE",".HE":"NASDAQ",
        ".T":"TSE",".KS":"KRX",".TW":"TWSE",".NS":"NSE",".BO":"BSE",
        ".AX":"ASX",".SI":"SGX",".KL":"MYX",".BK":"SET",".JK":"IDX",
        ".PS":"PSE",".TO":"TSX",".SA":"BMFBOVESPA",".MX":"BMV",
        ".JO":"JSE",".SR":"TADAWUL",".TA":"TASE",".NZ":"NZX",
    }
    for sfx, ex in exch.items():
        if ticker.endswith(sfx):
            return f"{ex}:{ticker[:ticker.rfind(sfx)]}"
    return ticker.replace("=X","").replace("-USD","").replace("=F","").replace("^","")

def tv_url(ticker: str) -> str:
    return f"https://www.tradingview.com/chart/?symbol={tv_symbol(ticker)}"


# ════════════════════════════════════════════════════════════════════
# 40 组品种定义
# ════════════════════════════════════════════════════════════════════
ASSET_GROUPS: Dict[str, Dict[str, Tuple[str, str]]] = {

# ━━━ 1. 贵金属 & 能源期货 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🥇 贵金属 & 能源期货": {
    "GC=F":("黄金 Gold","futures"),"SI=F":("白银 Silver","futures"),
    "PL=F":("铂金 Platinum","futures"),"PA=F":("钯金 Palladium","futures"),
    "CL=F":("原油 WTI","futures"),"BZ=F":("布伦特原油","futures"),
    "NG=F":("天然气","futures"),"RB=F":("汽油 RBOB","futures"),
    "HO=F":("取暖油","futures"),"HG=F":("铜","futures"),
    "ALI=F":("铝","futures"),"ZT=F":("锌 Zinc","futures"),
},

# ━━━ 2. 农产品期货 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🌾 农产品期货": {
    "ZW=F":("小麦 Wheat","futures"),"ZC=F":("玉米 Corn","futures"),
    "ZS=F":("大豆 Soybean","futures"),"ZL=F":("豆油 Soy Oil","futures"),
    "ZM=F":("豆粕 Soymeal","futures"),"KC=F":("咖啡 Coffee","futures"),
    "CT=F":("棉花 Cotton","futures"),"SB=F":("糖 Sugar","futures"),
    "CC=F":("可可 Cocoa","futures"),"OJ=F":("橙汁 OJ","futures"),
    "LE=F":("活牛 Live Cattle","futures"),"HE=F":("瘦猪肉 Hogs","futures"),
    "GF=F":("喂养牛 Feeder","futures"),"LBS=F":("木材 Lumber","futures"),
},

# ━━━ 3. 金融期货 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"📈 金融期货": {
    "ES=F":("E-mini S&P500","futures"),"NQ=F":("E-mini NASDAQ","futures"),
    "YM=F":("E-mini DOW","futures"),"RTY=F":("E-mini Russell","futures"),
    "ZB=F":("30Y美国国债","futures"),"ZN=F":("10Y美国国债","futures"),
    "ZF=F":("5Y美国国债","futures"),"ZT=F":("2Y美国国债","futures"),
    "^VIX":("VIX波动率","index"),"NKD=F":("日经期货","futures"),
    "6E=F":("欧元期货","futures"),"6J=F":("日元期货","futures"),
    "6B=F":("英镑期货","futures"),"6A=F":("澳元期货","futures"),
    "6C=F":("加元期货","futures"),"6S=F":("瑞郎期货","futures"),
    "6N=F":("纽元期货","futures"),"6M=F":("墨西哥比索期货","futures"),
},

# ━━━ 4. 全球指数 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🌍 全球主要指数": {
    "^GSPC":("S&P500","index"),"^NDX":("NASDAQ100","index"),
    "^DJI":("道琼斯","index"),"^RUT":("Russell2000","index"),
    "^VIX":("VIX恐慌","index"),"^COMP":("纳斯达克综合","index"),
    "^N225":("日经225","index"),"^TOPX":("日本TOPIX","index"),
    "^FTSE":("英国富时100","index"),"^GDAXI":("德国DAX","index"),
    "^FCHI":("法国CAC40","index"),"^STOXX50E":("欧洲STOXX50","index"),
    "^AEX":("荷兰AEX","index"),"^SMI":("瑞士SMI","index"),
    "^IBEX":("西班牙IBEX","index"),"^FTSEMIB":("意大利MIB","index"),
    "^AXJO":("澳洲ASX200","index"),"^KS11":("韩国KOSPI","index"),
    "^TWII":("台湾加权","index"),"^HSI":("恒生指数","index"),
    "^HSCE":("恒生国企","index"),"^HSTECH":("恒生科技","index"),
    "^BSESN":("印度SENSEX","index"),"^NSEI":("印度NIFTY50","index"),
    "^STI":("新加坡STI","index"),"^KLSE":("马来西亚KLCI","index"),
    "^SET":("泰国SET","index"),"^JKSE":("印尼雅加达","index"),
    "^BVSP":("巴西IBOV","index"),"^MXX":("墨西哥IPC","index"),
    "^MERV":("阿根廷MERV","index"),"^IPSA":("智利IPSA","index"),
    "^TA125.TA":("以色列TA125","index"),"^CASE30":("埃及EGX30","index"),
},

# ━━━ 5. 中国指数 & ETF ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇨🇳 中国指数 & ETF": {
    "000001.SS":("上证综指","index"),"399001.SZ":("深证成指","index"),
    "000300.SS":("沪深300","index"),"000016.SS":("上证50","index"),
    "000688.SS":("科创50","index"),"399006.SZ":("创业板指","index"),
    "399673.SZ":("创业板50","index"),"000905.SS":("中证500","index"),
    "000852.SS":("中证1000","index"),"932000.CSI":("中证2000","index"),
    "510050.SS":("上证50ETF","a_stock"),"510300.SS":("沪深300ETF","a_stock"),
    "510500.SS":("中证500ETF","a_stock"),"588000.SS":("科创50ETF","a_stock"),
    "159915.SZ":("创业板ETF","a_stock"),"159919.SZ":("300ETF深","a_stock"),
    "512880.SS":("证券ETF","a_stock"),"515050.SS":("5G ETF","a_stock"),
    "516160.SS":("新能源ETF","a_stock"),"159869.SZ":("黄金ETF(深)","a_stock"),
    "518880.SS":("黄金ETF(沪)","a_stock"),"512010.SS":("医药ETF","a_stock"),
    "512660.SS":("军工ETF","a_stock"),"512480.SS":("半导体ETF","a_stock"),
    "515700.SS":("新能车ETF","a_stock"),"159601.SZ":("港股通科技ETF","a_stock"),
    "513050.SS":("中概互联ETF","a_stock"),"513180.SS":("恒生科技ETF","a_stock"),
},

# ━━━ 6. 外汇主要货币对 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"💱 外汇 - 主要货币对": {
    "EURUSD=X":("EUR/USD","forex"),"GBPUSD=X":("GBP/USD","forex"),
    "USDJPY=X":("USD/JPY","forex"),"USDCHF=X":("USD/CHF","forex"),
    "AUDUSD=X":("AUD/USD","forex"),"NZDUSD=X":("NZD/USD","forex"),
    "USDCAD=X":("USD/CAD","forex"),"USDCNH=X":("USD/CNH","forex"),
    "USDHKD=X":("USD/HKD","forex"),"USDSGD=X":("USD/SGD","forex"),
    "USDINR=X":("USD/INR","forex"),"USDKRW=X":("USD/KRW","forex"),
    "USDTWD=X":("USD/TWD","forex"),"USDMYR=X":("USD/MYR","forex"),
    "USDTHB=X":("USD/THB","forex"),"USDIDR=X":("USD/IDR","forex"),
    "USDPHP=X":("USD/PHP","forex"),"USDVND=X":("USD/VND","forex"),
    "USDBRL=X":("USD/BRL","forex"),"USDMXN=X":("USD/MXN","forex"),
    "USDZAR=X":("USD/ZAR","forex"),"USDTRY=X":("USD/TRY","forex"),
    "USDRUB=X":("USD/RUB","forex"),"USDSAR=X":("USD/SAR","forex"),
    "USDAED=X":("USD/AED","forex"),"USDSEK=X":("USD/SEK","forex"),
    "USDNOK=X":("USD/NOK","forex"),"USDDKK=X":("USD/DKK","forex"),
    "USDPLN=X":("USD/PLN","forex"),"USDHUF=X":("USD/HUF","forex"),
    "USDCZK=X":("USD/CZK","forex"),"USDILS=X":("USD/ILS","forex"),
},

# ━━━ 7. 外汇交叉货币对 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"💱 外汇 - 交叉货币对": {
    "EURGBP=X":("EUR/GBP","forex"),"EURJPY=X":("EUR/JPY","forex"),
    "EURCHF=X":("EUR/CHF","forex"),"EURAUD=X":("EUR/AUD","forex"),
    "EURCAD=X":("EUR/CAD","forex"),"EURNZD=X":("EUR/NZD","forex"),
    "EURSEK=X":("EUR/SEK","forex"),"EURNOK=X":("EUR/NOK","forex"),
    "EURDKK=X":("EUR/DKK","forex"),"EURPLN=X":("EUR/PLN","forex"),
    "GBPJPY=X":("GBP/JPY","forex"),"GBPCHF=X":("GBP/CHF","forex"),
    "GBPAUD=X":("GBP/AUD","forex"),"GBPCAD=X":("GBP/CAD","forex"),
    "GBPNZD=X":("GBP/NZD","forex"),"GBPSGD=X":("GBP/SGD","forex"),
    "AUDJPY=X":("AUD/JPY","forex"),"AUDNZD=X":("AUD/NZD","forex"),
    "AUDCAD=X":("AUD/CAD","forex"),"AUDCHF=X":("AUD/CHF","forex"),
    "AUDSGD=X":("AUD/SGD","forex"),"CADJPY=X":("CAD/JPY","forex"),
    "CADCHF=X":("CAD/CHF","forex"),"NZDJPY=X":("NZD/JPY","forex"),
    "NZDCAD=X":("NZD/CAD","forex"),"CHFJPY=X":("CHF/JPY","forex"),
    "SGDJPY=X":("SGD/JPY","forex"),"EURSGD=X":("EUR/SGD","forex"),
    "EURCNH=X":("EUR/CNH","forex"),"GBPCNH=X":("GBP/CNH","forex"),
},

# ━━━ 8. 美国 ETF ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇺🇸 美国 ETF - 宽基": {
    "SPY":("SPDR S&P500","us_etf"),"QQQ":("Invesco NASDAQ100","us_etf"),
    "IWM":("iShares Russell2000","us_etf"),"DIA":("道琼斯 ETF","us_etf"),
    "VTI":("Vanguard全美股","us_etf"),"VOO":("Vanguard S&P500","us_etf"),
    "VEA":("Vanguard发达市场","us_etf"),"VWO":("Vanguard新兴市场","us_etf"),
    "EEM":("iShares新兴市场","us_etf"),"EFA":("iShares发达市场","us_etf"),
    "ACWI":("全球股票ETF","us_etf"),"VT":("全球全市场ETF","us_etf"),
    "SPDW":("SPDR发达市场","us_etf"),"SPEM":("SPDR新兴市场","us_etf"),
    "TLT":("20+年国债ETF","us_etf"),"IEF":("7-10年国债ETF","us_etf"),
    "SHY":("1-3年国债ETF","us_etf"),"BND":("全债券市场ETF","us_etf"),
    "LQD":("投资级公司债ETF","us_etf"),"HYG":("高收益债ETF","us_etf"),
    "JNK":("SPDR高收益债","us_etf"),"TIPS":("通胀保护债ETF","us_etf"),
    "GLD":("SPDR黄金ETF","us_etf"),"IAU":("iShares黄金ETF","us_etf"),
    "SLV":("白银ETF","us_etf"),"PDBC":("大宗商品ETF","us_etf"),
    "USO":("美国原油ETF","us_etf"),"UNG":("天然气ETF","us_etf"),
    "DBC":("PowerShares大宗","us_etf"),"PALL":("钯金ETF","us_etf"),
},

# ━━━ 9. 美国行业 ETF ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇺🇸 美国 ETF - 行业": {
    "XLK":("科技行业","us_etf"),"XLF":("金融行业","us_etf"),
    "XLV":("医疗行业","us_etf"),"XLE":("能源行业","us_etf"),
    "XLI":("工业行业","us_etf"),"XLY":("非必需消费","us_etf"),
    "XLP":("必需消费","us_etf"),"XLU":("公用事业","us_etf"),
    "XLB":("材料行业","us_etf"),"XLRE":("房地产","us_etf"),
    "XLC":("通信行业","us_etf"),"SOXX":("费城半导体ETF","us_etf"),
    "SMH":("VanEck半导体","us_etf"),"IGV":("软件ETF","us_etf"),
    "SKYY":("云计算ETF","us_etf"),"CLOU":("云计算ETF2","us_etf"),
    "HACK":("网络安全ETF","us_etf"),"CIBR":("网络安全ETF2","us_etf"),
    "ROBO":("机器人ETF","us_etf"),"BOTZ":("AI机器人ETF","us_etf"),
    "AIQ":("AI & 大数据ETF","us_etf"),"ARKK":("ARK创新ETF","us_etf"),
    "ARKG":("ARK基因组ETF","us_etf"),"ARKW":("ARK互联网ETF","us_etf"),
    "ARKX":("ARK航天ETF","us_etf"),"ARKF":("ARK金融科技ETF","us_etf"),
    "GDX":("黄金矿业ETF","us_etf"),"GDXJ":("初级黄金矿ETF","us_etf"),
    "XME":("金属矿业ETF","us_etf"),"COPX":("铜矿ETF","us_etf"),
    "IBIT":("BTC ETF(BlackRock)","us_etf"),"FBTC":("BTC ETF(Fidelity)","us_etf"),
    "BITB":("BTC ETF(Bitwise)","us_etf"),"ETHA":("ETH ETF(BlackRock)","us_etf"),
    "ITB":("房屋建筑ETF","us_etf"),"XHB":("房屋ETF","us_etf"),
    "KRE":("地区银行ETF","us_etf"),"KBE":("银行ETF","us_etf"),
    "IBB":("生物科技ETF","us_etf"),"XBI":("SPDR生物科技","us_etf"),
    "PBW":("清洁能源ETF","us_etf"),"ICLN":("全球清洁能源","us_etf"),
    "TAN":("太阳能ETF","us_etf"),"FAN":("风能ETF","us_etf"),
    "REMX":("稀土ETF","us_etf"),"LIT":("锂电ETF","us_etf"),
    "BATT":("电池ETF","us_etf"),"DRIV":("EV驾驶ETF","us_etf"),
    "FXI":("中国大盘ETF","us_etf"),"KWEB":("中国互联网ETF","us_etf"),
    "MCHI":("MSCI中国ETF","us_etf"),"CQQQ":("中国科技ETF","us_etf"),
    "EWJ":("日本ETF","us_etf"),"EWG":("德国ETF","us_etf"),
    "EWU":("英国ETF","us_etf"),"EWZ":("巴西ETF","us_etf"),
    "EWA":("澳大利亚ETF","us_etf"),"EWC":("加拿大ETF","us_etf"),
    "EWI":("意大利ETF","us_etf"),"EWP":("西班牙ETF","us_etf"),
    "EWQ":("法国ETF","us_etf"),"EWS":("新加坡ETF","us_etf"),
    "EWT":("台湾ETF","us_etf"),"EWY":("韩国ETF","us_etf"),
    "INDA":("印度ETF","us_etf"),"VNM":("越南ETF","us_etf"),
    "RSX":("俄罗斯ETF","us_etf"),"RSP":("S&P500等权ETF","us_etf"),
    "VOE":("中盘价值ETF","us_etf"),"VBR":("小盘价值ETF","us_etf"),
    "IWF":("Russell1000成长","us_etf"),"IWD":("Russell1000价值","us_etf"),
    "MTUM":("动量因子ETF","us_etf"),"USMV":("低波动ETF","us_etf"),
    "QUAL":("质量因子ETF","us_etf"),"VLUE":("价值因子ETF","us_etf"),
},

# ━━━ 10. 美股科技旗舰 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇺🇸 美股 - 科技旗舰": {
    "AAPL":("Apple","us_tech"),"MSFT":("Microsoft","us_tech"),
    "NVDA":("NVIDIA","us_tech"),"GOOGL":("Alphabet A","us_tech"),
    "GOOG":("Alphabet C","us_tech"),"META":("Meta","us_tech"),
    "TSLA":("Tesla","us_tech"),"AMZN":("Amazon","us_tech"),
    "AVGO":("Broadcom","us_tech"),"ORCL":("Oracle","us_tech"),
    "CSCO":("Cisco","us_tech"),"IBM":("IBM","us_tech"),
    "ACN":("Accenture","us_tech"),"ADSK":("Autodesk","us_tech"),
    "CDNS":("Cadence Design","us_tech"),"SNPS":("Synopsys","us_tech"),
    "ANET":("Arista Networks","us_tech"),"DELL":("Dell","us_tech"),
    "HPQ":("HP Inc","us_tech"),"HPE":("HP Enterprise","us_tech"),
    "NTAP":("NetApp","us_tech"),"WDC":("Western Digital","us_tech"),
    "STX":("Seagate","us_tech"),"PSTG":("Pure Storage","us_tech"),
    "PANW":("Palo Alto","us_tech"),"FTNT":("Fortinet","us_tech"),
},

# ━━━ 11. 美股半导体 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇺🇸 美股 - 半导体": {
    "AMD":("AMD","us_semi"),"INTC":("Intel","us_semi"),
    "QCOM":("Qualcomm","us_semi"),"TXN":("Texas Instruments","us_semi"),
    "MU":("Micron","us_semi"),"AMAT":("Applied Materials","us_semi"),
    "LRCX":("Lam Research","us_semi"),"KLAC":("KLA Corp","us_semi"),
    "MRVL":("Marvell","us_semi"),"SMCI":("SuperMicro","us_semi"),
    "ARM":("ARM Holdings","us_semi"),"ON":("ON Semiconductor","us_semi"),
    "MPWR":("Monolithic Power","us_semi"),"ADI":("Analog Devices","us_semi"),
    "MCHP":("Microchip Tech","us_semi"),"SWKS":("Skyworks","us_semi"),
    "QRVO":("Qorvo","us_semi"),"NXPI":("NXP Semi","us_semi"),
    "ASML":("ASML ADR","us_semi"),"TSM":("TSMC ADR","us_semi"),
    "UMC":("UMC ADR","us_semi"),"ACLS":("Axcelis Tech","us_semi"),
    "WOLF":("Wolfspeed","us_semi"),"FORM":("FormFactor","us_semi"),
    "ICHR":("Ichor Holdings","us_semi"),"ONTO":("Onto Innovation","us_semi"),
},

# ━━━ 12. 美股软件/云/AI ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇺🇸 美股 - 软件/云/AI": {
    "CRM":("Salesforce","us_sw"),"NOW":("ServiceNow","us_sw"),
    "ADBE":("Adobe","us_sw"),"INTU":("Intuit","us_sw"),
    "WDAY":("Workday","us_sw"),"TEAM":("Atlassian","us_sw"),
    "DDOG":("Datadog","us_sw"),"MDB":("MongoDB","us_sw"),
    "SNOW":("Snowflake","us_sw"),"PLTR":("Palantir","us_sw"),
    "ZM":("Zoom","us_sw"),"HUBS":("HubSpot","us_sw"),
    "GTLB":("GitLab","us_sw"),"ZI":("ZoomInfo","us_sw"),
    "BILL":("Bill.com","us_sw"),"PCTY":("Paylocity","us_sw"),
    "PAYC":("Paycom","us_sw"),"SMAR":("Smartsheet","us_sw"),
    "BOX":("Box","us_sw"),"DOCN":("DigitalOcean","us_sw"),
    "CFLT":("Confluent","us_sw"),"DBTX":("Definitive Healthcare","us_sw"),
    "AI":("C3.ai","us_sw"),"BBAI":("BigBear.ai","us_sw"),
    "IREN":("Iris Energy","us_sw"),"IONQ":("IonQ量子","us_sw"),
    "RGTI":("Rigetti Computing","us_sw"),"QUBT":("Quantum Computing","us_sw"),
},

# ━━━ 13. 美股网络安全 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇺🇸 美股 - 网络安全/企业软件": {
    "CRWD":("CrowdStrike","us_cyber"),"ZS":("Zscaler","us_cyber"),
    "OKTA":("Okta","us_cyber"),"S":("SentinelOne","us_cyber"),
    "CYBR":("CyberArk","us_cyber"),"CHKP":("Check Point","us_cyber"),
    "NET":("Cloudflare","us_cyber"),"QLYS":("Qualys","us_cyber"),
    "TENB":("Tenable","us_cyber"),"RPD":("Rapid7","us_cyber"),
    "VRNS":("Varonis","us_cyber"),"SAIL":("SailPoint","us_cyber"),
    "PATH":("UiPath","us_cyber"),"APPN":("Appian","us_cyber"),
    "PEGA":("Pegasystems","us_cyber"),"ALTR":("Altair Eng","us_cyber"),
    "ANSS":("Ansys","us_cyber"),"PTC":("PTC Inc","us_cyber"),
    "SAIC":("SAIC","us_cyber"),"CACI":("CACI Intl","us_cyber"),
},

# ━━━ 14. 美股互联网/电商/社媒 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇺🇸 美股 - 互联网/电商/社媒": {
    "UBER":("Uber","us_internet"),"LYFT":("Lyft","us_internet"),
    "DASH":("DoorDash","us_internet"),"ABNB":("Airbnb","us_internet"),
    "BKNG":("Booking Holdings","us_internet"),"EXPE":("Expedia","us_internet"),
    "TRIP":("TripAdvisor","us_internet"),"DESP":("Despegar","us_internet"),
    "SHOP":("Shopify","us_internet"),"ETSY":("Etsy","us_internet"),
    "EBAY":("eBay","us_internet"),"W":("Wayfair","us_internet"),
    "SNAP":("Snap","us_internet"),"PINS":("Pinterest","us_internet"),
    "RDDT":("Reddit","us_internet"),"BMBL":("Bumble","us_internet"),
    "MTCH":("Match Group","us_internet"),"IAC":("IAC","us_internet"),
    "APP":("AppLovin","us_internet"),"TTD":("Trade Desk","us_internet"),
    "MGNI":("Magnite","us_internet"),"DV":("DoubleVerify","us_internet"),
    "RBLX":("Roblox","us_internet"),"U":("Unity","us_internet"),
    "NFLX":("Netflix","us_internet"),"SPOT":("Spotify","us_internet"),
    "DIS":("Disney","us_internet"),"CMCSA":("Comcast","us_internet"),
    "WBD":("Warner Bros","us_internet"),"PARA":("Paramount","us_internet"),
    "FOXA":("Fox A","us_internet"),"SIRI":("Sirius XM","us_internet"),
},

# ━━━ 15. 美股金融科技/支付/加密 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇺🇸 美股 - 金融科技/支付/加密": {
    "V":("Visa","us_fintech"),"MA":("Mastercard","us_fintech"),
    "AXP":("American Express","us_fintech"),"PYPL":("PayPal","us_fintech"),
    "SQ":("Block","us_fintech"),"COIN":("Coinbase","us_fintech"),
    "MSTR":("MicroStrategy","us_fintech"),"HOOD":("Robinhood","us_fintech"),
    "AFRM":("Affirm","us_fintech"),"SOFI":("SoFi","us_fintech"),
    "UPST":("Upstart","us_fintech"),"LC":("LendingClub","us_fintech"),
    "OPFI":("OppFi","us_fintech"),"LPRO":("Open Lending","us_fintech"),
    "FI":("Fiserv","us_fintech"),"FIS":("FIS","us_fintech"),
    "GPN":("Global Payments","us_fintech"),"WEX":("WEX Inc","us_fintech"),
    "FOUR":("Shift4","us_fintech"),"DLO":("dLocal","us_fintech"),
    "STNE":("StoneCo","us_fintech"),"NU":("Nu Holdings","us_fintech"),
    "MELI":("MercadoLibre","us_fintech"),"XYZ":("Block+","us_fintech"),
    "HUT":("Hut 8 Mining","us_fintech"),"RIOT":("Riot Platforms","us_fintech"),
    "MARA":("Marathon Digital","us_fintech"),"CLSK":("CleanSpark","us_fintech"),
    "BTBT":("Bit Digital","us_fintech"),"CIFR":("Cipher Mining","us_fintech"),
},

# ━━━ 16. 美股传统金融/银行/保险 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇺🇸 美股 - 银行/金融/保险": {
    "JPM":("JPMorgan","us_bank"),"BAC":("Bank of America","us_bank"),
    "GS":("Goldman Sachs","us_bank"),"MS":("Morgan Stanley","us_bank"),
    "WFC":("Wells Fargo","us_bank"),"C":("Citigroup","us_bank"),
    "USB":("US Bancorp","us_bank"),"PNC":("PNC Financial","us_bank"),
    "TFC":("Truist","us_bank"),"COF":("Capital One","us_bank"),
    "RF":("Regions Financial","us_bank"),"CFG":("Citizens Financial","us_bank"),
    "FITB":("Fifth Third","us_bank"),"HBAN":("Huntington Bancshares","us_bank"),
    "KEY":("KeyCorp","us_bank"),"MTB":("M&T Bank","us_bank"),
    "BLK":("BlackRock","us_bank"),"SCHW":("Charles Schwab","us_bank"),
    "BRK-B":("Berkshire Hathaway B","us_bank"),"BX":("Blackstone","us_bank"),
    "KKR":("KKR","us_bank"),"APO":("Apollo Global","us_bank"),
    "ARES":("Ares Management","us_bank"),"CG":("Carlyle Group","us_bank"),
    "SPGI":("S&P Global","us_bank"),"MCO":("Moody's","us_bank"),
    "ICE":("ICE","us_bank"),"CME":("CME Group","us_bank"),
    "CBOE":("CBOE Global","us_bank"),"NDAQ":("Nasdaq Inc","us_bank"),
    "BRK-A":("Berkshire A","us_bank"),"MKL":("Markel Corp","us_bank"),
    "AIG":("AIG","us_bank"),"MET":("MetLife","us_bank"),
    "PRU":("Prudential","us_bank"),"AFL":("Aflac","us_bank"),
    "ALL":("Allstate","us_bank"),"TRV":("Travelers","us_bank"),
    "CB":("Chubb","us_bank"),"PGR":("Progressive","us_bank"),
    "HIG":("Hartford Financial","us_bank"),"EG":("Everest Group","us_bank"),
},

# ━━━ 17. 美股医疗/制药/生物科技 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇺🇸 美股 - 医疗/制药/生物科技": {
    "JNJ":("J&J","us_health"),"UNH":("UnitedHealth","us_health"),
    "LLY":("Eli Lilly","us_health"),"PFE":("Pfizer","us_health"),
    "ABBV":("AbbVie","us_health"),"MRK":("Merck","us_health"),
    "BMY":("Bristol-Myers","us_health"),"AMGN":("Amgen","us_health"),
    "GILD":("Gilead","us_health"),"MRNA":("Moderna","us_health"),
    "BNTX":("BioNTech","us_health"),"REGN":("Regeneron","us_health"),
    "VRTX":("Vertex","us_health"),"BIIB":("Biogen","us_health"),
    "ISRG":("Intuitive Surgical","us_health"),"MDT":("Medtronic","us_health"),
    "ABT":("Abbott","us_health"),"TMO":("ThermoFisher","us_health"),
    "DHR":("Danaher","us_health"),"SYK":("Stryker","us_health"),
    "BSX":("Boston Scientific","us_health"),"EW":("Edwards Lifesciences","us_health"),
    "ZBH":("Zimmer Biomet","us_health"),"HOLX":("Hologic","us_health"),
    "IDXX":("IDEXX Labs","us_health"),"IQV":("IQVIA","us_health"),
    "A":("Agilent","us_health"),"WAT":("Waters Corp","us_health"),
    "HCA":("HCA Healthcare","us_health"),"CNC":("Centene","us_health"),
    "CVS":("CVS Health","us_health"),"CI":("Cigna","us_health"),
    "HUM":("Humana","us_health"),"ANTM":("Elevance Health","us_health"),
    "NVO":("Novo Nordisk ADR","us_health"),"AZN":("AstraZeneca ADR","us_health"),
    "GSK":("GSK ADR","us_health"),"SNY":("Sanofi ADR","us_health"),
    "RHHBY":("Roche ADR","us_health"),"NVS":("Novartis ADR","us_health"),
},

# ━━━ 18. 美股消费/零售/食品饮料 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇺🇸 美股 - 消费/零售/食品": {
    "WMT":("Walmart","us_consumer"),"COST":("Costco","us_consumer"),
    "TGT":("Target","us_consumer"),"HD":("Home Depot","us_consumer"),
    "LOW":("Lowe's","us_consumer"),"BBY":("Best Buy","us_consumer"),
    "DG":("Dollar General","us_consumer"),"DLTR":("Dollar Tree","us_consumer"),
    "MCD":("McDonald's","us_consumer"),"SBUX":("Starbucks","us_consumer"),
    "CMG":("Chipotle","us_consumer"),"YUM":("Yum! Brands","us_consumer"),
    "DPZ":("Domino's","us_consumer"),"QSR":("Restaurant Brands","us_consumer"),
    "WING":("Wingstop","us_consumer"),"SHAK":("Shake Shack","us_consumer"),
    "NKE":("Nike","us_consumer"),"LULU":("Lululemon","us_consumer"),
    "UAA":("Under Armour","us_consumer"),"RL":("Ralph Lauren","us_consumer"),
    "TPR":("Tapestry","us_consumer"),"CPRI":("Capri Holdings","us_consumer"),
    "PG":("P&G","us_consumer"),"KO":("Coca-Cola","us_consumer"),
    "PEP":("PepsiCo","us_consumer"),"KDP":("Keurig Dr Pepper","us_consumer"),
    "MNST":("Monster Beverage","us_consumer"),"STZ":("Constellation Brands","us_consumer"),
    "BUD":("Anheuser-Busch ADR","us_consumer"),"TAP":("Molson Coors","us_consumer"),
    "PM":("Philip Morris","us_consumer"),"MO":("Altria","us_consumer"),
    "BTI":("British American ADR","us_consumer"),
    "MDLZ":("Mondelez","us_consumer"),"GIS":("General Mills","us_consumer"),
    "K":("Kellanova","us_consumer"),"CPB":("Campbell Soup","us_consumer"),
    "HSY":("Hershey","us_consumer"),"LANC":("Lancaster Colony","us_consumer"),
    "CL":("Colgate-Palmolive","us_consumer"),"KMB":("Kimberly-Clark","us_consumer"),
    "EL":("Estee Lauder","us_consumer"),"ULTA":("Ulta Beauty","us_consumer"),
    "AMZN":("Amazon","us_consumer"),
},

# ━━━ 19. 美股能源 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇺🇸 美股 - 能源": {
    "XOM":("ExxonMobil","us_energy"),"CVX":("Chevron","us_energy"),
    "COP":("ConocoPhillips","us_energy"),"SLB":("SLB","us_energy"),
    "OXY":("Occidental","us_energy"),"EOG":("EOG Resources","us_energy"),
    "DVN":("Devon Energy","us_energy"),"MPC":("Marathon Petroleum","us_energy"),
    "PSX":("Phillips 66","us_energy"),"VLO":("Valero","us_energy"),
    "HES":("Hess","us_energy"),"HAL":("Halliburton","us_energy"),
    "BKR":("Baker Hughes","us_energy"),"APA":("APA Corp","us_energy"),
    "EQT":("EQT Corp","us_energy"),"AR":("Antero Resources","us_energy"),
    "CTRA":("Coterra Energy","us_energy"),"MGY":("Magnolia Oil","us_energy"),
    "OKE":("ONEOK","us_energy"),"KMI":("Kinder Morgan","us_energy"),
    "WMB":("Williams Companies","us_energy"),"LNG":("Cheniere Energy","us_energy"),
    "ET":("Energy Transfer","us_energy"),"EPD":("Enterprise Products","us_energy"),
    "MMP":("Magellan Midstream","us_energy"),"PAA":("Plains All American","us_energy"),
    "FCX":("Freeport-McMoRan","us_energy"),"NEM":("Newmont","us_energy"),
    "GOLD":("Barrick Gold","us_energy"),"KGC":("Kinross Gold","us_energy"),
    "AEM":("Agnico Eagle","us_energy"),"WPM":("Wheaton Precious","us_energy"),
    "FNV":("Franco-Nevada","us_energy"),"RGLD":("Royal Gold","us_energy"),
},

# ━━━ 20. 美股工业/国防/航空/运输 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇺🇸 美股 - 工业/国防/航空/运输": {
    "BA":("Boeing","us_ind"),"GE":("GE Aerospace","us_ind"),
    "CAT":("Caterpillar","us_ind"),"HON":("Honeywell","us_ind"),
    "LMT":("Lockheed Martin","us_ind"),"RTX":("RTX Corp","us_ind"),
    "NOC":("Northrop Grumman","us_ind"),"GD":("General Dynamics","us_ind"),
    "LHX":("L3Harris","us_ind"),"HII":("Huntington Ingalls","us_ind"),
    "TDG":("TransDigm","us_ind"),"HEI":("HEICO","us_ind"),
    "SPR":("Spirit AeroSystems","us_ind"),"AXON":("Axon Enterprise","us_ind"),
    "DE":("Deere & Co","us_ind"),"CNHI":("CNH Industrial","us_ind"),
    "AGCO":("AGCO Corp","us_ind"),"ITW":("Illinois Tool","us_ind"),
    "EMR":("Emerson Electric","us_ind"),"ETN":("Eaton Corp","us_ind"),
    "PH":("Parker Hannifin","us_ind"),"AME":("AMETEK","us_ind"),
    "ROK":("Rockwell Automation","us_ind"),"MMM":("3M","us_ind"),
    "ROP":("Roper Technologies","us_ind"),"IEX":("IDEX Corp","us_ind"),
    "UAL":("United Airlines","us_ind"),"DAL":("Delta Airlines","us_ind"),
    "AAL":("American Airlines","us_ind"),"LUV":("Southwest Airlines","us_ind"),
    "ALK":("Alaska Air","us_ind"),"CCL":("Carnival Cruise","us_ind"),
    "RCL":("Royal Caribbean","us_ind"),"NCLH":("Norwegian Cruise","us_ind"),
    "UPS":("UPS","us_ind"),"FDX":("FedEx","us_ind"),
    "XPO":("XPO Logistics","us_ind"),"CHRW":("CH Robinson","us_ind"),
    "CSX":("CSX Corp","us_ind"),"UNP":("Union Pacific","us_ind"),
    "NSC":("Norfolk Southern","us_ind"),"CP":("Canadian Pacific","us_ind"),
},

# ━━━ 21. 美股新能源/EV/公用事业 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇺🇸 美股 - 新能源/EV/公用": {
    "NEE":("NextEra Energy","us_util"),"DUK":("Duke Energy","us_util"),
    "SO":("Southern Co","us_util"),"D":("Dominion Energy","us_util"),
    "AEP":("American Electric","us_util"),"EXC":("Exelon","us_util"),
    "CEG":("Constellation Energy","us_util"),"VST":("Vistra Energy","us_util"),
    "NRG":("NRG Energy","us_util"),"AES":("AES Corp","us_util"),
    "AWK":("American Water Works","us_util"),"PCG":("PG&E","us_util"),
    "ED":("Consolidated Edison","us_util"),"WEC":("WEC Energy","us_util"),
    "FSLR":("First Solar","us_ev"),"ENPH":("Enphase Energy","us_ev"),
    "SEDG":("SolarEdge","us_ev"),"RUN":("Sunrun","us_ev"),
    "ARRY":("Array Technologies","us_ev"),"SPWR":("SunPower","us_ev"),
    "RIVN":("Rivian","us_ev"),"LCID":("Lucid Motors","us_ev"),
    "PSNY":("Polestar","us_ev"),"CHPT":("ChargePoint","us_ev"),
    "BLNK":("Blink Charging","us_ev"),"EVGO":("EVgo","us_ev"),
    "BE":("Bloom Energy","us_ev"),"PLUG":("Plug Power","us_ev"),
    "HYLN":("Hyliion","us_ev"),"NKLA":("Nikola","us_ev"),
    "QS":("QuantumScape","us_ev"),"GOEV":("Canoo","us_ev"),
},

# ━━━ 22. 美股房地产/REIT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇺🇸 美股 - 房地产/REIT": {
    "AMT":("American Tower","us_reit"),"PLD":("Prologis","us_reit"),
    "EQIX":("Equinix","us_reit"),"CCI":("Crown Castle","us_reit"),
    "SPG":("Simon Property","us_reit"),"PSA":("Public Storage","us_reit"),
    "O":("Realty Income","us_reit"),"VICI":("VICI Properties","us_reit"),
    "WELL":("Welltower","us_reit"),"VTR":("Ventas","us_reit"),
    "AVB":("AvalonBay","us_reit"),"EQR":("Equity Residential","us_reit"),
    "DLR":("Digital Realty","us_reit"),"ARE":("Alexandria RE","us_reit"),
    "BXP":("BXP Inc","us_reit"),"KIM":("Kimco Realty","us_reit"),
    "NNN":("NNN REIT","us_reit"),"WPC":("W.P.Carey","us_reit"),
    "SBA":("SBA Communications","us_reit"),"IRM":("Iron Mountain","us_reit"),
    "Z":("Zillow","us_reit"),"RDFN":("Redfin","us_reit"),
    "TOL":("Toll Brothers","us_reit"),"LEN":("Lennar","us_reit"),
    "DHI":("D.R.Horton","us_reit"),"PHM":("PulteGroup","us_reit"),
},

# ━━━ 23. 中概 ADR ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇨🇳 中概 ADR": {
    "BIDU":("百度","cn_adr"),"PDD":("拼多多/Temu","cn_adr"),
    "JD":("京东","cn_adr"),"BABA":("阿里巴巴","cn_adr"),
    "NTES":("网易","cn_adr"),"IQ":("爱奇艺","cn_adr"),
    "TCOM":("携程","cn_adr"),"TAL":("好未来","cn_adr"),
    "EDU":("新东方","cn_adr"),"NIO":("蔚来","cn_adr"),
    "XPEV":("小鹏汽车","cn_adr"),"LI":("理想汽车","cn_adr"),
    "FUTU":("富途控股","cn_adr"),"TIGR":("老虎证券","cn_adr"),
    "QFIN":("360数科","cn_adr"),"GDS":("万国数据","cn_adr"),
    "YUMC":("百胜中国","cn_adr"),"RLX":("雾芯科技","cn_adr"),
    "WB":("微博","cn_adr"),"VNET":("世纪互联","cn_adr"),
    "CAN":("嘉楠科技","cn_adr"),"KC":("酷狗音乐","cn_adr"),
    "RERE":("爱回收","cn_adr"),"ZK":("卓健科技","cn_adr"),
    "LAIX":("乂学教育","cn_adr"),"DAO":("道可道","cn_adr"),
    "DIDI":("滴滴出行","cn_adr"),"GOTU":("跟谁学","cn_adr"),
},

# ━━━ 24. 港股 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇭🇰 港股 (HKEX)": {
    "9988.HK":("阿里巴巴","hk_stock"),"0700.HK":("腾讯","hk_stock"),
    "3690.HK":("美团","hk_stock"),"9618.HK":("京东","hk_stock"),
    "1810.HK":("小米","hk_stock"),"9999.HK":("网易","hk_stock"),
    "2318.HK":("中国平安","hk_stock"),"1299.HK":("友邦保险","hk_stock"),
    "941.HK":("中国移动","hk_stock"),"762.HK":("中国联通","hk_stock"),
    "728.HK":("中国电信HK","hk_stock"),"386.HK":("中国石化","hk_stock"),
    "857.HK":("中国石油","hk_stock"),"883.HK":("中国海洋石油","hk_stock"),
    "1024.HK":("快手","hk_stock"),"3968.HK":("招商银行HK","hk_stock"),
    "2388.HK":("中银香港","hk_stock"),"1398.HK":("工商银行HK","hk_stock"),
    "3988.HK":("中国银行HK","hk_stock"),"2628.HK":("中国人寿HK","hk_stock"),
    "2269.HK":("药明生物","hk_stock"),"9868.HK":("小鹏HK","hk_stock"),
    "9626.HK":("哔哩哔哩HK","hk_stock"),"1211.HK":("比亚迪HK","hk_stock"),
    "2333.HK":("长城汽车HK","hk_stock"),"175.HK":("吉利汽车","hk_stock"),
    "2015.HK":("理想HK","hk_stock"),"6690.HK":("海尔智家HK","hk_stock"),
    "9961.HK":("携程HK","hk_stock"),"2020.HK":("安踏体育","hk_stock"),
    "1177.HK":("中国生物制药","hk_stock"),"2382.HK":("舜宇光学","hk_stock"),
    "3888.HK":("金山软件","hk_stock"),"669.HK":("创科实业","hk_stock"),
    "267.HK":("中信股份","hk_stock"),"5.HK":("汇丰控股","hk_stock"),
    "2.HK":("中国电力","hk_stock"),"6.HK":("电能实业","hk_stock"),
    "12.HK":("恒基地产","hk_stock"),"16.HK":("长实集团","hk_stock"),
    "1.HK":("长和实业","hk_stock"),"17.HK":("新世界发展","hk_stock"),
    "101.HK":("恒隆地产","hk_stock"),"823.HK":("领展房托","hk_stock"),
},

# ━━━ 25. A股 - 上证蓝筹 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇨🇳 A股 - 上证蓝筹": {
    "600519.SS":("贵州茅台","a_stock"),"601318.SS":("中国平安","a_stock"),
    "600036.SS":("招商银行","a_stock"),"601166.SS":("兴业银行","a_stock"),
    "600900.SS":("长江电力","a_stock"),"601988.SS":("中国银行","a_stock"),
    "601398.SS":("工商银行","a_stock"),"601288.SS":("农业银行","a_stock"),
    "601939.SS":("建设银行","a_stock"),"601328.SS":("交通银行","a_stock"),
    "600276.SS":("恒瑞医药","a_stock"),"601628.SS":("中国人寿","a_stock"),
    "600309.SS":("万华化学","a_stock"),"600887.SS":("伊利股份","a_stock"),
    "600104.SS":("上汽集团","a_stock"),"600028.SS":("中国石化","a_stock"),
    "601857.SS":("中国石油","a_stock"),"601088.SS":("中国神华","a_stock"),
    "600030.SS":("中信证券","a_stock"),"601601.SS":("中国太保","a_stock"),
    "603288.SS":("海天味业","a_stock"),"601012.SS":("隆基绿能","a_stock"),
    "600585.SS":("海螺水泥","a_stock"),"600941.SS":("中国移动A","a_stock"),
    "600690.SS":("海尔智家","a_stock"),"601111.SS":("中国国航","a_stock"),
    "601919.SS":("中远海控","a_stock"),"600048.SS":("保利发展","a_stock"),
    "601390.SS":("中国中铁","a_stock"),"600031.SS":("三一重工","a_stock"),
    "600018.SS":("上港集团","a_stock"),"600050.SS":("中国联通A","a_stock"),
    "601668.SS":("中国建筑","a_stock"),"601800.SS":("中国交建","a_stock"),
    "600606.SS":("绿地控股","a_stock"),"603259.SS":("药明康德","a_stock"),
    "603986.SS":("兆易创新","a_stock"),"688981.SS":("中芯国际","a_stock"),
    "688036.SS":("传音控股","a_stock"),"688099.SS":("晶晨股份","a_stock"),
},

# ━━━ 26. A股 - 深证/创业板 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇨🇳 A股 - 深证/创业板": {
    "000858.SZ":("五粮液","a_stock"),"002594.SZ":("比亚迪","a_stock"),
    "300750.SZ":("宁德时代","a_stock"),"000333.SZ":("美的集团","a_stock"),
    "002415.SZ":("海康威视","a_stock"),"000651.SZ":("格力电器","a_stock"),
    "002142.SZ":("宁波银行","a_stock"),"000001.SZ":("平安银行","a_stock"),
    "002475.SZ":("立讯精密","a_stock"),"300059.SZ":("东方财富","a_stock"),
    "300015.SZ":("爱尔眼科","a_stock"),"000725.SZ":("京东方A","a_stock"),
    "300760.SZ":("迈瑞医疗","a_stock"),"002714.SZ":("牧原股份","a_stock"),
    "300274.SZ":("阳光电源","a_stock"),"000100.SZ":("TCL科技","a_stock"),
    "002049.SZ":("紫光国微","a_stock"),"000002.SZ":("万科A","a_stock"),
    "002352.SZ":("顺丰控股","a_stock"),"300122.SZ":("智飞生物","a_stock"),
    "300014.SZ":("亿纬锂能","a_stock"),"002027.SZ":("分众传媒","a_stock"),
    "002230.SZ":("科大讯飞","a_stock"),"300999.SZ":("金龙鱼","a_stock"),
    "002304.SZ":("洋河股份","a_stock"),"000895.SZ":("双汇发展","a_stock"),
    "002044.SZ":("美年健康","a_stock"),"300296.SZ":("利亚德","a_stock"),
    "002241.SZ":("歌尔股份","a_stock"),"300498.SZ":("温氏股份","a_stock"),
    "002460.SZ":("赣锋锂业","a_stock"),"002466.SZ":("天齐锂业","a_stock"),
    "300433.SZ":("蓝思科技","a_stock"),"002709.SZ":("天赐材料","a_stock"),
    "300124.SZ":("汇川技术","a_stock"),"002371.SZ":("北方华创","a_stock"),
    "300308.SZ":("中际旭创","a_stock"),"300347.SZ":("泰格医药","a_stock"),
},

# ━━━ 27. 日本股票 (TSE) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇯🇵 日本股票 (TSE)": {
    "7203.T":("丰田 Toyota","jp_stock"),"6758.T":("索尼 Sony","jp_stock"),
    "9984.T":("软银 SoftBank","jp_stock"),"6861.T":("基恩士 Keyence","jp_stock"),
    "6954.T":("发那科 Fanuc","jp_stock"),"8306.T":("三菱UFJ","jp_stock"),
    "8316.T":("三井住友 SMFG","jp_stock"),"8411.T":("瑞穗金融","jp_stock"),
    "7267.T":("本田 Honda","jp_stock"),"7751.T":("佳能 Canon","jp_stock"),
    "6501.T":("日立 Hitachi","jp_stock"),"6702.T":("富士通 Fujitsu","jp_stock"),
    "4063.T":("信越化学","jp_stock"),"4519.T":("中外制药","jp_stock"),
    "4502.T":("武田制药 Takeda","jp_stock"),"4503.T":("安斯泰来","jp_stock"),
    "2914.T":("日本烟草 JT","jp_stock"),"8031.T":("三井物产","jp_stock"),
    "8058.T":("三菱商事","jp_stock"),"8053.T":("住友商事","jp_stock"),
    "9432.T":("日本电报电话 NTT","jp_stock"),"9433.T":("KDDI","jp_stock"),
    "9434.T":("软银电信 SBT","jp_stock"),"7974.T":("任天堂 Nintendo","jp_stock"),
    "6857.T":("爱德万测试","jp_stock"),"4661.T":("东方乐园 OLC","jp_stock"),
    "9022.T":("东海旅客铁道 JR东海","jp_stock"),"9020.T":("东日本旅客铁道","jp_stock"),
    "8801.T":("三井不动产","jp_stock"),"8802.T":("三菱地所","jp_stock"),
    "5108.T":("普利司通 Bridgestone","jp_stock"),"7269.T":("铃木汽车 Suzuki","jp_stock"),
    "7270.T":("速霸陆 Subaru","jp_stock"),"7201.T":("日产 Nissan","jp_stock"),
    "4568.T":("第一三共","jp_stock"),"4151.T":("协和麒麟","jp_stock"),
    "6367.T":("大金工业 Daikin","jp_stock"),"6098.T":("瑞可利 Recruit","jp_stock"),
},

# ━━━ 28. 韩国股票 (KRX) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇰🇷 韩国股票 (KRX)": {
    "005930.KS":("三星电子","kr_stock"),"000660.KS":("SK海力士","kr_stock"),
    "051910.KS":("LG化学","kr_stock"),"006400.KS":("三星SDI","kr_stock"),
    "035420.KS":("Naver","kr_stock"),"035720.KS":("Kakao","kr_stock"),
    "207940.KS":("三星生物","kr_stock"),"068270.KS":("赛特瑞恩 Celltrion","kr_stock"),
    "000270.KS":("起亚汽车","kr_stock"),"005380.KS":("现代汽车","kr_stock"),
    "055550.KS":("新韩金融","kr_stock"),"105560.KS":("KB金融","kr_stock"),
    "030200.KS":("KT Corp","kr_stock"),"017670.KS":("SK电信","kr_stock"),
    "003550.KS":("LG集团","kr_stock"),"034730.KS":("SK控股","kr_stock"),
    "066570.KS":("LG电子","kr_stock"),"012330.KS":("现代摩比斯","kr_stock"),
    "028260.KS":("三星物产","kr_stock"),"018260.KS":("三星SDS","kr_stock"),
    "003490.KS":("大韩航空","kr_stock"),"011200.KS":("现代重工","kr_stock"),
    "010950.KS":("S-Oil","kr_stock"),"096770.KS":("SK Innovation","kr_stock"),
    "373220.KS":("LG新能源","kr_stock"),"247540.KS":("Ecopro BM","kr_stock"),
},

# ━━━ 29. 台湾股票 (TWSE) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇹🇼 台湾股票 (TWSE)": {
    "2330.TW":("台积电 TSMC","tw_stock"),"2317.TW":("鸿海精密","tw_stock"),
    "2454.TW":("联发科 MediaTek","tw_stock"),"2412.TW":("中华电信","tw_stock"),
    "2308.TW":("台达电","tw_stock"),"2382.TW":("广达电脑","tw_stock"),
    "3711.TW":("日月光半导体","tw_stock"),"2303.TW":("联华电子 UMC","tw_stock"),
    "2357.TW":("华硕 ASUS","tw_stock"),"2353.TW":("宏碁 Acer","tw_stock"),
    "4938.TW":("和硕 Pegatron","tw_stock"),"2395.TW":("研华科技","tw_stock"),
    "1301.TW":("台塑","tw_stock"),"1303.TW":("南亚塑胶","tw_stock"),
    "1326.TW":("台化","tw_stock"),"2881.TW":("富邦金控","tw_stock"),
    "2882.TW":("国泰金控","tw_stock"),"2886.TW":("兆丰金控","tw_stock"),
    "2891.TW":("中信金控","tw_stock"),"2892.TW":("第一金控","tw_stock"),
    "2884.TW":("玉山金控","tw_stock"),"5880.TW":("合库金控","tw_stock"),
    "2886.TW":("兆丰金控","tw_stock"),"2885.TW":("元大金控","tw_stock"),
    "2207.TW":("和泰车","tw_stock"),"2474.TW":("可成科技","tw_stock"),
    "3008.TW":("大立光 Largan","tw_stock"),"2327.TW":("国巨 YAGEO","tw_stock"),
    "0050.TW":("元大台湾50ETF","tw_stock"),"0056.TW":("元大高股息ETF","tw_stock"),
    "00878.TW":("国泰永续高股息ETF","tw_stock"),
},

# ━━━ 30. 印度股票 (NSE) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇮🇳 印度股票 (NSE)": {
    "RELIANCE.NS":("信实工业 Reliance","in_stock"),
    "TCS.NS":("塔塔咨询 TCS","in_stock"),
    "HDFCBANK.NS":("HDFC银行","in_stock"),
    "INFY.NS":("Infosys","in_stock"),
    "ICICIBANK.NS":("ICICI银行","in_stock"),
    "HINDUNILVR.NS":("印度斯坦联合利华","in_stock"),
    "KOTAKBANK.NS":("科达克银行","in_stock"),
    "BHARTIARTL.NS":("Bharti Airtel","in_stock"),
    "ITC.NS":("ITC集团","in_stock"),
    "SBIN.NS":("印度国家银行","in_stock"),
    "AXISBANK.NS":("Axis银行","in_stock"),
    "ASIANPAINT.NS":("亚洲油漆","in_stock"),
    "MARUTI.NS":("马鲁蒂铃木","in_stock"),
    "LT.NS":("Larsen&Toubro","in_stock"),
    "SUNPHARMA.NS":("太阳制药","in_stock"),
    "TITAN.NS":("Titan Company","in_stock"),
    "BAJFINANCE.NS":("巴贾金融","in_stock"),
    "WIPRO.NS":("Wipro","in_stock"),
    "HCLTECH.NS":("HCL科技","in_stock"),
    "ULTRACEMCO.NS":("超技水泥","in_stock"),
    "ADANIENT.NS":("阿达尼集团","in_stock"),
    "ADANIPORTS.NS":("阿达尼港口","in_stock"),
    "POWERGRID.NS":("电力电网","in_stock"),
    "NTPC.NS":("国家火电","in_stock"),
    "ONGC.NS":("印度石油天然气","in_stock"),
    "TATAMOTORS.NS":("塔塔汽车","in_stock"),
    "JSWSTEEL.NS":("JSW钢铁","in_stock"),
    "TATASTEEL.NS":("塔塔钢铁","in_stock"),
    "HINDCOPPER.NS":("印度铜业","in_stock"),
    "NIFTY50":("NIFTY50指数","index"),
},

# ━━━ 31. 澳大利亚股票 (ASX) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇦🇺 澳大利亚股票 (ASX)": {
    "BHP.AX":("必和必拓 BHP","au_stock"),"CBA.AX":("联邦银行","au_stock"),
    "ANZ.AX":("澳新银行 ANZ","au_stock"),"NAB.AX":("国民银行","au_stock"),
    "WBC.AX":("西太平洋银行","au_stock"),"MQG.AX":("麦格理集团","au_stock"),
    "RIO.AX":("力拓 Rio Tinto","au_stock"),"FMG.AX":("Fortescue","au_stock"),
    "WDS.AX":("伍德赛德能源","au_stock"),"STO.AX":("桑托斯 Santos","au_stock"),
    "WES.AX":("维斯法默斯","au_stock"),"WOW.AX":("Woolworths超市","au_stock"),
    "CSL.AX":("CSL生物制品","au_stock"),"COL.AX":("科尔斯集团","au_stock"),
    "GMG.AX":("古德曼集团","au_stock"),"TCL.AX":("Transurban","au_stock"),
    "TLS.AX":("澳电信 Telstra","au_stock"),"ALL.AX":("Aristocrat Leisure","au_stock"),
    "ASX.AX":("澳洲证交所","au_stock"),"AMC.AX":("Amcor包装","au_stock"),
    "NCM.AX":("纽克雷斯特金矿","au_stock"),"NST.AX":("北方之星","au_stock"),
    "EVN.AX":("Evolution Mining","au_stock"),"OZL.AX":("OZ Minerals","au_stock"),
    "S32.AX":("South32","au_stock"),"MIN.AX":("Mineral Resources","au_stock"),
    "PLS.AX":("Pilbara Minerals锂","au_stock"),"LTR.AX":("Liontown锂","au_stock"),
    "AGL.AX":("AGL Energy","au_stock"),"ORG.AX":("Origin Energy","au_stock"),
},

# ━━━ 32. 英国股票 (LSE) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇬🇧 英国股票 (LSE)": {
    "SHEL.L":("壳牌 Shell","uk_stock"),"HSBA.L":("汇丰 HSBC","uk_stock"),
    "AZN.L":("阿斯利康","uk_stock"),"BP.L":("英国石油 BP","uk_stock"),
    "GSK.L":("葛兰素史克","uk_stock"),"ULVR.L":("联合利华","uk_stock"),
    "DGE.L":("帝亚吉欧 Diageo","uk_stock"),"RIO.L":("力拓 Rio Tinto","uk_stock"),
    "AAL.L":("Anglo American","uk_stock"),"GLEN.L":("嘉能可 Glencore","uk_stock"),
    "BT-A.L":("英国电信","uk_stock"),"VOD.L":("沃达丰 Vodafone","uk_stock"),
    "LLOY.L":("劳埃德银行","uk_stock"),"BARC.L":("巴克莱银行","uk_stock"),
    "NWG.L":("苏格兰皇家银行","uk_stock"),"STAN.L":("渣打银行","uk_stock"),
    "PRU.L":("保诚集团","uk_stock"),"LSEG.L":("伦敦证交所","uk_stock"),
    "EXPN.L":("益博睿 Experian","uk_stock"),"REL.L":("RELX集团","uk_stock"),
    "RKT.L":("利洁时 Reckitt","uk_stock"),"BA.L":("BAE Systems","uk_stock"),
    "RR.L":("劳斯莱斯 Rolls-Royce","uk_stock"),"IMB.L":("英美烟草 Imperial","uk_stock"),
    "WPP.L":("WPP广告","uk_stock"),"IHG.L":("洲际酒店","uk_stock"),
    "CPG.L":("Compass集团","uk_stock"),"HIK.L":("哈金斯 Halma","uk_stock"),
    "SGE.L":("Sage Group","uk_stock"),"AUTO.L":("AutoTrader","uk_stock"),
},

# ━━━ 33. 德国股票 (XETRA) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇩🇪 德国股票 (XETRA)": {
    "SAP.DE":("SAP","de_stock"),"SIE.DE":("西门子 Siemens","de_stock"),
    "ALV.DE":("安联 Allianz","de_stock"),"MBG.DE":("梅赛德斯-奔驰","de_stock"),
    "BMW.DE":("宝马 BMW","de_stock"),"VOW3.DE":("大众 Volkswagen","de_stock"),
    "DTE.DE":("德国电信","de_stock"),"BAYN.DE":("拜耳 Bayer","de_stock"),
    "MRK.DE":("默克 Merck DE","de_stock"),"ADS.DE":("阿迪达斯","de_stock"),
    "BAS.DE":("巴斯夫 BASF","de_stock"),"IFX.DE":("英飞凌 Infineon","de_stock"),
    "DB1.DE":("德国交易所","de_stock"),"CON.DE":("大陆 Continental","de_stock"),
    "RHM.DE":("莱茵金属 Rheinmetall","de_stock"),"AIR.DE":("空客 Airbus","de_stock"),
    "HEN3.DE":("汉高 Henkel","de_stock"),"HEI.DE":("海德堡水泥","de_stock"),
    "SHL.DE":("Siemens Healthineers","de_stock"),"ENR.DE":("西门子能源","de_stock"),
    "P911.DE":("保时捷 Porsche","de_stock"),"MAN.DE":("曼恩 MAN","de_stock"),
    "FRE.DE":("弗雷森纽斯","de_stock"),"ZAL.DE":("Zalando","de_stock"),
    "MTX.DE":("MTU Aero Engines","de_stock"),"DHER.DE":("Delivery Hero","de_stock"),
},

# ━━━ 34. 法国/欧洲大陆股票 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇫🇷 法国/欧洲大陆股票": {
    "MC.PA":("LVMH","fr_stock"),"AIR.PA":("空客 Airbus","fr_stock"),
    "TTE.PA":("道达尔 TotalEnergies","fr_stock"),"SAN.PA":("赛诺菲 Sanofi","fr_stock"),
    "BNP.PA":("法巴 BNP Paribas","fr_stock"),"ACA.PA":("农业信贷","fr_stock"),
    "OR.PA":("欧莱雅 L'Oreal","fr_stock"),"RI.PA":("保乐力加","fr_stock"),
    "KER.PA":("开云 Kering","fr_stock"),"RMS.PA":("爱马仕 Hermes","fr_stock"),
    "CAP.PA":("凯捷 Capgemini","fr_stock"),"DSY.PA":("达索系统","fr_stock"),
    "ENGI.PA":("昂吉 Engie","fr_stock"),"ORA.PA":("法国电信 Orange","fr_stock"),
    "ASML.AS":("ASML荷兰","nl_stock"),"PHIA.AS":("飞利浦","nl_stock"),
    "HEIA.AS":("喜力 Heineken","nl_stock"),"WKL.AS":("威科集团","nl_stock"),
    "NOVN.SW":("诺华 Novartis","ch_stock"),"ROG.SW":("罗氏 Roche","ch_stock"),
    "NESN.SW":("雀巢 Nestle","ch_stock"),"ZURN.SW":("苏黎世保险","ch_stock"),
    "UBSG.SW":("瑞银 UBS","ch_stock"),"ABBN.SW":("ABB集团","ch_stock"),
    "GEBN.SW":("纪梵希/百富勤 Givaudan","ch_stock"),
    "SAN.MC":("桑坦德银行","es_stock"),"BBVA.MC":("对外银行 BBVA","es_stock"),
    "TEF.MC":("西班牙电信","es_stock"),"IBE.MC":("伊维尔德罗拉","es_stock"),
    "ITX.MC":("Inditex/Zara","es_stock"),"ENI.MI":("意大利石油","it_stock"),
    "ENEL.MI":("意大利电力","it_stock"),"ISP.MI":("意联银行","it_stock"),
    "UCG.MI":("裕信银行","it_stock"),
},

# ━━━ 35. 北欧股票 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇸🇪 北欧股票 (瑞典/丹麦/挪威/芬兰)": {
    "ERIC-B.ST":("爱立信 Ericsson","nordic"),"VOLV-B.ST":("沃尔沃 Volvo","nordic"),
    "ATCO-A.ST":("阿特拉斯科普柯","nordic"),"SKF-B.ST":("SKF轴承","nordic"),
    "ESSITY-B.ST":("Essity卫生纸","nordic"),"SEB-A.ST":("SEB银行","nordic"),
    "SHB-A.ST":("北欧联合银行 Handelsbanken","nordic"),
    "SWED-A.ST":("瑞典银行 Swedbank","nordic"),
    "SAND.ST":("山特维克 Sandvik","nordic"),"NDA-SE.ST":("北欧联合银行","nordic"),
    "NOVO-B.CO":("诺和诺德 Novo Nordisk","nordic"),
    "ORSTED.CO":("沃旭能源 Orsted","nordic"),
    "MAERSK-B.CO":("马士基 Maersk","nordic"),
    "DSV.CO":("DSV物流","nordic"),"NZYM-B.CO":("诺维信 Novozymes","nordic"),
    "EQNR.OL":("挪威国家石油","nordic"),"DNB.OL":("DNB银行","nordic"),
    "TEL.OL":("Telenor","nordic"),"AKERBP.OL":("Aker BP","nordic"),
    "YAR.OL":("雅苒 Yara国际","nordic"),"MOWI.OL":("Mowi三文鱼","nordic"),
    "NOKIA.HE":("诺基亚","nordic"),"FORTUM.HE":("芬兰Fortum","nordic"),
    "NESTE.HE":("耐斯特 Neste","nordic"),"SAMPO.HE":("桑普保险","nordic"),
},

# ━━━ 36. 加拿大股票 (TSX) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🇨🇦 加拿大股票 (TSX)": {
    "RY.TO":("皇家银行 RBC","ca_stock"),"TD.TO":("道明银行 TD","ca_stock"),
    "BNS.TO":("丰业银行 Scotiabank","ca_stock"),"BMO.TO":("蒙特利尔银行","ca_stock"),
    "CM.TO":("帝国商业银行 CIBC","ca_stock"),"MFC.TO":("宏利金融","ca_stock"),
    "SLF.TO":("永明金融 Sun Life","ca_stock"),"GWO.TO":("Great-West Lifeco","ca_stock"),
    "SU.TO":("森科能源 Suncor","ca_stock"),"CNQ.TO":("加拿大自然资源","ca_stock"),
    "CVE.TO":("加拿大石油 Cenovus","ca_stock"),"IMO.TO":("帝国石油","ca_stock"),
    "ABX.TO":("巴里克黄金 Barrick","ca_stock"),"AEM.TO":("爱格拉科金矿","ca_stock"),
    "FNV.TO":("Franco-Nevada","ca_stock"),"WPM.TO":("惠顿贵金属","ca_stock"),
    "K.TO":("Kinross Gold","ca_stock"),"AGI.TO":("Alamos Gold","ca_stock"),
    "SHOP.TO":("Shopify","ca_stock"),"CSU.TO":("Constellation Software","ca_stock"),
    "OTEX.TO":("Open Text","ca_stock"),"BB.TO":("BlackBerry","ca_stock"),
    "CP.TO":("加拿大太平洋铁路","ca_stock"),"CNR.TO":("加拿大国家铁路","ca_stock"),
    "TRP.TO":("TC能源","ca_stock"),"ENB.TO":("恩桥能源 Enbridge","ca_stock"),
    "PPL.TO":("Pembina Pipeline","ca_stock"),"T.TO":("Telus通信","ca_stock"),
    "BCE.TO":("BCE电信","ca_stock"),"QSR.TO":("汉堡王/Tim Hortons","ca_stock"),
    "ATD.TO":("Alimentation Couche-Tard","ca_stock"),"MRU.TO":("Metro超市","ca_stock"),
    "L.TO":("Loblaw Companies","ca_stock"),"NTR.TO":("Nutrien化肥","ca_stock"),
},

# ━━━ 37. 拉美/中东/非洲/其他新兴市场 ━━━━━━━━━━━━━━━━━━━━━━━━━━
"🌎 新兴市场 (拉美/中东/非洲)": {
    "PETR4.SA":("巴西石油 Petrobras","latam"),"VALE3.SA":("淡水河谷 Vale","latam"),
    "ITUB4.SA":("伊塔乌银行","latam"),"BBDC4.SA":("布拉德斯科银行","latam"),
    "B3SA3.SA":("B3交易所","latam"),"WEGE3.SA":("WEG电机","latam"),
    "RENT3.SA":("Localiza租车","latam"),"MGLU3.SA":("Magazine Luiza","latam"),
    "SUZB3.SA":("苏扎诺纸浆","latam"),"ABEV3.SA":("百威AB InBev巴西","latam"),
    "AMXL.MX":("墨西哥美洲电信","latam"),"GFNORTEO.MX":("北方银行","latam"),
    "GMEXICOB.MX":("墨西哥集团","latam"),"FEMSAUBD.MX":("FEMSA","latam"),
    "2222.SR":("沙特阿美","mideast"),"SABIC.SR":("沙特基础工业","mideast"),
    "SNB.SR":("沙特国家银行","mideast"),"RJHI.SR":("拉吉银行","mideast"),
    "NICE.TA":("NICE Systems以色列","mideast"),"CHKP.TA":("Check Point以色列","mideast"),
    "TEVA.TA":("梯瓦制药以色列","mideast"),"WIX.TA":("Wix.com","mideast"),
    "NPN.JO":("Naspers南非","africa"),"BTI.JO":("英美烟草南非","africa"),
    "AGL.JO":("盎格鲁黄金","africa"),"SOL.JO":("萨索尔 Sasol","africa"),
    "SBK.JO":("标准银行南非","africa"),"FSR.JO":("FirstRand南非","africa"),
},

# ━━━ 38. 东南亚/亚太股票 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"🌏 东南亚/亚太股票": {
    "D05.SI":("星展银行 DBS","sea"),"U11.SI":("大华银行 UOB","sea"),
    "O39.SI":("华侨银行 OCBC","sea"),"Z74.SI":("新加坡电信","sea"),
    "S68.SI":("新交所 SGX","sea"),"F34.SI":("丰益国际 Wilmar","sea"),
    "GRAB":("Grab Holdings美挂","sea_adr"),"SE":("Sea Limited美挂","sea_adr"),
    "TLKM.JK":("印尼电信","id_stock"),"BBCA.JK":("印尼中亚银行","id_stock"),
    "BMRI.JK":("印尼国家银行","id_stock"),"BBRI.JK":("印尼人民银行","id_stock"),
    "ASII.JK":("印尼Astra","id_stock"),"UNVR.JK":("联合利华印尼","id_stock"),
    "ADVANC.BK":("泰国AIS","th_stock"),"PTT.BK":("泰国国家石油","th_stock"),
    "PTTEP.BK":("泰国石油勘探","th_stock"),"KBANK.BK":("泰国开泰银行","th_stock"),
    "SCB.BK":("泰国商业银行","th_stock"),"CPF.BK":("泰国正大食品","th_stock"),
    "MAYB.KL":("马来亚银行","my_stock"),"PBBANK.KL":("马来西亚公众银行","my_stock"),
    "TENAGA.KL":("马来西亚电力","my_stock"),"AXIATA.KL":("Axiata电信","my_stock"),
    "SM.PS":("SM集团菲律宾","ph_stock"),"JFC.PS":("Jollibee菲律宾","ph_stock"),
    "BDO.PS":("BDO银行菲律宾","ph_stock"),"ALI.PS":("Ayala Land","ph_stock"),
    "FPH.NZ":("Fisher&Paykel新西兰","nz_stock"),"MEL.NZ":("Meridian Energy","nz_stock"),
},

# ━━━ 39. 加密货币 - 主流 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"₿ 加密货币 - 主流": {
    "BTC-USD":("Bitcoin BTC","crypto"),"ETH-USD":("Ethereum ETH","crypto"),
    "SOL-USD":("Solana SOL","crypto"),"BNB-USD":("BNB","crypto"),
    "XRP-USD":("Ripple XRP","crypto"),"ADA-USD":("Cardano ADA","crypto"),
    "AVAX-USD":("Avalanche AVAX","crypto"),"DOGE-USD":("Dogecoin DOGE","crypto"),
    "TRX-USD":("TRON TRX","crypto"),"DOT-USD":("Polkadot DOT","crypto"),
    "LTC-USD":("Litecoin LTC","crypto"),"BCH-USD":("Bitcoin Cash","crypto"),
    "LINK-USD":("Chainlink LINK","crypto"),"ATOM-USD":("Cosmos ATOM","crypto"),
    "XLM-USD":("Stellar XLM","crypto"),"UNI-USD":("Uniswap UNI","crypto"),
    "NEAR-USD":("NEAR Protocol","crypto"),"ICP-USD":("Internet Computer","crypto"),
    "FIL-USD":("Filecoin FIL","crypto"),"VET-USD":("VeChain VET","crypto"),
    "ALGO-USD":("Algorand ALGO","crypto"),"ETC-USD":("Ethereum Classic","crypto"),
    "MATIC-USD":("Polygon MATIC","crypto"),"XMR-USD":("Monero XMR","crypto"),
    "EGLD-USD":("MultiversX EGLD","crypto"),"KAS-USD":("Kaspa KAS","crypto"),
    "FTM-USD":("Fantom FTM","crypto"),"THETA-USD":("Theta Network","crypto"),
    "ONE-USD":("Harmony ONE","crypto"),"ZIL-USD":("Zilliqa ZIL","crypto"),
},

# ━━━ 40. 加密货币 - L2/DeFi/AI/Meme ━━━━━━━━━━━━━━━━━━━━━━━━━━━
"₿ 加密货币 - L2/DeFi/AI/Meme": {
    "APT-USD":("Aptos APT","crypto"),"ARB-USD":("Arbitrum ARB","crypto"),
    "OP-USD":("Optimism OP","crypto"),"SUI-USD":("Sui SUI","crypto"),
    "SEI-USD":("Sei SEI","crypto"),"TIA-USD":("Celestia TIA","crypto"),
    "INJ-USD":("Injective INJ","crypto"),"STRK-USD":("Starknet STRK","crypto"),
    "TON-USD":("Toncoin TON","crypto"),"PEPE-USD":("Pepe PEPE","crypto"),
    "WIF-USD":("dogwifhat WIF","crypto"),"BONK-USD":("Bonk BONK","crypto"),
    "SHIB-USD":("Shiba Inu SHIB","crypto"),"FLOKI-USD":("Floki FLOKI","crypto"),
    "JUP-USD":("Jupiter JUP","crypto"),"PYTH-USD":("Pyth Network","crypto"),
    "ONDO-USD":("Ondo Finance","crypto"),"BLUR-USD":("Blur","crypto"),
    "RNDR-USD":("Render RNDR","crypto"),"FET-USD":("Fetch.ai FET","crypto"),
    "AGIX-USD":("SingularityNET","crypto"),"WLD-USD":("Worldcoin WLD","crypto"),
    "TAO-USD":("Bittensor TAO","crypto"),"GRT-USD":("The Graph GRT","crypto"),
    "LDO-USD":("Lido DAO LDO","crypto"),"AAVE-USD":("Aave AAVE","crypto"),
    "MKR-USD":("Maker MKR","crypto"),"CRV-USD":("Curve CRV","crypto"),
    "RPL-USD":("Rocket Pool RPL","crypto"),"SAND-USD":("Sandbox SAND","crypto"),
    "MANA-USD":("Decentraland MANA","crypto"),"AXS-USD":("Axie Infinity","crypto"),
    "IMX-USD":("ImmutableX IMX","crypto"),"DYDX-USD":("dYdX","crypto"),
    "GMX-USD":("GMX","crypto"),"PENDLE-USD":("Pendle","crypto"),
    "EIGEN-USD":("EigenLayer","crypto"),"ENA-USD":("Ethena ENA","crypto"),
    "JTO-USD":("Jito JTO","crypto"),"W-USD":("Wormhole W","crypto"),
},
}  # end ASSET_GROUPS


# ════════════════════════════════════════════════════════════════════
# 向后兼容：合并所有组，去重
# ════════════════════════════════════════════════════════════════════
ASSETS: Dict[str, Tuple[str, str]] = {}
for _grp in ASSET_GROUPS.values():
    for _tk, _val in _grp.items():
        if _tk not in ASSETS:
            ASSETS[_tk] = _val

TIMEFRAMES: Dict[str, Tuple[str, str]] = {
    "Daily":   ("1d",  "2y"),
    "Weekly":  ("1wk", "5y"),
    "Monthly": ("1mo", "10y"),
}

GROUP_NAMES = list(ASSET_GROUPS.keys())

# 类别标签中文映射
CATEGORY_LABELS = {
    "futures":    "🥇 期货",    "index":      "📊 指数",
    "forex":      "💱 外汇",    "us_etf":     "📦 美国ETF",
    "us_tech":    "🖥️ 美科技",  "us_semi":    "💡 半导体",
    "us_sw":      "☁️ 软件/云", "us_internet":"🌐 互联网",
    "us_cyber":   "🔒 网络安全","us_fintech":  "💳 金融科技",
    "us_bank":    "🏦 美金融",  "us_health":  "💊 医疗",
    "us_consumer":"🛒 消费",    "us_energy":  "⚡ 能源",
    "us_ind":     "🏭 工业",    "us_util":    "🔋 公用事业",
    "us_ev":      "🚗 EV新能源","us_reit":    "🏠 REITs",
    "cn_adr":     "🇨🇳 中概ADR","hk_stock":   "🇭🇰 港股",
    "a_stock":    "🇨🇳 A股",    "jp_stock":   "🇯🇵 日股",
    "kr_stock":   "🇰🇷 韩股",   "tw_stock":   "🇹🇼 台股",
    "in_stock":   "🇮🇳 印股",   "au_stock":   "🇦🇺 澳股",
    "uk_stock":   "🇬🇧 英股",   "de_stock":   "🇩🇪 德股",
    "fr_stock":   "🇫🇷 法股",   "nl_stock":   "🇳🇱 荷股",
    "ch_stock":   "🇨🇭 瑞股",   "es_stock":   "🇪🇸 西/意股",
    "it_stock":   "🇮🇹 意股",   "nordic":     "🇸🇪 北欧股",
    "ca_stock":   "🇨🇦 加股",   "latam":      "🌎 拉美",
    "mideast":    "🌙 中东",    "africa":     "🌍 非洲",
    "sea":        "🌏 新加坡",  "sea_adr":    "🌏 东南亚ADR",
    "id_stock":   "🇮🇩 印尼股", "th_stock":   "🇹🇭 泰股",
    "my_stock":   "🇲🇾 马股",   "ph_stock":   "🇵🇭 菲股",
    "nz_stock":   "🇳🇿 新西兰", "crypto":     "₿ 加密",
}


# ════════════════════════════════════════════════════════════════════
# A股全市场扩展 — 按行业分组，约 800 只主要股票
# 覆盖沪深两市全部主要行业龙头及中盘股
# ════════════════════════════════════════════════════════════════════

# ━━━ A1. A股 - 银行业全部 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASSET_GROUPS["🇨🇳 A股 - 银行业"] = {
    "601398.SS":("工商银行","a_stock"),"601288.SS":("农业银行","a_stock"),
    "601939.SS":("建设银行","a_stock"),"601988.SS":("中国银行","a_stock"),
    "601328.SS":("交通银行","a_stock"),"600036.SS":("招商银行","a_stock"),
    "601166.SS":("兴业银行","a_stock"),"600016.SS":("民生银行","a_stock"),
    "601009.SS":("南京银行","a_stock"),"601229.SS":("上海银行","a_stock"),
    "601128.SS":("常熟银行","a_stock"),"601838.SS":("成都银行","a_stock"),
    "601577.SS":("长沙银行","a_stock"),"601997.SS":("贵阳银行","a_stock"),
    "002142.SZ":("宁波银行","a_stock"),"000001.SZ":("平安银行","a_stock"),
    "001227.SZ":("兰州银行","a_stock"),"002807.SZ":("江阴银行","a_stock"),
    "002936.SZ":("郑州银行","a_stock"),"002948.SZ":("青岛银行","a_stock"),
    "002966.SZ":("苏州银行","a_stock"),"003008.SZ":("西安银行","a_stock"),
    "600000.SS":("浦发银行","a_stock"),"601169.SS":("北京银行","a_stock"),
    "600015.SS":("华夏银行","a_stock"),"601187.SS":("厦门银行","a_stock"),
    "601963.SS":("重庆银行","a_stock"),"601825.SS":("沪农商行","a_stock"),
    "601860.SS":("紫金银行","a_stock"),"601077.SS":("渝农商行","a_stock"),
    "601665.SS":("齐鲁银行","a_stock"),"601122.SS":("浙江国商","a_stock"),
    "002839.SZ":("张家港行","a_stock"),"002929.SZ":("瑞丰银行","a_stock"),
    "002958.SZ":("青农商行","a_stock"),"002865.SZ":("京山轻机","a_stock"),
    "603323.SS":("苏农银行","a_stock"),"601528.SS":("瑞丰农商","a_stock"),
}

# ━━━ A2. A股 - 非银金融（证券/保险/信托） ━━━━━━━━━━━━━━━━━━━━━━━
ASSET_GROUPS["🇨🇳 A股 - 非银金融"] = {
    "600030.SS":("中信证券","a_stock"),"601211.SS":("国泰君安","a_stock"),
    "600837.SS":("海通证券","a_stock"),"000776.SZ":("广发证券","a_stock"),
    "000166.SZ":("申万宏源","a_stock"),"601688.SS":("华泰证券","a_stock"),
    "600999.SS":("招商证券","a_stock"),"601066.SS":("中信建投","a_stock"),
    "601375.SS":("中原证券","a_stock"),"601901.SS":("方正证券","a_stock"),
    "600606.SS":("绿地控股","a_stock"),"600995.SS":("华西证券","a_stock"),
    "601108.SS":("财通证券","a_stock"),"601162.SS":("天风证券","a_stock"),
    "601198.SS":("东兴证券","a_stock"),"601236.SS":("红塔证券","a_stock"),
    "601456.SS":("国联证券","a_stock"),"601555.SS":("东吴证券","a_stock"),
    "601699.SS":("山西证券","a_stock"),"601816.SS":("华安证券","a_stock"),
    "601878.SS":("浙商证券","a_stock"),"002500.SZ":("山西证券B","a_stock"),
    "000562.SZ":("宏源证券","a_stock"),"002673.SZ":("西部证券","a_stock"),
    "002685.SZ":("华数传媒","a_stock"),"002736.SZ":("国信证券","a_stock"),
    "300059.SZ":("东方财富","a_stock"),"601628.SS":("中国人寿","a_stock"),
    "601318.SS":("中国平安","a_stock"),"601601.SS":("中国太保","a_stock"),
    "601336.SS":("新华保险","a_stock"),"600048.SS":("保利发展","a_stock"),
    "601319.SS":("中国人保","a_stock"),"601800.SS":("中国交建","a_stock"),
}

# ━━━ A3. A股 - 医药/生物/医疗器械 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASSET_GROUPS["🇨🇳 A股 - 医药/生物/医疗"] = {
    "600276.SS":("恒瑞医药","a_stock"),"603259.SS":("药明康德","a_stock"),
    "300760.SZ":("迈瑞医疗","a_stock"),"300122.SZ":("智飞生物","a_stock"),
    "300015.SZ":("爱尔眼科","a_stock"),"600085.SS":("同仁堂","a_stock"),
    "600196.SS":("复星医药","a_stock"),"600518.SS":("康美药业","a_stock"),
    "000538.SZ":("云南白药","a_stock"),"000661.SZ":("长春高新","a_stock"),
    "002422.SZ":("科伦药业","a_stock"),"002007.SZ":("华兰生物","a_stock"),
    "002698.SZ":("博晖创新","a_stock"),"002773.SZ":("康弘药业","a_stock"),
    "300347.SZ":("泰格医药","a_stock"),"300015.SZ":("爱尔眼科","a_stock"),
    "688185.SS":("康希诺","a_stock"),"688521.SS":("申联生物","a_stock"),
    "688202.SS":("美迪西","a_stock"),"688626.SS":("翔宇医疗","a_stock"),
    "300243.SZ":("瑞康医药","a_stock"),"300759.SZ":("康龙化成","a_stock"),
    "300558.SZ":("贝达药业","a_stock"),"300601.SZ":("康泰生物","a_stock"),
    "300602.SZ":("飞利信","a_stock"),"300676.SZ":("华大基因","a_stock"),
    "300702.SZ":("天宇股份","a_stock"),"300725.SZ":("药石科技","a_stock"),
    "300727.SZ":("润达医疗","a_stock"),"300739.SZ":("明阳电气","a_stock"),
    "300782.SZ":("卓胜微","a_stock"),"300785.SZ":("值得买","a_stock"),
    "600867.SS":("通化东宝","a_stock"),"600079.SS":("人福医药","a_stock"),
    "600422.SS":("昆药集团","a_stock"),"000999.SZ":("华润三九","a_stock"),
    "002603.SZ":("以岭药业","a_stock"),"002637.SZ":("赞宇科技","a_stock"),
    "002727.SZ":("一心堂","a_stock"),"002869.SZ":("金溢科技","a_stock"),
    "002930.SZ":("宝利国际","a_stock"),"600276.SS":("恒瑞医药","a_stock"),
}

# ━━━ A4. A股 - 白酒/食品饮料/消费 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASSET_GROUPS["🇨🇳 A股 - 白酒/食品/消费"] = {
    "600519.SS":("贵州茅台","a_stock"),"000858.SZ":("五粮液","a_stock"),
    "002304.SZ":("洋河股份","a_stock"),"000596.SZ":("古井贡酒","a_stock"),
    "000568.SZ":("泸州老窖","a_stock"),"600779.SS":("水井坊","a_stock"),
    "600197.SS":("伊力特","a_stock"),"600809.SS":("山西汾酒","a_stock"),
    "000799.SZ":("酒鬼酒","a_stock"),"603589.SS":("口子窖","a_stock"),
    "600887.SS":("伊利股份","a_stock"),"002150.SZ":("通润装备","a_stock"),
    "000895.SZ":("双汇发展","a_stock"),"603288.SS":("海天味业","a_stock"),
    "002127.SZ":("南极电商","a_stock"),"600873.SS":("梅花生物","a_stock"),
    "000869.SZ":("张裕A","a_stock"),"002507.SZ":("涪陵榨菜","a_stock"),
    "000848.SZ":("承德露露","a_stock"),"600600.SS":("青岛啤酒","a_stock"),
    "000729.SZ":("燕京啤酒","a_stock"),"600298.SS":("安琪酵母","a_stock"),
    "002614.SZ":("奥佳华","a_stock"),"603866.SS":("桃李面包","a_stock"),
    "002568.SZ":("百润股份","a_stock"),"605577.SS":("龙版传媒","a_stock"),
    "603345.SS":("安井食品","a_stock"),"002762.SZ":("金发拉比","a_stock"),
    "002831.SZ":("裕同科技","a_stock"),"002910.SZ":("庄园牧场","a_stock"),
    "000630.SZ":("铜陵有色","a_stock"),"600690.SS":("海尔智家","a_stock"),
    "000651.SZ":("格力电器","a_stock"),"000333.SZ":("美的集团","a_stock"),
    "002032.SZ":("苏泊尔","a_stock"),"002040.SZ":("南华期货","a_stock"),
    "600521.SS":("华海药业","a_stock"),"603369.SS":("今世缘","a_stock"),
    "002013.SZ":("中航精机","a_stock"),"603198.SS":("迎驾贡酒","a_stock"),
}

# ━━━ A5. A股 - 新能源/储能/动力电池 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASSET_GROUPS["🇨🇳 A股 - 新能源/储能/动力电池"] = {
    "300750.SZ":("宁德时代","a_stock"),"300014.SZ":("亿纬锂能","a_stock"),
    "002460.SZ":("赣锋锂业","a_stock"),"002466.SZ":("天齐锂业","a_stock"),
    "002709.SZ":("天赐材料","a_stock"),"600438.SS":("通威股份","a_stock"),
    "601012.SS":("隆基绿能","a_stock"),"300274.SZ":("阳光电源","a_stock"),
    "688593.SS":("芳源股份","a_stock"),"002812.SZ":("恩捷股份","a_stock"),
    "300763.SZ":("锦浪科技","a_stock"),"300769.SZ":("德方纳米","a_stock"),
    "300782.SZ":("卓胜微","a_stock"),"688063.SS":("派能科技","a_stock"),
    "688120.SS":("华海清科","a_stock"),"688599.SS":("天合光能","a_stock"),
    "688601.SS":("百济神州","a_stock"),"688819.SS":("天能股份","a_stock"),
    "002137.SZ":("实益达","a_stock"),"002308.SZ":("威创股份","a_stock"),
    "002401.SZ":("中远麒麟","a_stock"),"002594.SZ":("比亚迪","a_stock"),
    "300207.SZ":("欣旺达","a_stock"),"300373.SZ":("扬杰科技","a_stock"),
    "300438.SZ":("鹏辉能源","a_stock"),"300454.SZ":("深信服","a_stock"),
    "300457.SZ":("赢合科技","a_stock"),"300484.SZ":("蓝思科技","a_stock"),
    "300496.SZ":("中科创达","a_stock"),"300502.SZ":("新易盛","a_stock"),
    "600580.SS":("卧龙电驱","a_stock"),"002027.SZ":("分众传媒","a_stock"),
    "300316.SZ":("晶盛机电","a_stock"),"300408.SZ":("三环集团","a_stock"),
    "300433.SZ":("蓝思科技","a_stock"),"688006.SS":("杭可科技","a_stock"),
    "688009.SS":("中国通号","a_stock"),"688011.SS":("新光光电","a_stock"),
    "688012.SS":("中微公司","a_stock"),"688018.SS":("乐鑫科技","a_stock"),
}

# ━━━ A6. A股 - 半导体/芯片/电子 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASSET_GROUPS["🇨🇳 A股 - 半导体/芯片/电子"] = {
    "688981.SS":("中芯国际","a_stock"),"603986.SS":("兆易创新","a_stock"),
    "002049.SZ":("紫光国微","a_stock"),"002371.SZ":("北方华创","a_stock"),
    "688039.SS":("当虹科技","a_stock"),"688041.SS":("海光信息","a_stock"),
    "688049.SS":("炬芯科技","a_stock"),"688052.SS":("纳芯微","a_stock"),
    "688068.SS":("热景生物","a_stock"),"688072.SS":("拓荆科技","a_stock"),
    "688074.SS":("盛美上海","a_stock"),"688076.SS":("诺泰生物","a_stock"),
    "688082.SS":("盛剑环境","a_stock"),"688083.SS":("中望软件","a_stock"),
    "688088.SS":("虹软科技","a_stock"),"688100.SS":("威胜信息","a_stock"),
    "688108.SS":("赛诺威盛","a_stock"),"688111.SS":("金宏气体","a_stock"),
    "688120.SS":("华海清科","a_stock"),"688122.SS":("西部超导","a_stock"),
    "688126.SS":("沪硅产业","a_stock"),"688128.SS":("中芯集成","a_stock"),
    "688130.SS":("芯源微","a_stock"),"688131.SS":("聚辰股份","a_stock"),
    "688148.SS":("芳源股份","a_stock"),"688153.SS":("唯捷创芯","a_stock"),
    "688160.SS":("华峰测控","a_stock"),"688171.SS":("纵横通信","a_stock"),
    "688175.SS":("石头科技","a_stock"),"688176.SS":("亚光科技","a_stock"),
    "300308.SZ":("中际旭创","a_stock"),"000725.SZ":("京东方A","a_stock"),
    "002415.SZ":("海康威视","a_stock"),"002516.SZ":("旷视科技","a_stock"),
    "300024.SZ":("机器人","a_stock"),"300033.SZ":("同花顺","a_stock"),
    "300036.SZ":("超图软件","a_stock"),"300104.SZ":("乐视网","a_stock"),
    "300144.SZ":("宋城演艺","a_stock"),"300145.SZ":("中金环境","a_stock"),
    "002230.SZ":("科大讯飞","a_stock"),"002241.SZ":("歌尔股份","a_stock"),
    "002475.SZ":("立讯精密","a_stock"),"300002.SZ":("神州泰岳","a_stock"),
}

# ━━━ A7. A股 - 军工/航天航空/国防 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASSET_GROUPS["🇨🇳 A股 - 军工/国防/航天"] = {
    "600760.SS":("中航沈飞","a_stock"),"000768.SZ":("中航飞机","a_stock"),
    "600893.SS":("航发动力","a_stock"),"600919.SS":("江苏银行","a_stock"),
    "600038.SS":("哈飞股份","a_stock"),"000422.SZ":("湖北宜化","a_stock"),
    "600316.SS":("洪都航空","a_stock"),"600765.SS":("中航重机","a_stock"),
    "000623.SZ":("吉林敖东","a_stock"),"002013.SZ":("中航精机","a_stock"),
    "002025.SZ":("航天电器","a_stock"),"002026.SZ":("山东威达","a_stock"),
    "002179.SZ":("中航光电","a_stock"),"002188.SZ":("利君股份","a_stock"),
    "002191.SZ":("劲嘉股份","a_stock"),"002217.SZ":("合力泰","a_stock"),
    "002218.SZ":("拓日新能","a_stock"),"002379.SZ":("宏创控股","a_stock"),
    "002389.SZ":("南洋科技","a_stock"),"600871.SS":("中船科技","a_stock"),
    "600350.SS":("山东高速","a_stock"),"600118.SS":("中国卫星","a_stock"),
    "688519.SS":("中微半导","a_stock"),"002019.SZ":("亿帆医药","a_stock"),
    "600706.SS":("曙光数创","a_stock"),"000089.SZ":("深圳机场","a_stock"),
    "600611.SS":("大众交通","a_stock"),"601919.SS":("中远海控","a_stock"),
    "600685.SS":("中船防务","a_stock"),"600782.SS":("新钢股份","a_stock"),
    "601100.SS":("中航重机","a_stock"),"002803.SZ":("吴通控股","a_stock"),
    "300810.SZ":("中国卫通","a_stock"),
}

# ━━━ A8. A股 - 汽车/新能源汽车/零部件 ━━━━━━━━━━━━━━━━━━━━━━━━━━
ASSET_GROUPS["🇨🇳 A股 - 汽车/新能源车/零部件"] = {
    "002594.SZ":("比亚迪","a_stock"),"600104.SS":("上汽集团","a_stock"),
    "000625.SZ":("长安汽车","a_stock"),"000800.SZ":("一汽轿车","a_stock"),
    "600166.SS":("福田汽车","a_stock"),"600418.SS":("江淮汽车","a_stock"),
    "601633.SS":("长城汽车","a_stock"),"601238.SS":("广汽集团","a_stock"),
    "000572.SZ":("海马汽车","a_stock"),"600006.SS":("东风汽车","a_stock"),
    "000550.SZ":("江铃汽车","a_stock"),"000951.SZ":("中国重汽","a_stock"),
    "600707.SS":("彩虹股份","a_stock"),"600741.SS":("华域汽车","a_stock"),
    "002739.SZ":("万达电影","a_stock"),"600546.SS":("山煤国际","a_stock"),
    "002703.SZ":("浙江世宝","a_stock"),"002906.SZ":("华阳集团","a_stock"),
    "300730.SZ":("利亚德","a_stock"),"002345.SZ":("潮宏基","a_stock"),
    "300751.SZ":("迈为股份","a_stock"),"300773.SZ":("拉卡拉","a_stock"),
    "002001.SZ":("新和成","a_stock"),"002074.SZ":("国轩高科","a_stock"),
    "300024.SZ":("机器人","a_stock"),"002733.SZ":("雄帝科技","a_stock"),
    "002756.SZ":("永兴材料","a_stock"),"002831.SZ":("裕同科技","a_stock"),
    "300285.SZ":("国瓷材料","a_stock"),"300296.SZ":("利亚德","a_stock"),
    "300410.SZ":("正业科技","a_stock"),"300415.SZ":("伊之密","a_stock"),
    "300497.SZ":("富祥药业","a_stock"),"600699.SS":("均胜电子","a_stock"),
    "600006.SS":("东风汽车","a_stock"),"002925.SZ":("盈趣科技","a_stock"),
}

# ━━━ A9. A股 - 房地产/建筑/建材 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASSET_GROUPS["🇨🇳 A股 - 房地产/建筑/建材"] = {
    "000002.SZ":("万科A","a_stock"),"600048.SS":("保利发展","a_stock"),
    "001979.SZ":("招商蛇口","a_stock"),"000069.SZ":("华侨城A","a_stock"),
    "000631.SZ":("顺发恒业","a_stock"),"600606.SS":("绿地控股","a_stock"),
    "600663.SS":("陆家嘴","a_stock"),"000153.SZ":("丰乐种业","a_stock"),
    "600266.SS":("城建发展","a_stock"),"600340.SS":("华夏幸福","a_stock"),
    "600533.SS":("栖霞建设","a_stock"),"600895.SS":("张江高科","a_stock"),
    "601588.SS":("北辰实业","a_stock"),"601668.SS":("中国建筑","a_stock"),
    "601800.SS":("中国交建","a_stock"),"601901.SS":("方正证券","a_stock"),
    "000060.SZ":("中金岭南","a_stock"),"002133.SZ":("广宇集团","a_stock"),
    "600585.SS":("海螺水泥","a_stock"),"000877.SZ":("天山股份","a_stock"),
    "000401.SZ":("冀东水泥","a_stock"),"002233.SZ":("塔牌集团","a_stock"),
    "601390.SS":("中国中铁","a_stock"),"601186.SS":("中国铁建","a_stock"),
    "601669.SS":("中国电建","a_stock"),"601702.SS":("中国联塑","a_stock"),
    "600170.SS":("上海建工","a_stock"),"600820.SS":("隧道股份","a_stock"),
    "002047.SZ":("宝鹰股份","a_stock"),"002189.SZ":("利君股份B","a_stock"),
    "002516.SZ":("旷视科技","a_stock"),"600068.SS":("葛洲坝","a_stock"),
    "601216.SS":("君正集团","a_stock"),"603501.SS":("韦尔股份","a_stock"),
}

# ━━━ A10. A股 - 钢铁/有色金属/化工原材料 ━━━━━━━━━━━━━━━━━━━━━━
ASSET_GROUPS["🇨🇳 A股 - 钢铁/有色金属/化工"] = {
    "600019.SS":("宝山钢铁","a_stock"),"601899.SS":("紫金矿业","a_stock"),
    "000878.SZ":("云南铜业","a_stock"),"000630.SZ":("铜陵有色","a_stock"),
    "600547.SS":("山东黄金","a_stock"),"600489.SS":("中金黄金","a_stock"),
    "000807.SZ":("云铝股份","a_stock"),"600362.SS":("江西铜业","a_stock"),
    "600111.SS":("北方稀土","a_stock"),"000831.SZ":("中油燃气","a_stock"),
    "002155.SZ":("湖南黄金","a_stock"),"601600.SS":("中国铝业","a_stock"),
    "000708.SZ":("中信特钢","a_stock"),"000598.SZ":("兴蓉环境","a_stock"),
    "600782.SS":("新钢股份","a_stock"),"601005.SS":("重庆钢铁","a_stock"),
    "000959.SZ":("首钢股份","a_stock"),"601558.SS":("华电重工","a_stock"),
    "600309.SS":("万华化学","a_stock"),"600023.SS":("浙能电力","a_stock"),
    "002001.SZ":("新和成","a_stock"),"000703.SZ":("恒逸石化","a_stock"),
    "002493.SZ":("荣盛石化","a_stock"),"600256.SS":("广汇能源","a_stock"),
    "002002.SZ":("鸿达兴业","a_stock"),"002648.SZ":("卫星化学","a_stock"),
    "600389.SS":("江山股份","a_stock"),"600597.SS":("光明乳业","a_stock"),
    "002648.SZ":("卫星化学","a_stock"),"603799.SS":("华友钴业","a_stock"),
    "002812.SZ":("恩捷股份","a_stock"),"600028.SS":("中国石化","a_stock"),
    "601857.SS":("中国石油","a_stock"),"000527.SZ":("美的置业","a_stock"),
}

# ━━━ A11. A股 - 煤炭/电力/能源 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASSET_GROUPS["🇨🇳 A股 - 煤炭/电力/能源"] = {
    "601088.SS":("中国神华","a_stock"),"601225.SS":("陕西煤业","a_stock"),
    "601666.SS":("平煤股份","a_stock"),"601001.SS":("大同煤业","a_stock"),
    "601898.SS":("中煤能源","a_stock"),"600188.SS":("兖矿能源","a_stock"),
    "000617.SZ":("中油化建","a_stock"),"601699.SS":("潞安环能","a_stock"),
    "000683.SZ":("远兴能源","a_stock"),"002128.SZ":("电投能源","a_stock"),
    "600900.SS":("长江电力","a_stock"),"601985.SS":("中国核电","a_stock"),
    "600025.SS":("华能水电","a_stock"),"600021.SS":("上海电力","a_stock"),
    "601991.SS":("大唐发电","a_stock"),"600011.SS":("华能国际","a_stock"),
    "600027.SS":("华电国际","a_stock"),"600795.SS":("国电电力","a_stock"),
    "002039.SZ":("黔源电力","a_stock"),"600023.SS":("浙能电力","a_stock"),
    "601918.SS":("新集能源","a_stock"),"603198.SS":("迎驾贡酒","a_stock"),
    "002218.SZ":("拓日新能","a_stock"),"000690.SZ":("宝新能源","a_stock"),
    "601717.SS":("郑煤机","a_stock"),"601021.SS":("春秋航空","a_stock"),
    "600406.SS":("国电南瑞","a_stock"),"000400.SZ":("许继电气","a_stock"),
    "002487.SZ":("大华股份","a_stock"),"002658.SZ":("雪迪龙","a_stock"),
}

# ━━━ A12. A股 - 交通运输/物流/航运 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASSET_GROUPS["🇨🇳 A股 - 交通/物流/航空"] = {
    "601111.SS":("中国国航","a_stock"),"600115.SS":("东方航空","a_stock"),
    "600221.SS":("海航控股","a_stock"),"601021.SS":("春秋航空","a_stock"),
    "000089.SZ":("深圳机场","a_stock"),"600004.SS":("白云机场","a_stock"),
    "600009.SS":("上海机场","a_stock"),"002006.SZ":("精功科技","a_stock"),
    "601919.SS":("中远海控","a_stock"),"600428.SS":("中远海运","a_stock"),
    "601872.SS":("招商轮船","a_stock"),"600026.SS":("中远海能","a_stock"),
    "002352.SZ":("顺丰控股","a_stock"),"600233.SS":("圆通速递","a_stock"),
    "002607.SZ":("中通快递","a_stock"),"600115.SS":("东方航空","a_stock"),
    "600018.SS":("上港集团","a_stock"),"601900.SS":("南方传媒","a_stock"),
    "600125.SS":("铁龙物流","a_stock"),"000956.SZ":("中国石化油服","a_stock"),
    "601388.SS":("怡球资源","a_stock"),"600368.SS":("五洲交通","a_stock"),
    "601727.SS":("上海电气","a_stock"),"000089.SZ":("深圳机场","a_stock"),
    "002651.SZ":("利君股份","a_stock"),"600515.SS":("海航基础","a_stock"),
    "601236.SS":("红塔证券","a_stock"),"000089.SZ":("深圳机场","a_stock"),
}

# ━━━ A13. A股 - 互联网/科技/软件/数字经济 ━━━━━━━━━━━━━━━━━━━━━
ASSET_GROUPS["🇨🇳 A股 - 互联网/科技/软件"] = {
    "300059.SZ":("东方财富","a_stock"),"002230.SZ":("科大讯飞","a_stock"),
    "000977.SZ":("浪潮信息","a_stock"),"600588.SS":("用友网络","a_stock"),
    "300033.SZ":("同花顺","a_stock"),"002236.SZ":("大华股份","a_stock"),
    "002415.SZ":("海康威视","a_stock"),"300496.SZ":("中科创达","a_stock"),
    "300036.SZ":("超图软件","a_stock"),"600271.SS":("航天信息","a_stock"),
    "600845.SS":("宝信软件","a_stock"),"300482.SZ":("万讯自控","a_stock"),
    "300454.SZ":("深信服","a_stock"),"002273.SZ":("水晶光电","a_stock"),
    "300122.SZ":("智飞生物","a_stock"),"300010.SZ":("立思辰","a_stock"),
    "300014.SZ":("亿纬锂能","a_stock"),"002100.SZ":("天然气","a_stock"),
    "002292.SZ":("奥飞数据","a_stock"),"300134.SZ":("大富科技","a_stock"),
    "002416.SZ":("爱施德","a_stock"),"600701.SS":("厦门信达","a_stock"),
    "002739.SZ":("万达电影","a_stock"),"002185.SZ":("华天科技","a_stock"),
    "002095.SZ":("生意宝","a_stock"),"600100.SS":("同方股份","a_stock"),
    "300168.SZ":("万达信息","a_stock"),"000547.SZ":("航天发展","a_stock"),
    "002583.SZ":("海能达","a_stock"),"002196.SZ":("深圳鸿超","a_stock"),
    "300152.SZ":("科恒股份","a_stock"),"002079.SZ":("苏州固锝","a_stock"),
}

# ━━━ A14. A股 - 农林牧渔 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASSET_GROUPS["🇨🇳 A股 - 农林牧渔"] = {
    "002714.SZ":("牧原股份","a_stock"),"000876.SZ":("新希望","a_stock"),
    "300498.SZ":("温氏股份","a_stock"),"002714.SZ":("牧原股份","a_stock"),
    "600201.SS":("生物股份","a_stock"),"002579.SZ":("中京电子","a_stock"),
    "000799.SZ":("酒鬼酒","a_stock"),"002234.SZ":("民和股份","a_stock"),
    "600371.SS":("万向德农","a_stock"),"600354.SS":("敦煌种业","a_stock"),
    "000998.SZ":("隆平高科","a_stock"),"600371.SS":("万向德农","a_stock"),
    "002073.SZ":("软控股份","a_stock"),"002714.SZ":("牧原股份","a_stock"),
    "600975.SS":("新五丰","a_stock"),"000930.SZ":("中粮科工","a_stock"),
    "002385.SZ":("大北农","a_stock"),"002411.SZ":("包钢稀土","a_stock"),
    "600438.SS":("通威股份","a_stock"),"600887.SS":("伊利股份","a_stock"),
    "600161.SS":("天坛生物","a_stock"),"002385.SZ":("大北农","a_stock"),
    "600506.SS":("香梨股份","a_stock"),"002100.SZ":("天然气","a_stock"),
    "600153.SS":("建发股份","a_stock"),"000735.SZ":("罗牛山","a_stock"),
}

# ━━━ A15. A股 - 传媒/教育/游戏/影视 ━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASSET_GROUPS["🇨🇳 A股 - 传媒/教育/游戏"] = {
    "002027.SZ":("分众传媒","a_stock"),"600539.SS":("狮头股份","a_stock"),
    "000756.SZ":("仙鹤股份","a_stock"),"002027.SZ":("分众传媒","a_stock"),
    "002292.SZ":("奥飞数据","a_stock"),"300144.SZ":("宋城演艺","a_stock"),
    "000755.SZ":("山西路桥","a_stock"),"002739.SZ":("万达电影","a_stock"),
    "600890.SS":("风华高科","a_stock"),"600999.SS":("招商证券","a_stock"),
    "002174.SZ":("游族网络","a_stock"),"002555.SZ":("三七互娱","a_stock"),
    "300413.SZ":("芒果超媒","a_stock"),"601929.SS":("歌华有线","a_stock"),
    "000681.SZ":("视觉中国","a_stock"),"002463.SZ":("沪电股份","a_stock"),
    "002250.SZ":("联化科技","a_stock"),"300418.SZ":("昆仑万维","a_stock"),
    "300104.SZ":("乐视网","a_stock"),"000516.SZ":("开元股份","a_stock"),
    "601599.SS":("中国电影","a_stock"),"002597.SZ":("金禾实业","a_stock"),
    "300465.SZ":("高伟达","a_stock"),"300431.SZ":("暴风集团","a_stock"),
    "002499.SZ":("科隆股份","a_stock"),"300315.SZ":("掌趣科技","a_stock"),
}

# ━━━ A16. A股 - 机械设备/工业 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASSET_GROUPS["🇨🇳 A股 - 机械设备/工业"] = {
    "600031.SS":("三一重工","a_stock"),"000425.SZ":("徐工机械","a_stock"),
    "601766.SS":("中国中车","a_stock"),"300024.SZ":("机器人","a_stock"),
    "002690.SZ":("美亚光电","a_stock"),"300124.SZ":("汇川技术","a_stock"),
    "601072.SS":("中船租赁","a_stock"),"000333.SZ":("美的集团","a_stock"),
    "601238.SS":("广汽集团","a_stock"),"000338.SZ":("潍柴动力","a_stock"),
    "002302.SZ":("西部建设","a_stock"),"002046.SZ":("国机精工","a_stock"),
    "002185.SZ":("华天科技","a_stock"),"002097.SZ":("山河智能","a_stock"),
    "300414.SZ":("中光防雷","a_stock"),"002366.SZ":("台海核电","a_stock"),
    "002380.SZ":("科远智慧","a_stock"),"002444.SZ":("巨星科技","a_stock"),
    "002477.SZ":("雅化集团","a_stock"),"002500.SZ":("山西证券","a_stock"),
    "002534.SZ":("西子洁能","a_stock"),"002566.SZ":("通源石油","a_stock"),
    "002577.SZ":("雷柏科技","a_stock"),"002592.SZ":("八菱科技","a_stock"),
    "600690.SS":("海尔智家","a_stock"),"600732.SS":("爱旭股份","a_stock"),
    "600903.SS":("贵州燃气","a_stock"),"601727.SS":("上海电气","a_stock"),
    "601717.SS":("郑煤机","a_stock"),"600406.SS":("国电南瑞","a_stock"),
    "002415.SZ":("海康威视","a_stock"),"601628.SS":("中国人寿","a_stock"),
}

# ━━━ 重新合并ASSETS（含新增A股） ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 注意：这段必须在所有新增组定义之后执行
# 由于模块级别的ASSETS在原文件底部已定义，需要在此追加更新
for _grp_name, _grp in ASSET_GROUPS.items():
    if _grp_name.startswith("🇨🇳 A股 -") and "上证" not in _grp_name and "深证" not in _grp_name:
        for _tk, _val in _grp.items():
            if _tk not in ASSETS:
                ASSETS[_tk] = _val

# 更新GROUP_NAMES
GROUP_NAMES = list(ASSET_GROUPS.keys())

# ════════════════════════════════════════════════════════════════════
# A股扩充 - 补充主要个股（沪深全市场精选）
# ════════════════════════════════════════════════════════════════════
_A_EXTRA: Dict[str, Dict[str, Tuple[str, str]]] = {

"🇨🇳 A股 - 银行业扩充": {
    "601169.SS":("北京银行","a_stock"),"601009.SS":("南京银行","a_stock"),
    "601229.SS":("上海银行","a_stock"),"600015.SS":("华夏银行","a_stock"),
    "600016.SS":("民生银行","a_stock"),"601998.SS":("中信银行","a_stock"),
    "601818.SS":("光大银行","a_stock"),"601916.SS":("浙商银行","a_stock"),
    "601963.SS":("重庆银行","a_stock"),"601577.SS":("长沙银行","a_stock"),
    "601825.SS":("沪农商行","a_stock"),"601128.SS":("常熟银行","a_stock"),
    "002958.SZ":("青农商行","a_stock"),"002936.SZ":("郑州银行","a_stock"),
    "002948.SZ":("青岛银行","a_stock"),"002966.SZ":("苏州银行","a_stock"),
    "001227.SZ":("兰州银行","a_stock"),"002807.SZ":("江阴银行","a_stock"),
    "002839.SZ":("张家港行","a_stock"),"600926.SS":("杭州银行","a_stock"),
},

"🇨🇳 A股 - 非银金融扩充": {
    "600030.SS":("中信证券","a_stock"),"601688.SS":("华泰证券","a_stock"),
    "600999.SS":("招商证券","a_stock"),"601211.SS":("国泰君安","a_stock"),
    "601901.SS":("方正证券","a_stock"),"601878.SS":("浙商证券","a_stock"),
    "601198.SS":("东兴证券","a_stock"),"601375.SS":("中原证券","a_stock"),
    "600369.SS":("西南证券","a_stock"),"601696.SS":("中银证券","a_stock"),
    "600837.SS":("海通证券","a_stock"),"601788.SS":("光大证券","a_stock"),
    "601995.SS":("中金公司","a_stock"),"601066.SS":("中信建投","a_stock"),
    "600958.SS":("东方证券","a_stock"),"600820.SS":("隧道股份","a_stock"),
    "601312.SS":("天风证券","a_stock"),"600109.SS":("国金证券","a_stock"),
    "600906.SS":("财达证券","a_stock"),
},

"🇨🇳 A股 - 医药生物扩充": {
    "603259.SS":("药明康德","a_stock"),"688488.SS":("科美诊断","a_stock"),
    "688316.SS":("细胞生物","a_stock"),"688598.SS":("义翘神州","a_stock"),
    "688180.SS":("君实生物","a_stock"),"688202.SS":("美迪西","a_stock"),
    "688363.SS":("华熙生物","a_stock"),"603938.SS":("三棵树","a_stock"),
    "600436.SS":("片仔癀","a_stock"),"600085.SS":("同仁堂","a_stock"),
    "000538.SZ":("云南白药","a_stock"),"000661.SZ":("长春高新","a_stock"),
    "300347.SZ":("泰格医药","a_stock"),"300718.SZ":("长源东谷","a_stock"),
    "300760.SZ":("迈瑞医疗","a_stock"),"300122.SZ":("智飞生物","a_stock"),
    "300015.SZ":("爱尔眼科","a_stock"),"300896.SZ":("爱美客","a_stock"),
    "300601.SZ":("康泰生物","a_stock"),"002294.SZ":("信立泰","a_stock"),
    "002422.SZ":("科伦药业","a_stock"),"002007.SZ":("华兰生物","a_stock"),
    "600276.SS":("恒瑞医药","a_stock"),"600518.SS":("康美药业","a_stock"),
    "600867.SS":("通化东宝","a_stock"),"300015.SZ":("爱尔眼科","a_stock"),
},

"🇨🇳 A股 - 半导体扩充": {
    "688981.SS":("中芯国际","a_stock"),"688036.SS":("传音控股","a_stock"),
    "688099.SS":("晶晨股份","a_stock"),"688396.SS":("华润微","a_stock"),
    "688008.SS":("澜起科技","a_stock"),"688019.SS":("安集科技","a_stock"),
    "688065.SS":("凯伦股份","a_stock"),"688126.SS":("沪硅产业","a_stock"),
    "688185.SS":("康希通信","a_stock"),"688256.SS":("寒武纪","a_stock"),
    "688187.SS":("时代电气","a_stock"),"688300.SS":("联瑞新材","a_stock"),
    "688041.SS":("海光信息","a_stock"),"688385.SS":("复旦微电","a_stock"),
    "688582.SS":("拓荆科技","a_stock"),"688522.SS":("纳芯微","a_stock"),
    "300661.SZ":("圣邦股份","a_stock"),"300433.SZ":("蓝思科技","a_stock"),
    "002049.SZ":("紫光国微","a_stock"),"300083.SZ":("创意信息","a_stock"),
    "300134.SZ":("大富科技","a_stock"),"002371.SZ":("北方华创","a_stock"),
    "000725.SZ":("京东方A","a_stock"),"002049.SZ":("紫光国微","a_stock"),
},

"🇨🇳 A股 - 新能源扩充": {
    "300750.SZ":("宁德时代","a_stock"),"600941.SS":("中国移动A","a_stock"),
    "601012.SS":("隆基绿能","a_stock"),"002460.SZ":("赣锋锂业","a_stock"),
    "002466.SZ":("天齐锂业","a_stock"),"300014.SZ":("亿纬锂能","a_stock"),
    "002709.SZ":("天赐材料","a_stock"),"300274.SZ":("阳光电源","a_stock"),
    "688567.SS":("孚能科技","a_stock"),"688690.SS":("纳微科技","a_stock"),
    "688208.SS":("道通科技","a_stock"),"688063.SS":("派能科技","a_stock"),
    "603929.SS":("亚翔集成","a_stock"),"600674.SS":("川投能源","a_stock"),
    "600025.SS":("华能水电","a_stock"),"600886.SS":("国投电力","a_stock"),
    "600795.SS":("国电电力","a_stock"),"600905.SS":("三峡能源","a_stock"),
    "600985.SS":("淮北矿业","a_stock"),"601699.SS":("潞安环能","a_stock"),
    "002610.SZ":("爱仕达","a_stock"),"002129.SZ":("中环股份","a_stock"),
    "300777.SZ":("中简科技","a_stock"),"002850.SZ":("科力远","a_stock"),
},

"🇨🇳 A股 - 消费白酒扩充": {
    "600519.SS":("贵州茅台","a_stock"),"000858.SZ":("五粮液","a_stock"),
    "000568.SZ":("泸州老窖","a_stock"),"000596.SZ":("古井贡酒","a_stock"),
    "002304.SZ":("洋河股份","a_stock"),"000799.SZ":("酒鬼酒","a_stock"),
    "600809.SS":("山西汾酒","a_stock"),"603601.SS":("再升科技","a_stock"),
    "000995.SZ":("皇台酒业","a_stock"),"000932.SZ":("华菱钢铁","a_stock"),
    "600600.SS":("青岛啤酒","a_stock"),"000729.SZ":("燕京啤酒","a_stock"),
    "603711.SS":("香飘飘","a_stock"),"605499.SS":("东鹏饮料","a_stock"),
    "600887.SS":("伊利股份","a_stock"),"002奶.SZ":("蒙牛乳业","a_stock"),
    "002557.SZ":("洽洽食品","a_stock"),"600218.SS":("全聚德","a_stock"),
    "000895.SZ":("双汇发展","a_stock"),"002714.SZ":("牧原股份","a_stock"),
},

"🇨🇳 A股 - 互联网科技扩充": {
    "300059.SZ":("东方财富","a_stock"),"002230.SZ":("科大讯飞","a_stock"),
    "600588.SS":("用友网络","a_stock"),"002368.SZ":("太极股份","a_stock"),
    "300496.SZ":("中科创达","a_stock"),"300468.SZ":("四方精创","a_stock"),
    "002236.SZ":("大华股份","a_stock"),"002415.SZ":("海康威视","a_stock"),
    "300454.SZ":("深信服","a_stock"),"300033.SZ":("同花顺","a_stock"),
    "688111.SS":("金山办公","a_stock"),"603198.SS":("迎驾贡酒","a_stock"),
    "688058.SS":("科思科技","a_stock"),"688003.SS":("天准科技","a_stock"),
    "688048.SS":("长光华芯","a_stock"),"688189.SS":("南微医学","a_stock"),
    "300782.SZ":("卓胜微","a_stock"),"002831.SZ":("裕太微","a_stock"),
    "300628.SZ":("亿联网络","a_stock"),"300024.SZ":("机器人","a_stock"),
},

"🇨🇳 A股 - 房地产/建筑/建材扩充": {
    "600048.SS":("保利发展","a_stock"),"601390.SS":("中国中铁","a_stock"),
    "601800.SS":("中国交建","a_stock"),"601668.SS":("中国建筑","a_stock"),
    "601186.SS":("中国铁建","a_stock"),"601766.SS":("中国中车","a_stock"),
    "600585.SS":("海螺水泥","a_stock"),"000401.SZ":("冀东水泥","a_stock"),
    "000786.SZ":("北新建材","a_stock"),"002233.SZ":("塔牌集团","a_stock"),
    "000002.SZ":("万科A","a_stock"),"600606.SS":("绿地控股","a_stock"),
    "000069.SZ":("华侨城A","a_stock"),"600383.SS":("金地集团","a_stock"),
    "001979.SZ":("招商蛇口","a_stock"),"600031.SS":("三一重工","a_stock"),
    "000425.SZ":("徐工机械","a_stock"),"000338.SZ":("潍柴动力","a_stock"),
    "002097.SZ":("山河智能","a_stock"),"300124.SZ":("汇川技术","a_stock"),
},
}

# 合并扩充的A股到主表
for _gname, _grp in _A_EXTRA.items():
    if _gname not in ASSET_GROUPS:
        ASSET_GROUPS[_gname] = {}
    for _tk, _val in _grp.items():
        if _tk not in ASSET_GROUPS[_gname]:
            ASSET_GROUPS[_gname][_tk] = _val
        if _tk not in ASSETS:
            ASSETS[_tk] = _val

GROUP_NAMES = list(ASSET_GROUPS.keys())
