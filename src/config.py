
import os

CONFIG_FILE = "config.txt"

def load_config(path):
    config = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if '=' in line:
                    key, val = line.strip().split('=', 1)
                    config[key] = val
    return config

def create_default_config(path):
    with open(path, 'w', encoding="utf-8") as f:
        f.write("audio=false\next=mp4\noutput=downloads\nlang=en\n")
