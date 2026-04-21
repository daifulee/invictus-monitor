#!/usr/bin/env python3
"""
error_reporter.py — 외부 API 호출 실패 카운트·Discord 통지 유틸.

언제 쓰나:
    외부 API(Yahoo/FRED/Anthropic 등)를 여러 번 호출하는 스크립트에서
    "except: pass"로 조용히 묻히는 실패를 구조적으로 관측·보고.

사용 패턴:

    from error_reporter import ErrorReporter

    reporter = ErrorReporter(
        webhook=os.environ.get("DISCORD_WEBHOOK", ""),
        threshold=5,           # 누적 실패 5개 이상이면 Discord 알림
        run_label="daily_briefing v4",
    )

    # safe_call로 감싸기
    vix = reporter.safe_call("yahoo:VIX", lambda: fetch_vix(), default=None)

    # 실행 끝에서 임계 초과 시 알림
    reporter.flush_if_threshold()

설계 원칙:
    - 메모리 내 누적, 종료 시 1회 요약 전송 → 스팸 방지
    - threshold 미달이면 아무것도 보내지 않음 (운영 소음 최소화)
    - Discord 전송 자체가 실패해도 본 스크립트를 crash시키지 않음
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Callable, TypeVar


T = TypeVar("T")
KST = timezone(timedelta(hours=9))


@dataclass
class ErrorRecord:
    label: str
    kind: str
    message: str
    occurred_at: str


@dataclass
class ErrorReporter:
    webhook: str
    threshold: int = 5
    run_label: str = "unknown"
    records: list = field(default_factory=list)

    def record(self, label: str, exc: BaseException) -> None:
        """에러를 기록한다. 즉시 전송하지 않는다."""
        rec = ErrorRecord(
            label=label,
            kind=type(exc).__name__,
            message=str(exc)[:200],
            occurred_at=datetime.now(KST).strftime("%H:%M:%S"),
        )
        self.records.append(rec)

    def safe_call(self, label: str, fn, default=None):
        """fn()을 실행하고 예외 발생 시 기록 + default 반환."""
        try:
            return fn()
        except Exception as e:
            self.record(label, e)
            return default

    def count(self) -> int:
        return len(self.records)

    def summary_text(self) -> str:
        """Discord 전송용 요약 텍스트 (markdown)."""
        by_kind = {}
        for r in self.records:
            by_kind[r.kind] = by_kind.get(r.kind, 0) + 1
        kind_parts = [f"`{k}`×{v}" for k, v in sorted(by_kind.items())]
        head = f"⚠️ **{self.run_label}** — API 오류 {self.count()}건 (임계 {self.threshold})"
        summary = " ".join(kind_parts) if kind_parts else "(종류 집계 없음)"

        # 최근 10개 상세
        recent = self.records[-10:]
        detail_lines = [
            f"• `{r.occurred_at}` **{r.label}** — {r.kind}: {r.message}"
            for r in recent
        ]
        detail = "\n".join(detail_lines)

        return f"{head}\n{summary}\n\n__최근 10건:__\n{detail}"

    def flush(self, force: bool = False) -> bool:
        """알림 전송. force=False면 threshold 미달 시 생략. 전송 여부 반환."""
        if not self.records:
            return False
        if not force and self.count() < self.threshold:
            return False
        if not self.webhook:
            print(f"[error_reporter] DISCORD_WEBHOOK 미설정 → 스킵 ({self.count()}건)")
            return False

        payload = {"content": self.summary_text()[:1900]}
        try:
            req = urllib.request.Request(
                self.webhook,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if 200 <= resp.status < 300:
                    print(f"[error_reporter] 알림 전송 성공 ({self.count()}건)")
                    return True
                print(f"[error_reporter] 알림 전송 실패 HTTP {resp.status}")
                return False
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            # 알림 자체 실패는 조용히 무시 (원 스크립트 보호)
            print(f"[error_reporter] 알림 전송 예외 무시: {e}")
            return False

    def flush_if_threshold(self) -> bool:
        """임계 초과 시에만 전송."""
        return self.flush(force=False)


__all__ = ["ErrorReporter", "ErrorRecord"]
