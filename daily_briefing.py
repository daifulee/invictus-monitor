#!/usr/bin/env python3
"""
INVICTUS Dashboard — 일일 풀 브리핑 (매일 08:00 KST)
Oracle v2.13 기반 | 자동화 가능 항목만 포함

브리핑 구조:
  B0  헤더 — 날짜, 레짐, 경보단계
  B1  센서 대시보드 — TIER1 + TIER2 전체
  B2  레짐 상세 — 그래디언트 분해, TIDE/INFERNO/CURVE
  B3  트리거 전체 — E0~L3 + 킬스위치 + GLD 매도금지
  B4  SPY 기술적 — 200MA/60MA 위치, BREADTH
  B5  재진입 조건 — VIX/MOVE/SAHM 체크
"""

import os
import requests
from datetime import datetime, timezone, timedelta

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}

# ── 데이터 수집 (monitor.py와 동일) ──
def yahoo_price(symbol):
    try:
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(symbol)}?interval=1d&range=1d"
        return requests.get(url, headers=UA, timeout=10).json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except: return None

def yahoo_history(symbol, rng="1y"):
    try:
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(symbol)}?interval=1d&range={rng}"
        closes = requests.get(url, headers=UA, timeout=15).json()["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        return [c for c in closes if c is not None]
    except: return []

def fred_value(sid):
    if not FRED_API_KEY: return None
    try:
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id={sid}&api_key={FRED_API_KEY}&limit=1&sort_order=desc&file_type=json"
        return float(requests.get(url, timeout=10).json()["observations"][0]["value"])
    except: return None

def fetch_all():
    vix=yahoo_price("^VIX"); vix3m=yahoo_price("^VIX3M"); move=yahoo_price("^MOVE")
    wti=yahoo_price("CL=F"); dxy=yahoo_price("DX-Y.NYB"); rsp=yahoo_price("RSP")
    spy_h=yahoo_history("SPY","1y"); rsp_h=yahoo_history("RSP","2mo")
    move_h=yahoo_history("^MOVE","2mo"); wti_h=yahoo_history("CL=F","2mo")
    oas=fred_value("BAMLH0A0HYM2"); t5yie=fred_value("T5YIE"); sahm=fred_value("SAHMCURRENT")
    dfii10=fred_value("DFII10"); t10y2y=fred_value("T10Y2Y"); icsa=fred_value("ICSA")

    spy = spy_h[-1] if spy_h else None
    spy200 = sum(spy_h[-200:])/200 if len(spy_h)>=200 else None
    spy60 = sum(spy_h[-60:])/60 if len(spy_h)>=60 else None
    def bd(arr,ma):
        if not ma: return 0
        c=0
        for p in reversed(arr):
            if p<ma: c+=1
            else: break
        return c
    below200=bd(spy_h,spy200); below60=bd(spy_h,spy60)
    breach60=(spy-spy60)/spy60 if spy and spy60 else None
    wti_chg=(wti_h[-1]-wti_h[-8])/wti_h[-8] if len(wti_h)>=8 else None
    vv=vix/vix3m if vix and vix3m and vix3m>0 else None
    move_ma20=sum(move_h[-20:])/20 if len(move_h)>=20 else None
    move_rel=move/move_ma20 if move and move_ma20 and move_ma20>0 else None
    breadth=None
    if len(spy_h)>=22 and len(rsp_h)>=22:
        sr=spy_h[-1]/spy_h[-22]; rr=rsp_h[-1]/rsp_h[-22]
        if rr>0: breadth=sr/rr
    # SPY 1일 변화율
    spy_1d_chg = (spy_h[-1]-spy_h[-2])/spy_h[-2]*100 if len(spy_h)>=2 else None
    # SPY 1주 변화율
    spy_1w_chg = (spy_h[-1]-spy_h[-6])/spy_h[-6]*100 if len(spy_h)>=6 else None
    # SPY 1달 변화율
    spy_1m_chg = (spy_h[-1]-spy_h[-22])/spy_h[-22]*100 if len(spy_h)>=22 else None

    return {
        "VIX":vix,"VIX3M":vix3m,"MOVE":move,"OAS":oas,"WTI":wti,"SPY":spy,
        "T5YIE":t5yie,"DXY":dxy,"RSP":rsp,"DFII10":dfii10,"T10Y2Y":t10y2y,
        "ICSA":icsa,"SAHM":sahm,"SPY_200MA":spy200,"SPY_60MA":spy60,
        "below200":below200,"below60":below60,"breach60":breach60,
        "WTI_CHG":wti_chg,"VV_RATIO":vv,"MOVE_MA20":move_ma20,"MOVE_REL":move_rel,
        "BREADTH":breadth,"SPY_1D":spy_1d_chg,"SPY_1W":spy_1w_chg,"SPY_1M":spy_1m_chg,
    }

# ── Oracle 레짐 (monitor.py와 동일) ──
def lin(v,lo,hi,mx):
    if v<=lo: return 0
    if v>=hi: return mx
    return round(mx*(v-lo)/(hi-lo),2)

def classify_tide(s,ic):
    s=s or 0; ic=ic or 220000
    if s>=0.50: return "RECESSION_CONFIRMED"
    if s>=0.30: return "RECESSION_WATCH"
    if s>=0.25 or ic>=300000: return "SLOWDOWN"
    return "EXPANSION"

def classify_inferno(t,w):
    t=t or 2.5; w=w or 80
    if t<1.5: return "DEFLATION_RISK"
    if t>=3.0 or w>=120: return "HOT"
    if t>=2.7 or w>=95: return "RISING"
    return "STABLE"

def classify_curve(s):
    s=s if s is not None else 0.5
    if s<=-0.5: return "DEEP_INVERT"
    if s<=0: return "INVERTED"
    if s<=0.3: return "FLAT"
    return "NORMAL"

def compute_gradient(d):
    vs=lin(d["VIX"] or 18,18,30,25); os_=lin(d["OAS"] or 3,3,5.5,25)
    ms=lin(d["MOVE"] or 80,80,130,25)
    mr=d.get("MOVE_REL")
    if mr and mr>1.0:
        b=5 if mr>=1.20 else 4 if mr>=1.15 else 3 if mr>=1.10 else 1.5 if mr>=1.05 else 0
        ms=min(25,ms+b)
    fs=8; rr=lin(d["DFII10"] or 1.0,0.5,2.5,15) if d.get("DFII10") else 0
    total=min(100,round(vs+os_+ms+fs+rr,1))
    defense=round(10+(total/100)*80,1)
    if total<20: bk="🟢GREEN"
    elif total<40: bk="🟡전환경계"
    elif total<60: bk="🟡YELLOW"
    elif total<80: bk="🟠RED경계"
    else: bk="🔴STORM"
    return {"total":total,"bracket":bk,"defense":defense,"attack":round(100-defense,1),
            "vix":vs,"oas":os_,"move":ms,"flow":fs,"rr":rr}

def classify_regime(d,g):
    tide=classify_tide(d["SAHM"],d["ICSA"])
    inferno=classify_inferno(d["T5YIE"],d["WTI"])
    curve=classify_curve(d["T10Y2Y"])
    dfii=d["DFII10"] or 1.0; gt=g["total"]; sahm=d["SAHM"]
    if tide=="RECESSION_CONFIRMED" or (tide=="RECESSION_WATCH" and curve=="DEEP_INVERT"):
        r,l,rp="RECESSION","🔴🔴 침체 확정",60
    elif tide in("SLOWDOWN","RECESSION_WATCH") and inferno in("RISING","HOT"):
        r,l,rp="STAGFLATION","🟠 스태그플레이션",30
    elif tide in("SLOWDOWN","RECESSION_WATCH") and inferno=="STABLE":
        r,l,rp="SLOWDOWN","🔴 침체 경계",40
    elif tide in("SLOWDOWN","RECESSION_WATCH") and inferno=="DEFLATION_RISK":
        r,l,rp="DEFLATION","🔵 디플레형",45
    elif tide=="EXPANSION" and dfii>1.5 and inferno in("RISING","HOT"):
        r,l,rp="HIGH_RATE","🟡 고금리",20
    elif tide=="EXPANSION" and gt<15 and (sahm or 0)<0.15 and curve!="DEEP_INVERT":
        r,l,rp="EXPANSION_BULL","🟢🟢 초강세장",5
    else: r,l,rp="EXPANSION","🟢 확장기",10
    return {"regime":r,"label":l,"rp":rp,"tide":tide,"inferno":inferno,"curve":curve}

# ── 트리거 ──
def evaluate(d):
    active=[]
    vix=d["VIX"] or 0; move=d["MOVE"] or 0; oas=d["OAS"] or 0
    wti=d["WTI"] or 0; t5y=d["T5YIE"] or 0; vv=d["VV_RATIO"] or 0
    all_t = [
        ("E0","PRE_STORM","PRE", vix>=30 or vv>1.05),
        ("E1","INFERNO","PRE", t5y>3.0 and wti>120),
        ("E2","BULL_BREAK","PRE", d["below200"]>=5),
        ("E3","BREADTH","PRE", d["BREADTH"] is not None and d["BREADTH"]>=1.12),
        ("E4","ATTRITION","PRE", d["WTI_CHG"] is not None and d["WTI_CHG"]>=0.20),
        ("L0a","AEGIS-EBP","L0", oas>=5.8),
        ("L0b","AEGIS-SB","L0", oas>=5.2),
        ("L1","STORM","L1", vix>=42 or move>=190 or oas>=8.5),
        ("L2","FAST_CRASH","L2", vix>=45),
        ("L3","KILLSWITCH","L3", d["below60"]>=12 and d.get("breach60") is not None and d["breach60"]<=-0.05),
    ]
    stage="CLEAR"
    for id,nm,lv,act in all_t:
        if act and lv=="L3": stage="L3"
        elif act and lv=="L2" and stage not in("L3",): stage="L2"
        elif act and lv=="L1" and stage not in("L3","L2"): stage="L1"
        elif act and lv=="L0" and stage not in("L3","L2","L1"): stage="L0"
        elif act and lv=="PRE" and stage=="CLEAR": stage="PRE"

    ks="CLEAR"
    if vix>=45: ks="FAST_CRASH"
    elif d["below60"]>=12 and d.get("breach60") and d["breach60"]<=-0.05:
        ks="OVERRIDE" if vix>=35 else "ARMED"
    elif d["below60"]>0: ks="WATCH"

    gld_no = t5y>=3.0 or (t5y>=2.7 and wti>=95)
    chips=" ".join(f"**{id}●**" if act else f"{id}○" for id,nm,lv,act in all_t)
    return {"all":all_t,"stage":stage,"ks":ks,"gld_no":gld_no,"chips":chips}

# ── Discord 전송 ──
def send(payload):
    if not DISCORD_WEBHOOK: return
    try: requests.post(DISCORD_WEBHOOK,json=payload,timeout=10)
    except: pass

def f(v,u="",d=1):
    if v is None: return "--"
    return f"{u}{v:.{d}f}"

def sign(v):
    if v is None: return "--"
    return f"+{v:.1f}%" if v>=0 else f"{v:.1f}%"

# ── 풀 브리핑 생성 ──
def build_briefing(d, regime, grad, trig):
    now = datetime.now(KST)
    date_str = now.strftime("%Y-%m-%d (%a)")
    time_str = now.strftime("%H:%M KST")
    stg = trig["stage"]
    stg_emoji = {"CLEAR":"🟢","PRE":"🟡","L0":"🟠","L1":"🔴","L2":"🔴🔴","L3":"⚫"}.get(stg,"⚪")

    # ━━ B0: 헤더 ━━
    b0 = {
        "title": f"📋 INVICTUS 일일 브리핑 — {date_str}",
        "description": (
            f"**경보 단계:** {stg_emoji} **{stg}** · "
            f"**레짐:** {regime['label']} · "
            f"**적정 RP:** {regime['rp']}%\n"
            f"**그래디언트:** {grad['total']}/100 {grad['bracket']} · "
            f"**방어/공격:** {grad['defense']}% / {grad['attack']}%"
        ),
        "color": {"CLEAR":0x3DBB7E,"PRE":0xEFB030,"L0":0xEFB030,"L1":0xE07238,"L2":0xD83030,"L3":0x2C2C2A}.get(stg,0x5B9CF6),
        "footer": {"text": f"INVICTUS Bot · {time_str} · 일일 브리핑"}
    }

    # ━━ B1: 센서 대시보드 ━━
    b1 = {
        "title": "📡 B1. 센서 대시보드",
        "color": 0x5B9CF6,
        "fields": [
            {"name": "VIX", "value": f"**{f(d['VIX'])}** (E0:30 L1:42 L2:45)", "inline": True},
            {"name": "MOVE", "value": f"**{f(d['MOVE'],d=0)}** (경보:150 L1:190)", "inline": True},
            {"name": "OAS_HY", "value": f"**{f(d['OAS'],'',2)}%** (L0b:5.2 L0a:5.8 L1:8.5)", "inline": True},
            {"name": "WTI", "value": f"**${f(d['WTI'])}** (E1:$120) 주간:{sign(d['WTI_CHG']*100 if d['WTI_CHG'] else None)}", "inline": True},
            {"name": "T5YIE", "value": f"**{f(d['T5YIE'],'',2)}%** (E1:3.0%)", "inline": True},
            {"name": "DXY", "value": f"**{f(d['DXY'],d=2)}** (차단:100 전차단:104)", "inline": True},
            {"name": "DFII10", "value": f"**{f(d['DFII10'],'',2)}%** (10Y 실질금리)", "inline": True},
            {"name": "T10Y2Y", "value": f"**{f(d['T10Y2Y'],'',2)}%** (수익률곡선)", "inline": True},
            {"name": "VIX/VIX3M", "value": f"**{f(d['VV_RATIO'],d=3)}** (E0:>1.05)", "inline": True},
            {"name": "SAHM", "value": f"**{f(d['SAHM'],'',2)}** (0.30:경계 0.50:침체)", "inline": True},
            {"name": "ICSA", "value": f"**{f(d['ICSA'],'',0)}** (실업수당)", "inline": True},
            {"name": "MOVE/MA20", "value": f"**{f(d['MOVE_REL'],d=3)}** (1.10:경고)", "inline": True},
        ]
    }

    # ━━ B2: 레짐 상세 ━━
    grad_bar = "█" * int(grad['total']/5) + "░" * (20-int(grad['total']/5))
    b2 = {
        "title": "🏛️ B2. Oracle 레짐 상세",
        "color": 0xEFB030,
        "fields": [
            {"name": "거시 레짐", "value": f"**{regime['label']}** (RP {regime['rp']}%)", "inline": False},
            {"name": "그래디언트 분해",
             "value": (
                 f"`{grad_bar}` **{grad['total']}**/100\n"
                 f"VIX: {grad['vix']}/25 · OAS: {grad['oas']}/25 · "
                 f"MOVE: {grad['move']}/25 · FLOW: {grad['flow']}/25"
                 + (f" · RR: {grad['rr']}/15" if grad.get('rr') else "")
             ), "inline": False},
            {"name": "🌊 TIDE (경기사이클)", "value": f"**{regime['tide']}**", "inline": True},
            {"name": "🔥 INFERNO (물가환경)", "value": f"**{regime['inferno']}**", "inline": True},
            {"name": "📐 CURVE (수익률곡선)", "value": f"**{regime['curve']}**", "inline": True},
        ]
    }

    # ━━ B3: 트리거 + 킬스위치 ━━
    ks_emoji = {"CLEAR":"🟢","WATCH":"🟡","ARMED":"🟠","OVERRIDE":"🔴","FAST_CRASH":"🔴🔴"}.get(trig["ks"],"⚪")
    b3 = {
        "title": "🚨 B3. 트리거 + 킬스위치",
        "color": 0xD83030 if stg not in ("CLEAR","PRE") else 0x3DBB7E,
        "fields": [
            {"name": "트리거 상태", "value": trig["chips"], "inline": False},
            {"name": "킬스위치", "value": f"{ks_emoji} **{trig['ks']}**", "inline": True},
            {"name": "GLD 매도", "value": "🚫 **금지**" if trig["gld_no"] else "✅ 허용", "inline": True},
            {"name": "경보 단계", "value": f"{stg_emoji} **{stg}**", "inline": True},
        ]
    }

    # ━━ B4: SPY 기술적 ━━
    spy_vs_200 = f"{(d['SPY']-d['SPY_200MA'])/d['SPY_200MA']*100:.1f}%" if d['SPY'] and d['SPY_200MA'] else "--"
    spy_vs_60 = f"{(d['SPY']-d['SPY_60MA'])/d['SPY_60MA']*100:.1f}%" if d['SPY'] and d['SPY_60MA'] else "--"
    b4 = {
        "title": "📈 B4. SPY 기술적 분석",
        "color": 0x3DBB7E,
        "fields": [
            {"name": "SPY 현재가", "value": f"**${f(d['SPY'])}**", "inline": True},
            {"name": "1일 변화", "value": f"**{sign(d['SPY_1D'])}**", "inline": True},
            {"name": "1주 변화", "value": f"**{sign(d['SPY_1W'])}**", "inline": True},
            {"name": "1달 변화", "value": f"**{sign(d['SPY_1M'])}**", "inline": True},
            {"name": "vs 200MA", "value": f"**{spy_vs_200}** (${f(d['SPY_200MA'])})", "inline": True},
            {"name": "vs 60MA", "value": f"**{spy_vs_60}** (${f(d['SPY_60MA'])})", "inline": True},
            {"name": "200MA 하회", "value": f"**{d['below200']}일** (E2:5일)", "inline": True},
            {"name": "60MA 하회", "value": f"**{d['below60']}일** (L3:12일)", "inline": True},
            {"name": "BREADTH", "value": f"**{f(d['BREADTH'],d=3)}** (E3:≥1.12)", "inline": True},
        ]
    }

    # ━━ B5: 재진입 조건 ━━
    re_vix = "✅" if d["VIX"] and d["VIX"]<20 else "❌"
    re_move = "✅" if d["MOVE"] and d["MOVE"]<100 else "❌"
    re_sahm = "✅" if d["SAHM"] and d["SAHM"]<0.30 else ("❓" if d["SAHM"] is None else "❌")
    b5 = {
        "title": "🔓 B5. 재진입 조건 (전부 충족 필수)",
        "color": 0x5B9CF6,
        "description": (
            f"{re_vix} VIX < 20 — 현재 **{f(d['VIX'])}**\n"
            f"{re_move} MOVE < 100 — 현재 **{f(d['MOVE'],d=0)}**\n"
            f"{re_sahm} SAHM < 0.30 — 현재 **{f(d['SAHM'],'',2)}**"
        )
    }

    return [b0, b1, b2, b3, b4, b5]

# ── 메인 ──
def main():
    print("📋 INVICTUS 일일 브리핑 생성 중...")
    d = fetch_all()
    grad = compute_gradient(d)
    regime = classify_regime(d, grad)
    trig = evaluate(d)

    embeds = build_briefing(d, regime, grad, trig)
    print(f"  레짐: {regime['label']} · 경보: {trig['stage']}")

    # Discord 10 embed 제한 → 2회 분할 전송
    send({"content": "📋 **INVICTUS 일일 브리핑** — " + datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
          "embeds": embeds[:5]})
    if len(embeds) > 5:
        send({"embeds": embeds[5:]})

    print("  ✅ Discord 전송 완료")

if __name__ == "__main__":
    main()
