"""Contract tests for the small ComfyUI prompt builder.

These tests intentionally inspect the serialized prompt rather than starting
ComfyUI.  That keeps the suite fast and makes wiring regressions obvious.
"""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _nodes(prompt: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return prompt entries that look like Comfy API-format nodes."""

    return [
        (str(node_id), node)
        for node_id, node in prompt.items()
        if isinstance(node, dict) and "class_type" in node and isinstance(node.get("inputs"), dict)
    ]


def _of_type(prompt: dict[str, Any], class_type: str) -> list[tuple[str, dict[str, Any]]]:
    return [(node_id, node) for node_id, node in _nodes(prompt) if node.get("class_type") == class_type]


def _one(prompt: dict[str, Any], class_type: str) -> tuple[str, dict[str, Any]]:
    matches = _of_type(prompt, class_type)
    if len(matches) != 1:
        raise AssertionError(f"expected one {class_type} node, found {len(matches)}")
    return matches[0]


def _is_ref(value: Any, node_id: str, output_index: int | None = None) -> bool:
    """Recognize the [node id, output slot] form used by Comfy prompts."""

    if not isinstance(value, (list, tuple)) or not value:
        return False
    if str(value[0]) != str(node_id):
        return False
    return output_index is None or (len(value) > 1 and int(value[1]) == output_index)


def _build_prompt(*, job_id: str, mode: str, planning: bool, uploaded_audio: str | None = None) -> dict[str, Any]:
    builder = importlib.import_module("yue2_app.workflow_builder")
    settings = {
        # These are deliberately non-default values: the resulting node inputs
        # must prove that settings are not silently discarded.
        "abc_planning": planning,
        "planning_enabled": planning,
        "planning": planning,
        "temperature": 0.61,
        "top_p": 0.73,
        "top_k": 17,
        "repetition_penalty": 1.13,
        "plan_temperature": 0.41,
        "plan_top_p": 0.67,
        "plan_top_k": 19,
        "plan_repetition_penalty": 1.07,
        "penalty_window": 91,
    }
    if hasattr(builder, "build_prompt"):
        # This is the public adapter contract.  Keep the positional call here
        # so a signature regression is reported clearly by the test suite.
        prompt = builder.build_prompt(
            job_id,
            mode,
            "cinematic ambient",
            "[Verse]\nA test lyric",
            47,
            123456,
            settings,
            uploaded_audio=uploaded_audio,
        )
    else:
        # Older/local implementations expose the same graph builder as
        # build_workflow with the settings expanded into keyword arguments.
        # This fallback keeps the test useful while the adapter is introduced.
        prompt = builder.build_workflow(
            job_id,
            mode,
            "cinematic ambient",
            "[Verse]\nA test lyric",
            47,
            123456,
            temperature=settings["temperature"],
            top_p=settings["top_p"],
            top_k=settings["top_k"],
            repetition_penalty=settings["repetition_penalty"],
            planning_enabled=planning,
            plan_temperature=settings["plan_temperature"],
            plan_top_p=settings["plan_top_p"],
            plan_top_k=settings["plan_top_k"],
            plan_repetition_penalty=settings["plan_repetition_penalty"],
            penalty_window=settings["penalty_window"],
            source_filename=uploaded_audio,
        )
    if not isinstance(prompt, dict):
        raise AssertionError(f"build_prompt returned {type(prompt)!r}, expected a dict")
    return prompt


class WorkflowBuilderContractTests(unittest.TestCase):
    def test_original_planning_controls_abc_generator_and_common_inputs(self) -> None:
        for planning in (True, False):
            with self.subTest(planning=planning):
                prompt = _build_prompt(job_id="contract-original", mode="original", planning=planning)
                music_id, music = _one(prompt, "YuE2GenerateMusic")
                generator_nodes = _of_type(prompt, "YuE2GenerateABC")

                self.assertEqual(len(generator_nodes), int(planning))
                self.assertEqual(music["inputs"].get("style"), "cinematic ambient")
                self.assertEqual(music["inputs"].get("lyrics"), "[Verse]\nA test lyric")
                self.assertEqual(music["inputs"].get("max_duration"), 47)
                self.assertEqual(music["inputs"].get("temperature"), 0.61)
                self.assertEqual(music["inputs"].get("top_p"), 0.73)
                self.assertEqual(music["inputs"].get("top_k"), 17)
                self.assertEqual(music["inputs"].get("repetition_penalty"), 1.13)
                self.assertIn("abc", music["inputs"])

                seed_id, seed_node = _one(prompt, "SeedNode")
                self.assertEqual(seed_node["inputs"].get("seed"), 123456)
                self.assertTrue(_is_ref(music["inputs"].get("seed"), seed_id, 0))

                if planning:
                    generator_id, generator = generator_nodes[0]
                    self.assertEqual(generator["inputs"].get("style"), "cinematic ambient")
                    self.assertEqual(generator["inputs"].get("lyrics"), "[Verse]\nA test lyric")
                    self.assertTrue(_is_ref(generator["inputs"].get("seed"), seed_id, 0))
                    self.assertTrue(_is_ref(music["inputs"]["abc"], generator_id, 0))
                    for key, value in {
                        "temperature": 0.41,
                        "top_p": 0.67,
                        "top_k": 19,
                        "repetition_penalty": 1.07,
                        "penalty_window": 91,
                    }.items():
                        self.assertEqual(generator["inputs"].get(key), value, key)
                else:
                    self.assertEqual(music["inputs"]["abc"], "")

                sampler_id, sampler = _one(prompt, "KSampler")
                self.assertIsNotNone(sampler_id)
                self.assertEqual(sampler["inputs"].get("steps"), 32)
                self.assertEqual(sampler["inputs"].get("cfg"), 1)
                self.assertEqual(sampler["inputs"].get("sampler_name"), "dpm_2")
                self.assertEqual(sampler["inputs"].get("scheduler"), "sgm_uniform")
                self.assertEqual(sampler["inputs"].get("denoise"), 1)

                _, saver = _one(prompt, "SaveAudioMP3")
                self.assertEqual(saver["inputs"].get("quality"), "320k")
                self.assertEqual(saver["inputs"].get("filename_prefix"), "yue2/contract-original")

    def test_cover_uses_audio_encoder_melody_preview_and_preview_abc(self) -> None:
        prompt = _build_prompt(
            job_id="contract-cover",
            mode="cover",
            planning=False,
            uploaded_audio="reference.wav",
        )

        load_id, load = _one(prompt, "LoadAudio")
        self.assertIn("reference.wav", str(load["inputs"]))
        self.assertEqual(len(_of_type(prompt, "AudioEncoderLoader")), 1)
        _, abc_encoder = _one(prompt, "SheetSage2AudioToABC")
        self.assertEqual(abc_encoder["inputs"].get("mode"), "melody")
        preview_nodes = _of_type(prompt, "PreviewAny")
        self.assertGreaterEqual(len(preview_nodes), 1)

        _, music = _one(prompt, "YuE2GenerateMusic")
        self.assertEqual(music["inputs"].get("mode"), "melody")
        self.assertEqual(music["inputs"].get("style"), "cinematic ambient")
        self.assertEqual(music["inputs"].get("lyrics"), "[Verse]\nA test lyric")
        self.assertEqual(music["inputs"].get("max_duration"), 47)
        self.assertEqual(music["inputs"].get("temperature"), 0.61)
        self.assertEqual(music["inputs"].get("top_p"), 0.73)
        self.assertEqual(music["inputs"].get("top_k"), 17)
        self.assertEqual(music["inputs"].get("repetition_penalty"), 1.13)
        self.assertTrue(
            any(_is_ref(music["inputs"].get("abc"), preview_id, 0) for preview_id, _ in preview_nodes),
            "cover music abc input must be wired from PreviewAny",
        )
        self.assertIn("audio", abc_encoder["inputs"])
        self.assertTrue(
            _is_ref(abc_encoder["inputs"]["audio"], load_id, 0)
            or "reference.wav" in str(abc_encoder["inputs"]["audio"])
        )

    def test_save_and_sampler_contract_is_present_for_each_supported_mode(self) -> None:
        # The Studio has two generation paths: original text generation and
        # audio cover.  Both must produce the same deterministic export setup.
        for mode, audio in (("original", None), ("cover", "reference.wav")):
            with self.subTest(mode=mode):
                prompt = _build_prompt(job_id=f"job-{mode}", mode=mode, planning=False, uploaded_audio=audio)
                _, checkpoint = _one(prompt, "CheckpointLoaderSimple")
                self.assertEqual(checkpoint["inputs"]["ckpt_name"], "yue2_3b_bf16.safetensors")
                _, sampler = _one(prompt, "KSampler")
                self.assertEqual(
                    {key: sampler["inputs"].get(key) for key in ("steps", "cfg", "sampler_name", "scheduler", "denoise")},
                    {"steps": 32, "cfg": 1, "sampler_name": "dpm_2", "scheduler": "sgm_uniform", "denoise": 1},
                )
                _, saver = _one(prompt, "SaveAudioMP3")
                self.assertEqual(saver["inputs"].get("quality"), "320k")
                self.assertEqual(saver["inputs"].get("filename_prefix"), f"yue2/job-{mode}")


if __name__ == "__main__":
    unittest.main()
