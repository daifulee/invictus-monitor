#!/usr/bin/env python3
"""INVICTUS 모닝 브리핑 v3 — 전체 센서 + 모멘텀 + 유동성 + 글로벌 + 각주"""
import os,requests,xml.etree.ElementTree as ET
from datetime import datetime,timezone,timedelta
DISCORD_WEBHOOK=os.environ.get("DISCORD_WEBHOOK","")
FRED_API_KEY=os.environ.get("FRED_API_KEY","")
ANTHROPIC_API_KEY=os.environ.get("ANTHROPIC_API_KEY","")
KST=timezone(timedelta(hours=9))
UA={"User-Agent":"Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}

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

TICKERS=["GLD","SMH","EWZ","XLE","SLV","PAVE","COPX","XLU"]
EMOJIS={"GLD":"🥇","SMH":"📱","EWZ":"🇧🇷","XLE":"🛢️","SLV":"🥈","PAVE":"🏗️","COPX":"🟤","XLU":"⚡"}

def fetch():
    vix=yp("^VIX");vix3m=yp("^VIX3M");move=yp("^MOVE");wti=yp("CL=F")
    dxy=yp("DX-Y.NYB");rsp=yp("RSP");vvix=yp("^VVIX")
    hyg=yp("HYG");tlt=yp("TLT")
    krw=yp("KRW=X");btc=yp("BTC-USD");esf=yp("ES=F");nqf=yp("NQ=F")
    sh=yh("SPY","1y");rh=yh("RSP","2mo");mh=yh("^MOVE","2mo");wh=yh("CL=F","2mo")
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
    # 종목별
    hdata={}
    for tk in TICKERS:
        h=yh(tk,"1y");p=h[-1] if h else yp(tk)
        hdata[tk]={"p":p,"1D":mom(h,1),"1M":mom(h,22),"3M":mom(h,63),"6M":mom(h,126),"12M":mom(h,252)}
    gp=hdata.get("GLD",{}).get("p");sp_=hdata.get("SLV",{}).get("p");cp=hdata.get("COPX",{}).get("p")
    gs_r=gp/sp_ if gp and sp_ and sp_>0 else None
    cg_r=cp/gp if cp and gp and gp>0 else None
    return{"VIX":vix,"VIX3M":vix3m,"MOVE":move,"OAS":oas,"WTI":wti,"SPY":spy,
        "T5YIE":t5y,"DXY":dxy,"RSP":rsp,"DFII10":dfii,"T10Y2Y":t10,"ICSA":icsa,
        "SAHM":sahm,"S200":s200,"S60":s60,"b200":b200,"b60":b60,"br60":br60,
        "WC":wc,"VV":vv,"MM":mm,"MR":mr,"BRD":brd,"S1D":s1d,"S1W":s1w,"S1M":s1m,
        "VVIX":vvix,"HYG":hyg,"TLT":tlt,"RRP":rrp,"GS2":gs2,"GS10":gs10,
        "KRW":krw,"BTC":btc,"ESF":esf,"NQF":nqf,
        "GS_R":gs_r,"CG_R":cg_r,"H":hdata}

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
def send(p):
    if not DISCORD_WEBHOOK:return
    try:requests.post(DISCORD_WEBHOOK,json=p,timeout=10)
    except:pass

# ── 뉴스 ──
def fetch_news():
    headlines=[]
    for url,src in[("https://www.cnbc.com/id/20910258/device/rss/rss.html","CNBC"),("https://feeds.marketwatch.com/marketwatch/topstories/","MW"),("https://www.cnbc.com/id/10000664/device/rss/rss.html","CNBC")]:
        try:
            r=requests.get(url,headers=UA,timeout=10);root=ET.fromstring(r.content)
            for item in root.findall(".//item")[:5]:
                t=item.find("title")
                if t is not None and t.text:headlines.append(f"[{src}] {t.text.strip()}")
        except:pass
    return headlines[:15]
def translate_news(headlines):
    if not ANTHROPIC_API_KEY or not headlines:return None
    try:
        joined="\n".join(f"{i+1}. {h}" for i,h in enumerate(headlines))
        r=requests.post("https://api.anthropic.com/v1/messages",headers={"x-api-key":ANTHROPIC_API_KEY,"anthropic-version":"2023-06-01","content-type":"application/json"},json={"model":"claude-haiku-4-5-20251001","max_tokens":1000,"messages":[{"role":"user","content":f"아래 영문 경제 뉴스를 한글 1줄 요약. 중복 합치고 5~8개만. ▸ 로 시작. 출처 불필요.\n\n{joined}"}]},timeout=30)
        print(f"  Claude: {r.status_code}")
        if r.status_code!=200:print(f"  응답: {r.text[:300]}");return None
        return r.json().get("content",[{}])[0].get("text","").strip() or None
    except Exception as e:print(f"  번역에러: {e}");return None

# ── 브리핑 생성 ──
def build(d,reg,grd,trg):
    now=datetime.now(KST);date=now.strftime("%Y-%m-%d (%a)")
    stg=trg["stg"];se={"CLEAR":"🟢","PRE":"🟡","L0":"🟠","L1":"🔴","L2":"🔴🔴","L3":"⚫"}.get(stg,"⚪")
    sc={"CLEAR":0x3DBB7E,"PRE":0xEFB030,"L0":0xEFB030,"L1":0xE07238,"L2":0xD83030,"L3":0x2C2C2A}.get(stg,0x5B9CF6)
    vs200=f"{(d['SPY']-d['S200'])/d['S200']*100:+.1f}%" if d['SPY'] and d['S200'] else"--"
    vs60=f"{(d['SPY']-d['S60'])/d['S60']*100:+.1f}%" if d['SPY'] and d['S60'] else"--"
    rv=d["VIX"]is not None and d["VIX"]<20;rm=d["MOVE"]is not None and d["MOVE"]<100;rs=d["SAHM"]is not None and d["SAHM"]<0.30

    # 1️⃣ 핵심 요약
    e1={"title":f"☀️ INVICTUS 모닝 브리핑 — {date}","color":sc,"description":(
        f"{se} **경보 {stg}** │ **{reg['l']}** │ RP **{reg['rp']}%**\n"
        f"📊 그래디언트 **{grd['t']}**/100 {grd['bk']} │ 🛡️{grd['df']}% │ ⚔️{grd['ak']}%"
    )}

    # 2️⃣ 센서 — 각 지표 의미 포함
    e2={"title":"📡 핵심 센서","color":0x5B9CF6,"description":(
        f"{dot(d['VIX'] and d['VIX']<30)} **VIX {f(d['VIX'])}** 공포지수 │ "
        f"{dot(d['MOVE'] and d['MOVE']<150)} **MOVE {f(d['MOVE'],dc=0)}** 채권변동성 │ "
        f"{dot(d['OAS'] and d['OAS']<5.2)} **OAS {f(d['OAS'],'',2)}%** 신용위험\n"
        f"{dot(d['WTI'] and d['WTI']<120)} **WTI ${f(d['WTI'])}** 유가 │ "
        f"{dot(d['T5YIE'] and d['T5YIE']<3)} **T5YIE {f(d['T5YIE'],'',2)}%** 기대인플레 │ "
        f"{dot(d['DXY'] and d['DXY']<100)} **DXY {f(d['DXY'],dc=2)}** 달러강도\n"
        f"{'🟡' if d['VVIX'] and d['VVIX']>=130 else'🟢'} **VVIX {f(d['VVIX'],dc=0)}** VIX선행경보 │ "
        f"{'🟡' if d['MR'] and d['MR']>=1.10 else'🟢'} **MOVE/MA20 {f(d['MR'],dc=3)}** 채권급변 │ "
        f"{'🟡' if d['VV'] and d['VV']>1.05 else'🟢'} **VIX/VIX3M {f(d['VV'],dc=3)}** 단기공포"
    )}

    # 3️⃣ 레짐 + TIER2
    e3={"title":"🏛️ 레짐 │ 경기·물가·금리","color":0xEFB030,"description":(
        f"🌊 **TIDE {reg['td']}** 경기사이클 │ "
        f"🔥 **INFERNO {reg['inf']}** 물가환경 │ "
        f"📐 **CURVE {reg['cv']}** 수익률곡선\n"
        f"📉 **DFII10 {f(d['DFII10'],'',2)}%** 실질금리 │ "
        f"📐 **T10Y2Y {f(d['T10Y2Y'],'',2)}%** 장단기차 │ "
        f"📋 **SAHM {f(d['SAHM'],'',2)}** 실업판정\n"
        f"🏦 **2Y {f(d['GS2'],'',2)}%** 단기금리 │ "
        f"🏦 **10Y {f(d['GS10'],'',2)}%** 장기금리 │ "
        f"📋 **ICSA {f(d['ICSA'],'',0)}** 실업수당\n\n"
        f"**그래디언트 분해** ({grd['t']}/100)\n"
        f"VIX **{grd['vs']}**/25 │ OAS **{grd['os']}**/25 │ MOVE **{grd['ms']}**/25 │ FLOW **{grd['fs']}**/25 │ RR **{grd['rr']}**/15"
    )}

    # 4️⃣ 유동성 + 글로벌
    rrp_t = f"{d['RRP']/1e9:.0f}B" if d['RRP'] else "--"
    e4={"title":"💧 유동성 │ 글로벌 │ 환율","color":0x1DA1F2,"description":(
        f"💧 **RRP ${rrp_t}** 역레포잔고(↑=유동성흡수) │ "
        f"**HYG ${f(d['HYG'])}** 하이일드채권(↓=신용불안) │ "
        f"**TLT ${f(d['TLT'])}** 장기국채(↑=금리하락)\n"
        f"💱 **원/달러 {f(d['KRW'],dc=0)}원** │ "
        f"🪙 **BTC ${f(d['BTC'],dc=0)}** 위험자산심리\n"
        f"📈 **S&P선물 {f(d['ESF'],dc=0)}** │ **나스닥선물 {f(d['NQF'],dc=0)}** 오늘장 방향\n"
        f"🥇🥈 **금/은비 {f(d['GS_R'],dc=1)}** (↑=공포) │ "
        f"🟤🥇 **구리/금비 {f(d['CG_R'],dc=3)}** (↑=성장기대)"
    )}

    # 5️⃣ 보유종목 모멘텀
    lines=[]
    for tk in TICKERS:
        h=d["H"].get(tk,{})
        em=EMOJIS.get(tk,"")
        p=h.get("p")
        m1=sg(h.get("1M"));m3=sg(h.get("3M"));m6=sg(h.get("6M"))
        d1=sg(h.get("1D"))
        lines.append(f"{em}**{tk}** ${f(p)} │ 1D {d1} │ 1M {m1} │ 3M {m3}")
    e5={"title":"📊 보유종목 모멘텀","color":0x3DBB7E,"description":(
        "\n".join(lines) +
        f"\n\n*모멘텀 = 해당 기간 수익률. 양수면 상승추세, 음수면 하락추세*"
    )}

    # 6️⃣ SPY + 트리거 + 재진입
    e6={"title":"📈 SPY │ 트리거 │ 재진입","color":0x3DBB7E,"description":(
        f"**SPY ${f(d['SPY'])}** │ 1D **{sg(d['S1D'])}** │ 1W **{sg(d['S1W'])}** │ 1M **{sg(d['S1M'])}**\n"
        f"vs200MA **{vs200}** │ vs60MA **{vs60}** │ BREADTH **{f(d['BRD'],dc=3)}** 시장폭\n"
        f"200MA하회 **{d['b200']}일** │ 60MA하회 **{d['b60']}일**\n\n"
        f"{trg['chips']}\n"
        f"🥇 GLD매도 {'🚫금지' if trg['gld'] else'✅허용'}\n\n"
        f"**재진입조건** (전부 충족 필수)\n"
        f"{dot(rv)} VIX<20 **{f(d['VIX'])}** │ {dot(rm)} MOVE<100 **{f(d['MOVE'],dc=0)}** │ {dot(rs)} SAHM<0.30 **{f(d['SAHM'],'',2)}**"
    )}

    # 7️⃣ 각주 (탭하면 펼쳐짐)
    e7={"color":0x485070,"description":(
        "📖 **지표 각주** (탭하여 펼치기)\n"
        "||▸ **VIX** S&P500 내재변동성. 시장 공포 수준. 30↑경계 42↑위기\n"
        "▸ **MOVE** 채권시장 변동성. 금리 불확실성. 150↑경보 190↑STORM\n"
        "▸ **OAS** 하이일드 신용스프레드. 기업 부도위험. 5.2↑경고 5.8↑경색\n"
        "▸ **WTI** 원유가격. 에너지 인플레 압력. 120↑극심\n"
        "▸ **T5YIE** 5년 기대인플레. 시장이 예상하는 물가. 3.0↑스태그 위험\n"
        "▸ **DXY** 달러지수. 달러 강세→신흥국·원자재 압박. 100↑경고\n"
        "▸ **VVIX** VIX의 변동성. STORM 1~3일 선행지표. 130↑예비경보\n"
        "▸ **DFII10** 10년 실질금리. 높을수록 성장주·금 압박. 1.5↑부담\n"
        "▸ **T10Y2Y** 장단기 금리차. 0↓역전=침체 선행신호\n"
        "▸ **GS2/GS10** 2년/10년 국채금리. 연준 정책 방향 반영\n"
        "▸ **SAHM** 실업률 3개월이평 변화. 0.30↑둔화 0.50↑침체 확정\n"
        "▸ **RRP** 연준 역레포 잔고. 증가=유동성 흡수, 감소=유동성 방출\n"
        "▸ **HYG** 하이일드 채권ETF. 하락=신용불안 (OAS 실시간 체감)\n"
        "▸ **TLT** 20년 국채ETF. 상승=금리하락 기대\n"
        "▸ **금/은비** 높으면 안전자산 선호(공포), 낮으면 산업수요(성장)\n"
        "▸ **구리/금비** 높으면 경기성장 기대, 낮으면 방어 심리\n"
        "▸ **BREADTH** SPY/RSP 1M수익률비. 1.12↑=소수 대형주만 상승(쏠림)\n"
        "▸ **모멘텀** 기간별 수익률. 양수=상승추세, 음수=하락추세||"
    ),"footer":{"text":f"INVICTUS Bot │ {datetime.now(KST).strftime('%H:%M KST')} │ Oracle v2.13"}}

    return[e1,e2,e3,e4,e5,e6,e7]

def main():
    print("📋 모닝 브리핑 v3 생성 중...")
    d=fetch();g=calc_gradient(d);r=calc_regime(d,g);t=calc_triggers(d)
    print(f"  레짐:{r['l']} 경보:{t['stg']}")
    embeds=build(d,r,g,t)
    # 뉴스
    print("  📰 뉴스 수집 중...")
    hl=fetch_news();print(f"  {len(hl)}개 헤드라인")
    if hl:
        tr=translate_news(hl)
        if tr:embeds.append({"title":"📰 글로벌 경제 뉴스","color":0x1DA1F2,"description":tr,"footer":{"text":"CNBC │ MarketWatch │ Claude 번역"}});print("  ✅ 뉴스 번역 완료")
        else:print("  ⚠️ 번역 생략")
    # Discord 전송 (5개씩 분할)
    now=datetime.now(KST)
    send({"content":f"☀️ **INVICTUS 모닝 브리핑** — {now.strftime('%Y-%m-%d %H:%M KST')}","embeds":embeds[:5]})
    if len(embeds)>5:send({"embeds":embeds[5:]})
    print("  ✅ 전송 완료")

if __name__=="__main__":main()
