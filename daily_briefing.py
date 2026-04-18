#!/usr/bin/env python3
"""INVICTUS Dashboard — 일일 풀 브리핑 (매일 08:00 KST)"""

import os, requests
from datetime import datetime, timezone, timedelta

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}

# ── 데이터 수집 ──
def yp(sym):
    try:
        url=f"https://query2.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(sym)}?interval=1d&range=1d"
        return requests.get(url,headers=UA,timeout=10).json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except: return None
def yh(sym,rng="1y"):
    try:
        url=f"https://query2.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(sym)}?interval=1d&range={rng}"
        c=requests.get(url,headers=UA,timeout=15).json()["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        return [x for x in c if x is not None]
    except: return []
def fv(sid):
    if not FRED_API_KEY: return None
    try:
        url=f"https://api.stlouisfed.org/fred/series/observations?series_id={sid}&api_key={FRED_API_KEY}&limit=1&sort_order=desc&file_type=json"
        return float(requests.get(url,timeout=10).json()["observations"][0]["value"])
    except: return None

def fetch():
    vix=yp("^VIX");vix3m=yp("^VIX3M");move=yp("^MOVE");wti=yp("CL=F")
    dxy=yp("DX-Y.NYB");rsp=yp("RSP")
    sh=yh("SPY","1y");rh=yh("RSP","2mo");mh=yh("^MOVE","2mo");wh=yh("CL=F","2mo")
    oas=fv("BAMLH0A0HYM2");t5y=fv("T5YIE");sahm=fv("SAHMCURRENT")
    dfii=fv("DFII10");t10=fv("T10Y2Y");icsa=fv("ICSA")
    spy=sh[-1] if sh else None
    s200=sum(sh[-200:])/200 if len(sh)>=200 else None
    s60=sum(sh[-60:])/60 if len(sh)>=60 else None
    def bd(a,m):
        if not m: return 0
        c=0
        for p in reversed(a):
            if p<m: c+=1
            else: break
        return c
    b200=bd(sh,s200);b60=bd(sh,s60)
    br60=(spy-s60)/s60 if spy and s60 else None
    wc=(wh[-1]-wh[-8])/wh[-8] if len(wh)>=8 else None
    vv=vix/vix3m if vix and vix3m and vix3m>0 else None
    mm=sum(mh[-20:])/20 if len(mh)>=20 else None
    mr=move/mm if move and mm and mm>0 else None
    brd=None
    if len(sh)>=22 and len(rh)>=22:
        sr=sh[-1]/sh[-22];rr=rh[-1]/rh[-22]
        if rr>0: brd=sr/rr
    s1d=(sh[-1]-sh[-2])/sh[-2]*100 if len(sh)>=2 else None
    s1w=(sh[-1]-sh[-6])/sh[-6]*100 if len(sh)>=6 else None
    s1m=(sh[-1]-sh[-22])/sh[-22]*100 if len(sh)>=22 else None
    return {"VIX":vix,"VIX3M":vix3m,"MOVE":move,"OAS":oas,"WTI":wti,"SPY":spy,
        "T5YIE":t5y,"DXY":dxy,"RSP":rsp,"DFII10":dfii,"T10Y2Y":t10,"ICSA":icsa,
        "SAHM":sahm,"SPY200":s200,"SPY60":s60,"b200":b200,"b60":b60,"br60":br60,
        "WC":wc,"VV":vv,"MM":mm,"MR":mr,"BRD":brd,"S1D":s1d,"S1W":s1w,"S1M":s1m}

# ── Oracle 레짐 ──
def lin(v,lo,hi,mx):
    if v<=lo: return 0
    if v>=hi: return mx
    return round(mx*(v-lo)/(hi-lo),2)
def tide(s,ic):
    s=s or 0;ic=ic or 220000
    if s>=0.50: return "RECESSION_CONFIRMED"
    if s>=0.30: return "RECESSION_WATCH"
    if s>=0.25 or ic>=300000: return "SLOWDOWN"
    return "EXPANSION"
def inferno(t,w):
    t=t or 2.5;w=w or 80
    if t<1.5: return "DEFLATION_RISK"
    if t>=3.0 or w>=120: return "HOT"
    if t>=2.7 or w>=95: return "RISING"
    return "STABLE"
def curve(s):
    s=s if s is not None else 0.5
    if s<=-0.5: return "DEEP_INVERT"
    if s<=0: return "INVERTED"
    if s<=0.3: return "FLAT"
    return "NORMAL"
def gradient(d):
    vs=lin(d["VIX"] or 18,18,30,25);os_=lin(d["OAS"] or 3,3,5.5,25)
    ms=lin(d["MOVE"] or 80,80,130,25)
    mr=d.get("MR")
    if mr and mr>1.0:
        b=5 if mr>=1.20 else 4 if mr>=1.15 else 3 if mr>=1.10 else 1.5 if mr>=1.05 else 0
        ms=min(25,ms+b)
    fs=8;rr=lin(d["DFII10"] or 1.0,0.5,2.5,15) if d.get("DFII10") else 0
    t=min(100,round(vs+os_+ms+fs+rr,1))
    df=round(10+(t/100)*80,1)
    if t<20: bk="🟢 GREEN"
    elif t<40: bk="🟡 전환경계"
    elif t<60: bk="🟡 YELLOW"
    elif t<80: bk="🟠 RED경계"
    else: bk="🔴 STORM"
    return {"t":t,"bk":bk,"df":df,"ak":round(100-df,1),"vs":vs,"os":os_,"ms":ms,"fs":fs,"rr":rr}
def regime(d,g):
    td=tide(d["SAHM"],d["ICSA"]);inf=inferno(d["T5YIE"],d["WTI"]);cv=curve(d["T10Y2Y"])
    df=d["DFII10"] or 1.0;gt=g["t"];sm=d["SAHM"]
    if td=="RECESSION_CONFIRMED" or (td=="RECESSION_WATCH" and cv=="DEEP_INVERT"):
        return {"r":"RECESSION","l":"🔴🔴 침체확정","rp":60,"td":td,"inf":inf,"cv":cv}
    if td in("SLOWDOWN","RECESSION_WATCH") and inf in("RISING","HOT"):
        return {"r":"STAGFLATION","l":"🟠 스태그플레이션","rp":30,"td":td,"inf":inf,"cv":cv}
    if td in("SLOWDOWN","RECESSION_WATCH") and inf=="STABLE":
        return {"r":"SLOWDOWN","l":"🔴 침체경계","rp":40,"td":td,"inf":inf,"cv":cv}
    if td in("SLOWDOWN","RECESSION_WATCH") and inf=="DEFLATION_RISK":
        return {"r":"DEFLATION","l":"🔵 디플레형","rp":45,"td":td,"inf":inf,"cv":cv}
    if td=="EXPANSION" and df>1.5 and inf in("RISING","HOT"):
        return {"r":"HIGH_RATE","l":"🟡 고금리","rp":20,"td":td,"inf":inf,"cv":cv}
    if td=="EXPANSION" and gt<15 and (sm or 0)<0.15 and cv!="DEEP_INVERT":
        return {"r":"EXPANSION_BULL","l":"🟢🟢 초강세장","rp":5,"td":td,"inf":inf,"cv":cv}
    return {"r":"EXPANSION","l":"🟢 확장기","rp":10,"td":td,"inf":inf,"cv":cv}

# ── 트리거 ──
def triggers(d):
    vix=d["VIX"] or 0;move=d["MOVE"] or 0;oas=d["OAS"] or 0
    wti=d["WTI"] or 0;t5y=d["T5YIE"] or 0;vv=d["VV"] or 0
    ids=["E0","E1","E2","E3","E4","L0a","L0b","L1","L2","L3"]
    act=[vix>=30 or vv>1.05, t5y>3 and wti>120, d["b200"]>=5,
         d["BRD"] is not None and d["BRD"]>=1.12,
         d["WC"] is not None and d["WC"]>=0.20,
         oas>=5.8, oas>=5.2, vix>=42 or move>=190 or oas>=8.5, vix>=45,
         d["b60"]>=12 and d.get("br60") is not None and d["br60"]<=-0.05]
    chips=" ".join(f"🔴**{ids[i]}**" if act[i] else f"⚪{ids[i]}" for i in range(len(ids)))
    stg="CLEAR"
    if act[9]: stg="L3"
    elif act[8]: stg="L2"
    elif act[7]: stg="L1"
    elif act[5] or act[6]: stg="L0"
    elif any(act[:5]): stg="PRE"
    gld=t5y>=3.0 or (t5y>=2.7 and wti>=95)
    return {"chips":chips,"stg":stg,"gld":gld}

# ── 포맷 유틸 ──
def f(v,u="",dc=1):
    if v is None: return "--"
    return f"{u}{v:.{dc}f}"
def sg(v):
    if v is None: return "--"
    return f"{'🟢+' if v>=0 else '🔴'}{v:.1f}%"
def bar(v, mx=100):
    filled = int(v / mx * 10)
    return "█" * filled + "░" * (10 - filled)
def dot(ok):
    if ok is None: return "❓"
    return "🟢" if ok else "🔴"

# ── Discord 전송 ──
def send(payload):
    if not DISCORD_WEBHOOK: return
    try: requests.post(DISCORD_WEBHOOK,json=payload,timeout=10)
    except: pass

# ── 브리핑 생성 ──
def build(d, reg, grd, trg):
    now=datetime.now(KST)
    date=now.strftime("%Y-%m-%d (%a)")
    time_=now.strftime("%H:%M KST")
    stg=trg["stg"]
    se={"CLEAR":"🟢","PRE":"🟡","L0":"🟠","L1":"🔴","L2":"🔴🔴","L3":"⚫"}.get(stg,"⚪")
    sc={"CLEAR":0x3DBB7E,"PRE":0xEFB030,"L0":0xEFB030,"L1":0xE07238,"L2":0xD83030,"L3":0x2C2C2A}.get(stg,0x5B9CF6)

    # SPY vs MA
    vs200=f"{(d['SPY']-d['SPY200'])/d['SPY200']*100:+.1f}%" if d['SPY'] and d['SPY200'] else "--"
    vs60=f"{(d['SPY']-d['SPY60'])/d['SPY60']*100:+.1f}%" if d['SPY'] and d['SPY60'] else "--"

    # 재진입
    rv=d["VIX"] is not None and d["VIX"]<20
    rm=d["MOVE"] is not None and d["MOVE"]<100
    rs=d["SAHM"] is not None and d["SAHM"]<0.30

    # ━━ EMBED 1: 헤더 + 핵심 한눈에 ━━
    e1 = {
        "title": f"📋 INVICTUS 모닝 브리핑 — {date}",
        "color": sc,
        "description": (
            f"```\n"
            f"┌─────────────────────────────────────┐\n"
            f"│  경보  {se} {stg:8s}  레짐  {reg['l']:14s}│\n"
            f"│  RP    {reg['rp']:>3d}%         그래디언트  {grd['t']:>5.1f}/100  │\n"
            f"│  방어  {grd['df']:>5.1f}%       공격     {grd['ak']:>5.1f}%     │\n"
            f"└─────────────────────────────────────┘\n"
            f"```"
        ),
    }

    # ━━ EMBED 2: 센서 대시보드 ━━
    e2 = {
        "title": "📡 센서 대시보드",
        "color": 0x5B9CF6,
        "description": (
            f"```\n"
            f"센서        현재값     상태   임계값\n"
            f"─────────────────────────────────────\n"
            f"VIX       {f(d['VIX']):>8s}   {dot(d['VIX'] is not None and d['VIX']<30)}   E0:30 L1:42 L2:45\n"
            f"MOVE      {f(d['MOVE'],dc=0):>8s}   {dot(d['MOVE'] is not None and d['MOVE']<150)}   경보:150 L1:190\n"
            f"OAS       {f(d['OAS'],'',2):>7s}%  {dot(d['OAS'] is not None and d['OAS']<5.2)}   L0b:5.2 L0a:5.8\n"
            f"WTI      ${f(d['WTI']):>7s}   {dot(d['WTI'] is not None and d['WTI']<120)}   E1:$120\n"
            f"T5YIE     {f(d['T5YIE'],'',2):>7s}%  {dot(d['T5YIE'] is not None and d['T5YIE']<3.0)}   E1:3.0%\n"
            f"DXY       {f(d['DXY'],dc=2):>8s}   {dot(d['DXY'] is not None and d['DXY']<100)}   차단:100 전차단:104\n"
            f"─────────────────────────────────────\n"
            f"DFII10    {f(d['DFII10'],'',2):>7s}%  {'🟡' if d['DFII10'] and d['DFII10']>1.5 else '🟢'}   실질금리\n"
            f"T10Y2Y    {f(d['T10Y2Y'],'',2):>7s}%  {'🔴' if d['T10Y2Y'] and d['T10Y2Y']<=0 else '🟢'}   수익률곡선\n"
            f"SAHM       {f(d['SAHM'],'',2):>6s}   {dot(d['SAHM'] is not None and d['SAHM']<0.25)}   0.30:경계 0.50:침체\n"
            f"MOVE/MA20  {f(d['MR'],dc=3):>6s}   {'🟡' if d['MR'] and d['MR']>=1.10 else '🟢'}   1.10:경고\n"
            f"VIX/VIX3M  {f(d['VV'],dc=3):>6s}   {'🟡' if d['VV'] and d['VV']>1.05 else '🟢'}   1.05:E0\n"
            f"```"
        ),
    }

    # ━━ EMBED 3: 레짐 + 그래디언트 ━━
    e3 = {
        "title": "🏛️ Oracle 레짐 분석",
        "color": 0xEFB030,
        "description": (
            f"**{reg['l']}** — 적정 RP **{reg['rp']}%**\n\n"
            f"**그래디언트** `{bar(grd['t'])}` **{grd['t']}**/100 {grd['bk']}\n"
            f"```\n"
            f"VIX   {bar(grd['vs'],25)} {grd['vs']:>5.1f}/25\n"
            f"OAS   {bar(grd['os'],25)} {grd['os']:>5.1f}/25\n"
            f"MOVE  {bar(grd['ms'],25)} {grd['ms']:>5.1f}/25\n"
            f"FLOW  {bar(grd['fs'],25)} {grd['fs']:>5.1f}/25\n"
            f"RR    {bar(grd['rr'],15)} {grd['rr']:>5.1f}/15\n"
            f"```\n"
            f"🌊 **TIDE** {reg['td']} · 🔥 **INFERNO** {reg['inf']} · 📐 **CURVE** {reg['cv']}"
        ),
    }

    # ━━ EMBED 4: SPY + 트리거 + 재진입 ━━
    e4 = {
        "title": "📈 SPY + 트리거 + 재진입",
        "color": 0x3DBB7E,
        "description": (
            f"**SPY ${f(d['SPY'])}** · "
            f"1D {sg(d['S1D'])} · 1W {sg(d['S1W'])} · 1M {sg(d['S1M'])}\n"
            f"vs200MA **{vs200}** (${f(d['SPY200'])}) · "
            f"vs60MA **{vs60}** (${f(d['SPY60'])})\n"
            f"200MA하회 **{d['b200']}일** · 60MA하회 **{d['b60']}일** · "
            f"BREADTH **{f(d['BRD'],dc=3)}**\n\n"
            f"**트리거** {trg['chips']}\n"
            f"**GLD 매도** {'🚫 금지' if trg['gld'] else '✅ 허용'}\n\n"
            f"**재진입 조건** (전부 충족 필수)\n"
            f"{dot(rv)} VIX < 20 — **{f(d['VIX'])}**\n"
            f"{dot(rm)} MOVE < 100 — **{f(d['MOVE'],dc=0)}**\n"
            f"{dot(rs)} SAHM < 0.30 — **{f(d['SAHM'],'',2)}**"
        ),
    }

    # ━━ EMBED 5: 각주 (지표 설명) ━━
    e5 = {
        "title": "📖 지표 각주",
        "color": 0x485070,
        "description": (
            "```\n"
            "VIX     S&P500 내재변동성. 공포지수. 30↑경계 42↑위기\n"
            "MOVE    채권시장 변동성. 금리불확실성. 150↑경보\n"
            "OAS     하이일드 신용스프레드. 부도위험. 5.8↑신용경색\n"
            "WTI     원유가격. 120↑인플레 압력 극심\n"
            "T5YIE   5년 기대인플레. 3.0↑스태그플레이션 위험\n"
            "DXY     달러인덱스. 100↑신흥국·원자재 압박\n"
            "DFII10  10년 실질금리. 1.5↑성장주·금 압박\n"
            "T10Y2Y  장단기 금리차. 0이하=역전=침체신호\n"
            "SAHM    실업률 변화. 0.30↑경기둔화 0.50↑침체\n"
            "BREADTH SPY/RSP 1M수익률비. 1.12↑시장폭 악화\n"
            "─────────────────────────────────────\n"
            "TIDE    경기사이클 (EXPANSION→SLOWDOWN→RECESSION)\n"
            "INFERNO 물가환경 (STABLE→RISING→HOT)\n"
            "CURVE   수익률곡선 (NORMAL→FLAT→INVERTED)\n"
            "그래디언트 시장위험 0~100 연속점수 (Oracle v2.13)\n"
            "```"
        ),
    }

    return [e1, e2, e3, e4, e5]

# ── 메인 ──
def main():
    print("📋 INVICTUS 모닝 브리핑 생성 중...")
    d=fetch(); g=gradient(d); r=regime(d,g); t=triggers(d)
    print(f"  레짐: {r['l']} · 경보: {t['stg']}")
    embeds=build(d,r,g,t)
    send({"content":f"☀️ **INVICTUS 모닝 브리핑** — {datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}",
          "embeds":embeds[:5]})
    if len(embeds)>5: send({"embeds":embeds[5:]})
    print("  ✅ Discord 전송 완료")

if __name__=="__main__": main()
