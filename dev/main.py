import requests


def get_models():
    response = requests.get("http://localhost:11434/api/tags")
    response.raise_for_status()
    data = response.json()
    return data["models"]


def ollama_online():
    try:
        r = requests.get("http://localhost:11434", timeout=1)
        return r.ok
    except requests.RequestException:
        return False

def comfy_online():
    try:
        r = requests.get("http://127.0.0.1:8188", timeout=1)
        return r.ok
    except requests.RequestException:
        return False

def receiver_online():
    try:
        r = requests.get("http://127.0.0.1:8765/events", timeout=1) # This doesn't work
        return r.ok
    except requests.RequestException:
        return False
    

print(ollama_online())
print(comfy_online())
print(receiver_online())