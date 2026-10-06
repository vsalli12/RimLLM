import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from PIL import Image
import image_generation as images
import host_frontend


def png():
    output = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(output, format="PNG")
    return output.getvalue()


class ImageTests(unittest.TestCase):
    def test_workflow_prompt_and_job_specific_download(self):
        queued = Mock(ok=True)
        queued.json.return_value = {"prompt_id": "job"}
        history = Mock()
        history.json.return_value = {"job": {"status": {"completed": True},
            "outputs": {"132": {"images": [{"filename": "right.png", "subfolder": "scribbles", "type": "output"}]}}}}
        download = Mock(content=png())
        with patch.object(images.requests, "post", return_value=queued) as post, patch.object(
                images.requests, "get", side_effect=[history, download]) as get:
            output = images.generate_scribble_image("A colonist carries stone.")
        workflow = post.call_args.kwargs["json"]["prompt"]
        self.assertEqual(workflow["130"]["inputs"]["value"], "A colonist carries stone.")
        self.assertIn("pencil", workflow["131"]["inputs"]["string_a"])
        self.assertTrue(output.startswith(b"\x89PNG"))
        self.assertEqual(get.call_args.kwargs["params"]["filename"], "right.png")

    def test_comfy_execution_failure_is_reported(self):
        queued = Mock(ok=True)
        queued.json.return_value = {"prompt_id": "bad"}
        history = Mock()
        history.json.return_value = {"bad": {"status": {"status_str": "error",
            "messages": [["execution_error", {"exception_message": "out of memory"}]]}}}
        with patch.object(images.requests, "post", return_value=queued), patch.object(images.requests, "get", return_value=history):
            with self.assertRaisesRegex(RuntimeError, "out of memory"):
                images.generate_scribble_image("A scene")

    def test_cache_frontend_and_stale_text(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            root = Path(folder)
            timeline = root / "chronicles/game/session"
            timeline.mkdir(parents=True)
            entry = timeline / "day001.json"
            entry.write_text(json.dumps({"day": 1, "chronicle": "Hauling stone.", "story_bits": []}))
            with patch.object(images.RAG_main, "generate_image_prompt", return_value="A colonist carries stone.") as prompt, patch.object(
                    images, "generate_scribble_image", return_value=png()) as render:
                output = images.ensure_entry_scribble(entry)
                self.assertEqual(images.ensure_entry_scribble(entry), output)
                self.assertEqual(prompt.call_count, 1)
                self.assertEqual(render.call_count, 1)
                with patch.object(host_frontend, "DIRECTORY", root):
                    url = host_frontend.load_diaries()[0]["entries"][0]["image_url"]
                    self.assertEqual(host_frontend.image_file(url), output.resolve())
                    self.assertIsNone(host_frontend.image_file('/scribbles/game/session/%2e%2e%2fsecret.png'))
                    self.assertIsNone(host_frontend.image_file('/scribbles/game/session/story_memory.json'))
                    changed = json.loads(entry.read_text())
                    changed["chronicle"] = "Planting crops."
                    entry.write_text(json.dumps(changed))
                    self.assertIsNone(host_frontend.load_diaries()[0]["entries"][0]["image_url"])
                self.assertNotEqual(images.ensure_entry_scribble(entry), output)
                self.assertEqual(render.call_count, 2)

    def test_failed_image_keeps_diary_and_reuses_scene_prompt_on_retry(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            entry = Path(folder) / "day001.json"
            original = json.dumps({"day": 1, "chronicle": "Hauling stone.", "story_bits": []})
            entry.write_text(original)
            with patch.object(images.RAG_main, "generate_image_prompt", return_value="A stone pile") as prompt, patch.object(
                    images, "generate_scribble_image", side_effect=[RuntimeError("offline"), png()]):
                with self.assertRaisesRegex(RuntimeError, "offline"):
                    images.ensure_entry_scribble(entry)
                self.assertEqual(entry.read_text(), original)
                images.ensure_entry_scribble(entry)
                self.assertEqual(prompt.call_count, 1)


if __name__ == "__main__":
    unittest.main()
