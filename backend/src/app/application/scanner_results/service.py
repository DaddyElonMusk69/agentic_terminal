from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional

from app.domain.scanner_results.interfaces import ScannerResultsRepository


class ScannerResultsService:
    def __init__(self, repository: ScannerResultsRepository) -> None:
        self._repository = repository

    async def get_calendar_data(self) -> Dict[str, int]:
        results = await self._repository.get_calendar_counts()
        return {item_date.isoformat(): count for item_date, count in results}

    async def get_results_by_date(self, target_date: date) -> List[dict]:
        results = await self._repository.list_results_for_date(target_date)
        payloads: List[dict] = []
        for result in results:
            data = result.data.copy() if isinstance(result.data, dict) else {}
            data["id"] = result.id
            payloads.append(data)
        return payloads

    async def get_latest_results(self) -> tuple[Optional[date], List[dict]]:
        latest = await self._repository.get_latest_date()
        if latest is None:
            return None, []
        return latest, await self.get_results_by_date(latest)

    async def save_scan_results(
        self,
        results: Iterable[dict],
        target_date: Optional[date] = None,
    ) -> List[dict]:
        scan_date = target_date or datetime.utcnow().date()
        output: List[dict] = []
        for result in results:
            stored = await self._upsert_result(scan_date, result, skip_zero=True)
            if stored is not None:
                output.append(stored)
        return output

    async def delete_result(self, result_id: int) -> bool:
        return await self._repository.delete_result(result_id)

    async def export_scan_results(self) -> str:
        results = await self._repository.list_all_results()
        lines = ["date,ticker,votes,ema_signals,bb_signals,intervals"]

        for result in results:
            data = result.data or {}
            ema_votes = _coerce_votes(data.get("ema_votes"))
            bb_votes = _coerce_votes(data.get("bb_votes"))
            intervals = data.get("intervals") or []
            ema_str = _format_signals(ema_votes)
            bb_str = _format_signals(bb_votes)
            intervals_str = ";".join(str(item) for item in intervals)
            lines.append(
                f"{result.date.isoformat()},{result.ticker},{result.score or 0},{ema_str},{bb_str},{intervals_str}"
            )

        return "\n".join(lines)

    async def import_scan_results(self, csv_content: str) -> int:
        stream = io.StringIO(csv_content)
        reader = csv.DictReader(stream)
        count = 0

        for row in reader:
            scan_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
            ticker = row["ticker"].upper().strip()
            votes = int(row.get("votes", 0) or 0)

            ema_votes = _parse_signals(row.get("ema_signals", ""))
            bb_votes = _parse_signals(row.get("bb_signals", ""))
            intervals = _parse_intervals(row.get("intervals", ""))

            data = {
                "ticker": ticker,
                "votes": votes,
                "ema_votes": ema_votes,
                "bb_votes": bb_votes,
                "intervals": intervals,
            }

            await self._upsert_result(scan_date, data, skip_zero=False)
            count += 1

        return count

    async def _upsert_result(
        self,
        scan_date: date,
        result: dict,
        skip_zero: bool,
    ) -> Optional[dict]:
        if not isinstance(result, dict):
            return None
        ticker = str(result.get("ticker", "")).strip().upper()
        if not ticker:
            return None

        votes = int(result.get("votes") or 0)
        if skip_zero and votes <= 0:
            return None

        payload = dict(result)
        payload["ticker"] = ticker
        payload["votes"] = votes
        payload.pop("id", None)

        existing = await self._repository.get_result_by_date_and_ticker(scan_date, ticker)
        if existing:
            record = await self._repository.update_result(existing.id, votes, payload)
            if record is None:
                return None
            payload["id"] = record.id
        else:
            record = await self._repository.create_result(scan_date, ticker, votes, payload)
            payload["id"] = record.id

        return payload


def _coerce_votes(payload: object) -> List[dict]:
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _format_signals(signals: List[dict]) -> str:
    parts: List[str] = []
    for vote in signals:
        interval = vote.get("interval")
        param = vote.get("param")
        if interval is None or param is None:
            continue
        parts.append(f"{interval}@{param}")
    return ";".join(parts)


def _parse_signals(raw: str) -> List[dict]:
    raw = raw.strip()
    if not raw:
        return []
    votes: List[dict] = []
    for entry in raw.split(";"):
        if "@" not in entry:
            continue
        interval, param = entry.split("@", 1)
        interval = interval.strip()
        param = param.strip()
        if not interval or not param:
            continue
        votes.append({"interval": interval, "param": param})
    return votes


def _parse_intervals(raw: str) -> List[str]:
    raw = raw.strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(";") if item.strip()]
