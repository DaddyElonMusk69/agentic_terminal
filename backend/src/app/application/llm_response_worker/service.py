from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from app.domain.llm_response_worker.models import ExecutionAction, ExecutionIdea, LlmResponseParseResult


class LlmResponseWorker:
    VALID_ACTIONS = {action.value for action in ExecutionAction}

    def parse(self, response: str) -> LlmResponseParseResult:
        if not response or not response.strip():
            return LlmResponseParseResult(
                success=False,
                error="Empty response from LLM",
                raw_response=response,
            )

        considerations = self.extract_considerations(response)

        ideas = self._try_json_parse(response)
        if not ideas:
            ideas = self._try_regex_extraction(response)

        if ideas:
            return LlmResponseParseResult(
                success=True,
                ideas=ideas,
                considerations=considerations,
                raw_response=response,
            )

        return LlmResponseParseResult(
            success=False,
            considerations=considerations,
            error="Failed to parse execution ideas from LLM response.",
            raw_response=response,
        )

    def _try_json_parse(self, response: str) -> List[ExecutionIdea]:
        try:
            data = json.loads(response.strip())
        except (json.JSONDecodeError, ValueError):
            return []

        if isinstance(data, list):
            ideas = [idea for idea in (self._dict_to_idea(item) for item in data) if idea]
            return ideas
        if isinstance(data, dict):
            idea = self._dict_to_idea(data)
            return [idea] if idea else []
        return []

    def _try_regex_extraction(self, response: str) -> List[ExecutionIdea]:
        all_ideas: List[ExecutionIdea] = []

        json_array_marker_pattern = r"JSON_ARRAY\s*(\[[\s\S]*\])"
        marker_matches = re.findall(json_array_marker_pattern, response, re.IGNORECASE)
        for match in marker_matches:
            ideas = self._parse_json_array(match.strip())
            if ideas:
                return ideas

        json_block_pattern = r"```json\s*([\s\S]*?)\s*```"
        matches = re.findall(json_block_pattern, response, re.IGNORECASE)
        for match in matches:
            ideas = self._parse_json_value(match.strip())
            if ideas:
                all_ideas.extend(ideas)
        if all_ideas:
            return all_ideas

        generic_block_pattern = r"```\s*([\s\S]*?)\s*```"
        matches = re.findall(generic_block_pattern, response)
        for match in matches:
            ideas = self._parse_json_value(match.strip())
            if ideas:
                all_ideas.extend(ideas)
        if all_ideas:
            return all_ideas

        json_array_pattern = r"\[[\s\S]*?\]"
        array_matches = re.findall(json_array_pattern, response)
        for match in array_matches:
            ideas = self._parse_json_value(match)
            if ideas:
                all_ideas.extend(ideas)
        if all_ideas:
            return all_ideas

        json_object_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
        matches = re.findall(json_object_pattern, response)
        for match in matches:
            ideas = self._parse_json_value(match)
            if ideas:
                all_ideas.extend(ideas)

        return all_ideas

    def _parse_json_value(self, value: str) -> List[ExecutionIdea]:
        try:
            data = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return []

        if isinstance(data, list):
            return [idea for idea in (self._dict_to_idea(item) for item in data) if idea]
        if isinstance(data, dict):
            idea = self._dict_to_idea(data)
            return [idea] if idea else []
        return []

    def _parse_json_array(self, json_str: str) -> List[ExecutionIdea]:
        try:
            data = json.loads(json_str)
            if isinstance(data, list):
                return [idea for idea in (self._dict_to_idea(item) for item in data) if idea]
        except json.JSONDecodeError:
            try:
                bracket_count = 0
                start_idx = json_str.find("[")
                if start_idx == -1:
                    return []
                for i, char in enumerate(json_str[start_idx:], start_idx):
                    if char == "[":
                        bracket_count += 1
                    elif char == "]":
                        bracket_count -= 1
                        if bracket_count == 0:
                            clean_json = json_str[start_idx : i + 1]
                            data = json.loads(clean_json)
                            if isinstance(data, list):
                                return [idea for idea in (self._dict_to_idea(item) for item in data) if idea]
                            break
            except (json.JSONDecodeError, ValueError):
                return []
        return []

    def _dict_to_idea(self, data: Any) -> Optional[ExecutionIdea]:
        if not isinstance(data, dict):
            return None

        action_str = str(data.get("action", "")).upper()
        if action_str not in self.VALID_ACTIONS:
            return None

        symbol = str(data.get("symbol", "")).strip().upper()
        if not symbol:
            return None

        action = ExecutionAction(action_str)
        tier = self._safe_int(data.get("tier"))
        leverage = self._safe_int(data.get("leverage"))

        return ExecutionIdea(
            action=action,
            symbol=symbol,
            position_size_usd=self._safe_float(data.get("position_size_usd")),
            entry_price=self._safe_float(data.get("entry_price")),
            limit_price=self._safe_float(data.get("limit_price")),
            time_in_force=self._safe_str(data.get("time_in_force")),
            stop_loss=self._safe_float(data.get("stop_loss")),
            take_profit=self._safe_float(data.get("take_profit")),
            new_stop_loss=self._safe_float(data.get("new_stop_loss")),
            new_take_profit=self._safe_float(data.get("new_take_profit")),
            reduce_pct=self._safe_float(data.get("reduce_pct")),
            confidence=self._safe_float(data.get("confidence")),
            reasoning=self._safe_str(data.get("reasoning")) or "",
            execute=bool(data.get("execute", True)),
            leverage=leverage,
            tier=tier,
            position_pct=self._safe_float(data.get("position_pct")),
            take_profit_roe=self._safe_float(data.get("take_profit_roe")),
        )

    def _safe_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _safe_int(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _safe_str(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        return str(value)

    def extract_considerations(self, response: str) -> List[Dict[str, Any]]:
        if not response:
            return []

        marker = "JSON_CONSIDER"
        marker_idx = response.upper().find(marker.upper())
        if marker_idx == -1:
            return []

        search_start = marker_idx + len(marker)
        bracket_start = response.find("[", search_start)
        if bracket_start == -1:
            return []

        bracket_count = 0
        bracket_end = -1
        for i, char in enumerate(response[bracket_start:], bracket_start):
            if char == "[":
                bracket_count += 1
            elif char == "]":
                bracket_count -= 1
                if bracket_count == 0:
                    bracket_end = i
                    break

        if bracket_end == -1:
            return []

        json_str = response[bracket_start : bracket_end + 1]
        try:
            data = json.loads(json_str)
            if isinstance(data, list):
                return [
                    item
                    for item in data
                    if isinstance(item, dict) and ("asset" in item or "symbol" in item)
                ]
        except json.JSONDecodeError:
            return []

        return []
