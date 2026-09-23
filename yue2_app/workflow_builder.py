"""Build the private ComfyUI prompt graph used by the YuE2 web app."""

from __future__ import annotations

from typing import Any


YUE2_CHECKPOINT = "yue2_3b_bf16.safetensors"
SHEETSAGE_CHECKPOINT = "sheetsage2_bf16.safetensors"


def _link(node_id: str, output_index: int) -> list[str | int]:
    """Return ComfyUI's standard ``[node_id, output_index]`` link."""

    return [node_id, output_index]


def _source_reference(filename: str, subfolder: str, source_type: str) -> str:
    filename = str(filename).replace("\\", "/").lstrip("/")
    subfolder = str(subfolder or "").replace("\\", "/").strip("/")
    value = f"{subfolder}/{filename}" if subfolder else filename
    return f"{value} [{source_type}]" if source_type else value


def build_workflow(
    job_id: str,
    mode: str,
    style: str,
    lyrics: str = "",
    duration: float = 120.0,
    seed: int = 0,
    temperature: float = 1.0,
    top_p: float = 0.95,
    top_k: int = 100,
    repetition_penalty: float = 1.2,
    planning_enabled: bool = True,
    plan_temperature: float = 0.7,
    plan_top_p: float = 0.9,
    plan_top_k: int = 30,
    plan_repetition_penalty: float = 1.005,
    penalty_window: int = 100,
    source_filename: str | None = None,
    source_subfolder: str = "yue2_uploads",
    source_type: str = "input",
) -> dict[str, dict[str, Any]]:
    """Return a ComfyUI API prompt for an original or cover generation.

    The graph intentionally uses only the node fields accepted by the local
    YuE2 nodes.  Links use string node IDs, which is the format accepted by
    ComfyUI's ``/prompt`` endpoint and keeps the prompt independent of the UI
    workflow format.
    """

    if mode not in {"original", "cover"}:
        raise ValueError("unsupported generation mode")
    if mode == "cover" and not source_filename:
        raise ValueError("cover workflow requires an uploaded audio filename")

    graph: dict[str, dict[str, Any]] = {}
    graph["1"] = {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": YUE2_CHECKPOINT},
    }
    graph["2"] = {
        "class_type": "SeedNode",
        "inputs": {"seed": int(seed)},
    }

    music_id: str
    if mode == "original":
        if planning_enabled:
            graph["3"] = {
                "class_type": "YuE2GenerateABC",
                "inputs": {
                    "clip": _link("1", 1),
                    "style": style,
                    "lyrics": lyrics,
                    "seed": _link("2", 0),
                    "mode": "full",
                    "max_abc_tokens": 8192,
                    "temperature": float(plan_temperature),
                    "top_p": float(plan_top_p),
                    "top_k": int(plan_top_k),
                    "repetition_penalty": float(plan_repetition_penalty),
                    "penalty_window": int(penalty_window),
                },
            }
            abc: str | list[str | int] = _link("3", 0)
            music_id = "4"
        else:
            abc = ""
            music_id = "3"
    else:
        # Cover generations derive melody ABC from the uploaded source audio.
        graph["3"] = {
            "class_type": "LoadAudio",
            "inputs": {
                "audio": _source_reference(source_filename or "", source_subfolder, source_type),
            },
        }
        graph["4"] = {
            "class_type": "AudioEncoderLoader",
            "inputs": {"audio_encoder_name": SHEETSAGE_CHECKPOINT},
        }
        graph["5"] = {
            "class_type": "SheetSage2AudioToABC",
            "inputs": {
                "audio_encoder": _link("4", 0),
                "audio": _link("3", 0),
                "mode": "melody",
            },
        }
        graph["6"] = {
            "class_type": "PreviewAny",
            "inputs": {"source": _link("5", 0)},
        }
        abc = _link("6", 0)
        music_id = "7"

    graph[music_id] = {
        "class_type": "YuE2GenerateMusic",
        "inputs": {
            "clip": _link("1", 1),
            "style": style,
            "lyrics": lyrics,
            "abc": abc,
            "seed": _link("2", 0),
            "mode": "melody" if mode == "cover" else "full",
            "max_duration": float(duration),
            "min_duration": 0.0,
            "temperature": float(temperature),
            "top_p": float(top_p),
            "top_k": int(top_k),
            "repetition_penalty": float(repetition_penalty),
        },
    }

    zero_id = str(int(music_id) + 1)
    latent_id = str(int(music_id) + 2)
    sampler_id = str(int(music_id) + 3)
    vae_id = str(int(music_id) + 4)
    save_id = str(int(music_id) + 5)
    graph[zero_id] = {
        "class_type": "ConditioningZeroOut",
        "inputs": {"conditioning": _link(music_id, 0)},
    }
    graph[latent_id] = {
        "class_type": "EmptyYuE2LatentAudio",
        "inputs": {"seconds": _link(music_id, 1), "batch_size": 1},
    }
    graph[sampler_id] = {
        "class_type": "KSampler",
        "inputs": {
            "model": _link("1", 0),
            "positive": _link(music_id, 0),
            "negative": _link(zero_id, 0),
            "latent_image": _link(latent_id, 0),
            "seed": _link("2", 0),
            "steps": 32,
            "cfg": 1.0,
            "sampler_name": "dpm_2",
            "scheduler": "sgm_uniform",
            "denoise": 1.0,
        },
    }
    graph[vae_id] = {
        "class_type": "VAEDecodeAudio",
        "inputs": {
            "samples": _link(sampler_id, 0),
            "vae": _link("1", 2),
        },
    }
    graph[save_id] = {
        "class_type": "SaveAudioMP3",
        "inputs": {
            "audio": _link(vae_id, 0),
            "filename_prefix": f"yue2/{job_id}",
            "quality": "320k",
        },
    }
    return graph


__all__ = ["YUE2_CHECKPOINT", "SHEETSAGE_CHECKPOINT", "build_workflow"]
