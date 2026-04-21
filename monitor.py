 #!/usr/bin/env python3
"""
INVICTUS Dashboard — GitHub Actions 자동 모니터링
5분 주기 실행 | Mac 불필요 | 터미널 불필요

전송 규칙:
    - L0 이상 트리거 발동 → 🚨 즉시 긴급 알림
    - PRE 단계, 매시 정각 직후(00~04분) → 📊 정기 리포트 (시간당 1회)
    - 그 외 → 조용히 체크만 (Discord 스팸 방지)

패치 이력:
    - 2026-04-21 v1.1: error_reporter 통합, PEP8 리팩터링, except:pass 제거
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta

import requests

# error_reporter는 같은 디렉터리에 있다고 가정 (레포 루트)
try:
    from error_reporter import ErrorReporter
except ImportError:
    ErrorReporter = None  # 없으면 legacy 모드로 동작


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 설정 (GitHub Secrets에서 주입)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
KST = timezone(timedelta(hours=9))

UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Error Reporter (임계 초과 시에만 Discord 알림)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if ErrorReporter is not None:
    REPORTER = ErrorReporter(
        webhook=DISCORD_WEBHOOK,
        threshold=5,  # 한 run에 5건 이상 실패 시 알림
        run_label="monitor",
    )
else:
    REPORTER = None


def _report(label, exc):
    """에러 리포터가 있으면 기록, 없으면 stderr."""
    if REPORTER is not None:
        REPORTER.record(label, exc)
    else:
        print(f"[warn] {label}: {type(exc).__name__}: {exc}", file=sys.stderr)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 데이터 수집
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def yahoo_price(symbol):
    """Yahoo Finance 현재가."""
    try:
        url = (
            f"https://query2.finance.yahoo.com/v8/finance/chart/"
            f"{requests.utils.quote(symbol)}?interval=1d&range=1d"
        )
        r = requests.get(url, headers=UA, timeout=10)
        return r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except Exception as e:
        _report(f"yahoo_price:{symbol}", e)
        return None


def yahoo_history(symbol, rng="1y"):
    """Yahoo Finance 종가 히스토리."""
    try:
        url = (
            f"https://query2.finance.yahoo.com/v8/finance/chart/"
            f"{requests.utils.quote(symbol)}?interval=1d&range={rng}"
        )
        r = requests.get(url, headers=UA, timeout=15)
        closes = r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        return [c for c in closes if c is not None]
    except Exception as e:
        _report(f"yahoo_history:{symbol}:{rng}", e)
        return []


def fred_value(series_id):
    """FRED 최신값."""
    if not FRED_API_KEY:
        return None
    try:
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}"
            f"&api_key={FRED_API_KEY}"
            f"&limit=1&sort_order=desc&file_type=json"
        )
        r = requests.get(url, timeout=10)
        return float(r.json()["observations"][0]["value"])
    except Exception as e:
        _report(f"fred:{series_id}", e)
        return None


def fetch_all():
    """모든 센서를 수집해 딕셔너리로 반환."""
    vix = yahoo_price("^VIX")
    vix3m = yahoo_price("^VIX3M")
    move = yahoo_price("^MOVE")
    wti = yahoo_price("CL=F")
    dxy = yahoo_price("DX-Y.NYB")
    rsp = yahoo_price("RSP")

    spy_h = yahoo_history("SPY", "1y")
    rsp_h = yahoo_history("RSP", "2mo")
    move_h = yahoo_history("^MOVE", "2mo")
    wti_h = yahoo_history("CL=F", "2mo")

    oas = fred_value("BAMLH0A0HYM2")
    t5yie = fred_value("T5YIE")
    sahm = fred_value("SAHMCURRENT")
    dfii10 = fred_value("DFII10")
    t10y2y = fred_value("T10Y2Y")
    icsa = fred_value("ICSA")

    spy = spy_h[-1] if spy_h else None
    spy200 = sum(spy_h[-200:]) / 200 if len(spy_h) >= 200 else None
    spy60 = sum(spy_h[-60:]) / 60 if len(spy_h) >= 60 else None

    def below_days(arr, ma):
        if not ma:
            return 0
        c = 0
        for p in reversed(arr):
            if p < ma:
                c += 1
            else:
                break
        return c

    below200 = below_days(spy_h, spy200)
    below60 = below_days(spy_h, spy60)
    breach60 = (spy - spy60) / spy60 if spy and spy60 else None

    wti_chg = (wti_h[-1] - wti_h[-8]) / wti_h[-8] if len(wti_h) >= 8 else None
    vv_ratio = vix / vix3m if vix and vix3m and vix3m > 0 else None

    move_ma20 = sum(move_h[-20:]) / 20 if len(move_h) >= 20 else None
    move_rel = move / move_ma20 if move and move_ma20 and move_ma20 > 0 else None

    breadth = None
    if len(spy_h) >= 22 and len(rsp_h) >= 22:
        sr = spy_h[-1] / spy_h[-22]
        rr = rsp_h[-1] / rsp_h[-22]
        if rr > 0:
            breadth = sr / rr

    return {
        "VIX": vix, "VIX3M": vix3m, "MOVE": move, "OAS": oas,
        "WTI": wti, "SPY": spy, "T5YIE": t5yie, "DXY": dxy, "RSP": rsp,
        "DFII10": dfii10, "T10Y2Y": t10y2y, "ICSA": icsa, "SAHM": sahm,
        "SPY_200MA": spy200, "SPY_60MA": spy60,
        "below200": below200, "below60": below60, "breach60": breach60,
        "WTI_CHG": wti_chg, "VV_RATIO": vv_ratio,
        "MOVE_MA20": move_ma20, "MOVE_REL": move_rel,
        "BREADTH": breadth,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Oracle 레짐 판정 (v2.13)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def lin(val, lo, hi, mx):
    if val <= lo:
        return 0
    if val >= hi:
        return mx
    return round(mx * (val - lo) / (hi - lo), 2)


def classify_tide(sahm, icsa):
    s = sahm or 0
    ic = icsa or 220000
    if s >= 0.50:
        return "RECESSION_CONFIRMED"
    if s >= 0.30:
        return "RECESSION_WATCH"
    if s >= 0.25 or ic >= 300000:
        return "SLOWDOWN"
    return "EXPANSION"


def classify_inferno(t5yie, wti):
    t = t5yie or 2.5
    w = wti or 80
    if t < 1.5:
        return "DEFLATION_RISK"
    if t >= 3.0 or w >= 120:
        return "HOT"
    if t >= 2.7 or w >= 95:
        return "RISING"
    return "STABLE"


def classify_curve(t10y2y):
    s = t10y2y if t10y2y is not None else 0.5
    if s <= -0.5:
        return "DEEP_INVERT"
    if s <= 0:
        return "INVERTED"
    if s <= 0.3:
        return "FLAT"
    return "NORMAL"


def compute_gradient(d):
    vix_s = lin(d["VIX"] or 18, 18, 30, 25)
    oas_s = lin(d["OAS"] or 3, 3, 5.5, 25)
    move_s = lin(d["MOVE"] or 80, 80, 130, 25)

    mr = d.get("MOVE_REL")
    if mr and mr > 1.0:
        if mr >= 1.20:
            b = 5
        elif mr >= 1.15:
            b = 4
        elif mr >= 1.10:
            b = 3
        elif mr >= 1.05:
            b = 1.5
        else:
            b = 0
        move_s = min(25, move_s + b)

    flow_s = 8
    rr_s = lin(d["DFII10"] or 1.0, 0.5, 2.5, 15) if d.get("DFII10") else 0

    total = min(100, round(vix_s + oas_s + move_s + flow_s + rr_s, 1))
    defense = round(10 + (total / 100) * 80, 1)

    if total < 20:
        bracket = "🟢GREEN"
    elif total < 40:
        bracket = "🟡전환경계"
    elif total < 60:
        bracket = "🟡YELLOW"
    elif total < 80:
        bracket = "🟠RED경계"
    else:
        bracket = "🔴STORM"

    return {
        "total": total, "bracket": bracket,
        "defense": defense, "attack": round(100 - defense, 1),
    }


def classify_regime(d, grad):
    tide = classify_tide(d["SAHM"], d["ICSA"])
    inferno = classify_inferno(d["T5YIE"], d["WTI"])
    curve = classify_curve(d["T10Y2Y"])
    dfii = d["DFII10"] or 1.0
    g = grad["total"]
    sahm = d["SAHM"]

    if tide == "RECESSION_CONFIRMED" or (tide == "RECESSION_WATCH" and curve == "DEEP_INVERT"):
        regime, label, rp = "RECESSION", "🔴🔴 침체 확정", 60
    elif tide in ("SLOWDOWN", "RECESSION_WATCH") and inferno in ("RISING", "HOT"):
        regime, label, rp = "STAGFLATION", "🟠 스태그플레이션", 30
    elif tide in ("SLOWDOWN", "RECESSION_WATCH") and inferno == "STABLE":
        regime, label, rp = "SLOWDOWN", "🔴 침체 경계", 40
    elif tide in ("SLOWDOWN", "RECESSION_WATCH") and inferno == "DEFLATION_RISK":
        regime, label, rp = "DEFLATION", "🔵 디플레형", 45
    elif tide == "EXPANSION" and dfii > 1.5 and inferno in ("RISING", "HOT"):
        regime, label, rp = "HIGH_RATE", "🟡 고금리", 20
    elif tide == "EXPANSION" and g < 15 and (sahm or 0) < 0.15 and curve != "DEEP_INVERT":
        regime, label, rp = "EXPANSION_BULL", "🟢🟢 초강세장", 5
    else:
        regime, label, rp = "EXPANSION", "🟢 확장기", 10

    return {
        "regime": regime, "label": label, "rp": rp,
        "tide": tide, "inferno": inferno, "curve": curve,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 트리거 판정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def evaluate_triggers(d):
    active = []
    vix = d["VIX"] or 0
    move = d["MOVE"] or 0
    oas = d["OAS"] or 0
    wti = d["WTI"] or 0
    t5y = d["T5YIE"] or 0
    vv = d["VV_RATIO"] or 0

    # PRE
    if vix >= 30 or vv > 1.05:
        active.append({"id": "E0", "lvl": "PRE", "name": "PRE_STORM",
                       "reason": f"VIX {vix:.1f}", "act": "공격억제"})
    if t5y > 3.0 and wti > 120:
        active.append({"id": "E1", "lvl": "PRE", "name": "INFERNO",
                       "reason": f"T5YIE {t5y:.2f}%+WTI ${wti:.0f}", "act": "RP 20%"})
    if d["below200"] >= 5:
        active.append({"id": "E2", "lvl": "PRE", "name": "BULL_BREAK",
                       "reason": f"200MA 하회 {d['below200']}일", "act": "매수차단"})
    br = d["BREADTH"]
    if br is not None and br >= 1.12:
        active.append({"id": "E3", "lvl": "PRE", "name": "BREADTH",
                       "reason": f"SPY/RSP={br:.3f}", "act": "매수차단"})
    wc = d["WTI_CHG"]
    if wc is not None and wc >= 0.20:
        active.append({"id": "E4", "lvl": "PRE", "name": "ATTRITION",
                       "reason": f"WTI 주간 {wc*100:.1f}%", "act": "매수차단"})

    # L0+
    if oas >= 5.8:
        active.append({"id": "L0a", "lvl": "L0", "name": "AEGIS-EBP",
                       "reason": f"OAS {oas:.2f}%≥5.8%", "act": "RP 20%·축소"})
    if oas >= 5.2:
        active.append({"id": "L0b", "lvl": "L0", "name": "AEGIS-SB",
                       "reason": f"OAS {oas:.2f}%≥5.2%", "act": "L1 승급"})

    l1r = []
    if vix >= 42:
        l1r.append(f"VIX {vix:.1f}≥42")
    if move >= 190:
        l1r.append(f"MOVE {move:.0f}≥190")
    if oas >= 8.5:
        l1r.append(f"OAS {oas:.2f}%≥8.5%")
    if l1r:
        active.append({"id": "L1", "lvl": "L1", "name": "STORM",
                       "reason": " / ".join(l1r), "act": "SMH·EWZ 전량"})

    if vix >= 45:
        active.append({"id": "L2", "lvl": "L2", "name": "FAST_CRASH",
                       "reason": f"VIX {vix:.1f}≥45", "act": "SLV·COPX·XLU"})

    ks_armed = d["below60"] >= 12 and d.get("breach60") is not None and d["breach60"] <= -0.05
    if ks_armed:
        active.append({"id": "L3", "lvl": "L3", "name": "KILLSWITCH",
                       "reason": f"60MA 하회 {d['below60']}일", "act": "전량매도"})

    # 스테이지
    if ks_armed:
        stage = "L3"
    elif vix >= 45:
        stage = "L2"
    elif l1r:
        stage = "L1"
    elif any(t["lvl"] == "L0" for t in active):
        stage = "L0"
    elif any(t["lvl"] == "PRE" for t in active):
        stage = "PRE"
    else:
        stage = "CLEAR"

    # GLD 매도 금지
    gld_no = t5y >= 3.0 or (t5y >= 2.7 and wti >= 95)

    # 응급 트리거 (L0 이상)
    emergency = [t for t in active if t["lvl"] not in ("PRE",)]

    return {
        "active": active, "emergency": emergency,
        "stage": stage, "gld_prohibited": gld_no,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Discord 전송 (retry 포함)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def fmt(v, unit="", dec=1):
    if v is None:
        return "--"
    return f"{unit}{v:.{dec}f}"


def send_discord(payload, retries=3):
    """Webhook POST. 재시도 3회 (지수 백오프)."""
    if not DISCORD_WEBHOOK:
        print("⚠️ DISCORD_WEBHOOK 미설정")
        return False
    import time
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
            print(f" Discord: {r.status_code}")
            if 200 <= r.status_code < 300:
                return True
            # 429 Retry-After 존중
            if r.status_code == 429:
                try:
                    ra = float(r.json().get("retry_after", 1.0))
                except Exception:
                    ra = 2.0
                print(f" Rate limit. {ra}s 대기...")
                time.sleep(ra)
                continue
            # 5xx 재시도
            if 500 <= r.status_code < 600 and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            # 4xx (429 제외)는 재시도 무의미
            print(f" 치명 응답: {r.text[:200]}")
            return False
        except Exception as e:
            print(f" Discord 에러 (시도 {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)
    return False


def send_status(d, regime, grad, trig):
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    stg = trig["stage"]
    emoji = {"CLEAR": "🟢", "PRE": "🟡", "L0": "🟠",
             "L1": "🔴", "L2": "🔴🔴", "L3": "⚫"}.get(stg, "⚪")
    color = {"CLEAR": 0x3DBB7E, "PRE": 0xEFB030, "L0": 0xEFB030,
             "L1": 0xE07238, "L2": 0xD83030, "L3": 0x2C2C2A}.get(stg, 0x5B9CF6)

    # 트리거 칩 — 전체 E0~L3 표시
    all_ids = ["E0", "E1", "E2", "E3", "E4", "L0a", "L0b", "L1", "L2", "L3"]
    active_ids = {t["id"] for t in trig["active"]}
    chips = " ".join(f"**{i}**●" if i in active_ids else f"{i}○" for i in all_ids)

    fields = [
        {"name": "📊 경보", "value": f"{emoji} **{stg}**", "inline": True},
        {"name": "🏛️ 레짐", "value": regime["label"], "inline": True},
        {"name": "📈 그래디언트",
         "value": f"**{grad['total']}/100** {grad['bracket']}", "inline": True},
        {"name": "🌊TIDE", "value": regime["tide"], "inline": True},
        {"name": "🔥INFERNO", "value": regime["inferno"], "inline": True},
        {"name": "📐CURVE", "value": regime["curve"], "inline": True},
        {"name": "💰 RP", "value": f"{regime['rp']}%", "inline": True},
        {"name": "🥇 GLD",
         "value": "🚫금지" if trig["gld_prohibited"] else "✅허용", "inline": True},
        {"name": "🛡️방어/⚔️공격",
         "value": f"{grad['defense']}% / {grad['attack']}%", "inline": True},
        {"name": "TIER1",
         "value": (
             f"VIX **{fmt(d['VIX'])}** · MOVE **{fmt(d['MOVE'],dec=0)}** · "
             f"OAS **{fmt(d['OAS'],'',2)}%**\n"
             f"WTI **${fmt(d['WTI'])}** · T5YIE **{fmt(d['T5YIE'],'',2)}%** · "
             f"DXY **{fmt(d['DXY'],dec=2)}**"
         ),
         "inline": False},
        {"name": "TIER2",
         "value": (
             f"DFII10 **{fmt(d['DFII10'],'',2)}%** · "
             f"T10Y2Y **{fmt(d['T10Y2Y'],'',2)}%** · "
             f"SAHM **{fmt(d['SAHM'],'',2)}** · "
             f"ICSA **{fmt(d['ICSA'],'',0)}**"
         ),
         "inline": False},
        {"name": "트리거", "value": chips, "inline": False},
    ]

    send_discord({
        "embeds": [{
            "title": f"🛡️ INVICTUS — {emoji} {stg}",
            "color": color,
            "fields": fields,
            "footer": {"text": now},
        }]
    })


def send_alert(d, regime, grad, trig):
    now = datetime.now(KST).strftime("%H:%M KST")
    lines = []
    for t in trig["emergency"]:
        emoji = {"L0": "🟠", "L1": "🔴", "L2": "🔴🔴", "L3": "⚫"}.get(t["lvl"], "⚪")
        lines.append(f"{emoji} **{t['id']} {t['name']}** — {t['reason']}\n→ {t['act']}")

    send_discord({
        "content": "🚨 **INVICTUS 긴급 경보** 🚨 @here",
        "embeds": [{
            "title": f"⚠️ 경보: {trig['stage']}",
            "description": "\n\n".join(lines),
            "color": 0xFF0000,
            "footer": {"text": now},
        }],
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 (1회 실행)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    now = datetime.now(KST)
    minute = now.minute

    print(f"[{now.strftime('%H:%M:%S')}] 센서 조회 중...")

    d = fetch_all()
    print(f" VIX={fmt(d['VIX'])} MOVE={fmt(d['MOVE'],dec=0)} OAS={fmt(d['OAS'],'',2)}%")

    grad = compute_gradient(d)
    print(f" 그래디언트: {grad['total']}/100 {grad['bracket']}")

    regime = classify_regime(d, grad)
    print(f" 레짐: {regime['label']} · RP {regime['rp']}%")

    trig = evaluate_triggers(d)
    print(f" 경보: {trig['stage']}")

    # L0 이상 → 🚨 긴급 알림 (매번 전송)
    if trig["emergency"]:
        print(" 🚨 긴급 경보 전송!")
        send_alert(d, regime, grad, trig)
        send_status(d, regime, grad, trig)

    # PRE 단계 → ⚠️ 경고 (매시 00~04분만 전송 = 시간당 1회)
    # 5분 간격 cron이므로 정각 직후 run에서만 minute < 5 참 → 정확히 시간당 1회
    elif trig["stage"] == "PRE" and minute < 5:
        print(" ⚠️ PRE 경고 전송 (시간당 1회)")
        send_status(d, regime, grad, trig)

    # CLEAR → 전송 안 함 (스팸 방지)
    else:
        print(" ✅ 정상 — 전송 생략")

    # Error reporter: 임계 초과 시 요약 알림
    if REPORTER is not None:
        REPORTER.flush_if_threshold()


if __name__ == "__main__":
    main()
