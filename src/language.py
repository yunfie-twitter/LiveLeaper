
import os

def load_language(lang_code):
    messages = {
        "start": "Starting download...",
        "done": "Download completed."
    }
    lang_path = os.path.join("lang", f"{lang_code}.txt")
    if os.path.exists(lang_path):
        with open(lang_path, encoding="utf-8") as f:
            for line in f:
                if '=' in line:
                    key, val = line.strip().split('=', 1)
                    messages[key] = val
    return messages
