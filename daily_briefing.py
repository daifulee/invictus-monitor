#!/usr/bin/env python3
"""INVICTUS 모닝 브리핑 v4.1 — 전 지표 신호등 + 모멘텀 순위 + Polymarket §3.5"""
import os,requests,json,random,math
from datetime import datetime,timezone,timedelta
DISCORD_WEBHOOK=os.environ.get("DISCORD_WEBHOOK","")
FRED_API_KEY=os.environ.get("FRED_API_KEY","")
KST=timezone(timedelta(hours=9))
UA={"User-Agent":"Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 보유종목 — 변경 시 여기만 수정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TICKERS = ["GLD","SMH","EWZ","XLE","SLV","PAVE","COPX","XLU","VEA","QQQM","IWM","XLF","XLV","INDA","ITA","CIBR","NLR","CQQQ","VNM","TLT"]
EMOJIS  = {"GLD":"🥇","SMH":"📱","EWZ":"🇧🇷","XLE":"🛢️","SLV":"🥈","PAVE":"🏗️","COPX":"🟤","XLU":"⚡","VEA":"🌍","QQQM":"💻","IWM":"🏢","XLF":"🏦","XLV":"🏥","INDA":"🇮🇳","ITA":"✈️","CIBR":"🔒","NLR":"☢️","CQQQ":"🇨🇳","VNM":"🇻🇳","TLT":"📉"}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔭 Oracle §3.5 Polymarket 시나리오 매핑
# 편집 방법:
#   1) polymarket.com에서 원하는 마켓 페이지 방문
#   2) URL 패턴: polymarket.com/event/{slug} → {slug} 부분만 복사
#   3) dir: "YES"=가격↑이면 시나리오 강화 / "NO"=가격↑이면 시나리오 약화
#   4) w: 같은 시나리오 내 상대 가중치 (합 1.0 권장)
# 제약: binary(단일 yes/no) 마켓만 지원. multi-outcome event는 조회 실패함
#       (예: "Fed rate cut by...?"는 여러 월별 outcome 있어 불가)
# 유지보수: 마켓 해결/만료 시 커버리지 `ok/total`에 경고 표시 → 월 1회 점검 권장
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCENARIO_MAP = {
    "S1": {"label":"🕊️ 급속해결","method":"weighted","markets":[
        # 호르무즈 해협 정상화 = S1 핵심 지표 (이란 전쟁 외교적 해결)
        {"slug":"strait-of-hormuz-traffic-returns-to-normal-by-end-of-april","dir":"YES","w":0.30},
        {"slug":"strait-of-hormuz-traffic-returns-to-normal-by-end-of-may","dir":"YES","w":0.35},
        {"slug":"strait-of-hormuz-traffic-returns-to-normal-by-end-of-june","dir":"YES","w":0.15},
        # 침체 회피 = S1 확증
        {"slug":"us-recession-by-end-of-2026","dir":"NO","w":0.20},
    ]},
    "S2": {"label":"⚖️ 통제된긴장","method":"complement","markets":[]},  # 1-(S1+S3+S4)
    "S3": {"label":"🔥 스태그플레이션","method":"weighted","markets":[
        # 침체 위험
        {"slug":"us-recession-by-end-of-2026","dir":"YES","w":0.30},
        # 인플레 지속 → 금리 인상 확률↑
        {"slug":"fed-rate-hike-in-2026","dir":"YES","w":0.30},
        {"slug":"ecb-rate-hike-in-2026","dir":"YES","w":0.20},
        # 성장 둔화
        {"slug":"negative-gdp-growth-in-2026","dir":"YES","w":0.20},
    ]},
    "S4": {"label":"💀 복합위기","method":"weighted","markets":[
        # 극단 성장 붕괴
        {"slug":"negative-gdp-growth-in-2026","dir":"YES","w":0.35},
        # 침체 본격화
        {"slug":"us-recession-by-end-of-2026","dir":"YES","w":0.30},
        # 미국 중남미 개입 = 지정학 추가 확전
        {"slug":"will-the-us-invade-a-latin-american-country-in-2026","dir":"YES","w":0.35},
    ]},
}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def yp(s):
    try:return requests.get(f"https://query2.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(s)}?interval=1d&range=1d",headers=UA,timeout=10).json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except:return None
def yh(s,r="1y"):
    try:
        c=requests.get(f"https://query2.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(s)}?interval=1d&range={r}",headers=UA,timeout=15).json()["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        return[x for x in c if x is not None]
    except:return[]
def fv(s):
    if not FRED_API_KEY:return None
    try:return float(requests.get(f"https://api.stlouisfed.org/fred/series/observations?series_id={s}&api_key={FRED_API_KEY}&limit=1&sort_order=desc&file_type=json",timeout=10).json()["observations"][0]["value"])
    except:return None
def mom(h,days):
    if len(h)<days+1:return None
    return(h[-1]-h[-days-1])/h[-days-1]*100

# ── Legio v2.11 mom_score ──
VOL_PENALTY_DENOM=0.80
VOL_PENALTY_FLOOR=0.50
MOMMA_ALPHA=0.30
MOMMA_SLOPE_NORM=0.011
MOMMA_SLOPE_LB=5

def legio_mom_score(h):
    """Legio v2.11 가중 모멘텀 = base × vol_penalty × momma"""
    if len(h)<22:return None
    # ① base = 0.25×1M + 0.30×3M + 0.30×6M + 0.15×12M
    r1m=mom(h,21) or 0;r3m=mom(h,63) or 0;r6m=mom(h,126) or 0;r12m=mom(h,252) or 0
    if len(h)<63:r3m=mom(h,20) or 0
    if len(h)<126:r6m=mom(h,20) or 0
    if len(h)<252:r12m=r6m
    # 수익률을 비율로 (% → 소수)
    base=0.25*(r1m/100)+0.30*(r3m/100)+0.30*(r6m/100)+0.15*(r12m/100)
    # ② vol_penalty: 63일 연환산 변동성
    vp=1.0
    if len(h)>=63:
        rets=[]
        for j in range(len(h)-63,len(h)):
            if h[j-1]>0:rets.append((h[j]-h[j-1])/h[j-1])
        if len(rets)>=10:
            avg=sum(rets)/len(rets)
            var=sum((x-avg)**2 for x in rets)/(len(rets)-1)
            ann_vol=math.sqrt(var)*math.sqrt(252)
            vp=max(VOL_PENALTY_FLOOR,min(1.0,1.0-ann_vol/VOL_PENALTY_DENOM))
    # ③ momma: MA20 5일 기울기 감쇠
    mp=1.0
    if len(h)>=25:
        ma20_now=sum(h[-20:])/20
        ma20_prev=sum(h[-20-MOMMA_SLOPE_LB:-MOMMA_SLOPE_LB])/20
        if ma20_prev>0:
            slope=(ma20_now-ma20_prev)/ma20_prev
            slope_neg=min(slope/MOMMA_SLOPE_NORM,0.0)
            slope_neg=max(slope_neg,-1.0)
            mp=1.0+MOMMA_ALPHA*slope_neg
    return round(base*vp*mp,4)

# ── Legio RSI (Wilder 14일) ──
def compute_rsi(h,period=14):
    if len(h)<period+1:return None
    gains=[];losses=[]
    for i in range(len(h)-period,len(h)):
        d=h[i]-h[i-1]
        gains.append(max(d,0));losses.append(max(-d,0))
    avg_g=sum(gains)/period;avg_l=sum(losses)/period
    if avg_l==0:return 100.0
    rs=avg_g/avg_l
    return round(100-100/(1+rs),1)

# ── Legio 52주 최고가 거리 ──
W52_BOOST_ALPHA=0.15
def w52_distance(h):
    if len(h)<126:return None
    h252=h[-252:] if len(h)>=252 else h
    high=max(h252);cur=h[-1]
    if high<=0:return None
    pct=(cur/high-1)*100  # 고점 대비 % (0이면 고점, -10이면 고점 대비 -10%)
    return round(pct,1)

# ── Oracle 연속 하락일 ──
def consecutive_drops(h):
    if len(h)<2:return 0
    c=0
    for i in range(len(h)-1,0,-1):
        if h[i]<h[i-1]:c+=1
        else:break
    return c

# ── Legio 변동성 타겟 스케일 (SPY 기반) ──
TARGET_VOL=0.10
def vol_target(spy_h):
    if len(spy_h)<21:return 1.0
    rets=[]
    for i in range(len(spy_h)-20,len(spy_h)):
        if spy_h[i-1]>0:rets.append((spy_h[i]-spy_h[i-1])/spy_h[i-1])
    if len(rets)<19:return 1.0
    avg=sum(rets)/len(rets)
    var=sum((x-avg)**2 for x in rets)/(len(rets)-1)
    rv=math.sqrt(var)*math.sqrt(252)
    if rv<=0.01:return 1.0
    return round(max(0.20,min(1.0,TARGET_VOL/rv)),2)

# ── Defense 진입게이트 ──
def entry_gates(dxy,vix):
    if dxy is None or vix is None:return{"SLV":"--","COPX":"--","VEA":"--","block":False}
    if dxy>104:return{"SLV":"⛔0%","COPX":"⛔0%","VEA":"⛔0%","block":True}
    # SLV
    sd=100 if dxy<=97 else(50 if dxy<=100 else 0)
    sv=100 if vix<=24 else(50 if vix<=26 else 0)
    slv=min(sd,sv)
    # COPX
    cd=100 if dxy<=96 else(50 if dxy<=99 else 0)
    cv=100 if vix<=23 else(50 if vix<=25 else 0)
    copx=min(cd,cv)
    # VEA
    vea=100 if(dxy<=100 and vix<=26) else 0
    def fmt_gate(v):
        if v==100:return"🟢100%"
        if v==50:return"🟡50%"
        return"🔴0%"
    return{"SLV":fmt_gate(slv),"COPX":fmt_gate(copx),"VEA":fmt_gate(vea),"block":False}

def fetch():
    vix=yp("^VIX");vix3m=yp("^VIX3M");move=yp("^MOVE");wti=yp("CL=F")
    dxy=yp("DX-Y.NYB");rsp=yp("RSP");vvix=yp("^VVIX")
    hyg=yp("HYG");tlt=yp("TLT")
    krw=yp("KRW=X");btc=yp("BTC-USD");esf=yp("ES=F");nqf=yp("NQ=F")
    sh=yh("SPY","1y");rh=yh("RSP","2mo");mh=yh("^MOVE","2mo");wh=yh("CL=F","2mo")
    hyg_h=yh("HYG","2mo");tlt_h=yh("TLT","2mo");btc_h=yh("BTC-USD","2mo")
    oas=fv("BAMLH0A0HYM2");t5y=fv("T5YIE");sahm=fv("SAHMCURRENT")
    dfii=fv("DFII10");t10=fv("T10Y2Y");icsa=fv("ICSA")
    rrp=fv("RRPONTSYD");gs2=fv("GS2");gs10=fv("GS10")
    spy=sh[-1] if sh else None
    s200=sum(sh[-200:])/200 if len(sh)>=200 else None
    s60=sum(sh[-60:])/60 if len(sh)>=60 else None
    def bd(a,m):
        if not m:return 0
        c=0
        for p in reversed(a):
            if p<m:c+=1
            else:break
        return c
    b200=bd(sh,s200);b60=bd(sh,s60);br60=(spy-s60)/s60 if spy and s60 else None
    wc=(wh[-1]-wh[-8])/wh[-8] if len(wh)>=8 else None
    vv=vix/vix3m if vix and vix3m and vix3m>0 else None
    mm=sum(mh[-20:])/20 if len(mh)>=20 else None
    mr=move/mm if move and mm and mm>0 else None
    brd=None
    if len(sh)>=22 and len(rh)>=22:
        sr=sh[-1]/sh[-22];rr_=rh[-1]/rh[-22]
        if rr_>0:brd=sr/rr_
    s1d=mom(sh,1);s1w=mom(sh,5);s1m=mom(sh,22)
    # 유동성 일간변화
    hyg_1d=mom(hyg_h,1);tlt_1d=mom(tlt_h,1);btc_1d=mom(btc_h,1)
    # 종목별
    hdata={}
    for tk in TICKERS:
        h=yh(tk,"1y");p=h[-1] if h else yp(tk)
        ms=legio_mom_score(h)
        rsi=compute_rsi(h)
        w52=w52_distance(h)
        cdrops=consecutive_drops(h)
        hdata[tk]={"p":p,"1D":mom(h,1),"1M":mom(h,22),"3M":mom(h,63),"6M":mom(h,126),"12M":mom(h,252),"score":ms,"rsi":rsi,"w52":w52,"cdrops":cdrops}
    gp=hdata.get("GLD",{}).get("p");sp_=hdata.get("SLV",{}).get("p");cp=hdata.get("COPX",{}).get("p")
    gs_r=gp/sp_ if gp and sp_ and sp_>0 else None
    cg_r=cp/gp if cp and gp and gp>0 else None
    # 엔진 함수
    vt=vol_target(sh)
    eg=entry_gates(dxy,vix)
    return{
        "VIX":vix,"VIX3M":vix3m,"MOVE":move,"OAS":oas,"WTI":wti,"SPY":spy,
        "T5YIE":t5y,"DXY":dxy,"RSP":rsp,"DFII10":dfii,"T10Y2Y":t10,"ICSA":icsa,
        "SAHM":sahm,"S200":s200,"S60":s60,"b200":b200,"b60":b60,"br60":br60,
        "WC":wc,"VV":vv,"MM":mm,"MR":mr,"BRD":brd,"S1D":s1d,"S1W":s1w,"S1M":s1m,
        "VVIX":vvix,"HYG":hyg,"TLT":tlt,"RRP":rrp,"GS2":gs2,"GS10":gs10,
        "KRW":krw,"BTC":btc,"ESF":esf,"NQF":nqf,
        "GS_R":gs_r,"CG_R":cg_r,"H":hdata,"VT":vt,"EG":eg,
        "HYG_1D":hyg_1d,"TLT_1D":tlt_1d,"BTC_1D":btc_1d,
    }

# ── Oracle ──
def lin(v,lo,hi,mx):
    if v<=lo:return 0
    if v>=hi:return mx
    return round(mx*(v-lo)/(hi-lo),2)
def calc_tide(s,ic):
    s=s or 0;ic=ic or 220000
    if s>=0.50:return"RECESSION_CONFIRMED"
    if s>=0.30:return"RECESSION_WATCH"
    if s>=0.25 or ic>=300000:return"SLOWDOWN"
    return"EXPANSION"
def calc_inferno(t,w):
    t=t or 2.5;w=w or 80
    if t<1.5:return"DEFLATION_RISK"
    if t>=3.0 or w>=120:return"HOT"
    if t>=2.7 or w>=95:return"RISING"
    return"STABLE"
def calc_curve(s):
    s=s if s is not None else 0.5
    if s<=-0.5:return"DEEP_INVERT"
    if s<=0:return"INVERTED"
    if s<=0.3:return"FLAT"
    return"NORMAL"
def calc_gradient(d):
    vs=lin(d["VIX"]or 18,18,30,25);os_=lin(d["OAS"]or 3,3,5.5,25);ms=lin(d["MOVE"]or 80,80,130,25)
    mr=d.get("MR")
    if mr and mr>1.0:
        b=5 if mr>=1.20 else 4 if mr>=1.15 else 3 if mr>=1.10 else 1.5 if mr>=1.05 else 0
        ms=min(25,ms+b)
    fs=8;rr=lin(d["DFII10"]or 1.0,0.5,2.5,15) if d.get("DFII10") else 0
    t=min(100,round(vs+os_+ms+fs+rr,1));df=round(10+(t/100)*80,1)
    if t<20:bk="🟢GREEN"
    elif t<40:bk="🟡경계"
    elif t<60:bk="🟡YELLOW"
    elif t<80:bk="🟠RED"
    else:bk="🔴STORM"
    return{"t":t,"bk":bk,"df":df,"ak":round(100-df,1),"vs":vs,"os":os_,"ms":ms,"fs":fs,"rr":rr}
def calc_regime(d,g):
    td=calc_tide(d["SAHM"],d["ICSA"]);inf=calc_inferno(d["T5YIE"],d["WTI"]);cv=calc_curve(d["T10Y2Y"])
    df=d["DFII10"]or 1.0;gt=g["t"];sm=d["SAHM"]
    if td=="RECESSION_CONFIRMED" or(td=="RECESSION_WATCH" and cv=="DEEP_INVERT"):return{"l":"🔴🔴 침체확정","rp":60,"td":td,"inf":inf,"cv":cv}
    if td in("SLOWDOWN","RECESSION_WATCH") and inf in("RISING","HOT"):return{"l":"🟠 스태그플레이션","rp":30,"td":td,"inf":inf,"cv":cv}
    if td in("SLOWDOWN","RECESSION_WATCH") and inf=="STABLE":return{"l":"🔴 침체경계","rp":40,"td":td,"inf":inf,"cv":cv}
    if td in("SLOWDOWN","RECESSION_WATCH") and inf=="DEFLATION_RISK":return{"l":"🔵 디플레형","rp":45,"td":td,"inf":inf,"cv":cv}
    if td=="EXPANSION" and df>1.5 and inf in("RISING","HOT"):return{"l":"🟡 고금리","rp":20,"td":td,"inf":inf,"cv":cv}
    if td=="EXPANSION" and gt<15 and(sm or 0)<0.15 and cv!="DEEP_INVERT":return{"l":"🟢🟢 초강세장","rp":5,"td":td,"inf":inf,"cv":cv}
    return{"l":"🟢 확장기","rp":10,"td":td,"inf":inf,"cv":cv}
def calc_triggers(d):
    vix=d["VIX"]or 0;move=d["MOVE"]or 0;oas=d["OAS"]or 0;wti=d["WTI"]or 0;t5y=d["T5YIE"]or 0;vv=d["VV"]or 0
    ids=["E0","E1","E2","E3","E4","L0a","L0b","L1","L2","L3"]
    act=[vix>=30 or vv>1.05,t5y>3 and wti>120,d["b200"]>=5,d["BRD"]is not None and d["BRD"]>=1.12,d["WC"]is not None and d["WC"]>=0.20,oas>=5.8,oas>=5.2,vix>=42 or move>=190 or oas>=8.5,vix>=45,d["b60"]>=12 and d.get("br60")is not None and d["br60"]<=-0.05]
    chips=" ".join(f"🔴{ids[i]}" if act[i] else f"⚪{ids[i]}" for i in range(len(ids)))
    stg="CLEAR"
    if act[9]:stg="L3"
    elif act[8]:stg="L2"
    elif act[7]:stg="L1"
    elif act[5]or act[6]:stg="L0"
    elif any(act[:5]):stg="PRE"
    gld=t5y>=3.0 or(t5y>=2.7 and wti>=95)
    return{"chips":chips,"stg":stg,"gld":gld}

# ── 유틸 ──
def f(v,u="",dc=1):
    if v is None:return"--"
    return f"{u}{v:.{dc}f}"
def sg(v):
    if v is None:return"--"
    return f"+{v:.1f}%" if v>=0 else f"{v:.1f}%"
def dot(ok):
    if ok is None:return"❓"
    return"🟢" if ok else"🔴"
def dot3(v,good,warn):
    """3단계 신호등: 🟢정상 🟡경고 🔴위험"""
    if v is None:return"❓"
    if isinstance(good,str):
        if good=="pos":return"🟢" if v>0 else("🟡" if v>-2 else"🔴")
        if good=="neg":return"🟢" if v<0 else("🟡" if v<2 else"🔴")
    if warn is None:return"🟢" if v<good else"🔴"
    if v<good:return"🟢"
    if v<warn:return"🟡"
    return"🔴"
def momdot(v):
    if v is None:return"⚪"
    if v>=5:return"🟢"
    if v>=0:return"🟡"
    if v>=-5:return"🟠"
    return"🔴"
def send(p):
    if not DISCORD_WEBHOOK:return
    try:requests.post(DISCORD_WEBHOOK,json=p,timeout=10)
    except:pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔭 Polymarket §3.5 시나리오 확률
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def poly(slug):
    """Polymarket Gamma API: slug로 YES outcome 가격 (0~1) 반환. 실패 시 None."""
    try:
        r=requests.get("https://gamma-api.polymarket.com/markets",params={"slug":slug},timeout=10)
        if r.status_code!=200:return None
        data=r.json()
        if not data:return None
        m=data[0] if isinstance(data,list) else data
        # outcomePrices는 JSON 문자열 형태로 올 수 있음
        raw=m.get("outcomePrices")
        if isinstance(raw,str):
            try:prices=json.loads(raw)
            except:prices=[]
        else:prices=raw or []
        if prices:return float(prices[0])  # 첫 번째 outcome = YES
        lt=m.get("lastTradePrice")
        return float(lt) if lt else None
    except:return None

def calc_oracle():
    """S1~S4 정규화 확률 계산. 반환: (probs dict, raw_markets dict, status dict)"""
    raw_scores={};raw_markets={};status={}
    for sid,sc in SCENARIO_MAP.items():
        if sc["method"]=="complement":
            raw_scores[sid]=None;status[sid]={"ok":0,"total":0};continue
        tot=0.0;ws=0.0;ok=0
        for m in sc["markets"]:
            p=poly(m["slug"])
            if p is None:continue
            raw_markets[m["slug"]]=p;ok+=1
            contrib=p if m["dir"]=="YES" else(1.0-p)
            tot+=contrib*m["w"];ws+=m["w"]
        raw_scores[sid]=(tot/ws) if ws>0 else 0.0
        status[sid]={"ok":ok,"total":len(sc["markets"])}
    # complement 처리: 1 - (나머지 합)
    nc=[v for v in raw_scores.values() if v is not None]
    comp=max(0.0,1.0-sum(nc))
    for sid,v in raw_scores.items():
        if v is None:raw_scores[sid]=comp
    # 정규화 (합=100%)
    tot=sum(raw_scores.values()) or 1.0
    probs={sid:round(v/tot*100,1) for sid,v in raw_scores.items()}
    return probs,raw_markets,status

def build_oracle_embed(probs,raw_markets,status):
    """🔭 Oracle §3.5 Polymarket 시나리오 확률 embed 생성"""
    def bar(p):
        n=int(round(p/5))  # 5%당 █ 하나 (최대 20칸)
        n=max(0,min(20,n))
        return"█"*n+"░"*(20-n)
    # 주도 시나리오
    max_sid=max(probs,key=probs.get)
    max_label=SCENARIO_MAP[max_sid]["label"]
    # 시나리오별 라인
    lines=[]
    for sid in["S1","S2","S3","S4"]:
        p=probs[sid];lab=SCENARIO_MAP[sid]["label"]
        st=status[sid];cov=f" `{st['ok']}/{st['total']}`" if st["total"]>0 else""
        mk=" 🔴**주도**" if sid==max_sid else""
        lines.append(f"{lab} `{p:5.1f}%` {bar(p)}{cov}{mk}")
    # 원천 마켓 노출 (상위 6개)
    mk_lines=[]
    if raw_markets:
        for slug,price in list(raw_markets.items())[:6]:
            short=slug if len(slug)<=45 else slug[:42]+"..."
            mk_lines.append(f"▸ `{short}` **{price*100:.0f}%**")
    else:
        mk_lines.append("⚠️ 모든 마켓 조회 실패 — SCENARIO_MAP의 slug 갱신 필요")
    desc=(
        f"**주도 시나리오**: {max_label} (`{probs[max_sid]:.1f}%`)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        +"\n".join(lines)+
        f"\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**📎 원천 마켓 스냅샷**\n"+"\n".join(mk_lines)+
        f"\n\n*커버리지 `ok/total`: 조회 성공 마켓 수. 0/N이면 해당 시나리오 slug 갱신 필요*"
    )
    return{"title":"§3.5 🔭 Oracle │ Polymarket 시나리오 확률","color":0x9B59B6,"description":desc}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📜 오늘의 명언 (quotes.json 기반 date rotation, API 호출 無)
# 편집: quotes.json 파일에서 {"ko","en","author","tag"} 구조로 추가
# 회전: 매일 3개씩 전진, 같은 날은 동일 결과 (idempotent)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUOTES_FILE=os.path.join(os.path.dirname(os.path.abspath(__file__)),'quotes.json')

def load_quotes():
    """quotes.json 로드. 실패 시 빈 리스트."""
    try:
        with open(QUOTES_FILE,'r',encoding='utf-8') as f:
            return json.load(f).get('quotes',[])
    except Exception as e:
        print(f"  ⚠️ quotes.json 로드 실패: {e}")
        return []

def pick_daily_quotes(quotes,n=3):
    """카테고리 균형 rotation: 매일 각 카테고리에서 1개씩 (date-deterministic)"""
    if not quotes:return[]
    today_ord=datetime.now(KST).date().toordinal()
    # 카테고리별 분리
    by_tag={}
    for q in quotes:
        by_tag.setdefault(q.get('tag','기타'),[]).append(q)
    tags_sorted=sorted(by_tag.keys())  # 일관된 순서 보장
    picks=[]
    for i,tag in enumerate(tags_sorted[:n]):
        pool=by_tag[tag]
        if pool:
            idx=(today_ord+i*7)%len(pool)  # 카테고리별 다른 오프셋
            picks.append(pool[idx])
    # n이 카테고리 수보다 많으면 나머지는 전체에서 순차 채움
    if len(picks)<n:
        used=set(id(p) for p in picks)
        remaining=[q for q in quotes if id(q) not in used]
        for i in range(n-len(picks)):
            if remaining:
                idx=(today_ord*13+i)%len(remaining)
                picks.append(remaining[idx])
    return picks[:n]

def build_quotes_embed(quotes):
    """📜 오늘의 명언 embed 생성"""
    if not quotes:return None
    tag_emoji={"투자":"💰","경영":"🏢","자기성찰":"🧘"}
    lines=[]
    for q in quotes:
        ko=q.get('ko','');en=q.get('en','');author=q.get('author','?');tag=q.get('tag','')
        em=tag_emoji.get(tag,"📖")
        lines.append(f"{em} **{ko}**\n> — *{author}*\n> _\"{en}\"_")
    return{"title":"§9 📜 오늘의 명언","color":0xE8B923,"description":"\n\n".join(lines)}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🟠 SOLIDUS BTC 통합 모듈 (v1.3 이식, 2026-04-22)
# 원본: solidus-daily-briefing repo / 최소 침습 이식
# 독립적 urllib 사용 (INVICTUS requests와 공존)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
import urllib.request as _sol_urlreq
SOLIDUS_WEIGHTS={"mvrv":0.30,"etf":0.25,"fng":0.20,"dxy":0.15,"btc24h":0.10}
SOLIDUS_UA={"User-Agent":"Mozilla/5.0 (compatible; SOLIDUS-Briefing/1.3-integrated)"}

def _sol_get(url,timeout=15,retries=2):
    """urllib 기반 JSON GET + 지수백오프 리트라이 (SOLIDUS 원본 로직)"""
    import time as _t
    for attempt in range(retries+1):
        try:
            req=_sol_urlreq.Request(url,headers=SOLIDUS_UA)
            with _sol_urlreq.urlopen(req,timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if attempt<retries:_t.sleep(2**attempt)
            else:print(f"  [SOL FAIL] {url[:60]}: {e}")
    return None

def _sol_yahoo_close(symbol,days=10):
    end=int(datetime.now(timezone.utc).timestamp());start=end-(days+5)*86400
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={start}&period2={end}&interval=1d"
    d=_sol_get(url)
    if not d:return None
    try:
        closes=d["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        return [c for c in closes if c is not None]
    except:return None

def fetch_btc_price():
    """CoinGecko: BTC 가격 + 24h 변동률 + 시총"""
    url="https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true&include_market_cap=true"
    d=_sol_get(url)
    if not d or "bitcoin" not in d:return{"price":None,"change_24h":None,"mcap":None}
    b=d["bitcoin"]
    return{"price":b.get("usd"),"change_24h":b.get("usd_24h_change"),"mcap":b.get("usd_market_cap")}

def fetch_fng():
    """Alternative.me: Fear & Greed (0~100)"""
    d=_sol_get("https://api.alternative.me/fng/?limit=1")
    if not d or "data" not in d or not d["data"]:return None
    try:return int(d["data"][0]["value"])
    except:return None

def fetch_dxy_change_5d():
    closes=_sol_yahoo_close("DX-Y.NYB",days=10)
    if not closes or len(closes)<6:return None
    return(closes[-1]/closes[-6]-1)*100

def fetch_sol_vix():
    """SOLIDUS 전용 VIX (INVICTUS 센서와 별도 호출)"""
    closes=_sol_yahoo_close("^VIX",days=5)
    return closes[-1] if closes else None

def fetch_mvrv():
    """bitcoin-data.com: MVRV Z-Score → MVRV 비율 근사"""
    d=_sol_get("https://bitcoin-data.com/api/v1/mvrv-zscore/last")
    if not d:return None
    try:
        z=float(d.get("mvrvZscore",d.get("value",0)))
        return 1.5+z*0.6  # Z=0→1.5, Z=3→3.3 근사
    except:return None

def fetch_etf_flow_7d():
    """BTC ETF 7일 플로우 - 무료 소스 미구현, 보수적으로 None (스코어 제외)"""
    return None

# 스코어 매핑 (0~100)
def _sc_mvrv(v):
    if v is None:return None
    if v<1.0:return 90
    if v<1.5:return 70
    if v<2.5:return 50
    if v<3.5:return 30
    return 10
def _sc_fng(v):
    if v is None:return None
    if v<=25:return 80
    if v<=45:return 60
    if v<=55:return 50
    if v<=75:return 40
    return 20
def _sc_etf(v):
    if v is None:return None
    if v<-500:return 20
    if v<0:return 40
    if v<500:return 60
    if v<1000:return 75
    return 90
def _sc_dxy(v):
    if v is None:return None
    if v<-1.0:return 70
    if v<0.5:return 50
    return 30
def _sc_btc24h(v):
    if v is None:return None
    if v<-5:return 70
    if v<-2:return 60
    if v<2:return 50
    if v<5:return 40
    return 30

def compute_sol_target(scores,vix,mvrv,btc24h):
    """가중평균 목표비중 + 게이팅"""
    available={k:v for k,v in scores.items() if v is not None}
    if not available:return 0.0,["NO_DATA"],0
    tw=sum(SOLIDUS_WEIGHTS[k] for k in available)
    target=sum(available[k]*SOLIDUS_WEIGHTS[k] for k in available)/tw
    gates=[]
    if vix is not None and vix>30:
        target=min(target,70);gates.append(f"VIX>30({vix:.1f}) CAP=70%")
    if mvrv is not None and mvrv>4.0:
        target=min(target,30);gates.append(f"MVRV>4.0({mvrv:.2f}) CAP=30%")
    if btc24h is not None and btc24h>10:
        gates.append(f"24h>+10%({btc24h:.1f}%) NO-INCREASE")
    target=max(0.0,min(100.0,target))
    return target,gates,len(available)

# 방향 이모지
def _arr_mvrv(v):
    if v is None:return"—"
    return"🟢 저평가" if v<1.5 else("🟡 중립" if v<2.5 else("🟠 고평가" if v<3.5 else"🔴 과열"))
def _arr_etf(v):
    if v is None:return"—"
    return"🔴 유출" if v<0 else("🟡 미약" if v<500 else"🟢 유입")
def _arr_fng(v):
    if v is None:return"—"
    if v<=25:return"🟢 공포"
    if v<=45:return"🟡 약공포"
    if v<=55:return"⚪ 중립"
    if v<=75:return"🟠 탐욕"
    return"🔴 극탐욕"
def _arr_dxy(v):
    if v is None:return"—"
    return"🟢 약달러" if v<-0.5 else("⚪ 중립" if v<0.5 else"🔴 강달러")
def _arr_vix(v):
    if v is None:return"—"
    return"🟢 평온" if v<20 else("🟡 경계" if v<30 else"🔴 위기")

def build_solidus_embeds(sd):
    """🟠 SOLIDUS BTC 블록 embed 2개 반환"""
    def _f(v,unit="",nd=2,na="N/A"):
        if v is None:return na
        return f"{v:,.{nd}f}{unit}"
    target=sd["target"];price=sd["price"];ch24=sd["change_24h"];mcap=sd.get("mcap")
    mvrv=sd["mvrv"];etf=sd["etf_flow"];fng=sd["fng"];dxy=sd["dxy_5d"];vix=sd["vix"]
    gates=sd["gates"];n_ind=sd["n_indicators"]
    # Embed 1: 헤더 + 가격 + 목표비중
    price_str=_f(price,nd=0)
    mcap_str=f"${mcap/1e12:.2f}T" if mcap else"N/A"
    desc1=(f"💰 **BTC** ${price_str}  ({_f(ch24,'%',2)})\n"
           f"📊 시가총액 {mcap_str}\n\n"
           f"🎯 **참고 목표비중: {target:.1f}%**\n"
           f"⚠️ 경량 프록시 참고치 (지표 {n_ind}/5). 최종 결정은 👑Commander.")
    e1={"title":"§7 [Part 3] 🟠 SOLIDUS BTC 데일리","color":0xF7931A,"description":desc1}
    # Embed 2: 5지표 테이블 + 게이팅
    table=f"```\n{'지표':<13}{'값':<11}방향\n{'─'*38}\n"
    rows=[
        ("MVRV",_f(mvrv,nd=2),_arr_mvrv(mvrv)),
        ("ETF 7d",_f(etf,'',0) if etf is not None else"N/A",_arr_etf(etf)),
        ("Fear&Greed",str(fng) if fng is not None else"N/A",_arr_fng(fng)),
        ("DXY 5d",_f(dxy,'%',2),_arr_dxy(dxy)),
        ("VIX",_f(vix,nd=1),_arr_vix(vix)),
    ]
    for n,v,dr in rows:table+=f"{n:<13}{v:<11}{dr}\n"
    table+="```"
    gate_str="\n".join(f"• {g}" for g in gates) if gates else"_(발동된 게이팅 없음)_"
    desc2=(f"**📊 5지표**\n{table}\n"
           f"**🛡️ 게이팅**\n{gate_str}\n\n"
           f"_가중치 SSOT: MVRV 30% │ ETF 25% │ F&G 20% │ DXY 15% │ BTC24h 10%_")
    e2={"title":"§8 [Part 3] 📊 SOLIDUS 5지표 & 게이팅","color":0xF7931A,"description":desc2}
    return[e1,e2]

def collect_solidus():
    """SOLIDUS 전체 데이터 수집 + 스코어링 + 목표비중 계산"""
    btc=fetch_btc_price()
    fng=fetch_fng()
    dxy5d=fetch_dxy_change_5d()
    svix=fetch_sol_vix()
    mvrv=fetch_mvrv()
    etf=fetch_etf_flow_7d()
    scores={"mvrv":_sc_mvrv(mvrv),"etf":_sc_etf(etf),"fng":_sc_fng(fng),
            "dxy":_sc_dxy(dxy5d),"btc24h":_sc_btc24h(btc["change_24h"])}
    target,gates,n_ind=compute_sol_target(scores,svix,mvrv,btc["change_24h"])
    return{"target":target,"price":btc["price"],"change_24h":btc["change_24h"],
           "mcap":btc.get("mcap"),"mvrv":mvrv,"etf_flow":etf,"fng":fng,
           "dxy_5d":dxy5d,"vix":svix,"gates":gates,"n_indicators":n_ind}

# ── 브리핑 생성 ──
def build(d,reg,grd,trg,oracle):
    now=datetime.now(KST);date=now.strftime("%Y-%m-%d (%a)")
    stg=trg["stg"];se={"CLEAR":"🟢","PRE":"🟡","L0":"🟠","L1":"🔴","L2":"🔴🔴","L3":"⚫"}.get(stg,"⚪")
    sc={"CLEAR":0x3DBB7E,"PRE":0xEFB030,"L0":0xEFB030,"L1":0xE07238,"L2":0xD83030,"L3":0x2C2C2A}.get(stg,0x5B9CF6)
    vs200=f"{(d['SPY']-d['S200'])/d['S200']*100:+.1f}%" if d['SPY'] and d['S200'] else"--"
    vs60=f"{(d['SPY']-d['S60'])/d['S60']*100:+.1f}%" if d['SPY'] and d['S60'] else"--"
    rv=d["VIX"]is not None and d["VIX"]<20;rm=d["MOVE"]is not None and d["MOVE"]<100;rs=d["SAHM"]is not None and d["SAHM"]<0.30

    # 1️⃣ 핵심 요약
    vt=d["VT"];vt_pct=int(vt*100)
    eff_atk=round(grd['ak']*vt,1)  # 실효 공격 = 그래디언트 공격 × VT스케일
    vt_dot="🟢" if vt_pct>=80 else("🟡" if vt_pct>=50 else"🔴")
    e1={"title":f"§1 🛡️ INVICTUS 모닝 리포트 ☕ — {date}","color":sc,"description":(
        f"{se} **경보 {stg}** │ **{reg['l']}** │ RP **{reg['rp']}%**\n"
        f"📊 그래디언트 **{grd['t']}**/100 {grd['bk']} │ 🛡️방어 {grd['df']}% │ ⚔️공격 {grd['ak']}%\n"
        f"{vt_dot} **VT스케일** {vt_pct}% → 실효공격 **{eff_atk}%** (공격×SPY변동성축소)"
    )}

    # 2️⃣ 센서
    e2={"title":"§2 📡 핵심 센서","color":0x5B9CF6,"description":(
        f"{dot3(d['VIX'],30,42)} **VIX {f(d['VIX'])}** 공포지수 │ "
        f"{dot3(d['MOVE'],150,190)} **MOVE {f(d['MOVE'],dc=0)}** 채권변동성 │ "
        f"{dot3(d['OAS'],5.2,5.8)} **OAS {f(d['OAS'],'',2)}%** 신용위험\n"
        f"{dot3(d['WTI'],95,120)} **WTI ${f(d['WTI'])}** 유가 │ "
        f"{dot3(d['T5YIE'],2.7,3.0)} **T5YIE {f(d['T5YIE'],'',2)}%** 기대인플레 │ "
        f"{dot3(d['DXY'],100,104)} **DXY {f(d['DXY'],dc=2)}** 달러강도\n"
        f"{dot3(d['VVIX'],110,130)} **VVIX {f(d['VVIX'],dc=0)}** VIX선행경보 │ "
        f"{dot3(d['MR'],1.05,1.10) if d['MR'] else'❓'} **MOVE/MA20 {f(d['MR'],dc=3)}** 채권급변 │ "
        f"{dot3(d['VV'],1.00,1.05) if d['VV'] else'❓'} **VIX/VIX3M {f(d['VV'],dc=3)}** 단기공포"
    )}

    # 3️⃣ 레짐 + TIER2
    td_dot={"EXPANSION":"🟢","SLOWDOWN":"🟡","RECESSION_WATCH":"🟠","RECESSION_CONFIRMED":"🔴"}.get(reg["td"],"❓")
    inf_dot={"STABLE":"🟢","RISING":"🟡","HOT":"🔴","DEFLATION_RISK":"🔵"}.get(reg["inf"],"❓")
    cv_dot={"NORMAL":"🟢","FLAT":"🟡","INVERTED":"🟠","DEEP_INVERT":"🔴"}.get(reg["cv"],"❓")
    e3={"title":"§3 🏛️ 레짐 │ 경기·물가·금리","color":0xEFB030,"description":(
        f"{td_dot} **TIDE {reg['td']}** 경기사이클 │ "
        f"{inf_dot} **INFERNO {reg['inf']}** 물가환경 │ "
        f"{cv_dot} **CURVE {reg['cv']}** 수익률곡선\n"
        f"{dot3(d['DFII10'],1.5,2.0) if d['DFII10'] else'❓'} **DFII10 {f(d['DFII10'],'',2)}%** 실질금리 │ "
        f"{'🟢' if d['T10Y2Y'] and d['T10Y2Y']>0 else'🔴'} **T10Y2Y {f(d['T10Y2Y'],'',2)}%** 장단기차 │ "
        f"{dot3(d['SAHM'],0.25,0.30) if d['SAHM'] else'❓'} **SAHM {f(d['SAHM'],'',2)}** 실업판정\n"
        f"🏦 **2Y {f(d['GS2'],'',2)}%** │ **10Y {f(d['GS10'],'',2)}%** │ "
        f"{dot3(d['ICSA'],250000,300000) if d['ICSA'] else'❓'} **ICSA {f(d['ICSA'],'',0)}** 실업수당\n\n"
        f"**그래디언트 분해** ({grd['t']}/100)\n"
        f"VIX **{grd['vs']}**/25 │ OAS **{grd['os']}**/25 │ MOVE **{grd['ms']}**/25 │ FLOW **{grd['fs']}**/25 │ RR **{grd['rr']}**/15"
    )}

    # 3.5️⃣ 🔭 Oracle Polymarket 시나리오 (🆕)
    e3_5=build_oracle_embed(*oracle)

    # 4️⃣ 유동성 + 글로벌
    rrp_t=f"{d['RRP']/1e9:.0f}B" if d['RRP'] else"--"
    e4={"title":"§4 💧 유동성 │ 글로벌 │ 환율","color":0x1DA1F2,"description":(
        f"{'🟡' if d['RRP'] and d['RRP']>500e9 else'🟢'} **RRP ${rrp_t}** 역레포잔고 │ "
        f"{momdot(d['HYG_1D'])} **HYG ${f(d['HYG'])}** ({sg(d['HYG_1D'])}) 하이일드 │ "
        f"{momdot(d['TLT_1D'])} **TLT ${f(d['TLT'])}** ({sg(d['TLT_1D'])}) 장기국채\n"
        f"{'🟡' if d['KRW'] and d['KRW']>1350 else'🟢'} **원/달러 {f(d['KRW'],dc=0)}원** │ "
        f"{momdot(d['BTC_1D'])} **BTC ${f(d['BTC'],dc=0)}** ({sg(d['BTC_1D'])}) 위험자산심리\n"
        f"{momdot(d['S1D'])} **S&P선물 {f(d['ESF'],dc=0)}** │ **나스닥선물 {f(d['NQF'],dc=0)}** 오늘장 방향\n"
        f"{'🔴' if d['GS_R'] and d['GS_R']>80 else('🟡' if d['GS_R'] and d['GS_R']>70 else'🟢')} **금/은비 {f(d['GS_R'],dc=1)}** 높으면 공포 │ "
        f"{'🟢' if d['CG_R'] and d['CG_R']>0.20 else('🟡' if d['CG_R'] and d['CG_R']>0.15 else'🔴')} **구리/금비 {f(d['CG_R'],dc=3)}** 높으면 성장"
    )}

    # 5️⃣ 보유종목 모멘텀 (Legio 20종목 중 Top10)
    ranked=[]
    for tk in TICKERS:
        h=d["H"].get(tk,{})
        sc=h.get("score")
        ranked.append((tk,h,sc if sc is not None else -999))
    ranked.sort(key=lambda x:x[2],reverse=True)
    lines=[]
    for i,(tk,h,scv) in enumerate(ranked[:10]):
        em=EMOJIS.get(tk,"")
        p=h.get("p");d1=h.get("1D");m1=h.get("1M");m3=h.get("3M")
        sc=h.get("score");rsi=h.get("rsi");w52=h.get("w52");cd=h.get("cdrops",0)
        sc_str=f"{sc:+.3f}" if sc is not None else"--"
        sc_dot=momdot(sc*100 if sc else None)
        # RSI 신호등
        rsi_dot="❓"
        if rsi is not None:
            if rsi>=70:rsi_dot="🔴"  # 과매수
            elif rsi>=60:rsi_dot="🟡"
            elif rsi<=30:rsi_dot="🔵"  # 과매도 (매수기회)
            elif rsi<=40:rsi_dot="🟡"
            else:rsi_dot="🟢"
        # 52주 신호등
        w52_dot="❓"
        if w52 is not None:
            if w52>=-3:w52_dot="🟢"  # 고점 근접
            elif w52>=-10:w52_dot="🟡"
            else:w52_dot="🔴"  # 고점 대비 -10% 이상 하락
        # 연속하락 경고
        cd_str=f" ⚠️{cd}일↓" if cd>=3 else""
        lines.append(
            f"**#{i+1}** {sc_dot} {em}{tk} **{sc_str}** │ "
            f"${f(p)} │ 1D {sg(d1)}\n"
            f"　　{rsi_dot}RSI {f(rsi,dc=0)} │ "
            f"{w52_dot}52주 {f(w52)}%{cd_str}"
        )
    e5={"title":"§5 📊 Legio 모멘텀 Top10 (20종목 중)","color":0x3DBB7E,"description":(
        "\n".join(lines)
    )}

    # 6️⃣ SPY + 트리거 + 재진입 + 진입게이트
    eg=d["EG"]
    e6={"title":"§6 📈 SPY │ 트리거 │ 재진입 │ 진입게이트","color":0x3DBB7E,"description":(
        f"{momdot(d['S1D'])} **SPY ${f(d['SPY'])}** │ 1D **{sg(d['S1D'])}** │ 1W **{sg(d['S1W'])}** │ 1M **{sg(d['S1M'])}**\n"
        f"{'🟢' if vs200[0]=='+' else'🔴'} vs200MA **{vs200}** │ {'🟢' if vs60[0]=='+' else'🔴'} vs60MA **{vs60}** │ {dot3(d['BRD'],1.08,1.12) if d['BRD'] else'❓'} BREADTH **{f(d['BRD'],dc=3)}**\n"
        f"{dot(d['b200']<5)} 200MA하회 **{d['b200']}일** │ {dot(d['b60']<12)} 60MA하회 **{d['b60']}일**\n\n"
        f"{trg['chips']}\n"
        f"🥇 GLD매도 {'🚫금지' if trg['gld'] else'✅허용'}\n\n"
        f"**재진입조건** (전부 충족 필수)\n"
        f"{dot(rv)} VIX<20 **{f(d['VIX'])}** │ {dot(rm)} MOVE<100 **{f(d['MOVE'],dc=0)}** │ {dot(rs)} SAHM<0.30 **{f(d['SAHM'],'',2)}**\n\n"
        f"**진입게이트** (DXY {f(d['DXY'],dc=1)} │ VIX {f(d['VIX'])})\n"
        f"🥈SLV **{eg['SLV']}** │ 🟤COPX **{eg['COPX']}** │ 🌍VEA **{eg['VEA']}**"
    )}

    # 7️⃣ 각주
    e7={"color":0x485070,"description":(
        "📖 **트리거 각주**\n"
        "▸ **E0** PRE_STORM: VIX≥30 or VIX/VIX3M>1.05 → 공격매수 억제\n"
        "▸ **E1** INFERNO: T5YIE>3%+WTI>$120 → RP 20% 강제\n"
        "▸ **E2** BULL_BREAK: SPY<200MA 5일연속 → 공격매수 차단\n"
        "▸ **E3** BREADTH: SPY/RSP 1M≥1.12 → 공격매수 차단\n"
        "▸ **E4** ATTRITION: WTI 주간≥+20% → 공격매수 차단\n"
        "▸ **L0a** AEGIS: OAS≥5.8% → RP 20%+비례축소\n"
        "▸ **L0b** AEGIS-SB: OAS≥5.2% → L1 즉시승급 준비\n"
        "▸ **L1** STORM: VIX≥42/MOVE≥190/OAS≥8.5% → SMH·EWZ 전량매도\n"
        "▸ **L2** FAST_CRASH: VIX≥45 or SPY 1일-7% → SLV·COPX·XLU 추가매도\n"
        "▸ **L3** KILLSWITCH: SPY 60MA-5% 12일 → 잔여공격 전량매도\n\n"
        "📖 **지표 각주**\n"
        "▸ **VIX** 공포지수 🟢<30 🟡30~42 🔴42↑ │ **MOVE** 채권변동성 🟢<150 🟡150~190 🔴190↑\n"
        "▸ **OAS** 신용스프레드 🟢<5.2 🟡5.2~5.8 🔴5.8↑ │ **WTI** 유가 🟢<95 🟡95~120 🔴120↑\n"
        "▸ **T5YIE** 기대인플레 🟢<2.7 🟡2.7~3.0 🔴3.0↑ │ **DXY** 달러 🟢<100 🟡100~104 🔴104↑\n"
        "▸ **VVIX** VIX선행 🟢<110 🟡110~130 🔴130↑ │ **DFII10** 실질금리 🟢<1.5 🟡1.5~2.0 🔴2.0↑\n"
        "▸ **T10Y2Y** 장단기차 🟢양수 🔴역전 │ **SAHM** 실업 🟢<0.25 🟡0.25~0.30 🔴0.30↑\n"
        "▸ **RRP** 역레포 🟢<500B 🟡500B↑ │ **HYG** 하이일드 ↓=신용불안 │ **TLT** 국채 ↑=금리하락\n"
        "▸ **금/은비** 🟢<70 🟡70~80 🔴80↑(공포) │ **구리/금비** 🟢>0.20(성장) 🔴<0.15(방어)\n"
        "▸ **RSI** 🟢40~60 🟡60~70/30~40 🔴70↑과매수 🔵30↓과매도(매수기회)\n"
        "▸ **52주** 고점대비 🟢-3%내 🟡-10%내 🔴-10%↓ │ **연속↓** 3일↑ ⚠️경고\n"
        "▸ **VT스케일** 공격×(목표10%÷SPY실현변동성). 변동성↑→공격자동축소\n"
        "▸ **진입게이트** DXY/VIX 기반 SLV·COPX·VEA 매수허용%\n"
        "▸ **Oracle §3.5** Polymarket 가중평균 후 합=100% 정규화. `ok/total`은 조회 성공 마켓 수\n"
        "▸ **Legio score** (0.25×1M+0.30×3M+0.30×6M+0.15×12M)×vol감쇠×MA20감쇠"
    ),"footer":{"text":f"INVICTUS Bot │ {datetime.now(KST).strftime('%H:%M KST')} │ Oracle v2.13"}}

    return[e1,e2,e3,e3_5,e4,e5,e6,e7]

def main():
    print("📋 모닝 브리핑 v4.1 생성 중...")
    d=fetch();g=calc_gradient(d);r=calc_regime(d,g);t=calc_triggers(d)
    print(f"  레짐:{r['l']} 경보:{t['stg']}")
    # 🔭 Polymarket §3.5
    print("  🔭 Polymarket 시나리오 조회 중...")
    oracle=calc_oracle()
    probs,raw_markets,status=oracle
    print(f"  S1={probs['S1']}% S2={probs['S2']}% S3={probs['S3']}% S4={probs['S4']}% │ 마켓커버리지:{len(raw_markets)}")
    embeds=build(d,r,g,t,oracle)
    # 🟠 SOLIDUS BTC 블록 (v1.3 이식)
    print("  🟠 SOLIDUS BTC 데이터 수집...")
    try:
        sd=collect_solidus()
        sol_embeds=build_solidus_embeds(sd)
        embeds.extend(sol_embeds)
        print(f"  🟠 SOLIDUS embed 2개 (target={sd['target']:.1f}%, 지표 {sd['n_indicators']}/5)")
    except Exception as e:
        print(f"  ⚠️ SOLIDUS 수집 실패(스킵): {e}")
    # 📜 오늘의 명언
    quotes_all=load_quotes()
    if quotes_all:
        daily_q=pick_daily_quotes(quotes_all,3)
        qe=build_quotes_embed(daily_q)
        if qe:embeds.append(qe);print(f"  📜 명언 3개 로드 (풀 {len(quotes_all)}개)")
    now=datetime.now(KST)
    # 자동 5개씩 분할 전송 (Discord 10 embed 한계 대응 + INVICTUS+SOLIDUS 통합 12개 대응)
    header=f"🛡️ **INVICTUS 모닝 리포트** ☕\n{now.strftime('%Y-%m-%d %H:%M KST')}"
    for i in range(0,len(embeds),5):
        payload={"embeds":embeds[i:i+5]}
        if i==0:payload["content"]=header
        send(payload)
    print(f"  ✅ 전송 완료 ({len(embeds)}개 embed / {(len(embeds)+4)//5}개 메시지)")

if __name__=="__main__":main()
