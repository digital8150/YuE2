"""Caption grammar for the YuE2 instrumental AR LoRA."""

from __future__ import annotations

import re


INSTRUMENTAL_LORA = "ar_lora_inst_v3abc_comfyui.safetensors"
DEFAULT_INSTRUMENTAL_PLAN = "[instrumental]"
_SECTION = re.compile(
    r"\[(intro|verse|pre-chorus|chorus|bridge|outro)(?: ([0-9]+:[0-5][0-9])-([0-9]+:[0-5][0-9]))?\]",
    re.IGNORECASE,
)


def normalize_instrumental_plan(value: str) -> str:
    """Return a LoRA-trained caption, rejecting sung words and production notes."""
    lines = [line.strip().lower() for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    if not lines:
        return DEFAULT_INSTRUMENTAL_PLAN
    if lines == [DEFAULT_INSTRUMENTAL_PLAN]:
        return DEFAULT_INSTRUMENTAL_PLAN
    if len(lines) > 32:
        raise ValueError("instrumental plan has too many sections")
    timed: bool | None = None
    previous_end = -1
    for line in lines:
        match = _SECTION.fullmatch(line)
        if match is None:
            raise ValueError("instrumental plan must contain only section tags")
        has_times = match.group(2) is not None
        if timed is not None and timed != has_times:
            raise ValueError("instrumental plan cannot mix timed and untimed tags")
        timed = has_times
        if has_times:
            start = _seconds(match.group(2))
            end = _seconds(match.group(3))
            if start >= end or start < previous_end:
                raise ValueError("instrumental section times must be ordered")
            previous_end = end
    return "\n".join(lines)


def _seconds(value: str) -> int:
    minutes, seconds = value.split(":")
    return int(minutes) * 60 + int(seconds)
