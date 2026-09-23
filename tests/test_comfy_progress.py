"""Progress events from ComfyUI remain scoped to their prompt and phase."""

import unittest
from unittest.mock import patch

from yue2_app.comfy_client import ComfyClient


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


if __name__ == "__main__":
    unittest.main()
