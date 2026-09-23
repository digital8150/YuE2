"""ComfyUI cancellation states must reach the Studio as cancelled."""

import unittest

from yue2_app.comfy_client import ComfyClient


class StubComfy(ComfyClient):
    def __init__(self, history_result, queue_result=None):
        super().__init__()
        self.history_result = history_result
        self.queue_result = queue_result or {"queue_running": [], "queue_pending": []}

    async def history(self, prompt_id):
        return self.history_result

    async def queue(self):
        return self.queue_result


class ComfyCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_interrupted_execution_is_cancelled(self):
        client = StubComfy({"p1": {"status": {
            "status_str": "error", "completed": False,
            "messages": [["execution_interrupted", {"prompt_id": "p1"}]],
        }}})
        self.assertEqual(await client.inspect_prompt("p1"), {"status": "cancelled"})

    async def test_removed_pending_prompt_is_cancelled(self):
        client = StubComfy({})
        self.assertEqual(await client.inspect_prompt("p1"), {"status": "cancelled"})

    async def test_execution_error_remains_failed(self):
        client = StubComfy({"p1": {"status": {
            "status_str": "error", "completed": False,
            "messages": [["execution_error", {"prompt_id": "p1"}]],
        }}})
        self.assertEqual((await client.inspect_prompt("p1"))["status"], "failed")


if __name__ == "__main__":
    unittest.main()
