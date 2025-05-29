
import argparse
import os
import sys
from src import config, downloader, utils, language

def main():
    utils.setup_logging()

    if not os.path.exists(config.CONFIG_FILE):
        config.create_default_config(config.CONFIG_FILE)

    cfg = config.load_config(config.CONFIG_FILE)

    parser = argparse.ArgumentParser(description="LiveLeaper: YouTube downloader with GPU encoding and language support")
    parser.add_argument('urls', nargs='+', help='Target URL(s)')
    parser.add_argument('--audio', action='store_true', default=cfg.get('audio', 'false').lower() == 'true', help='Extract audio only')
    parser.add_argument('--ext', default=cfg.get('ext', 'mp4'), help='Output format extension (e.g., mp4, webm, mp3)')
    parser.add_argument('--output', default=cfg.get('output', 'downloads'), help='Output directory')
    parser.add_argument('--lang', default=cfg.get('lang', 'en'), help='Language file (default: en)')
    parser.add_argument('--info', action='store_true', help='Only fetch video info without downloading')

    args = parser.parse_args()
    os.makedirs(args.output, exist_ok=True)

    global L
    L = language.load_language(args.lang)

    downloader.download_videos(args.urls, args)
