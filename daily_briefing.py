#!/usr/bin/env python3
"""INVICTUS 모닝 브리핑 v4 — 전 지표 신호등 + 모멘텀 순위.

패치 이력:
    - 2026-04-21 v4.2: 실효공격비율 30일 시계열 + 스파크라인 추가 (e1에 삽입).
                      yh_dated/fv_series/compute_historical_eff_atk 신규.
                      수식·알고리즘 그대로 재사용, 과거 일자별 재계산 방식 (stateless).
    - 2026-04-21 v4.1: error_reporter 통합, send()에 재시도 3회,
                      TICKERS/EMOJIS를 tickers.json으로 분리,
                      except:pass 패턴 제거, PEP8 리팩터링.
                      수식·알고리즘·상수는 전부 불변.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

# error_reporter는 레포 루트에 있다고 가정 (없으면 legacy 모드)
try:
    from error_reporter import ErrorReporter
except ImportError:
    ErrorReporter = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 환경·상수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TICKERS/EMOJIS — tickers.json이 있으면 로드, 없으면 fallback
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_FALLBACK_TICKERS = [
    "GLD", "SMH", "EWZ", "XLE", "SLV", "PAVE", "COPX", "XLU", "VEA", "QQQM",
    "IWM", "XLF", "XLV", "INDA", "ITA", "CIBR", "NLR", "CQQQ", "VNM", "TLT",
]

_FALLBACK_EMOJIS = {
    "GLD": "🥇", "SMH": "📱", "EWZ": "🇧🇷", "XLE": "🛢️", "SLV": "🥈",
    "PAVE": "🏗️", "COPX": "🟤", "XLU": "⚡", "VEA": "🌍", "QQQM": "💻",
    "IWM": "🏢", "XLF": "🏦", "XLV": "🏥", "INDA": "🇮🇳", "ITA": "✈️",
    "CIBR": "🔒", "NLR": "☢️", "CQQQ": "🇨🇳", "VNM": "🇻🇳", "TLT": "📉",
}


def _load_tickers():
    """tickers.json을 읽어 (tickers, emojis)를 반환. 실패 시 fallback."""
    path = Path(__file__).resolve().parent / "tickers.json"
    if not path.exists():
        return list(_FALLBACK_TICKERS), dict(_FALLBACK_EMOJIS)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        tickers = data.get("tickers") or _FALLBACK_TICKERS
        emojis = data.get("emojis") or _FALLBACK_EMOJIS
        return list(tickers), dict(emojis)
    except Exception as e:
        print(f"[warn] tickers.json 로드 실패, fallback 사용: {e}", file=sys.stderr)
        return list(_FALLBACK_TICKERS), dict(_FALLBACK_EMOJIS)


TICKERS, EMOJIS = _load_tickers()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Error Reporter
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if ErrorReporter is not None:
    REPORTER = ErrorReporter(
        webhook=DISCORD_WEBHOOK,
        threshold=5,
        run_label="daily_briefing v4",
    )
else:
    REPORTER = None


def _report(label, exc):
    if REPORTER is not None:
        REPORTER.record(label, exc)
    else:
        print(f"[warn] {label}: {type(exc).__name__}: {exc}", file=sys.stderr)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Yahoo/FRED 수집 (함수명·시그니처 기존 그대로, 에러 처리만 구조화)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def yp(s):
    """Yahoo 현재가."""
    try:
        url = (
            f"https://query2.finance.yahoo.com/v8/finance/chart/"
            f"{requests.utils.quote(s)}?interval=1d&range=1d"
        )
        return requests.get(url, headers=UA, timeout=10).json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except Exception as e:
        _report(f"yp:{s}", e)
        return None


def yh(s, r="1y"):
    """Yahoo 종가 히스토리 (값만)."""
    try:
        url = (
            f"https://query2.finance.yahoo.com/v8/finance/chart/"
            f"{requests.utils.quote(s)}?interval=1d&range={r}"
        )
        c = requests.get(url, headers=UA, timeout=15).json()["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        return [x for x in c if x is not None]
    except Exception as e:
        _report(f"yh:{s}:{r}", e)
        return []


def yh_dated(s, r="3mo"):
    """Yahoo 종가 히스토리 (날짜 포함) → {YYYY-MM-DD: close}.

    v4.2 신규. 역사적 시계열 재계산용.
    """
    try:
        url = (
            f"https://query2.finance.yahoo.com/v8/finance/chart/"
            f"{requests.utils.quote(s)}?interval=1d&range={r}"
        )
        data = requests.get(url, headers=UA, timeout=15).json()["chart"]["result"][0]
        timestamps = data["timestamp"]
        closes = data["indicators"]["quote"][0]["close"]
        result = {}
        for ts, c in zip(timestamps, closes):
            if c is None:
                continue
            date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            result[date] = c
        return result
    except Exception as e:
        _report(f"yh_dated:{s}:{r}", e)
        return {}


def fv(s):
    """FRED 최신값."""
    if not FRED_API_KEY:
        return None
    try:
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={s}&api_key={FRED_API_KEY}"
            f"&limit=1&sort_order=desc&file_type=json"
        )
        return float(requests.get(url, timeout=10).json()["observations"][0]["value"])
    except Exception as e:
        _report(f"fv:{s}", e)
        return None


def fv_series(s, limit=80):
    """FRED 시계열 → {YYYY-MM-DD: value}.

    v4.2 신규. 역사적 시계열 재계산용.
    """
    if not FRED_API_KEY:
        return {}
    try:
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={s}&api_key={FRED_API_KEY}"
            f"&limit={limit}&sort_order=desc&file_type=json"
        )
        obs = requests.get(url, timeout=10).json()["observations"]
        result = {}
        for o in obs:
            try:
                result[o["date"]] = float(o["value"])
            except (ValueError, KeyError):
                # FRED는 휴일에 "." 값을 넣는 경우가 있음 — skip
                continue
        return result
    except Exception as e:
        _report(f"fv_series:{s}", e)
        return {}


def mom(h, days):
    if len(h) < days + 1:
        return None
    return (h[-1] - h[-days - 1]) / h[-days - 1] * 100


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Legio v2.11 mom_score (수식 불변)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VOL_PENALTY_DENOM = 0.80
VOL_PENALTY_FLOOR = 0.50
MOMMA_ALPHA = 0.30
MOMMA_SLOPE_NORM = 0.011
MOMMA_SLOPE_LB = 5


def legio_mom_score(h):
    """Legio v2.11 가중 모멘텀 = base × vol_penalty × momma."""
    if len(h) < 22:
        return None

    # ① base = 0.25×1M + 0.30×3M + 0.30×6M + 0.15×12M
    r1m = mom(h, 21) or 0
    r3m = mom(h, 63) or 0
    r6m = mom(h, 126) or 0
    r12m = mom(h, 252) or 0

    if len(h) < 63:
        r3m = mom(h, 20) or 0
    if len(h) < 126:
        r6m = mom(h, 20) or 0
    if len(h) < 252:
        r12m = r6m

    base = 0.25 * (r1m / 100) + 0.30 * (r3m / 100) + 0.30 * (r6m / 100) + 0.15 * (r12m / 100)

    # ② vol_penalty: 63일 연환산 변동성
    vp = 1.0
    if len(h) >= 63:
        rets = []
        for j in range(len(h) - 63, len(h)):
            if h[j - 1] > 0:
                rets.append((h[j] - h[j - 1]) / h[j - 1])
        if len(rets) >= 10:
            avg = sum(rets) / len(rets)
            var = sum((x - avg) ** 2 for x in rets) / (len(rets) - 1)
            ann_vol = math.sqrt(var) * math.sqrt(252)
            vp = max(VOL_PENALTY_FLOOR, min(1.0, 1.0 - ann_vol / VOL_PENALTY_DENOM))

    # ③ momma: MA20 5일 기울기 감쇠
    mp = 1.0
    if len(h) >= 25:
        ma20_now = sum(h[-20:]) / 20
        ma20_prev = sum(h[-20 - MOMMA_SLOPE_LB:-MOMMA_SLOPE_LB]) / 20
        if ma20_prev > 0:
            slope = (ma20_now - ma20_prev) / ma20_prev
            slope_neg = min(slope / MOMMA_SLOPE_NORM, 0.0)
            slope_neg = max(slope_neg, -1.0)
            mp = 1.0 + MOMMA_ALPHA * slope_neg

    return round(base * vp * mp, 4)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Legio RSI (Wilder 14일)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def compute_rsi(h, period=14):
    if len(h) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(len(h) - period, len(h)):
        d = h[i] - h[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return round(100 - 100 / (1 + rs), 1)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Legio 52주 최고가 거리
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

W52_BOOST_ALPHA = 0.15


def w52_distance(h):
    if len(h) < 126:
        return None
    h252 = h[-252:] if len(h) >= 252 else h
    high = max(h252)
    cur = h[-1]
    if high <= 0:
        return None
    pct = (cur / high - 1) * 100
    return round(pct, 1)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Oracle 연속 하락일
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def consecutive_drops(h):
    if len(h) < 2:
        return 0
    c = 0
    for i in range(len(h) - 1, 0, -1):
        if h[i] < h[i - 1]:
            c += 1
        else:
            break
    return c


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Legio 변동성 타겟 스케일 (SPY 기반)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TARGET_VOL = 0.10


def vol_target(spy_h):
    if len(spy_h) < 21:
        return 1.0
    rets = []
    for i in range(len(spy_h) - 20, len(spy_h)):
        if spy_h[i - 1] > 0:
            rets.append((spy_h[i] - spy_h[i - 1]) / spy_h[i - 1])
    if len(rets) < 19:
        return 1.0
    avg = sum(rets) / len(rets)
    var = sum((x - avg) ** 2 for x in rets) / (len(rets) - 1)
    rv = math.sqrt(var) * math.sqrt(252)
    if rv <= 0.01:
        return 1.0
    return round(max(0.20, min(1.0, TARGET_VOL / rv)), 2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Defense 진입게이트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def entry_gates(dxy, vix):
    if dxy is None or vix is None:
        return {"SLV": "--", "COPX": "--", "VEA": "--", "block": False}
    if dxy > 104:
        return {"SLV": "⛔0%", "COPX": "⛔0%", "VEA": "⛔0%", "block": True}

    sd = 100 if dxy <= 97 else (50 if dxy <= 100 else 0)
    sv = 100 if vix <= 24 else (50 if vix <= 26 else 0)
    slv = min(sd, sv)

    cd = 100 if dxy <= 96 else (50 if dxy <= 99 else 0)
    cv = 100 if vix <= 23 else (50 if vix <= 25 else 0)
    copx = min(cd, cv)

    vea = 100 if (dxy <= 100 and vix <= 26) else 0

    def fmt_gate(v):
        if v == 100:
            return "🟢100%"
        if v == 50:
            return "🟡50%"
        return "🔴0%"

    return {
        "SLV": fmt_gate(slv),
        "COPX": fmt_gate(copx),
        "VEA": fmt_gate(vea),
        "block": False,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# v4.2 NEW: 역사적 실효공격비율 시계열 (stateless 재계산)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _compute_gradient_for_day(vix_v, oas_v, move_v, move_rel, dfii_v):
    """특정 일자의 gradient·defense·attack 계산. calc_gradient와 동일 수식."""
    vs = lin(vix_v or 18, 18, 30, 25)
    os_ = lin(oas_v or 3, 3, 5.5, 25)
    ms = lin(move_v or 80, 80, 130, 25)

    if move_rel and move_rel > 1.0:
        if move_rel >= 1.20:
            b = 5
        elif move_rel >= 1.15:
            b = 4
        elif move_rel >= 1.10:
            b = 3
        elif move_rel >= 1.05:
            b = 1.5
        else:
            b = 0
        ms = min(25, ms + b)

    fs = 8
    rr = lin(dfii_v or 1.0, 0.5, 2.5, 15) if dfii_v else 0
    total = min(100, round(vs + os_ + ms + fs + rr, 1))
    defense = round(10 + (total / 100) * 80, 1)
    attack = round(100 - defense, 1)
    return total, defense, attack


def _vt_for_window(spy_window):
    """특정 20일 SPY 종가 윈도우에서 VT 스케일 계산. vol_target과 동일 수식."""
    if len(spy_window) < 21:
        return 1.0
    rets = []
    for j in range(1, len(spy_window)):
        if spy_window[j - 1] > 0:
            rets.append((spy_window[j] - spy_window[j - 1]) / spy_window[j - 1])
    if len(rets) < 19:
        return 1.0
    avg = sum(rets) / len(rets)
    var = sum((x - avg) ** 2 for x in rets) / (len(rets) - 1)
    rv = math.sqrt(var) * math.sqrt(252)
    if rv <= 0.01:
        return 1.0
    return round(max(0.20, min(1.0, TARGET_VOL / rv)), 2)


def compute_historical_eff_atk(days=30):
    """최근 `days` 영업일의 실효공격비율 시계열.

    반환: [{date, eff_atk, vt, defense, attack}, ...] (오름차순, 가장 최근이 마지막)
    실패·데이터 부족 시 빈 list.

    수식·상수는 calc_gradient·vol_target과 동일. 단, MOVE_REL은
    MOVE 시계열 기반 MA20으로 재구성해서 정확도 유지.
    """
    # 시계열 fetch (약 3개월치)
    spy_map = yh_dated("SPY", "3mo")
    vix_map = yh_dated("^VIX", "3mo")
    move_map = yh_dated("^MOVE", "3mo")
    oas_map = fv_series("BAMLH0A0HYM2", limit=80)
    dfii_map = fv_series("DFII10", limit=80)

    if not spy_map or not vix_map:
        return []

    # SPY 날짜 오름차순 → 순서 보장
    spy_dates = sorted(spy_map.keys())
    spy_closes = [spy_map[d] for d in spy_dates]

    # MOVE 시계열도 오름차순
    move_dates = sorted(move_map.keys())
    move_closes = [move_map[d] for d in move_dates]
    move_date_idx = {d: i for i, d in enumerate(move_dates)}

    # FRED forward fill 준비 (오름차순 순회하며 누적)
    last_oas = None
    last_dfii = None

    results = []
    start_i = max(0, len(spy_dates) - days)

    for i, date in enumerate(spy_dates):
        # forward fill 업데이트 (모든 날짜 순회)
        if date in oas_map:
            last_oas = oas_map[date]
        if date in dfii_map:
            last_dfii = dfii_map[date]

        # 대상 구간만 수집
        if i < start_i:
            continue
        if date not in vix_map or date not in move_map:
            continue

        v = vix_map[date]
        mv = move_map[date]

        # MOVE_REL 재구성: 해당 일자의 MOVE MA20
        mr = None
        mi = move_date_idx.get(date, -1)
        if mi >= 20:
            ma20 = sum(move_closes[mi - 20:mi]) / 20
            if ma20 > 0:
                mr = mv / ma20

        _total, _defense, attack = _compute_gradient_for_day(
            v, last_oas, mv, mr, last_dfii
        )

        # VT: 해당 일자 이전 21개 SPY 종가
        if i < 21:
            vt = 1.0
        else:
            window = spy_closes[i - 20:i + 1]  # 21개 (vol_target 로직과 일치)
            vt = _vt_for_window(window)

        eff_atk = round(attack * vt, 1)
        results.append({
            "date": date,
            "eff_atk": eff_atk,
            "vt": vt,
            "defense": _defense,
            "attack": attack,
        })

    return results


def sparkline(values):
    """유니코드 블록 스파크라인 (1문자 = 1값).

    반환 길이 = len(values). 빈 list면 빈 문자열.
    """
    if not values:
        return ""
    blocks = "▁▂▃▄▅▆▇█"
    mn = min(values)
    mx = max(values)
    if mx == mn:
        # 전부 동일 → 중간 블록
        return blocks[len(blocks) // 2] * len(values)
    span = mx - mn
    last = len(blocks) - 1
    return "".join(
        blocks[min(last, int((v - mn) / span * last))] for v in values
    )


def format_history_block(results):
    """실효공격 시계열을 embed용 텍스트로 변환. 데이터 부족 시 빈 문자열."""
    if not results or len(results) < 2:
        return ""

    values = [r["eff_atk"] for r in results]
    spark = sparkline(values)
    mn = min(values)
    mx = max(values)
    cur = values[-1]
    avg = sum(values) / len(values)

    direction = ""
    if len(values) >= 14:
        last7 = sum(values[-7:]) / 7
        prev7 = sum(values[-14:-7]) / 7
        delta = last7 - prev7
        if delta > 1.0:
            arrow = "↗"
        elif delta < -1.0:
            arrow = "↘"
        else:
            arrow = "→"
        direction = (
            f"\n방향 {arrow} (7일 평균 {last7:.1f}% vs "
            f"이전 7일 {prev7:.1f}%, {delta:+.1f}%p)"
        )

    return (
        f"\n\n📈 **실효공격 {len(values)}일 추이**\n"
        f"`{spark}`\n"
        f"최저 **{mn:.1f}%** · 평균 **{avg:.1f}%** · "
        f"최고 **{mx:.1f}%** · 오늘 **{cur:.1f}%**"
        f"{direction}"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 센서 수집 총괄
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def fetch():
    vix = yp("^VIX")
    vix3m = yp("^VIX3M")
    move = yp("^MOVE")
    wti = yp("CL=F")
    dxy = yp("DX-Y.NYB")
    rsp = yp("RSP")
    vvix = yp("^VVIX")
    hyg = yp("HYG")
    tlt = yp("TLT")
    krw = yp("KRW=X")
    btc = yp("BTC-USD")
    esf = yp("ES=F")
    nqf = yp("NQ=F")

    sh = yh("SPY", "1y")
    rh = yh("RSP", "2mo")
    mh = yh("^MOVE", "2mo")
    wh = yh("CL=F", "2mo")
    hyg_h = yh("HYG", "2mo")
    tlt_h = yh("TLT", "2mo")
    btc_h = yh("BTC-USD", "2mo")

    oas = fv("BAMLH0A0HYM2")
    t5y = fv("T5YIE")
    sahm = fv("SAHMCURRENT")
    dfii = fv("DFII10")
    t10 = fv("T10Y2Y")
    icsa = fv("ICSA")
    rrp = fv("RRPONTSYD")
    gs2 = fv("GS2")
    gs10 = fv("GS10")

    spy = sh[-1] if sh else None
    s200 = sum(sh[-200:]) / 200 if len(sh) >= 200 else None
    s60 = sum(sh[-60:]) / 60 if len(sh) >= 60 else None

    def bd(a, m):
        if not m:
            return 0
        c = 0
        for p in reversed(a):
            if p < m:
                c += 1
            else:
                break
        return c

    b200 = bd(sh, s200)
    b60 = bd(sh, s60)
    br60 = (spy - s60) / s60 if spy and s60 else None
    wc = (wh[-1] - wh[-8]) / wh[-8] if len(wh) >= 8 else None
    vv = vix / vix3m if vix and vix3m and vix3m > 0 else None
    mm = sum(mh[-20:]) / 20 if len(mh) >= 20 else None
    mr = move / mm if move and mm and mm > 0 else None

    brd = None
    if len(sh) >= 22 and len(rh) >= 22:
        sr = sh[-1] / sh[-22]
        rr_ = rh[-1] / rh[-22]
        if rr_ > 0:
            brd = sr / rr_

    s1d = mom(sh, 1)
    s1w = mom(sh, 5)
    s1m = mom(sh, 22)

    hyg_1d = mom(hyg_h, 1)
    tlt_1d = mom(tlt_h, 1)
    btc_1d = mom(btc_h, 1)

    hdata = {}
    for tk in TICKERS:
        h = yh(tk, "1y")
        p = h[-1] if h else yp(tk)
        ms = legio_mom_score(h)
        rsi = compute_rsi(h)
        w52 = w52_distance(h)
        cdrops = consecutive_drops(h)
        hdata[tk] = {
            "p": p,
            "1D": mom(h, 1),
            "1M": mom(h, 22),
            "3M": mom(h, 63),
            "6M": mom(h, 126),
            "12M": mom(h, 252),
            "score": ms,
            "rsi": rsi,
            "w52": w52,
            "cdrops": cdrops,
        }

    gp = hdata.get("GLD", {}).get("p")
    sp_ = hdata.get("SLV", {}).get("p")
    cp = hdata.get("COPX", {}).get("p")
    gs_r = gp / sp_ if gp and sp_ and sp_ > 0 else None
    cg_r = cp / gp if cp and gp and gp > 0 else None

    vt = vol_target(sh)
    eg = entry_gates(dxy, vix)

    return {
        "VIX": vix, "VIX3M": vix3m, "MOVE": move, "OAS": oas, "WTI": wti, "SPY": spy,
        "T5YIE": t5y, "DXY": dxy, "RSP": rsp, "DFII10": dfii,
        "T10Y2Y": t10, "ICSA": icsa, "SAHM": sahm,
        "S200": s200, "S60": s60, "b200": b200, "b60": b60, "br60": br60,
        "WC": wc, "VV": vv, "MM": mm, "MR": mr, "BRD": brd,
        "S1D": s1d, "S1W": s1w, "S1M": s1m,
        "VVIX": vvix, "HYG": hyg, "TLT": tlt, "RRP": rrp, "GS2": gs2, "GS10": gs10,
        "KRW": krw, "BTC": btc, "ESF": esf, "NQF": nqf,
        "GS_R": gs_r, "CG_R": cg_r, "H": hdata, "VT": vt, "EG": eg,
        "HYG_1D": hyg_1d, "TLT_1D": tlt_1d, "BTC_1D": btc_1d,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Oracle
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def lin(v, lo, hi, mx):
    if v <= lo:
        return 0
    if v >= hi:
        return mx
    return round(mx * (v - lo) / (hi - lo), 2)


def calc_tide(s, ic):
    s = s or 0
    ic = ic or 220000
    if s >= 0.50:
        return "RECESSION_CONFIRMED"
    if s >= 0.30:
        return "RECESSION_WATCH"
    if s >= 0.25 or ic >= 300000:
        return "SLOWDOWN"
    return "EXPANSION"


def calc_inferno(t, w):
    t = t or 2.5
    w = w or 80
    if t < 1.5:
        return "DEFLATION_RISK"
    if t >= 3.0 or w >= 120:
        return "HOT"
    if t >= 2.7 or w >= 95:
        return "RISING"
    return "STABLE"


def calc_curve(s):
    s = s if s is not None else 0.5
    if s <= -0.5:
        return "DEEP_INVERT"
    if s <= 0:
        return "INVERTED"
    if s <= 0.3:
        return "FLAT"
    return "NORMAL"


def calc_gradient(d):
    vs = lin(d["VIX"] or 18, 18, 30, 25)
    os_ = lin(d["OAS"] or 3, 3, 5.5, 25)
    ms = lin(d["MOVE"] or 80, 80, 130, 25)

    mr = d.get("MR")
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
        ms = min(25, ms + b)

    fs = 8
    rr = lin(d["DFII10"] or 1.0, 0.5, 2.5, 15) if d.get("DFII10") else 0

    t = min(100, round(vs + os_ + ms + fs + rr, 1))
    df = round(10 + (t / 100) * 80, 1)

    if t < 20:
        bk = "🟢GREEN"
    elif t < 40:
        bk = "🟡경계"
    elif t < 60:
        bk = "🟡YELLOW"
    elif t < 80:
        bk = "🟠RED"
    else:
        bk = "🔴STORM"

    return {
        "t": t, "bk": bk, "df": df,
        "ak": round(100 - df, 1),
        "vs": vs, "os": os_, "ms": ms, "fs": fs, "rr": rr,
    }


def calc_regime(d, g):
    td = calc_tide(d["SAHM"], d["ICSA"])
    inf = calc_inferno(d["T5YIE"], d["WTI"])
    cv = calc_curve(d["T10Y2Y"])
    df = d["DFII10"] or 1.0
    gt = g["t"]
    sm = d["SAHM"]

    if td == "RECESSION_CONFIRMED" or (td == "RECESSION_WATCH" and cv == "DEEP_INVERT"):
        return {"l": "🔴🔴 침체확정", "rp": 60, "td": td, "inf": inf, "cv": cv}
    if td in ("SLOWDOWN", "RECESSION_WATCH") and inf in ("RISING", "HOT"):
        return {"l": "🟠 스태그플레이션", "rp": 30, "td": td, "inf": inf, "cv": cv}
    if td in ("SLOWDOWN", "RECESSION_WATCH") and inf == "STABLE":
        return {"l": "🔴 침체경계", "rp": 40, "td": td, "inf": inf, "cv": cv}
    if td in ("SLOWDOWN", "RECESSION_WATCH") and inf == "DEFLATION_RISK":
        return {"l": "🔵 디플레형", "rp": 45, "td": td, "inf": inf, "cv": cv}
    if td == "EXPANSION" and df > 1.5 and inf in ("RISING", "HOT"):
        return {"l": "🟡 고금리", "rp": 20, "td": td, "inf": inf, "cv": cv}
    if td == "EXPANSION" and gt < 15 and (sm or 0) < 0.15 and cv != "DEEP_INVERT":
        return {"l": "🟢🟢 초강세장", "rp": 5, "td": td, "inf": inf, "cv": cv}
    return {"l": "🟢 확장기", "rp": 10, "td": td, "inf": inf, "cv": cv}


def calc_triggers(d):
    vix = d["VIX"] or 0
    move = d["MOVE"] or 0
    oas = d["OAS"] or 0
    wti = d["WTI"] or 0
    t5y = d["T5YIE"] or 0
    vv = d["VV"] or 0

    ids = ["E0", "E1", "E2", "E3", "E4", "L0a", "L0b", "L1", "L2", "L3"]
    act = [
        vix >= 30 or vv > 1.05,
        t5y > 3 and wti > 120,
        d["b200"] >= 5,
        d["BRD"] is not None and d["BRD"] >= 1.12,
        d["WC"] is not None and d["WC"] >= 0.20,
        oas >= 5.8,
        oas >= 5.2,
        vix >= 42 or move >= 190 or oas >= 8.5,
        vix >= 45,
        d["b60"] >= 12 and d.get("br60") is not None and d["br60"] <= -0.05,
    ]
    chips = " ".join(f"🔴{ids[i]}" if act[i] else f"⚪{ids[i]}" for i in range(len(ids)))

    stg = "CLEAR"
    if act[9]:
        stg = "L3"
    elif act[8]:
        stg = "L2"
    elif act[7]:
        stg = "L1"
    elif act[5] or act[6]:
        stg = "L0"
    elif any(act[:5]):
        stg = "PRE"

    gld = t5y >= 3.0 or (t5y >= 2.7 and wti >= 95)
    return {"chips": chips, "stg": stg, "gld": gld}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 포맷 유틸
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def f(v, u="", dc=1):
    if v is None:
        return "--"
    return f"{u}{v:.{dc}f}"


def sg(v):
    if v is None:
        return "--"
    return f"+{v:.1f}%" if v >= 0 else f"{v:.1f}%"


def dot(ok):
    if ok is None:
        return "❓"
    return "🟢" if ok else "🔴"


def dot3(v, good, warn):
    if v is None:
        return "❓"
    if isinstance(good, str):
        if good == "pos":
            return "🟢" if v > 0 else ("🟡" if v > -2 else "🔴")
        if good == "neg":
            return "🟢" if v < 0 else ("🟡" if v < 2 else "🔴")
    if warn is None:
        return "🟢" if v < good else "🔴"
    if v < good:
        return "🟢"
    if v < warn:
        return "🟡"
    return "🔴"


def momdot(v):
    if v is None:
        return "⚪"
    if v >= 5:
        return "🟢"
    if v >= 0:
        return "🟡"
    if v >= -5:
        return "🟠"
    return "🔴"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Discord 전송 (재시도 3회, 지수 백오프)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def send(p, retries=3):
    if not DISCORD_WEBHOOK:
        return False
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(DISCORD_WEBHOOK, json=p, timeout=10)
            if 200 <= r.status_code < 300:
                return True
            if r.status_code == 429:
                try:
                    ra = float(r.json().get("retry_after", 1.0))
                except Exception:
                    ra = 2.0
                print(f" 429. {ra}s 대기 (시도 {attempt}/{retries})")
                time.sleep(ra)
                continue
            if 500 <= r.status_code < 600 and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            print(f" Discord {r.status_code}: {r.text[:200]}")
            return False
        except Exception as e:
            print(f" send 예외 (시도 {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)
    return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 뉴스 수집·번역
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def fetch_news():
    headlines = []
    sources = [
        ("https://www.cnbc.com/id/20910258/device/rss/rss.html", "CNBC"),
        ("https://feeds.marketwatch.com/marketwatch/topstories/", "MW"),
        ("https://www.cnbc.com/id/10000664/device/rss/rss.html", "CNBC"),
    ]
    for url, src in sources:
        try:
            r = requests.get(url, headers=UA, timeout=10)
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:5]:
                t = item.find("title")
                if t is not None and t.text:
                    headlines.append(f"[{src}] {t.text.strip()}")
        except Exception as e:
            _report(f"news:{src}", e)
    return headlines[:15]


def translate_news(headlines):
    if not ANTHROPIC_API_KEY or not headlines:
        return None
    try:
        joined = "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines))
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1000,
                "messages": [{
                    "role": "user",
                    "content": (
                        "아래 영문 경제 뉴스를 한글 1줄 요약. "
                        "중복 합치고 5~8개만. ▸ 로 시작. 출처 불필요.\n\n"
                        f"{joined}"
                    ),
                }],
            },
            timeout=30,
        )
        print(f" Claude: {r.status_code}")
        if r.status_code != 200:
            print(f" 응답: {r.text[:300]}")
            return None
        return r.json().get("content", [{}])[0].get("text", "").strip() or None
    except Exception as e:
        _report("anthropic:translate", e)
        print(f" 번역에러: {e}")
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 브리핑 embed 생성 (v4.2: hist_eff_atk 인자 추가)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build(d, reg, grd, trg, hist_eff_atk=None):
    now = datetime.now(KST)
    date = now.strftime("%Y-%m-%d (%a)")
    stg = trg["stg"]
    se = {"CLEAR": "🟢", "PRE": "🟡", "L0": "🟠",
          "L1": "🔴", "L2": "🔴🔴", "L3": "⚫"}.get(stg, "⚪")
    sc = {"CLEAR": 0x3DBB7E, "PRE": 0xEFB030, "L0": 0xEFB030,
          "L1": 0xE07238, "L2": 0xD83030, "L3": 0x2C2C2A}.get(stg, 0x5B9CF6)

    vs200 = f"{(d['SPY']-d['S200'])/d['S200']*100:+.1f}%" if d["SPY"] and d["S200"] else "--"
    vs60 = f"{(d['SPY']-d['S60'])/d['S60']*100:+.1f}%" if d["SPY"] and d["S60"] else "--"
    rv = d["VIX"] is not None and d["VIX"] < 20
    rm = d["MOVE"] is not None and d["MOVE"] < 100
    rs = d["SAHM"] is not None and d["SAHM"] < 0.30

    # 1️⃣ 핵심 요약 (+ 실효공격 30일 스파크라인)
    vt = d["VT"]
    vt_pct = int(vt * 100)
    eff_atk = round(grd["ak"] * vt, 1)
    vt_dot = "🟢" if vt_pct >= 80 else ("🟡" if vt_pct >= 50 else "🔴")

    history_block = format_history_block(hist_eff_atk) if hist_eff_atk else ""

    e1 = {
        "title": f"☀️ INVICTUS 모닝 브리핑 — {date}",
        "color": sc,
        "description": (
            f"{se} **경보 {stg}** │ **{reg['l']}** │ RP **{reg['rp']}%**\n"
            f"📊 그래디언트 **{grd['t']}**/100 {grd['bk']} │ "
            f"🛡️방어 {grd['df']}% │ ⚔️공격 {grd['ak']}%\n"
            f"{vt_dot} **VT스케일** {vt_pct}% → 실효공격 **{eff_atk}%** "
            f"(공격×SPY변동성축소)"
            f"{history_block}"
        ),
    }

    # 2️⃣ 센서
    e2 = {
        "title": "📡 핵심 센서",
        "color": 0x5B9CF6,
        "description": (
            f"{dot3(d['VIX'],30,42)} **VIX {f(d['VIX'])}** 공포지수 │ "
            f"{dot3(d['MOVE'],150,190)} **MOVE {f(d['MOVE'],dc=0)}** 채권변동성 │ "
            f"{dot3(d['OAS'],5.2,5.8)} **OAS {f(d['OAS'],'',2)}%** 신용위험\n"
            f"{dot3(d['WTI'],95,120)} **WTI ${f(d['WTI'])}** 유가 │ "
            f"{dot3(d['T5YIE'],2.7,3.0)} **T5YIE {f(d['T5YIE'],'',2)}%** 기대인플레 │ "
            f"{dot3(d['DXY'],100,104)} **DXY {f(d['DXY'],dc=2)}** 달러강도\n"
            f"{dot3(d['VVIX'],110,130)} **VVIX {f(d['VVIX'],dc=0)}** VIX선행경보 │ "
            f"{dot3(d['MR'],1.05,1.10) if d['MR'] else '❓'} "
            f"**MOVE/MA20 {f(d['MR'],dc=3)}** 채권급변 │ "
            f"{dot3(d['VV'],1.00,1.05) if d['VV'] else '❓'} "
            f"**VIX/VIX3M {f(d['VV'],dc=3)}** 단기공포"
        ),
    }

    # 3️⃣ 레짐 + TIER2
    td_dot = {"EXPANSION": "🟢", "SLOWDOWN": "🟡",
              "RECESSION_WATCH": "🟠", "RECESSION_CONFIRMED": "🔴"}.get(reg["td"], "❓")
    inf_dot = {"STABLE": "🟢", "RISING": "🟡",
               "HOT": "🔴", "DEFLATION_RISK": "🔵"}.get(reg["inf"], "❓")
    cv_dot = {"NORMAL": "🟢", "FLAT": "🟡",
              "INVERTED": "🟠", "DEEP_INVERT": "🔴"}.get(reg["cv"], "❓")

    e3 = {
        "title": "🏛️ 레짐 │ 경기·물가·금리",
        "color": 0xEFB030,
        "description": (
            f"{td_dot} **TIDE {reg['td']}** 경기사이클 │ "
            f"{inf_dot} **INFERNO {reg['inf']}** 물가환경 │ "
            f"{cv_dot} **CURVE {reg['cv']}** 수익률곡선\n"
            f"{dot3(d['DFII10'],1.5,2.0) if d['DFII10'] else '❓'} "
            f"**DFII10 {f(d['DFII10'],'',2)}%** 실질금리 │ "
            f"{'🟢' if d['T10Y2Y'] and d['T10Y2Y']>0 else '🔴'} "
            f"**T10Y2Y {f(d['T10Y2Y'],'',2)}%** 장단기차 │ "
            f"{dot3(d['SAHM'],0.25,0.30) if d['SAHM'] else '❓'} "
            f"**SAHM {f(d['SAHM'],'',2)}** 실업판정\n"
            f"🏦 **2Y {f(d['GS2'],'',2)}%** │ **10Y {f(d['GS10'],'',2)}%** │ "
            f"{dot3(d['ICSA'],250000,300000) if d['ICSA'] else '❓'} "
            f"**ICSA {f(d['ICSA'],'',0)}** 실업수당\n\n"
            f"**그래디언트 분해** ({grd['t']}/100)\n"
            f"VIX **{grd['vs']}**/25 │ OAS **{grd['os']}**/25 │ "
            f"MOVE **{grd['ms']}**/25 │ FLOW **{grd['fs']}**/25 │ "
            f"RR **{grd['rr']}**/15"
        ),
    }

    # 4️⃣ 유동성 + 글로벌
    rrp_t = f"{d['RRP']/1e9:.0f}B" if d["RRP"] else "--"
    e4 = {
        "title": "💧 유동성 │ 글로벌 │ 환율",
        "color": 0x1DA1F2,
        "description": (
            f"{'🟡' if d['RRP'] and d['RRP']>500e9 else '🟢'} "
            f"**RRP ${rrp_t}** 역레포잔고 │ "
            f"{momdot(d['HYG_1D'])} **HYG ${f(d['HYG'])}** ({sg(d['HYG_1D'])}) 하이일드 │ "
            f"{momdot(d['TLT_1D'])} **TLT ${f(d['TLT'])}** ({sg(d['TLT_1D'])}) 장기국채\n"
            f"{'🟡' if d['KRW'] and d['KRW']>1350 else '🟢'} "
            f"**원/달러 {f(d['KRW'],dc=0)}원** │ "
            f"{momdot(d['BTC_1D'])} **BTC ${f(d['BTC'],dc=0)}** ({sg(d['BTC_1D'])}) 위험자산심리\n"
            f"{momdot(d['S1D'])} **S&P선물 {f(d['ESF'],dc=0)}** │ "
            f"**나스닥선물 {f(d['NQF'],dc=0)}** 오늘장 방향\n"
            f"{'🔴' if d['GS_R'] and d['GS_R']>80 else ('🟡' if d['GS_R'] and d['GS_R']>70 else '🟢')} "
            f"**금/은비 {f(d['GS_R'],dc=1)}** 높으면 공포 │ "
            f"{'🟢' if d['CG_R'] and d['CG_R']>0.20 else ('🟡' if d['CG_R'] and d['CG_R']>0.15 else '🔴')} "
            f"**구리/금비 {f(d['CG_R'],dc=3)}** 높으면 성장"
        ),
    }

    # 5️⃣ 보유종목 모멘텀 Top10
    ranked = []
    for tk in TICKERS:
        h = d["H"].get(tk, {})
        scv = h.get("score")
        ranked.append((tk, h, scv if scv is not None else -999))
    ranked.sort(key=lambda x: x[2], reverse=True)

    lines = []
    for i, (tk, h, _scv) in enumerate(ranked[:10]):
        em = EMOJIS.get(tk, "")
        p = h.get("p")
        d1 = h.get("1D")
        score = h.get("score")
        rsi = h.get("rsi")
        w52 = h.get("w52")
        cd = h.get("cdrops", 0)

        sc_str = f"{score:+.3f}" if score is not None else "--"
        sc_dot = momdot(score * 100 if score else None)

        rsi_dot = "❓"
        if rsi is not None:
            if rsi >= 70:
                rsi_dot = "🔴"
            elif rsi >= 60:
                rsi_dot = "🟡"
            elif rsi <= 30:
                rsi_dot = "🔵"
            elif rsi <= 40:
                rsi_dot = "🟡"
            else:
                rsi_dot = "🟢"

        w52_dot = "❓"
        if w52 is not None:
            if w52 >= -3:
                w52_dot = "🟢"
            elif w52 >= -10:
                w52_dot = "🟡"
            else:
                w52_dot = "🔴"

        cd_str = f" ⚠️{cd}일↓" if cd >= 3 else ""

        lines.append(
            f"**#{i+1}** {sc_dot} {em}{tk} **{sc_str}** │ "
            f"${f(p)} │ 1D {sg(d1)}\n"
            f"　　{rsi_dot}RSI {f(rsi,dc=0)} │ "
            f"{w52_dot}52주 {f(w52)}%{cd_str}"
        )

    e5 = {
        "title": "📊 Legio 모멘텀 Top10 (20종목 중)",
        "color": 0x3DBB7E,
        "description": "\n".join(lines),
    }

    # 6️⃣ SPY + 트리거 + 재진입 + 진입게이트
    eg = d["EG"]
    e6 = {
        "title": "📈 SPY │ 트리거 │ 재진입 │ 진입게이트",
        "color": 0x3DBB7E,
        "description": (
            f"{momdot(d['S1D'])} **SPY ${f(d['SPY'])}** │ "
            f"1D **{sg(d['S1D'])}** │ 1W **{sg(d['S1W'])}** │ 1M **{sg(d['S1M'])}**\n"
            f"{'🟢' if vs200[0]=='+' else '🔴'} vs200MA **{vs200}** │ "
            f"{'🟢' if vs60[0]=='+' else '🔴'} vs60MA **{vs60}** │ "
            f"{dot3(d['BRD'],1.08,1.12) if d['BRD'] else '❓'} "
            f"BREADTH **{f(d['BRD'],dc=3)}**\n"
            f"{dot(d['b200']<5)} 200MA하회 **{d['b200']}일** │ "
            f"{dot(d['b60']<12)} 60MA하회 **{d['b60']}일**\n\n"
            f"{trg['chips']}\n"
            f"🥇 GLD매도 {'🚫금지' if trg['gld'] else '✅허용'}\n\n"
            f"**재진입조건** (전부 충족 필수)\n"
            f"{dot(rv)} VIX<20 **{f(d['VIX'])}** │ "
            f"{dot(rm)} MOVE<100 **{f(d['MOVE'],dc=0)}** │ "
            f"{dot(rs)} SAHM<0.30 **{f(d['SAHM'],'',2)}**\n\n"
            f"**진입게이트** (DXY {f(d['DXY'],dc=1)} │ VIX {f(d['VIX'])})\n"
            f"🥈SLV **{eg['SLV']}** │ 🟤COPX **{eg['COPX']}** │ 🌍VEA **{eg['VEA']}**"
        ),
    }

    # 7️⃣ 각주
    e7 = {
        "color": 0x485070,
        "description": (
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
            "▸ **VIX** 공포지수 🟢<30 🟡30~42 🔴42↑ │ "
            "**MOVE** 채권변동성 🟢<150 🟡150~190 🔴190↑\n"
            "▸ **OAS** 신용스프레드 🟢<5.2 🟡5.2~5.8 🔴5.8↑ │ "
            "**WTI** 유가 🟢<95 🟡95~120 🔴120↑\n"
            "▸ **T5YIE** 기대인플레 🟢<2.7 🟡2.7~3.0 🔴3.0↑ │ "
            "**DXY** 달러 🟢<100 🟡100~104 🔴104↑\n"
            "▸ **VVIX** VIX선행 🟢<110 🟡110~130 🔴130↑ │ "
            "**DFII10** 실질금리 🟢<1.5 🟡1.5~2.0 🔴2.0↑\n"
            "▸ **T10Y2Y** 장단기차 🟢양수 🔴역전 │ "
            "**SAHM** 실업 🟢<0.25 🟡0.25~0.30 🔴0.30↑\n"
            "▸ **RRP** 역레포 🟢<500B 🟡500B↑ │ "
            "**HYG** 하이일드 ↓=신용불안 │ **TLT** 국채 ↑=금리하락\n"
            "▸ **금/은비** 🟢<70 🟡70~80 🔴80↑(공포) │ "
            "**구리/금비** 🟢>0.20(성장) 🔴<0.15(방어)\n"
            "▸ **RSI** 🟢40~60 🟡60~70/30~40 🔴70↑과매수 🔵30↓과매도(매수기회)\n"
            "▸ **52주** 고점대비 🟢-3%내 🟡-10%내 🔴-10%↓ │ **연속↓** 3일↑ ⚠️경고\n"
            "▸ **VT스케일** 공격×(목표10%÷SPY실현변동성). 변동성↑→공격자동축소\n"
            "▸ **실효공격 30일** 유니코드 스파크라인. 방향↗↘→ 7일 평균 비교\n"
            "▸ **진입게이트** DXY/VIX 기반 SLV·COPX·VEA 매수허용%\n"
            "▸ **Legio score** (0.25×1M+0.30×3M+0.30×6M+0.15×12M)×vol감쇠×MA20감쇠"
        ),
        "footer": {
            "text": f"INVICTUS Bot │ {datetime.now(KST).strftime('%H:%M KST')} │ Oracle v2.13"
        },
    }

    return [e1, e2, e3, e4, e5, e6, e7]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    print("📋 모닝 브리핑 v4 생성 중...")
    d = fetch()
    g = calc_gradient(d)
    r = calc_regime(d, g)
    t = calc_triggers(d)
    print(f" 레짐:{r['l']} 경보:{t['stg']}")

    # 실효공격 30일 시계열 (v4.2 신규, 실패 시 빈 list → build가 스킵)
    print(" 📈 실효공격 30일 시계열 수집 중...")
    hist = compute_historical_eff_atk(30)
    print(f"   {len(hist)}일 복원 완료")

    embeds = build(d, r, g, t, hist)

    # 뉴스
    print(" 📰 뉴스 수집 중...")
    hl = fetch_news()
    print(f" {len(hl)}개 헤드라인")
    if hl:
        tr = translate_news(hl)
        if tr:
            embeds.append({
                "title": "📰 글로벌 경제 뉴스",
                "color": 0x1DA1F2,
                "description": tr,
                "footer": {"text": "CNBC │ MarketWatch │ Claude 번역"},
            })
            print(" ✅ 뉴스 번역 완료")
        else:
            print(" ⚠️ 번역 생략")

    now = datetime.now(KST)
    ok1 = send({
        "content": f"☀️ **INVICTUS 모닝 브리핑** — {now.strftime('%Y-%m-%d %H:%M KST')}",
        "embeds": embeds[:5],
    })
    ok2 = True
    if len(embeds) > 5:
        ok2 = send({"embeds": embeds[5:]})

    if ok1 and ok2:
        print(" ✅ 전송 완료")
    else:
        print(f" ⚠️ 부분 실패 (첫 메시지 {'ok' if ok1 else 'fail'}, "
              f"두 번째 {'ok' if ok2 else 'fail'})")

    if REPORTER is not None:
        REPORTER.flush_if_threshold()


if __name__ == "__main__":
    main()
