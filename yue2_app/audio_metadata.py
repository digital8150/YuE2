"""Read ComfyUI's existing prompt tag from a generated MP3."""

from __future__ import annotations

import json
from typing import Any


def _syncsafe(value: bytes) -> int:
    return (value[0] << 21) | (value[1] << 14) | (value[2] << 7) | value[3]


def prompt_from_mp3(data: bytes) -> dict[str, Any] | None:
    """Return the ComfyUI graph in an ID3v2 TXXX:prompt frame, if present."""
    if len(data) < 10 or data[:3] != b"ID3" or data[3] not in (3, 4):
        return None
    version = data[3]
    end = min(len(data), 10 + _syncsafe(data[6:10]))
    offset = 10
    while offset + 10 <= end:
        frame = data[offset:offset + 10]
        if frame[:4] == b"\0" * 4:
            break
        size = _syncsafe(frame[4:8]) if version == 4 else int.from_bytes(frame[4:8], "big")
        offset += 10
        if size < 1 or offset + size > end:
            break
        payload = data[offset:offset + size]
        offset += size
        if frame[:4] != b"TXXX":
            continue
        encoding = payload[0]
        codec = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}.get(encoding)
        if codec is None:
            continue
        try:
            value = payload[1:].decode(codec).strip("\0")
            label, prompt = value.split("\0", 1)
            if label.lower() != "prompt":
                continue
            graph = json.loads(prompt.strip("\0"))
            return graph if isinstance(graph, dict) else None
        except (UnicodeError, ValueError, TypeError):
            continue
    return None


def recipe_from_prompt(graph: dict[str, Any]) -> dict[str, Any] | None:
    """Project ComfyUI node inputs onto fields supported by the Studio editor."""
    nodes = [node for node in graph.values() if isinstance(node, dict)]
    music = next((node.get("inputs") for node in nodes if node.get("class_type") == "YuE2GenerateMusic"), None)
    seed_node = next((node.get("inputs") for node in nodes if node.get("class_type") == "SeedNode"), None)
    if not isinstance(music, dict) or not isinstance(seed_node, dict):
        return None
    plan = next((node.get("inputs") for node in nodes if node.get("class_type") == "YuE2GenerateABC"), None)
    mode = "cover" if music.get("mode") == "melody" else "original"
    fields = ("temperature", "top_p", "top_k", "repetition_penalty")
    settings = {key: music[key] for key in ("max_duration", *fields) if isinstance(music.get(key), (int, float))}
    if "max_duration" in settings:
        settings["duration"] = settings.pop("max_duration")
    settings["planning_enabled"] = isinstance(plan, dict)
    if isinstance(plan, dict):
        for key in (*fields, "penalty_window"):
            if isinstance(plan.get(key), (int, float)):
                settings[f"plan_{key}" if key != "penalty_window" else key] = plan[key]
    seed = seed_node.get("seed")
    return {
        "mode": mode,
        "style": str(music.get("style") or ""),
        "lyrics": str(music.get("lyrics") or ""),
        "seed": seed if isinstance(seed, int) else None,
        "settings": settings,
    }
