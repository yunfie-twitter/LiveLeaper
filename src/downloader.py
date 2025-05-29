
from src import utils
import yt_dlp
import os

import subprocess

def detect_hwaccel():
    """簡易的にNVENCの有無を検出（必要に応じて他形式も追加）"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if "h264_nvenc" in result.stdout:
            return "h264_nvenc"
        elif "h264_qsv" in result.stdout:
            return "h264_qsv"
        elif "h264_vaapi" in result.stdout:
            return "h264_vaapi"
    except Exception as e:
        print(f"Hardware encoder detection failed: {e}")
    return None


def download_videos(urls, args):
    hw_encoder = detect_hwaccel()

    ydl_opts = {
        'outtmpl': os.path.join(args.output, '%(title)s.%(ext)s'),
        'noplaylist': True,
        'quiet': False,
        'merge_output_format': args.ext,  # ← 出力拡張子を明示する
    }


    if args.audio:
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': args.ext,
            'preferredquality': '192',
        }]
    else:
        ydl_opts['format'] = 'bestvideo+bestaudio/best'

        if args.ext == "mp4":
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }]
            # ハードウェアエンコードを使えるならffmpegに明示
            if hw_encoder:
                print(f"Using hardware encoder: {hw_encoder}")
                ydl_opts['postprocessor_args'] = [
                    '-c:v', hw_encoder
                ]
        elif args.ext == "webm":
            pass  # 変換なし
        else:
            print(f"Unsupported video format: {args.ext}")

    if args.info:
        ydl_opts['skip_download'] = True

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for url in urls:
            try:
                ydl.download([url])
            except Exception as e:
                print(f"Error downloading {url}: {e}")
