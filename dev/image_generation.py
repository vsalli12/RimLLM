"""Create diary scribbles through ComfyUI. Run with an entry JSON or timeline folder."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import secrets
import time
import uuid

import requests
from PIL import Image

import RAG_main

COMFY_SERVER = "http://127.0.0.1:8188"
WORKFLOW_PATH = Path(__file__).with_name("ZIT_scribble_generate.json")
PROMPT_INPUT_NODE = "130"
KSAMPLER_NODE = "3"
SAVE_IMAGE_NODE = "132"


def source_hash(chronicle):
    return hashlib.sha256(chronicle.encode("utf-8")).hexdigest()


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def generate_scribble_image(image_prompt, timeout=600):
    """Return PNG bytes from this exact ComfyUI job, not a shared output glob."""
    if not isinstance(image_prompt, str) or not image_prompt.strip():
        raise ValueError("Image prompt must be nonempty text")
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    workflow[PROMPT_INPUT_NODE]["inputs"]["value"] = image_prompt
    workflow[KSAMPLER_NODE]["inputs"]["seed"] = secrets.randbits(48)
    workflow[SAVE_IMAGE_NODE]["inputs"]["filename_prefix"] = "scribbles/diary_" + uuid.uuid4().hex
    response = requests.post(COMFY_SERVER + "/prompt", json={"prompt": workflow}, timeout=30)
    if not response.ok:
        raise RuntimeError(f"ComfyUI rejected workflow ({response.status_code}): {response.text[:2000]}")
    queued = response.json()
    if queued.get("node_errors"):
        raise RuntimeError(f"ComfyUI node errors: {queued['node_errors']}")
    prompt_id = queued["prompt_id"]
    deadline = time.monotonic() + timeout
    # History polling also works when execution finishes before we begin waiting.
    while time.monotonic() < deadline:
        response = requests.get(COMFY_SERVER + f"/history/{prompt_id}", timeout=30)
        response.raise_for_status()
        record = response.json().get(prompt_id)
        if record:
            status = record.get("status", {})
            messages = status.get("messages", [])
            if status.get("status_str") == "error" or any(
                    message[0] in {"execution_error", "execution_interrupted"} for message in messages):
                raise RuntimeError(f"ComfyUI job {prompt_id} failed: {messages}")
            images = record.get("outputs", {}).get(SAVE_IMAGE_NODE, {}).get("images", [])
            if images:
                output = images[0]
                response = requests.get(COMFY_SERVER + "/view", params={
                    "filename": output["filename"], "subfolder": output.get("subfolder", ""),
                    "type": output.get("type", "output")}, timeout=60)
                response.raise_for_status()
                # Decode/verify before publishing a file to the frontend.
                with Image.open(io.BytesIO(response.content)) as image:
                    result = io.BytesIO()
                    image.save(result, format="PNG")
                return result.getvalue()
            if status.get("completed"):
                raise RuntimeError(f"ComfyUI job {prompt_id} completed without an image from node {SAVE_IMAGE_NODE}")
        time.sleep(1)
    raise TimeoutError(f"ComfyUI job {prompt_id} did not finish within {timeout}s; it may still be queued")


def ensure_entry_scribble(entry_path, force=False):
    """Generate/reuse the image for a saved entry; retain text if generation fails."""
    print("Generating a scribble")
    entry_path = Path(entry_path)
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    chronicle = entry["chronicle"]
    digest = source_hash(chronicle)
    workflow_digest = hashlib.sha256(WORKFLOW_PATH.read_bytes()).hexdigest()
    key = source_hash(digest + workflow_digest)
    filename = f"{entry_path.stem}.scribble.{key[:16]}.png"
    image_path = entry_path.with_name(filename)
    metadata_path = entry_path.with_suffix(".scribble.json")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        metadata = {}
    if not isinstance(metadata, dict) or metadata.get("key") != key or force:
        metadata = {}
    image_prompt = metadata.get("prompt")

    if not isinstance(image_prompt, str) or not image_prompt.strip():
        print(f"Creating image prompt for {entry_path.stem}...", flush=True)
        image_prompt = RAG_main.generate_image_prompt(chronicle)
        if not image_prompt.strip():
            raise ValueError("No drawable scene returned for this entry")
        metadata = {"key": key, "source_hash": digest, "prompt": image_prompt,
                    "filename": filename, "workflow_hash": workflow_digest}
        write_json(metadata_path, metadata)
    if force or not image_path.is_file():
        print(f"Generating scribble for {entry_path.stem}...", flush=True)
        image_bytes = generate_scribble_image(image_prompt)
        temporary = image_path.with_suffix(".png.tmp")
        temporary.write_bytes(image_bytes)
        temporary.replace(image_path)
    # Do not attach an illustration to text replaced by another generation process.
    current = json.loads(entry_path.read_text(encoding="utf-8"))
    if source_hash(current["chronicle"]) != digest:
        raise RuntimeError("Diary changed during image generation; image was not attached")
    current["scribble"] = metadata
    write_json(entry_path, current)
    print(f"Scribble ready: {image_path}", flush=True)
    return image_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("entries", type=Path, help="Entry JSON or timeline folder")
    parser.add_argument("--force", action="store_true", help="Regenerate matching cached images and prompts")
    args = parser.parse_args()
    paths = sorted(args.entries.glob("day*.json")) if args.entries.is_dir() else [args.entries]
    failures = 0
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "chronicle" not in data or "day" not in data:
                continue
            ensure_entry_scribble(path, force=args.force)
        except (OSError, ValueError, KeyError, RuntimeError, requests.RequestException) as error:
            failures += 1
            print(f"Could not illustrate {path}: {error}", flush=True)
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
