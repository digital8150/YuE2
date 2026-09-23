"""Progress events from ComfyUI remain scoped to their prompt and phase."""

import unittest
from unittest.mock import patch

from yue2_app.comfy_client import ComfyClient
from yue2_app.workflow_builder import build_workflow


class ComfyProgressTests(unittest.TestCase):
    def test_token_rate_and_phase_reset(self) -> None:
        client = ComfyClient()
        client._progress_nodes["prompt-1"] = {"3": "abc", "4": "music", "7": "rendering"}

        with patch("yue2_app.comfy_client.time.monotonic", side_effect=[10.0, 12.0, 13.0]):
            client._record_progress({"type": "progress", "data": {"prompt_id": "prompt-1", "node": "3", "value": 20, "max": 100}})
            client._record_progress({"type": "progress", "data": {"prompt_id": "prompt-1", "node": "3", "value": 40, "max": 100}})
            self.assertEqual(client.progress_for("prompt-1"), {"phase": "abc", "current": 40, "total": 100, "rate": 10.0})
            client._record_progress({"type": "progress", "data": {"prompt_id": "prompt-1", "node": "4", "value": 1, "max": 500}})

        self.assertEqual(client.progress_for("prompt-1"), {"phase": "music", "current": 1, "total": 500, "rate": 0})
        client._record_progress({"type": "executing", "data": {"prompt_id": "prompt-1", "node": "7"}})
        self.assertEqual(client.progress_for("prompt-1"), {"phase": "rendering"})
        client.clear_progress("prompt-1")
        self.assertIsNone(client.progress_for("prompt-1"))

    def test_other_prompts_and_invalid_events_are_ignored(self) -> None:
        client = ComfyClient()
        client._progress_nodes["prompt-1"] = {"4": "music"}
        client._record_progress({"type": "progress", "data": {"prompt_id": "prompt-2", "node": "4", "value": 4, "max": 10}})
        client._record_progress({"type": "progress", "data": {"prompt_id": "prompt-1", "node": "4", "value": -1, "max": 10}})
        self.assertIsNone(client.progress_for("prompt-1"))


class WorkflowProgressTests(unittest.IsolatedAsyncioTestCase):
    async def test_original_and_cover_nodes_advance_through_three_stages(self) -> None:
        class Response:
            status = 200

            def __init__(self, prompt_id):
                self.prompt_id = prompt_id

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

            async def json(self, content_type=None):
                return {"prompt_id": self.prompt_id}

        class Session:
            def post(self, url, *, json, timeout):
                is_cover = any(node["class_type"] == "SheetSage2AudioToABC" for node in json["prompt"].values())
                return Response("cover" if is_cover else "original")

        client = ComfyClient(session=Session())
        for mode, first_phase, first_node in (("original", "abc", "3"), ("cover", "sheet", "5")):
            workflow = build_workflow("job", mode, "piano", source_filename="source.wav" if mode == "cover" else None)
            prompt_id = await client.queue_prompt(workflow, "studio")
            client._record_progress({"type": "executing", "data": {"prompt_id": prompt_id, "node": first_node}})
            self.assertEqual(client.progress_for(prompt_id), {"phase": first_phase})
            client._record_progress({"type": "executing", "data": {"prompt_id": prompt_id, "node": "6" if mode == "cover" else "1"}})
            self.assertEqual(client.progress_for(prompt_id), {"phase": first_phase})

            music_node = "7" if mode == "cover" else "4"
            sampler_node = "10" if mode == "cover" else "7"
            client._record_progress({"type": "executing", "data": {"prompt_id": prompt_id, "node": music_node}})
            self.assertEqual(client.progress_for(prompt_id), {"phase": "music"})
            client._record_progress({"type": "executing", "data": {"prompt_id": prompt_id, "node": sampler_node}})
            self.assertEqual(client.progress_for(prompt_id), {"phase": "rendering"})
            client._record_progress({"type": "executing", "data": {"prompt_id": prompt_id, "node": str(int(sampler_node) + 1)}})
            self.assertEqual(client.progress_for(prompt_id), {"phase": "finishing"})


if __name__ == "__main__":
    unittest.main()
