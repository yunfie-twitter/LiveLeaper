from src import utils
import yt_dlp
import os
import subprocess
import glob

def detect_hwaccel():
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
    }

    # 音声のみ
    if args.audio:
        ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio/best'  # 優先的にm4aに
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': args.ext,
            'preferredquality': '192',
        }]
    else:
        # 動画 + 音声（mp4優先）
        ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'

        if args.ext == "mp4":
            ydl_opts['merge_output_format'] = "mp4"
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }]
            if hw_encoder:
                print(f"Using hardware encoder: {hw_encoder}")
                ydl_opts['postprocessor_args'] = [
                    '-c:v', hw_encoder
                ]
        elif args.ext == "webm":
            ydl_opts['merge_output_format'] = "webm"
        else:
            print(f"Unsupported video format: {args.ext}")

    if args.info:
        ydl_opts['skip_download'] = True

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for url in urls:
            try:
                ydl.download([url])

                # ダウンロード後処理（temp.mp3 → mp3、不要ファイル削除）
                if args.audio and args.ext == 'mp3':
                    # .temp.mp3 を探してリネーム
                    for temp_file in glob.glob(os.path.join(args.output, '*.temp.mp3')):
                        final_file = temp_file.replace('.temp.mp3', '.mp3')
                        os.rename(temp_file, final_file)
                        print(f"Renamed {temp_file} → {final_file}")

                    # .webm, .mp4 など不要ファイルを削除
                    for ext in ['*.webm', '*.mp4']:
                        for f in glob.glob(os.path.join(args.output, ext)):
                            if not f.endswith('.mp3'):
                                os.remove(f)
                                print(f"Deleted: {f}")

            except Exception as e:
                print(f"Error downloading {url}: {e}")
