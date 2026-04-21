# invictus-monitor 패치 v5 — 2026-04-21

Commander 승인 하에 누적된 패치:
v1 기본 리팩터 → v2 실효공격 시계열 → v3 Top10 시인성 → v4 한경 RSS 통합
→ **v5 Rich 카드형 한경+외신 + Top10 v4.2 형식 복원**.

## v5 주요 변경

| 영역 | 변경 |
|---|---|
| 한경 (rich) | `fetch_hankyung_articles` + `generate_rich_briefing("hankyung")` → 5 카드 |
| 외신 (rich) | CNBC + **BBC + Guardian** 3사 교차검증 + 한국 투자시사 → 5 카드 |
| 메시지 구조 | 2 → **4 메시지 분할** (코어 2 + 한경 1 + 외신 1) |
| Claude max_tokens | 1000 → **4000** (rich JSON 출력) |
| Top10 (e5) | v4.3 막대 → **v4.2 형식 복원** (종가 + 1D 변동율 + RSI + 52주, 2줄/종목) |
| 봇 운영 | Hankyoungbot · GlobalnewsBot **폐기 가능** (INVICTUS 단일 봇으로 대체) |

## 봇·채널 운영 결정 (2026-04-21 Commander 결정)

**채널 배치:** **🅰️ 단일 채널** (#invictus-모닝리포트로 통합)

후속 작업 (Discord 측):
1. Hankyoungbot 권한 회수 또는 봇 제거
2. GlobalnewsBot 권한 회수 또는 봇 제거
3. (선택) #한경브리핑·#외신종합 채널 아카이브 또는 삭제
4. INVICTUS 봇이 4개 메시지를 #invictus-모닝리포트에 정상 발송하는지 다음 08:00 KST에 확인

코드·webhook 변경 없음 — `DISCORD_WEBHOOK` 단일 secret 그대로.

## v5 메시지 발송 구조

```
[메시지 1] ☀️ INVICTUS 모닝 브리핑 — YYYY-MM-DD HH:MM KST
  ├─ e1 핵심 요약 + 실효공격 30일 스파크라인
  ├─ e2 핵심 센서 (VIX/MOVE/OAS/WTI/T5YIE/DXY...)
  ├─ e3 레짐 + TIER2 + 그래디언트 분해
  ├─ e4 유동성 + 글로벌 + 환율
  └─ e5 Legio Top10 (v4.2 형식: 종가·1D·RSI·52주)

[메시지 2]
  ├─ e6 SPY + 트리거 + 진입게이트
  └─ e7 각주

[메시지 3] 🇰🇷 한국경제 모닝 브리핑 — YYYY-MM-DD (요일)
  └─ 5 카드 (각 카드: 결론 + bullets, 카테고리별 색상)

[메시지 4] 🌐 외신 종합 모닝 브리핑 — YYYY-MM-DD (요일)
  └─ 5 카드 (각 카드: 핵심 + 투자 시사 + 교차검증, CNBC·BBC·Guardian)
```

## v5 토큰 비용

| 항목 | v4.4 | v5 | 차이 |
|---|---|---|---|
| Claude 호출 횟수 | 2회 (단순 요약) | 2회 (rich JSON) | = |
| 호출당 max_tokens | 1000 | 4000 | +3x |
| 일 토큰 예상 | ~1500 | ~6000 | +4x |
| 월 비용 (Haiku 기준) | < $0.05 | < $0.20 | +$0.15 |



## v4 추가분 — daily_briefing v4.4 (한경 RSS 통합)

**신규 함수:**

| 함수 | 역할 |
|---|---|
| `fetch_hankyung_news()` | `https://www.hankyung.com/feed`에서 헤드라인 최대 15개 수집 |
| `summarize_hankyung(headlines)` | Claude Haiku로 5~7개 선별·요약 (광고·연예 제외) |

**상수 신규:**
- `HANKYUNG_RSS = "https://www.hankyung.com/feed"`

**main() 변경:** 기존 외신 단독 embed → **외신 + 한경 통합 embed** (제목 `📰 경제 뉴스 종합`).

**렌더 예시:**

```
📰 경제 뉴스 종합

🇰🇷 한경 주요 뉴스
▸ 한은 기준금리 연 3.5% 동결
▸ 코스피 2500선 회복, 외인 매수
▸ 부동산 PF 부실 우려 지속
...

🌐 외신 종합
▸ Fed 12월 금리동결 확률 82%
▸ 미 10월 CPI 2.8%, 시장 부합
▸ 엔비디아 실적 앞두고 AI주 강세
...

한경 · CNBC · MarketWatch · Claude 번역
```

**실패 처리:**
- 한경 fetch 실패 → 외신만 표시
- 외신 fetch 실패 → 한경만 표시
- 둘 다 실패 → 뉴스 embed 자체 생략 (브리핑 본문은 영향 없음)
- footer 출처도 동적 구성 (실제 사용된 소스만 표시)

**Anthropic 비용 영향:**
- 기존: 외신 1회 호출 (~1000 tokens out)
- 신규: 외신 + 한경 2회 호출 (~1800 tokens out)
- 일 1회 실행이므로 월 비용 미미 (Haiku 기준 < $0.05/월 추가)

**샌드박스 검증 한계:** 워크스페이스 환경에서 `https://www.hankyung.com/feed`가 프록시에 차단되어 실 데이터 fetch 검증 불가. GitHub Actions 환경(인터넷 무제한)에서 정상 동작 예상.

## v3 추가분 — daily_briefing v4.3 (Top10 포맷 개선)

**변경 위치:** `build()` 내 e5 embed + 각주 e7 1줄 추가.

**변경 전 (v4.2):**
```
**#1** 🟢 🥇GLD +0.135 │ $185.5 │ 1D +0.5%
　　🟢RSI 58 │ 🟢52주 -2.1%
```
- 2줄/종목 × 10 = 20줄
- 가격·1D%로 시선 분산
- 상대강도 눈으로 비교 어려움

**변경 후 (v4.3):**
```
#1  🥇 GLD  ██████████ +0.135 │ 58🟢  -2.1%🟢
#2  📱 SMH  ██████░░░░ +0.085 │ 65🟡  -3.5%🟡
```
- 1줄/종목 × 10 = 10줄
- 점수 막대 `█░` 10칸 (#1 기준 비례)
- 음수 점수는 막대 0칸
- RSI + 52주만 남겨 한눈 스캔 최적화

**제거된 필드:** 가격(`$185.5`), 1D%(`1D +0.5%`)
→ 해당 정보는 e1(핵심요약)과 e6(SPY블록)에서 이미 제공되므로 중복

**수식·알고리즘 무변경:** 정렬 기준(`score`), RSI/52주 신호등 임계치 모두 동일.

## v2 추가분 — daily_briefing v4.2

| 추가 | 위치 | 효과 |
|---|---|---|
| `yh_dated(s, r)` | Yahoo 시계열 (날짜 포함) | 과거 일자별 VIX/MOVE/SPY 복원 |
| `fv_series(s, limit)` | FRED 시계열 | 과거 OAS/DFII10 복원 |
| `_compute_gradient_for_day()` | 보조 | `calc_gradient` 수식 그대로 재사용 |
| `_vt_for_window()` | 보조 | `vol_target` 수식 그대로 재사용 |
| `compute_historical_eff_atk(days=30)` | 시계열 복원 | 최근 30영업일 실효공격비율 list |
| `sparkline(values)` | 유틸 | 유니코드 블록 `▁▂▃▄▅▆▇█` 스파크라인 |
| `format_history_block(results)` | e1 embed 삽입 텍스트 | `📈 실효공격 30일 추이` 블록 |
| `build(..., hist_eff_atk=None)` | 시그니처 확장 | 스파크라인 블록 삽입 (옵션) |
| `main()` | 호출 추가 | `compute_historical_eff_atk(30)` → `build()`에 전달 |

**출력 형식 (e1 embed 하단에 추가):**

```
📈 실효공격 30일 추이
▁▁▂▃▅▇▆▅▄▃▂▂▃▄▅▆▇▇▆▅▄▃▂▁▁▂▃▄▅▆
최저 3.6% · 평균 42.1% · 최고 82.0% · 오늘 65.3%
방향 ↗ (7일 평균 52.1% vs 이전 7일 43.8%, +8.3%p)
```

**실패 처리:** Yahoo/FRED fetch 실패 시 `compute_historical_eff_atk`가 빈 list 반환 → `format_history_block`이 빈 문자열 반환 → e1 embed는 기존 3줄만 표시 (브리핑 자체는 영향 없음).

**방향 화살표 임계:** 7일 평균 델타 `>+1.0%p → ↗`, `<-1.0%p → ↘`, 그 사이 `→`.

## v1 변경 파일 (하단 원본 유지)

## 변경 파일 (덮어쓰기 대상)

| 파일 | 상태 | 변경 요약 |
|---|---|---|
| `daily_briefing.py` | 🔄 교체 | error_reporter 통합, send 재시도 3회, TICKERS JSON 로드, PEP8, `except:pass` 제거 |
| `monitor.py` | 🔄 교체 | error_reporter 통합, send_discord 재시도, PEP8, `minute < 5` 의도 주석 명확화 |
| `.github/workflows/daily_briefing.yml` | 🔄 교체 | timeout 3→5분, PYTHONUNBUFFERED 추가 |
| `.github/workflows/monitor.yml` | 🔄 교체 | concurrency 추가(job 적체 방지), PYTHONUNBUFFERED |
| `tickers.json` | ➕ 신규 | TICKERS/EMOJIS 중앙 관리 (SSOT) |
| `error_reporter.py` | ➕ 신규 | API 오류 누적 추적 + 임계 초과 시 Discord 알림 유틸 |

## 로직/수식 불변 보장

**절대 바뀌지 않은 것 (재확인용):**
- Legio v2.11 `legio_mom_score` — base/vol_penalty/momma 가중치 동일
- Oracle v2.13 — `classify_tide/inferno/curve`, `compute_gradient`, `classify_regime` 분기 동일
- 트리거 E0~L3 판정 기준 동일 (VIX≥30, OAS≥5.8, 등)
- 재진입 조건(VIX<20 & MOVE<100 & SAHM<0.30)
- 진입게이트(SLV/COPX/VEA) 계수
- RSI Wilder 14일, 52주거리, 연속하락 카운트
- VT 스케일 TARGET_VOL=0.10, floor 0.20
- Embed 색상·이모지 매핑 동일
- 7개 embed 구조 + 뉴스 append 순서 동일

**바뀐 것 (의도적):**
- 함수 내부의 `try/except: pass` → `try/except Exception: _report(...)` 로 교체
- `send()`: 단발 POST → **최대 3회 재시도** + 지수 백오프 + 429/5xx 분기
- TICKERS/EMOJIS: 하드코딩 → `tickers.json` 로드 (로드 실패 시 동일한 fallback)
- 세미콜론·한줄 다중문장 → PEP8 (로직 무변경)
- `main()` 말미: `REPORTER.flush_if_threshold()` 추가 (옵트인, 임계 5건)

## 위험성 평가

|위험|영향|완화|
|---|---|---|
|`tickers.json` 로드 실패|종목 순위 미표시|fallback 내장, 로드 실패 시 stderr 경고 후 정상 동작|
|`error_reporter` import 실패|에러 추적 중단|try/except로 감싸 ImportError 시 legacy 모드(stderr 출력)|
|재시도로 실행시간 증가|타임아웃 유발 가능|daily는 5분(기존 3분→5분)으로 상향, monitor는 3분 유지 + 재시도 3회 최대 ~14초 추가|
|`DISCORD_WEBHOOK` 환경변수 이름 변경 없음|- |기존 그대로 사용|

## 커밋 순서 (권장)

Chrome(Claude in Chrome)으로 `github.com/daifulee/invictus-monitor`를 열고:

1. `tickers.json` 커밋 → **안전** (새 파일, 아무도 아직 참조 안 함)
2. `error_reporter.py` 커밋 → **안전** (새 파일)
3. `.github/workflows/daily_briefing.yml` 커밋 → timeout 상향
4. `.github/workflows/monitor.yml` 커밋 → concurrency 추가
5. `monitor.py` 커밋 → 재시작 후 5분 뒤 Actions에서 녹색 확인
6. `daily_briefing.py` 커밋 → 다음 08:00 KST 브리핑에서 검증

→ 2-3-5-6 순서로 나누어 커밋하면 문제 발생 시 어느 파일이 원인인지 바로 특정 가능.

## 수동 검증 체크리스트

- [ ] `workflow_dispatch`로 monitor 수동 실행 → Discord 채널에 "🛡️ INVICTUS — 🟢 CLEAR" 류 메시지 수신
- [ ] `workflow_dispatch`로 daily_briefing 수동 실행 → 7~8개 embed 정상 수신, 레이아웃 동일
- [ ] Actions 로그에서 `[warn]` 발생 건수 확인 (0~2건 정상, 5건↑이면 `error_reporter`가 Discord로 요약 알림)
- [ ] `tickers.json` 수정 → daily_briefing 다음 실행에서 즉시 반영 확인

## 롤백 방법

Chrome에서 각 파일의 커밋 히스토리를 열어 `Revert this commit` 클릭. 6건 독립 revert 가능 (의존성 없음, 단 `monitor.py`/`daily_briefing.py`는 `error_reporter.py` import 시도 → ImportError면 legacy 모드이므로 안전).
