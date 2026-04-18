#!/usr/bin/env python3
"""INVICTUS 모닝 브리핑 — 모바일 최적화 (세로 압축)"""
import os,requests
from datetime import datetime,timezone,timedelta
DISCORD_WEBHOOK=os.environ.get("DISCORD_WEBHOOK","")
FRED_API_KEY=os.environ.get("FRED_API_KEY","")
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
def fetch():
    vix=yp("^VIX");vix3m=yp("^VIX3M");move=yp("^MOVE");wti=yp("CL=F");dxy=yp("DX-Y.NYB");rsp=yp("RSP")
    sh=yh("SPY","1y");rh=yh("RSP","2mo");mh=yh("^MOVE","2mo");wh=yh("CL=F","2mo")
    oas=fv("BAMLH0A0HYM2");t5y=fv("T5YIE");sahm=fv("SAHMCURRENT");dfii=fv("DFII10");t10=fv("T10Y2Y");icsa=fv("ICSA")
    spy=sh[-1] if sh else None;s200=sum(sh[-200:])/200 if len(sh)>=200 else None;s60=sum(sh[-60:])/60 if len(sh)>=60 else None
    def bd(a,m):
        if not m:return 0
        c=0
        for p in reversed(a):
            if p<m:c+=1
            else:break
        return c
    b200=bd(sh,s200);b60=bd(sh,s60);br60=(spy-s60)/s60 if spy and s60 else None
    wc=(wh[-1]-wh[-8])/wh[-8] if len(wh)>=8 else None;vv=vix/vix3m if vix and vix3m and vix3m>0 else None
    mm=sum(mh[-20:])/20 if len(mh)>=20 else None;mr=move/mm if move and mm and mm>0 else None
    brd=None
    if len(sh)>=22 and len(rh)>=22:
        sr=sh[-1]/sh[-22];rr=rh[-1]/rh[-22]
        if rr>0:brd=sr/rr
    s1d=(sh[-1]-sh[-2])/sh[-2]*100 if len(sh)>=2 else None;s1w=(sh[-1]-sh[-6])/sh[-6]*100 if len(sh)>=6 else None;s1m=(sh[-1]-sh[-22])/sh[-22]*100 if len(sh)>=22 else None
    return{"VIX":vix,"VIX3M":vix3m,"MOVE":move,"OAS":oas,"WTI":wti,"SPY":spy,"T5YIE":t5y,"DXY":dxy,"RSP":rsp,"DFII10":dfii,"T10Y2Y":t10,"ICSA":icsa,"SAHM":sahm,"SPY200":s200,"SPY60":s60,"b200":b200,"b60":b60,"br60":br60,"WC":wc,"VV":vv,"MM":mm,"MR":mr,"BRD":brd,"S1D":s1d,"S1W":s1w,"S1M":s1m}
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

def build(d,reg,grd,trg):
    now=datetime.now(KST);date=now.strftime("%Y-%m-%d (%a)")
    stg=trg["stg"];se={"CLEAR":"🟢","PRE":"🟡","L0":"🟠","L1":"🔴","L2":"🔴🔴","L3":"⚫"}.get(stg,"⚪")
    sc={"CLEAR":0x3DBB7E,"PRE":0xEFB030,"L0":0xEFB030,"L1":0xE07238,"L2":0xD83030,"L3":0x2C2C2A}.get(stg,0x5B9CF6)
    vs200=f"{(d['SPY']-d['SPY200'])/d['SPY200']*100:+.1f}%" if d['SPY'] and d['SPY200'] else"--"
    vs60=f"{(d['SPY']-d['SPY60'])/d['SPY60']*100:+.1f}%" if d['SPY'] and d['SPY60'] else"--"
    rv=d["VIX"]is not None and d["VIX"]<20;rm=d["MOVE"]is not None and d["MOVE"]<100;rs=d["SAHM"]is not None and d["SAHM"]<0.30

    e1={"title":f"☀️ INVICTUS 모닝 브리핑 — {date}","color":sc,"description":(
        f"{se} **경보 {stg}** · **{reg['l']}** · RP **{reg['rp']}%**\n"
        f"📊 그래디언트 **{grd['t']}**/100 {grd['bk']} · 🛡️{grd['df']}% ⚔️{grd['ak']}%"
    )}

    e2={"title":"📡 TIER1 센서","color":0x5B9CF6,"description":(
        f"{dot(d['VIX'] and d['VIX']<30)} **VIX {f(d['VIX'])}** · "
        f"{dot(d['MOVE'] and d['MOVE']<150)} **MOVE {f(d['MOVE'],dc=0)}** · "
        f"{dot(d['OAS'] and d['OAS']<5.2)} **OAS {f(d['OAS'],'',2)}%**\n"
        f"{dot(d['WTI'] and d['WTI']<120)} **WTI ${f(d['WTI'])}** · "
        f"{dot(d['T5YIE'] and d['T5YIE']<3)} **T5YIE {f(d['T5YIE'],'',2)}%** · "
        f"{dot(d['DXY'] and d['DXY']<100)} **DXY {f(d['DXY'],dc=2)}**\n"
        f"{'🟡' if d['MR'] and d['MR']>=1.10 else'🟢'} MOVE/MA20 **{f(d['MR'],dc=3)}** · "
        f"{'🟡' if d['VV'] and d['VV']>1.05 else'🟢'} VIX/VIX3M **{f(d['VV'],dc=3)}**"
    )}

    e3={"title":"🏛️ 레짐 + TIER2","color":0xEFB030,"description":(
        f"🌊 TIDE **{reg['td']}** · 🔥 INFERNO **{reg['inf']}** · 📐 CURVE **{reg['cv']}**\n"
        f"📉 DFII10 **{f(d['DFII10'],'',2)}%** · 📐 T10Y2Y **{f(d['T10Y2Y'],'',2)}%** · 📋 SAHM **{f(d['SAHM'],'',2)}**\n\n"
        f"**그래디언트 분해** ({grd['t']}/100)\n"
        f"VIX **{grd['vs']}**/25 · OAS **{grd['os']}**/25 · MOVE **{grd['ms']}**/25 · FLOW **{grd['fs']}**/25 · RR **{grd['rr']}**/15"
    )}

    e4={"title":"📈 SPY · 트리거 · 재진입","color":0x3DBB7E,"description":(
        f"**SPY ${f(d['SPY'])}** · 1D **{sg(d['S1D'])}** · 1W **{sg(d['S1W'])}** · 1M **{sg(d['S1M'])}**\n"
        f"vs200MA **{vs200}** · vs60MA **{vs60}** · BREADTH **{f(d['BRD'],dc=3)}**\n"
        f"200MA하회 **{d['b200']}일** · 60MA하회 **{d['b60']}일**\n\n"
        f"{trg['chips']}\n"
        f"🥇 GLD 매도 {'🚫금지' if trg['gld'] else'✅허용'}\n\n"
        f"**재진입** (전부 충족 필수)\n"
        f"{dot(rv)} VIX<20 **{f(d['VIX'])}** · {dot(rm)} MOVE<100 **{f(d['MOVE'],dc=0)}** · {dot(rs)} SAHM<0.30 **{f(d['SAHM'],'',2)}**"
    )}

    e5={"color":0x485070,"description":(
        "📖 **지표 각주**\n"
        "▸ VIX 공포지수 30↑경계 42↑위기 · MOVE 채권변동성 150↑경보\n"
        "▸ OAS 신용스프레드 5.8↑경색 · WTI 원유 120↑인플레\n"
        "▸ T5YIE 기대인플레 3.0↑스태그 · DXY 달러 100↑압박\n"
        "▸ DFII10 실질금리 1.5↑성장주압박 · T10Y2Y 0↓역전=침체\n"
        "▸ SAHM 0.30↑둔화 0.50↑침체 · BREADTH 1.12↑쏠림\n"
        "▸ TIDE 경기사이클 · INFERNO 물가 · CURVE 수익률곡선\n"
        "▸ 그래디언트 시장위험 0~100 (Oracle v2.13)"
    ),"footer":{"text":f"INVICTUS Bot · {datetime.now(KST).strftime('%H:%M KST')}"}}

    return[e1,e2,e3,e4,e5]

def main():
    print("📋 모닝 브리핑 생성 중...")
    d=fetch();g=calc_gradient(d);r=calc_regime(d,g);t=calc_triggers(d)
    print(f"  레짐:{r['l']} 경보:{t['stg']}")
    embeds=build(d,r,g,t)
    send({"content":f"☀️ **INVICTUS 모닝 브리핑** — {datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}","embeds":embeds})
    print("  ✅ 전송 완료")
if __name__=="__main__":main()
