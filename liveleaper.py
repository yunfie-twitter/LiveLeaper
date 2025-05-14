import sys
import os
import subprocess
from urllib.parse import urlparse, parse_qs
import traceback # エラー詳細表示用

# --- PyQt5 または PyQt6 を選択 ---
try:
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QLabel, QLineEdit, QPushButton,
        QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox,
        QProgressBar, QComboBox, QSizePolicy, QSplashScreen, QDesktopWidget
    )
    from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl, QTimer
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    from PyQt5.QtGui import QPixmap
    print("PyQt5 を使用します。")
except ImportError:
    try:
        from PyQt6.QtWidgets import (
            QApplication, QWidget, QLabel, QLineEdit, QPushButton,
            QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox,
            QProgressBar, QComboBox, QSizePolicy, QSplashScreen
        )
        # QDesktopWidget は PyQt6 では非推奨 -> QScreen を使用
        from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QTimer
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtGui import QPixmap, QScreen
        print("PyQt6 を使用します。")
    except ImportError:
        print("エラー: PyQt5 または PyQt6 が見つかりません。")
        print("インストールしてください: pip install PyQt5 PyQtWebEngine")
        print("または: pip install PyQt6 PyQt6-WebEngine")
        sys.exit(1)
# --- PyQt 選択ここまで ---

import yt_dlp
# from pytube import YouTube # 未使用のためコメントアウト

# --- ハードウェアエンコード検出関数 ---
def detect_hw_encoder(ffmpeg_path="./ffmpeg.exe"):
    """利用可能なハードウェアエンコーダーを検出する (H.264優先)"""
    if not os.path.exists(ffmpeg_path):
        print(f"エラー: ffmpegが見つかりません: {ffmpeg_path}", file=sys.stderr)
        return None, "ffmpegが見つかりません。" # エンコーダー名とエラーメッセージを返す

    try:
        process = subprocess.run(
            [ffmpeg_path, "-encoders"],
            capture_output=True, text=True, encoding='utf-8', errors='ignore', check=False
        )

        if process.returncode != 0 and "Unknown argument" not in process.stderr:
             error_msg = f"ffmpeg -encoders 失敗 (コード:{process.returncode})\n{process.stderr}"
             print(f"エラー: {error_msg}", file=sys.stderr)
             return None, error_msg

        encoders = process.stdout.lower() # 小文字で比較

        # 一般的なH.264ハードウェアエンコーダーを確認 (優先度順)
        if 'h264_nvenc' in encoders:
            print("検出: NVIDIA NVENC (h264_nvenc)")
            return 'h264_nvenc', None
        if 'h264_qsv' in encoders:
            print("検出: Intel QSV (h264_qsv)")
            return 'h264_qsv', None
        if 'h264_amf' in encoders:
            print("検出: AMD AMF (h264_amf)")
            return 'h264_amf', None
        # 他のエンコーダー (HEVC等) も必要ならここに追加
        # if 'hevc_nvenc' in encoders: return 'hevc_nvenc', None
        # ...

    except FileNotFoundError:
        error_msg = f"ffmpegが見つかりません: {ffmpeg_path}"
        print(f"エラー: {error_msg}", file=sys.stderr)
        return None, error_msg
    except Exception as e:
        error_msg = f"HWエンコーダー検出中に予期せぬエラー: {e}"
        print(f"エラー: {error_msg}\n{traceback.format_exc()}", file=sys.stderr)
        return None, error_msg

    print("利用可能なH.264ハードウェアエンコーダーが見つかりませんでした。")
    return None, "利用可能なH.264 HWエンコーダーが見つかりません。"

# --- URL正規化関数 ---
def clean_url(url):
    """入力されたURLをyt-dlpが扱いやすい形式に試みる"""
    url = url.strip()
    # googleusercontent.com の特殊形式対応 (例)
    if "googleusercontent.com/youtube.com/" in url:
        # より堅牢なID抽出が必要な場合あり
        parts = url.split('/')
        if len(parts) > 2:
            # ID部分らしきものを取得して通常のYouTube URL形式に変換を試みる
            video_id = parts[-1].split('?')[0] # ? 以降を除去
            # IDのプレフィックス (例: '0', '1') を除去する処理が必要なら追加
            if video_id.startswith(('0', '1')) and len(video_id) > 5: # 仮のID長チェック
                 video_id = video_id[1:]
            return f"https://www.youtube.com/watch?v={video_id}"

    # shorts URL -> watch URL
    if "/shorts/" in url:
        video_id = url.split("/shorts/")[-1].split("?")[0]
        return f"https://www.youtube.com/watch?v={video_id}"

    # 通常のURLから不要なパラメータを除去 (v= だけ残す)
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    vid = query_params.get("v")
    if vid and isinstance(vid, list):
        # netloc が youtube.com かどうかなどもチェックするとより良い
        return f"https://{parsed.netloc}/watch?v={vid[0]}"

    # 上記以外はそのまま返す
    return url

# --- 修正済み Downloader クラス ---
class Downloader(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str) # 成功時は最終的なファイルパスを返す
    error = pyqtSignal(str)

    def __init__(self, url, save_path, resolution, fmt, use_hw_encode=False, hw_encoder=None, ffmpeg_path="./ffmpeg.exe"):
        super().__init__()
        self.url = url
        self.save_path = save_path
        # resolution は "1080", "720" または "" (最高画質)
        self.resolution = resolution
        self.fmt = fmt # 'mp4', 'mp3', 'no_conversion'
        self.use_hw_encode = use_hw_encode and fmt == "mp4" # HWエンコードはMP4時のみ
        self.hw_encoder = hw_encoder if self.use_hw_encode else None
        self._ffmpeg_path = ffmpeg_path

        self._downloaded_filepath = None # yt-dlpが実際に保存したファイルパス
        self._final_output_path = None   # 処理後の最終的なファイルパス

        # 安全なファイル名を生成する関数
        def sanitize_filename(name):
            # Windows/Linux/macOSで使えない文字を除去または置換
            invalid_chars = '<>:"/\\|?*'
            for char in invalid_chars:
                name = name.replace(char, '_')
            # 先頭・末尾の空白やピリオドを除去
            name = name.strip('. ')
            # 長すぎるファイル名を切り詰める (OS制限考慮)
            max_len = 200 # 安全マージン込み
            if len(name.encode('utf-8')) > max_len: # バイト数でチェック
                 # 簡単な切り詰め（より良い方法は文字単位で確認）
                 name = name[:max_len // 2] + "..."
            return name if name else "downloaded_video" # 空になった場合のデフォルト名

        # --- runメソッド内で使う変数を先に初期化 ---
        self._safe_title = "downloaded_video" # デフォルトタイトル
        self._base_filename = os.path.join(self.save_path, self._safe_title)

        # 先にyt-dlpで情報を取得してタイトルを確定（runメソッド冒頭に移動）
        try:
            info_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True, 'ffmpeg_location': self._ffmpeg_path}
            with yt_dlp.YoutubeDL(info_opts) as ydl_info:
                info = ydl_info.extract_info(self.url, download=False)
                title = info.get('title', 'video')
                self._safe_title = sanitize_filename(title)
                self._base_filename = os.path.join(self.save_path, self._safe_title)
                print(f"動画タイトル取得: {title} -> 安全なファイル名: {self._safe_title}")
        except Exception as e:
             print(f"警告: 動画情報の事前取得に失敗しました: {e}")
             # タイトルが取得できなくても処理は続行するが、ファイル名がデフォルトになる

    def run(self):
        try:
            # --- yt-dlp ダウンロードオプション設定 ---
            ydl_opts = {
                'ffmpeg_location': self._ffmpeg_path,
                'progress_hooks': [self.hook],
                'quiet': True,
                'no_warnings': True,
                # 中間ファイル名 (衝突回避のためプロセスIDなどを追加するのも手)
                'outtmpl': f'{self._base_filename}_temp_%(id)s.%(ext)s',
                'format_sort': ['+res:1080', '+res:720', '+res:480', '+res', 'ext:mp4:m4a', 'vcodec:h264', 'acodec:m4a'], # 解像度, MP4, H.264を優先
                'merge_output_format': 'mp4', # 可能なら結合時にMP4にする
            }

            # --- フォーマットごとの設定 ---
            final_extension = "mp4" # デフォルト

            if self.fmt == "mp3":
                final_extension = "mp3"
                self._final_output_path = f'{self._base_filename}.mp3'
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192', # yt-dlpでは文字列で指定
                }]
                # MP3の場合、outtmplを最終パスに直接指定できる
                ydl_opts['outtmpl'] = self._final_output_path
                # format_sortは音声のみなので不要か、専用のものを設定
                ydl_opts['format_sort'] = ['abr', 'ext:m4a'] # ビットレート優先

            elif self.fmt == "mp4":
                final_extension = "mp4"
                self._final_output_path = f'{self._base_filename}.mp4'
                # フォーマット指定 (解像度を考慮)
                format_specifier = 'bestvideo'
                if self.resolution.isdigit():
                    format_specifier += f'[height<={self.resolution}]' # 指定解像度以下
                # bestaudio を組み合わせる
                # bestvideo* は webm も含みうるため、変換が必要になる可能性がある
                # merge_output_format='mp4' で MP4 へのマージを試みる
                ydl_opts['format'] = f'{format_specifier}+bestaudio/best'

            elif self.fmt == "no_conversion":
                # yt-dlpが最適と判断した形式でダウンロード
                ydl_opts['format'] = 'bestvideo+bestaudio/best'
                # 最終的なファイル名は hook で取得する or 変換しないので元の拡張子を使う
                # final_extension は不定

            else:
                 self.error.emit(f"未対応のフォーマット形式です: {self.fmt}")
                 return

            # --- ダウンロード実行 ---
            print(f"yt-dlp オプション: {ydl_opts}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # download=True で実際にダウンロード
                download_result = ydl.download([self.url])
                # 戻り値は通常0だが、エラー時は非0
                if download_result != 0:
                     print(f"警告: yt-dlp.download が非0のコード ({download_result}) を返しました。")
                     # エラー処理が必要な場合がある

            # --- ダウンロードされたファイルの特定 ---
            if not self._downloaded_filepath or not os.path.exists(self._downloaded_filepath):
                print("警告: hookでダウンロードファイルパスを取得できなかったか、ファイルが存在しません。ファイル検索を試みます...")
                downloaded_files = []
                # 検索パターンをより具体的に (IDも考慮に入れるなど)
                # outtmplの %(id)s 部分が実際のIDに置き換わる
                # info取得が成功していれば info['id'] が使えるが、失敗している可能性もある
                expected_prefix = f"{self._safe_title}_temp_"
                try:
                    for f in os.listdir(self.save_path):
                        if f.startswith(expected_prefix):
                            downloaded_files.append(os.path.join(self.save_path, f))
                except FileNotFoundError:
                    self.error.emit(f"保存先ディレクトリが見つかりません: {self.save_path}")
                    return
                except Exception as e:
                    self.error.emit(f"ダウンロードファイル検索中にエラー: {e}")
                    return

                if not downloaded_files:
                    # MP3の場合は最終ファイル名で存在するか再確認
                    if self.fmt == "mp3" and self._final_output_path and os.path.exists(self._final_output_path):
                        self._downloaded_filepath = self._final_output_path
                        print(f"MP3ファイルを直接確認: {self._downloaded_filepath}")
                    else:
                        self.error.emit(f"ダウンロードされたファイルが見つかりません (検索パターン: {expected_prefix}*)")
                        return
                elif len(downloaded_files) == 1:
                    self._downloaded_filepath = downloaded_files[0]
                    print(f"フォールバック検索で見つかったファイル: {self._downloaded_filepath}")
                else:
                    # 複数見つかった場合、一番新しいファイルを選択する試み
                    try:
                        latest_file = max(downloaded_files, key=os.path.getmtime)
                        self._downloaded_filepath = latest_file
                        print(f"複数ファイルが見つかりましたが、最新のものを選択: {self._downloaded_filepath}")
                    except Exception as e:
                        self.error.emit(f"複数ファイルが見つかり、最新ファイルの特定に失敗: {e}")
                        return

            if not self._downloaded_filepath or not os.path.exists(self._downloaded_filepath):
                self.error.emit("ダウンロードされたファイルの特定に最終的に失敗しました。")
                return

            current_file = self._downloaded_filepath

            # --- 無変換の場合の処理 ---
            if self.fmt == "no_conversion":
                # 拡張子を維持した最終ファイル名にリネーム
                original_ext = os.path.splitext(current_file)[1]
                # _temp_...部分を除去
                final_name_base = self._base_filename # 事前取得したタイトルベース
                self._final_output_path = f"{final_name_base}{original_ext}"

                if current_file != self._final_output_path:
                    try:
                        if os.path.exists(self._final_output_path):
                            print(f"警告: 既存ファイル {self._final_output_path} を上書きします。")
                            os.remove(self._final_output_path)
                        os.rename(current_file, self._final_output_path)
                        print(f"無変換: ファイル名を変更 {current_file} -> {self._final_output_path}")
                        current_file = self._final_output_path
                    except OSError as e:
                        self.error.emit(f"無変換: ファイル名変更エラー {e}")
                        return
                else:
                    print(f"無変換: ファイル名は既に最終形式 {current_file}")

                self.finished.emit(current_file)
                return

            # --- MP4への変換とリサイズ (fmt='mp4' の場合) ---
            if self.fmt == "mp4":
                # yt-dlpが既にMP4でマージしてくれているか確認
                needs_conversion = not current_file.lower().endswith(".mp4")
                # 解像度変更が必要か確認 (指定があり、かつ変換が必要な場合 or 既にMP4の場合)
                needs_resizing = self.resolution.isdigit()

                ffmpeg_processed = False # FFmpeg処理が行われたか

                # ステップ1: 必要ならMP4に変換
                if needs_conversion:
                    ffmpeg_processed = True
                    print(f"MP4への変換が必要: {current_file}")
                    # 中間ファイル (衝突回避のためプロセスIDなど含めると尚良い)
                    mp4_temp_file = f"{self._base_filename}_conv_temp.mp4"
                    target_file = mp4_temp_file

                    cmd = [self._ffmpeg_path, "-y", "-i", current_file]

                    if self.use_hw_encode and self.hw_encoder:
                        print(f"ハードウェアエンコード ({self.hw_encoder}) でMP4変換")
                        cmd.extend(["-c:v", self.hw_encoder])
                        # HWオプション例 (品質指定: cq/qp/global_quality など)
                        if "nvenc" in self.hw_encoder: cmd.extend(["-preset", "p5", "-cq", "23"])
                        elif "qsv" in self.hw_encoder: cmd.extend(["-preset", "medium", "-global_quality", "23"])
                        elif "amf" in self.hw_encoder: cmd.extend(["-quality", "balanced", "-rc", "cqp", "-qp_p", "23", "-qp_i", "23"])
                        else: cmd.extend(["-preset", "fast"])
                        cmd.extend(["-c:a", "aac", "-b:a", "192k"]) # 音声再エンコード
                    else:
                        print("CPUエンコード (libx264) でMP4変換")
                        cmd.extend(["-c:v", "libx264", "-crf", "23", "-preset", "fast"])
                        cmd.extend(["-c:a", "aac", "-b:a", "192k"]) # 音声再エンコード
                    cmd.append(target_file)

                    try:
                        print(f"実行(変換): {' '.join(cmd)}")
                        process = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                        print(f"FFmpeg(変換)完了: {target_file}\nstderr:\n{process.stderr[-500:]}") # stderr末尾表示
                        if os.path.exists(target_file):
                            try:
                                os.remove(current_file)
                            except OSError as e: print(f"警告: 元ファイル削除失敗 {current_file}: {e}")
                            current_file = target_file
                        else:
                            raise RuntimeError(f"変換後ファイルが見つかりません: {target_file}")
                    except subprocess.CalledProcessError as e:
                        self.error.emit(f"FFmpeg(MP4変換)失敗:\n{e.stderr}")
                        return
                    except Exception as e:
                        self.error.emit(f"MP4変換中に予期せぬエラー: {e}\n{traceback.format_exc()}")
                        return

                # ステップ2: 解像度変更が必要な場合 (current_fileはMP4のはず)
                # かつ、指定された解像度と異なる可能性がある場合（厳密なチェックはffprobeが必要）
                # ここでは指定があれば常にリサイズを試みることにする
                if needs_resizing:
                    ffmpeg_processed = True
                    target_height = self.resolution
                    print(f"解像度変更を実行: {current_file} -> 高さ {target_height}p")
                    resized_temp_file = f"{self._base_filename}_resized_temp.mp4"
                    resized_target_file = resized_temp_file

                    cmd = [self._ffmpeg_path, "-y", "-i", current_file]
                    cmd.extend(["-vf", f"scale=-2:{target_height}"])

                    if self.use_hw_encode and self.hw_encoder:
                        print(f"ハードウェアエンコード ({self.hw_encoder}) でリサイズ")
                        cmd.extend(["-c:v", self.hw_encoder])
                        if "nvenc" in self.hw_encoder: cmd.extend(["-preset", "p5", "-cq", "23"])
                        elif "qsv" in self.hw_encoder: cmd.extend(["-preset", "medium", "-global_quality", "23"])
                        elif "amf" in self.hw_encoder: cmd.extend(["-quality", "balanced", "-rc", "cqp", "-qp_p", "23", "-qp_i", "23"])
                        else: cmd.extend(["-preset", "fast"])
                        cmd.extend(["-c:a", "copy"]) # 音声コピー
                    else:
                        print("CPUエンコード (libx264) でリサイズ")
                        cmd.extend(["-c:v", "libx264", "-crf", "23", "-preset", "fast"])
                        cmd.extend(["-c:a", "copy"]) # 音声コピー
                    cmd.append(resized_target_file)

                    try:
                        print(f"実行(リサイズ): {' '.join(cmd)}")
                        process = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                        print(f"FFmpeg(リサイズ)完了: {resized_target_file}\nstderr:\n{process.stderr[-500:]}")
                        if os.path.exists(resized_target_file):
                            try:
                                os.remove(current_file)
                            except OSError as e: print(f"警告: 元ファイル削除失敗 {current_file}: {e}")
                            current_file = resized_target_file
                        else:
                            raise RuntimeError(f"リサイズ後ファイルが見つかりません: {resized_target_file}")
                    except subprocess.CalledProcessError as e:
                        self.error.emit(f"FFmpeg(解像度変更)失敗:\n{e.stderr}")
                        return
                    except Exception as e:
                        self.error.emit(f"解像度変更中に予期せぬエラー: {e}\n{traceback.format_exc()}")
                        return

                # ステップ3: 最終ファイル名へのリネーム (FFmpeg処理が行われた場合 or 元々MP4だが一時ファイル名だった場合)
                if ffmpeg_processed or current_file != self._final_output_path:
                    try:
                        if os.path.exists(self._final_output_path):
                            print(f"警告: 既存ファイル {self._final_output_path} を上書きします。")
                            os.remove(self._final_output_path)
                        os.rename(current_file, self._final_output_path)
                        print(f"最終ファイル名に変更: {current_file} -> {self._final_output_path}")
                        current_file = self._final_output_path
                    except OSError as e:
                        self.error.emit(f"最終ファイル名への変更に失敗: {e}")
                        return

            # --- 完了処理 ---
            # 最終的なファイルパスが存在するか確認
            final_path_to_emit = None
            if self._final_output_path and os.path.exists(self._final_output_path):
                 final_path_to_emit = self._final_output_path
            elif current_file and os.path.exists(current_file): # MP3などでfinal_output_pathを使わない場合
                 final_path_to_emit = current_file

            if final_path_to_emit:
                 print(f"処理完了: {final_path_to_emit}")
                 self.finished.emit(final_path_to_emit)
            else:
                 # 予期せぬケース: 最終ファイルが見つからない
                 self.error.emit("処理は完了しましたが、最終的な出力ファイルが見つかりませんでした。")


        except yt_dlp.utils.DownloadError as e:
             # yt-dlpのダウンロード段階でのエラー
             self.error.emit(f"ダウンロードエラー: {e}")
        except FileNotFoundError as e:
             # ffmpegが見つからない場合など
             if self._ffmpeg_path in str(e):
                 self.error.emit(f"エラー: ffmpegが見つかりません ({self._ffmpeg_path})。パスを確認してください。")
             else:
                 self.error.emit(f"ファイル関連エラー: {e}")
        except Exception as e:
            # その他の予期せぬエラー
            error_details = f"予期せぬエラーが発生しました:\n{traceback.format_exc()}"
            print(error_details, file=sys.stderr)
            self.error.emit(error_details)

    def hook(self, d):
        """yt-dlpからの進捗情報を受け取るコールバック"""
        # print(f"hook status: {d.get('status')}, filename: {d.get('filename')}") # デバッグ用
        if d['status'] == 'finished':
            # ダウンロード/マージ完了時にファイルパスを取得
            # 'info_dict' 内の '_filename' の方が確実な場合が多い
            filename = d.get('info_dict', {}).get('_filename') or d.get('filename')
            if filename and os.path.exists(filename):
                 self._downloaded_filepath = filename
                 print(f"Hook: '{d['status']}' -> ファイルパス取得: {self._downloaded_filepath}")
                 # ここで100%をemitすると後続処理がある場合に早すぎる
                 # self.progress.emit(100)
            else:
                 print(f"Hook: '{d['status']}' -> ファイルパス取得失敗 or ファイル不在 (filename={filename})")
                 # ファイルパスが取れなくても進捗は100にしておく
                 self.progress.emit(100)

        elif d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded = d.get('downloaded_bytes')
            if total and downloaded is not None:
                 # 完了処理があるので99%を上限とする
                 percent = min(int(downloaded * 100 / total), 99)
                 self.progress.emit(percent)
        # 'postprocessing' ステータスなども利用可能

# --- ここから CustomTitleBar クラスを差し替え ---
class CustomTitleBar(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.setFixedHeight(30)
        self.setStyleSheet("background-color: #000000;") # 指定されたスタイル
        self.offset = None

        # 指定された QLabel (タイトル部分は空白)
        self.title_label = QLabel("                                                                                                                                                                                                                                                                ")
        self.title_label.setStyleSheet("color: #CCCCCC; font-size: 14px; font-weight: bold; margin-left: 0px;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self.title_label)
        layout.addStretch()

        # 指定された最小化ボタン (ホバー時のスタイルを追加)
        self.min_btn = QPushButton("─")
        self.min_btn.setFixedSize(40, 30)
        self.min_btn.setStyleSheet("""
            QPushButton {
                color: #CCCCCC;
                background-color: #000000;
                border: none;
            }
            QPushButton:hover {
                background-color: #222222; /* 超薄い白に近いグレー */
                color: white;
            }
        """)
        self.min_btn.clicked.connect(self.parent.showMinimized)

        # 指定された閉じるボタン
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(40, 30)
        self.close_btn.setStyleSheet("""
            QPushButton {
                color: #CCCCCC;
                background-color: #000000;
                border: none;
            }
            QPushButton:hover {
                background-color: #FF3333;
                color: white;
            }
        """)
        self.close_btn.clicked.connect(self.parent.close)

        layout.addWidget(self.min_btn)
        layout.addWidget(self.close_btn)

    def mousePressEvent(self, event):
        # PyQt5/6 互換性対応
        global_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()

        if event.button() == Qt.LeftButton:
            # ボタン上をクリックした場合も移動が開始される (元の仕様通り)
            self.offset = global_pos - self.parent.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        # PyQt5/6 互換性対応
        global_pos = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()

        if event.buttons() == Qt.LeftButton and self.offset:
            self.parent.move(global_pos - self.offset)

    def mouseReleaseEvent(self, event):
        self.offset = None

# --- ローディングドットクラス ---
class LoadingDots(QWidget):
    def __init__(self, color="white"): # 色を指定可能に
        super().__init__()
        self.dots = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.current = 0
        self.color = color
        self.setStyleSheet("background-color: transparent;")

        layout = QHBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(6) # 少し間隔を空ける
        layout.setContentsMargins(0, 0, 0, 0)

        for i in range(4):
            dot = QLabel("●")
            dot.setStyleSheet(f"color: gray; font-size: 18px;")
            dot.setAlignment(Qt.AlignCenter)
            self.dots.append(dot)
            layout.addWidget(dot)

        self.adjustSize()
        self.timer.start(300)

    def animate(self):
        for i, dot in enumerate(self.dots):
            if i == self.current:
                dot.setStyleSheet(f"color: {self.color}; font-size: 18px;")
            else:
                dot.setStyleSheet(f"color: gray; font-size: 18px;")
        self.current = (self.current + 1) % len(self.dots)

    def stop(self):
         """タイマーを停止するメソッド"""
         self.timer.stop()
         self.hide() # 非表示にする

    def start(self):
         """タイマーを開始して表示するメソッド"""
         self.current = 0
         self.animate() # 初期状態表示
         self.timer.start(1200)
         self.show()

# --- メインアプリケーションクラス ---
class App(QWidget):
    def __init__(self):
        super().__init__()
        # ffmpegのパス (設定などで変更可能にするのが望ましい)
        self.ffmpeg_path = self.find_ffmpeg() # ffmpegを探す

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("LiveLeaper")
        self.current_download_path = None # ダウンロード中のファイルパス

        self.show_splash_screen()

    def find_ffmpeg(self):
        """環境変数PATHまたはカレントディレクトリからffmpegを探す"""
        ffmpeg_exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        # カレントディレクトリ
        if os.path.exists(f"./{ffmpeg_exe}"):
            print(f"ffmpegをカレントディレクトリで発見: ./{ffmpeg_exe}")
            return f"./{ffmpeg_exe}"
        # 環境変数PATH
        paths = os.environ.get("PATH", "").split(os.pathsep)
        for path in paths:
            filepath = os.path.join(path, ffmpeg_exe)
            if os.path.exists(filepath) and os.access(filepath, os.X_OK):
                print(f"ffmpegをPATHで発見: {filepath}")
                return filepath
        print("警告: ffmpegが見つかりませんでした。カレントディレクトリまたはPATHを確認してください。")
        return f"./{ffmpeg_exe}" # 見つからなくてもデフォルトパスを返す

    def get_screen_geometry(self):
        """PyQt5/6互換のスクリーンジオメトリ取得"""
        if 'PyQt6' in sys.modules:
             screen = QApplication.primaryScreen()
             if screen:
                  return screen.availableGeometry()
        elif 'PyQt5' in sys.modules:
             return QDesktopWidget().availableGeometry()
        return None # 取得失敗

    def center_window(self, window):
        """ウィンドウを画面中央に配置"""
        screen_geometry = self.get_screen_geometry()
        if screen_geometry:
            x = (screen_geometry.width() - window.width()) // 2
            y = (screen_geometry.height() - window.height()) // 2
            window.move(screen_geometry.left() + x, screen_geometry.top() + y) # マルチモニタ考慮

    def show_splash_screen(self):
        try:
            pixmap = QPixmap("LiveLeaper.png") # ロゴファイル名
            if pixmap.isNull():
                 print("警告: スプラッシュ画像 'LiveLeaper.png' が読み込めません。")
                 pixmap = QPixmap(300, 150)
                 pixmap.fill(Qt.transparent)

            self.splash = QSplashScreen(pixmap, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground, False)
            self.splash.setAttribute(Qt.WA_TranslucentBackground)
            self.center_window(self.splash) # 中央配置

            # ローディングドット
            self.loading_dots_splash = LoadingDots(color="#CCCCCC") # スプラッシュ用
            dots_layout = QVBoxLayout(self.splash)
            dots_layout.addStretch()
            dots_layout.addWidget(self.loading_dots_splash, 0, Qt.AlignHCenter)
            dots_layout.addSpacing(25) # 下部マージン

            self.splash.show()
            QTimer.singleShot(2500, self.show_main_window) # 表示時間

        except Exception as e:
            print(f"スプラッシュスクリーン表示中にエラー: {e}\n{traceback.format_exc()}")
            self.show_main_window() # エラーでもメイン表示試行

    def show_main_window(self):
        if hasattr(self, 'splash'):
            self.splash.close()
        if hasattr(self, 'loading_dots_splash'):
             self.loading_dots_splash.stop()

        try:
            self.setAttribute(Qt.WA_TranslucentBackground, False)
            self.setWindowFlags(Qt.FramelessWindowHint)
            self.setStyleSheet("background-color: #282828; color: #E0E0E0;") # 全体の基本スタイル

            self.init_ui()
            self.setMinimumSize(650, 550) # 少し大きく
            self.resize(700, 600) # デフォルトサイズ
            self.center_window(self) # 中央表示
            self.show()
        except Exception as e:
             print(f"メインウィンドウ初期化・表示中にエラー: {e}\n{traceback.format_exc()}")
             QMessageBox.critical(None, "起動エラー", f"アプリケーションの起動に失敗しました:\n{e}")
             sys.exit(1)

    def init_ui(self):
        # タイトルバーは黒背景のまま
        self.titlebar = CustomTitleBar(self)

        # --- 全体のレイアウト構成を変更 ---
        # Appウィジェット自身には main_layout のみ設定
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.titlebar) # まずタイトルバーを追加

        # --- タイトルバー以外のコンテンツを配置する白い背景のウィジェットを作成 ---
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background-color: #FFFFFF; color: #000000;") # このウィジェットの背景を白に

        # --- コンテンツ用のレイアウトを content_widget に設定 ---
        content_layout = QVBoxLayout(self.content_widget) # レイアウトの親を content_widget に
        content_layout.setContentsMargins(20, 15, 20, 15) # マージン
        content_layout.setSpacing(12)                   # スペース

        # --- UI要素 スタイル定義 (白背景用に変更済み) ---
        # (input_style, combo_style, button_style, secondary_button_style, label_style は前回のコードと同じ)
        input_style = """
            QLineEdit, QComboBox { padding: 6px; border: 1px solid #CCCCCC; border-radius: 4px; color: #000000; background-color: #FFFFFF; }
            QComboBox::drop-down { border: none; } QComboBox::down-arrow { image: url(none); }
            QLineEdit:focus, QComboBox:focus { border: 1px solid #0078D7; }
            QLineEdit:disabled, QComboBox:disabled { color: #AAAAAA; background-color: #F5F5F5; border: 1px solid #E0E0E0; }
        """
        button_style = """
            QPushButton { padding: 8px 15px; border: 1px solid #ADADAD; border-radius: 4px; color: #000000; background-color: #F0F0F0; font-weight: bold; }
            QPushButton:hover { background-color: #E5F1FB; border: 1px solid #0078D7; }
            QPushButton:pressed { background-color: #CCE4F7; border: 1px solid #005EA6; }
            QPushButton:disabled { color: #A0A0A0; background-color: #F5F5F5; border: 1px solid #DCDCDC; }
        """
        secondary_button_style = button_style.replace("#F0F0F0", "#FFFFFF").replace("font-weight: bold;", "")
        label_style = "color: #555555; font-size: 12px; margin-bottom: 2px;"

        # --- UI要素 作成 (前回のコードと同じ) ---
        self.url_label = QLabel("動画 URL:")
        self.url_label.setStyleSheet(label_style)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("YouTube動画のURLを入力してください")
        self.url_input.setStyleSheet(input_style)
        self.url_input.textChanged.connect(self.clear_webview)

        self.format_label = QLabel("保存形式:")
        self.format_label.setStyleSheet(label_style)
        self.format_box = QComboBox()
        self.format_box.addItems(["mp4", "mp3", "no_conversion"])
        self.format_box.setStyleSheet(input_style)
        self.format_box.currentTextChanged.connect(self.update_quality_box_visibility)

        self.quality_label = QLabel("画質 (MP4):")
        self.quality_label.setStyleSheet(label_style)
        self.quality_box = QComboBox()
        self.quality_box.addItems(["最高画質", "1080", "720", "480", "360", "144"])
        self.quality_box.setStyleSheet(input_style)

        self.save_path_label = QLabel("保存先:")
        self.save_path_label.setStyleSheet(label_style)
        self.save_path_button = QPushButton("フォルダを選択...")
        self.save_path_button.setStyleSheet(secondary_button_style)
        self.save_path_button.clicked.connect(self.select_save_path)
        self.save_path_display = QLabel("選択されていません")
        self.save_path_display.setStyleSheet("color: #666666; font-size: 11px; margin-left: 5px;")
        self.current_save_path = os.path.join(os.path.expanduser("~"), "Downloads")
        self.update_save_path_display()

        self.btn = QPushButton("📥 ダウンロード開始")
        self.btn.setStyleSheet(button_style)
        self.btn.clicked.connect(self.confirm_and_start_download)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100); self.progress.setValue(0); self.progress.setTextVisible(False); self.progress.setFixedHeight(6)
        self.progress.setStyleSheet("""
            QProgressBar { border: 1px solid #CCCCCC; border-radius: 3px; background-color: #E6E6E6; height: 6px; }
            QProgressBar::chunk { background-color: #0078D7; border-radius: 3px; }
        """)

        self.webview = QWebEngineView(); self.webview.setMinimumHeight(200); self.webview.setContextMenuPolicy(Qt.NoContextMenu); self.webview.setUrl(QUrl("about:blank"))
        self.status_label = QLabel("準備完了"); self.status_label.setStyleSheet("color: #666666; font-size: 11px; margin-top: 5px;"); self.status_label.setAlignment(Qt.AlignRight)

        # --- content_layout にウィジェットを追加 (この部分は変更なし) ---
        content_layout.addWidget(self.url_label)
        content_layout.addWidget(self.url_input)

        options_layout1 = QHBoxLayout(); options_layout1.setSpacing(10)
        format_group = QVBoxLayout(); format_group.setSpacing(2)
        format_group.addWidget(self.format_label); format_group.addWidget(self.format_box)
        options_layout1.addLayout(format_group, 1)

        self.quality_group_widget = QWidget()
        quality_group_layout = QVBoxLayout(self.quality_group_widget); quality_group_layout.setSpacing(2); quality_group_layout.setContentsMargins(0,0,0,0)
        quality_group_layout.addWidget(self.quality_label); quality_group_layout.addWidget(self.quality_box)
        options_layout1.addWidget(self.quality_group_widget, 1)
        content_layout.addLayout(options_layout1)
        self.update_quality_box_visibility(self.format_box.currentText())

        save_path_layout = QHBoxLayout(); save_path_layout.setSpacing(8)
        save_path_group = QVBoxLayout(); save_path_group.setSpacing(2)
        save_path_group.addWidget(self.save_path_label)
        save_path_layout_inner = QHBoxLayout()
        save_path_layout_inner.addWidget(self.save_path_button)
        save_path_layout_inner.addWidget(self.save_path_display, 1)
        save_path_group.addLayout(save_path_layout_inner)
        save_path_layout.addLayout(save_path_group)
        content_layout.addLayout(save_path_layout)

        content_layout.addSpacing(10)
        content_layout.addWidget(self.btn, 0, Qt.AlignRight)
        content_layout.addSpacing(15)

        content_layout.addWidget(self.webview, 1)
        content_layout.addWidget(self.progress)
        content_layout.addWidget(self.status_label)

        # --- 最後に content_widget を main_layout に追加 ---
        main_layout.addWidget(self.content_widget, 1) # stretch=1 で縦に伸びるように

    def clear_webview(self):
        """URL入力が変更されたらWebviewをクリア"""
        self.webview.setUrl(QUrl("about:blank"))

    def update_quality_box_visibility(self, text):
        """形式に応じて画質選択ボックスの表示/非表示を切り替え"""
        is_mp4 = (text == "mp4")
        self.quality_group_widget.setVisible(is_mp4)

    def select_save_path(self):
        """保存先フォルダ選択ダイアログを表示"""
        directory = QFileDialog.getExistingDirectory(
            self, "保存先フォルダを選択", self.current_save_path
        )
        if directory:
            self.current_save_path = directory
            self.update_save_path_display()

    def update_save_path_display(self):
        """選択された保存先パスをラベルに表示"""
        # パスが長すぎる場合は短縮表示
        max_len = 50
        display_path = self.current_save_path
        if len(display_path) > max_len:
            # 末尾部分を表示
            display_path = "..." + display_path[-(max_len-3):]
        self.save_path_display.setText(display_path)
        self.save_path_display.setToolTip(self.current_save_path) # フルパスはツールチップに

    def confirm_and_start_download(self):
        """入力と設定を確認し、ダウンロードを開始する"""
        url = clean_url(self.url_input.text())
        if not url or not url.startswith(("http://", "https://")):
            self.show_error_message("入力エラー", "有効な動画URLを入力してください。")
            return

        if not self.current_save_path or not os.path.isdir(self.current_save_path):
            self.show_error_message("設定エラー", "有効な保存先フォルダを選択してください。")
            return

        fmt = self.format_box.currentText()
        resolution_text = self.quality_box.currentText()
        resolution = resolution_text if fmt == "mp4" and resolution_text != "最高画質" else ""

        use_hw_encode = False
        hw_encoder = None
        hw_check_error = None

        # MP4形式の場合のみハードウェアエンコードを確認
        if fmt == "mp4":
            # ffmpegの存在確認も兼ねる
            hw_encoder, hw_check_error = detect_hw_encoder(self.ffmpeg_path)
            if hw_check_error and "ffmpegが見つかりません" in hw_check_error:
                 self.show_error_message("ffmpegエラー", f"{hw_check_error}\nffmpegのパスを確認するか、インストールしてください。")
                 return

            if hw_encoder:
                reply = QMessageBox.question(self, 'ハードウェアエンコード確認',
                                             f"利用可能なHWエンコーダー ({hw_encoder}) を検出しました。\nこれを使用してエンコードしますか？\n（GPUを使用し高速化が期待できますが、不安定になる場合もあります）",
                                             QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if reply == QMessageBox.Yes:
                    use_hw_encode = True
                    self.update_status(f"ハードウェアエンコード ({hw_encoder}) を使用します。")
                else:
                    self.update_status("CPUエンコードを使用します。")
            elif hw_check_error:
                 self.update_status(f"CPUエンコードを使用します。(HW検出エラー: {hw_check_error})")
            else: # エンコーダーなし
                 self.update_status("CPUエンコードを使用します。(利用可能なHWエンコーダーなし)")

        # ダウンロード状態にUIを更新
        self.set_downloading_state(True)
        self.update_status("ダウンロード準備中...")
        self.progress.setValue(0)

        # Downloader スレッド開始
        self.downloader_thread = Downloader(
            url, self.current_save_path, resolution, fmt,
            use_hw_encode, hw_encoder, self.ffmpeg_path
        )
        self.downloader_thread.progress.connect(self.update_progress)
        self.downloader_thread.finished.connect(self.download_finished)
        self.downloader_thread.error.connect(self.download_error)
        self.downloader_thread.start()

    def set_downloading_state(self, downloading):
        """ダウンロード中/完了時のUI状態を切り替え"""
        self.url_input.setEnabled(not downloading)
        self.format_box.setEnabled(not downloading)
        self.quality_box.setEnabled(not downloading and self.format_box.currentText() == "mp4")
        self.save_path_button.setEnabled(not downloading)
        self.btn.setEnabled(not downloading)
        if downloading:
            self.btn.setText("⏳ 処理中...")
        else:
            self.btn.setText("📥 ダウンロード開始")

    def update_progress(self, value):
         """プログレスバーとステータス表示を更新"""
         self.progress.setValue(value)
         if value < 100:
              self.update_status(f"ダウンロード中... {value}%")
         # 100%時のメッセージは finished/error で表示

    def download_finished(self, final_filepath):
        self.current_download_path = final_filepath # 完了パス保持
        self.set_downloading_state(False)
        self.progress.setValue(100)
        self.update_status("完了しました！")
        QMessageBox.information(self, "ダウンロード完了",
                                f"処理が完了しました。\nファイル: {final_filepath}",
                                QMessageBox.Ok)

        # MP4ならプレビュー
        if final_filepath and final_filepath.lower().endswith((".mp4", ".webm", ".mov")): # WebMなどもプレビュー試行
            try:
                 # QUrl.fromLocalFile は PyQt6 では非推奨の場合あり
                 local_url = QUrl.fromLocalFile(final_filepath) if hasattr(QUrl, 'fromLocalFile') else QUrl(f"file:///{final_filepath.replace(os.sep, '/')}")
                 self.webview.setUrl(local_url)
                 # self.webview.reload() # 必要なら
            except Exception as e:
                 print(f"Webviewでのプレビューエラー: {e}")
                 self.webview.setUrl(QUrl("about:blank"))
        else:
            self.webview.setUrl(QUrl("about:blank"))

    def download_error(self, err):
        self.set_downloading_state(False)
        self.progress.setValue(0) # エラー時はリセット
        self.update_status("エラーが発生しました。")
        self.show_error_message("処理エラー", f"ダウンロードまたは変換処理中にエラーが発生しました:\n{err}")
        self.webview.setUrl(QUrl("about:blank")) # Webviewクリア

    def update_status(self, message):
        """下部のステータスラベルを更新"""
        self.status_label.setText(message)
        print(f"Status: {message}") # コンソールにも出力

    def show_error_message(self, title, message):
         """エラーメッセージボックスを表示"""
         # 長すぎるメッセージを省略
         short_message = (message[:800] + '...') if len(message) > 800 else message
         QMessageBox.critical(self, title, short_message)

    def closeEvent(self, event):
        """ウィンドウを閉じる前に確認 (オプション)"""
        # ダウンロード中に閉じようとした場合の処理などを追加可能
        # reply = QMessageBox.question(self, '終了確認',
        #                              'アプリケーションを終了しますか？',
        #                              QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        # if reply == QMessageBox.Yes:
        #     # ダウンローダースレッドが動作中なら停止を試みる
        #     if hasattr(self, 'downloader_thread') and self.downloader_thread.isRunning():
        #         print("ダウンローダースレッドを停止試行...")
        #         # スレッドの安全な停止処理が必要 (ここでは簡単のため terminate)
        #         # self.downloader_thread.requestInterruption() # QThreadの機能
        #         # self.downloader_thread.quit()
        #         self.downloader_thread.terminate() # 強制終了 (非推奨)
        #         self.downloader_thread.wait(1000) # 少し待つ
        #     event.accept()
        # else:
        #     event.ignore()
        event.accept() # 確認なしで閉じる


if __name__ == "__main__":
    # 高DPI対応設定
    try:
        if hasattr(Qt, 'AA_EnableHighDpiScaling'):
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except Exception as e:
        print(f"高DPI設定エラー: {e}")

    app = QApplication(sys.argv)

    # スタイルの適用 (Fusionなど)
    # app.setStyle("Fusion")

    window = App()
    # window.show() は App 内の show_main_window で呼ばれるため不要
    sys.exit(app.exec())
