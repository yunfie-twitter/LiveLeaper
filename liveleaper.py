import sys
import os
import subprocess
from urllib.parse import urlparse, parse_qs

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox,
    QProgressBar, QComboBox, QSizePolicy, QSplashScreen, QDesktopWidget
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl, QTimer
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtGui import QPixmap


import yt_dlp
from pytube import YouTube


def clean_url(url):
    if "youtube.com/shorts/" in url:
        vid = url.split("/shorts/")[-1].split("?")[0]
        return f"https://www.youtube.com/watch?v={vid}"
    parsed = urlparse(url)
    vid = parse_qs(parsed.query).get("v")
    return f"https://www.youtube.com/watch?v={vid[0]}" if vid else url

class Downloader(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, url, save_path, resolution, fmt):
        super().__init__()
        self.url = url
        self.save_path = save_path
        self.resolution = resolution
        self.fmt = fmt

    def run(self):
        try:
            ydl_opts = {
                'format': 'bestaudio+bestvideo/best',
                'outtmpl': f'{self.save_path}/%(title)s.%(ext)s',
                'ffmpeg_location': './ffmpeg.exe',
                'progress_hooks': [self.hook],
                'quiet': True
            }

            if self.fmt == "mp3":
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192'
                }]
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                title = info.get('title', 'video')
                ext = 'mp3' if self.fmt == 'mp3' else 'mp4'
                output_file = os.path.join(self.save_path, f"{title}.{ext}")
                ydl.download([self.url])

                # ダウンロードしたファイルを自動的に確認する
                downloaded_files = [f for f in os.listdir(self.save_path) if f.startswith(title)]


                # 「無変換」オプションが選ばれた場合
                if self.fmt == "no_conversion":
                    # 無変換のままで保存
                    self.finished.emit(self.save_path)
                    return
                
                if not downloaded_files:
                    self.error.emit(f"ファイルが見つかりません: {title}")
                    return

                # 最初に見つかったファイルを使用
                output_file = os.path.join(self.save_path, downloaded_files[0])

                # 動画が webm であれば mp4 に変換する
                if output_file.endswith(".webm") or output_file.endswith(".flv") or output_file.endswith(".mov"):
                    mp4_output_file = os.path.join(self.save_path, f"{title}.mp4")
                    
                    if os.path.exists(output_file):
                        subprocess.run([  # MP4に変換
                            "./ffmpeg.exe", "-i", output_file,
                            "-c:v", "libx264", "-crf", "23", "-preset", "fast",
                            "-c:a", "aac", "-b:a", "192k", "-strict", "experimental", mp4_output_file
                        ])
                        os.remove(output_file)  # 元の .webm ファイルを削除
                        output_file = mp4_output_file  # 出力ファイルを .mp4 に更新
                    else:
                        self.error.emit(f"ファイルが見つかりません: {output_file}")
                        return

                # 解像度変更が必要であれば
                if self.fmt == "mp4":
                    resized_file = os.path.join(self.save_path, f"{title}_resized.mp4")
                    subprocess.run([  # 解像度変更
                        "./ffmpeg.exe", "-i", output_file,
                        "-vf", f"scale=-2:{self.resolution}",
                        "-c:v", "libx264", "-crf", "23", "-preset", "fast",
                        "-c:a", "copy", resized_file
                    ])
                    os.remove(output_file)
                    os.rename(resized_file, output_file)

            self.finished.emit(self.save_path)

        except Exception as e:
            self.error.emit(str(e))

    def hook(self, d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded = d.get('downloaded_bytes', 0)
            if total:
                self.progress.emit(int(downloaded * 100 / total))
        elif d['status'] == 'finished':
            self.progress.emit(100)


class CustomTitleBar(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.setFixedHeight(30)
        self.setStyleSheet("background-color: #000000;")
        self.offset = None

        self.title_label = QLabel("                                                                                                                                                                                                                  ")
        self.title_label.setStyleSheet("color: #CCCCCC; font-size: 14px; font-weight: bold; margin-left: 0px;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self.title_label)
        layout.addStretch()

        self.min_btn = QPushButton("─")
        self.min_btn.setFixedSize(40, 30)
        self.min_btn.setStyleSheet("color: #CCCCCC; background-color: #000000; border: none;")
        self.min_btn.clicked.connect(self.parent.showMinimized)

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
        if event.button() == Qt.LeftButton:
            self.offset = event.globalPos() - self.parent.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.offset:
            self.parent.move(event.globalPos() - self.offset)

    def mouseReleaseEvent(self, event):
        self.offset = None

class LoadingDots(QWidget):
    def __init__(self):
        super().__init__()
        self.dots = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.current = 0

        self.setFixedSize(200, 100)  # サイズ明示

        layout = QHBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(0, 0, 0, 0)

        for i in range(4):
            dot = QLabel("●")  # ●のほうが視認性高い
            dot.setStyleSheet("color: gray; font-size: 20px;")
            dot.setFixedSize(5, 5)
            dot.setAlignment(Qt.AlignCenter)
            self.dots.append(dot)
            layout.addWidget(dot)

        self.timer.start(300)

    def animate(self):
        for i, dot in enumerate(self.dots):
            if i == self.current:
                dot.setStyleSheet("color: white; font-size: 20px;")  # 明るく
            else:
                dot.setStyleSheet("color: gray; font-size: 20px;")
        self.current = (self.current + 1) % 4


class App(QWidget):
    def __init__(self):
        super().__init__()

        # メインウィンドウを非表示にしておく
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setWindowTitle("DowTube")
        self.setMinimumSize(600, 500)

        # スプラッシュスクリーンを表示
        self.show_splash_screen()

    def show_splash_screen(self):
        # ロゴ読み込み
        pixmap = QPixmap("LiveLeaper.png")
        splash = QSplashScreen(pixmap, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        splash.setMask(pixmap.mask())
        splash.setStyleSheet("background: transparent;")

        # 中央配置
        screen_geometry = QDesktopWidget().availableGeometry()
        splash_width = splash.pixmap().width()
        splash_height = splash.pixmap().height()
        x = (screen_geometry.width() - splash_width) // 2
        y = (screen_geometry.height() - splash_height) // 2
        splash.move(x, y)

        splash.show()

        # --- ローディングドット追加 ---
        self.loading_dots = LoadingDots()
        self.loading_dots.setParent(splash)
        self.loading_dots.resize(500, 500)  # ← サイズを明示的に指定

        # splash pixmap の下に中央配置
        dots_x = (splash_width - self.loading_dots.width()) // 2
        dots_y = splash_height - 10  # 画像のすぐ下に
        self.loading_dots.move(dots_x, dots_y)

        self.loading_dots.show()
        
        # スプラッシュから本画面に移動
        QTimer.singleShot(1500, lambda: self.show_main_window(splash))

    def show_main_window(self, splash):
        # スプラッシュスクリーンを閉じ、メインウィンドウを表示
        splash.close()

        # メインウィンドウの初期化
        self.init_ui()
        self.show()

    def init_ui(self):
        self.titlebar = CustomTitleBar(self)
        self.titlebar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("YouTubeのURLを入力")

        self.format_box = QComboBox()
        self.format_box.addItems(["mp4", "mp3", "無変換"])  # 無変換を追加
        self.format_box.currentTextChanged.connect(self.update_quality_box)

        self.quality_box = QComboBox()
        self.quality_box.addItems(["144", "360", "480", "720", "1080"])

        self.btn = QPushButton("📥 ダウンロード")
        self.btn.clicked.connect(self.download)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(20)

        self.webview = QWebEngineView()
        self.webview.setMinimumHeight(200)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.titlebar)

        form_layout = QVBoxLayout()
        form_layout.setContentsMargins(15, 15, 15, 0)
        form_layout.setSpacing(8)
        form_layout.addWidget(self.url_input)

        opt_layout = QHBoxLayout()
        opt_layout.addWidget(QLabel("形式:"))
        opt_layout.addWidget(self.format_box)
        opt_layout.addSpacing(10)
        opt_layout.addWidget(QLabel("画質:"))
        opt_layout.addWidget(self.quality_box)
        form_layout.addLayout(opt_layout)
        form_layout.addWidget(self.btn)

        layout.addLayout(form_layout)

        layout.addWidget(self.webview)
        layout.addWidget(self.progress)

    def update_quality_box(self, text):
        # "無変換"の場合、画質選択ボックスを無効にする
        self.quality_box.setEnabled(text != "無変換")

    def download(self):
        url = clean_url(self.url_input.text())
        if not url:
            QMessageBox.warning(self, "エラー", "URLを入力してください。")
            return

        save_path = QFileDialog.getExistingDirectory(self, "保存先を選択")
        if not save_path:
            return

        fmt = self.format_box.currentText()
        resolution = self.quality_box.currentText()

        self.progress.setValue(0)
        self.downloader = Downloader(url, save_path, resolution, fmt)
        self.downloader.progress.connect(self.progress.setValue)
        self.downloader.finished.connect(self.download_finished)
        self.downloader.error.connect(self.download_error)
        self.downloader.start()

    def download_finished(self, path):
        QMessageBox.information(self, "完了", "ダウンロードが完了しました。")
        for file in os.listdir(path):
            if file.endswith(".mp4"):
                self.webview.setUrl(QUrl.fromLocalFile(os.path.join(path, file)))
                break

    def download_error(self, err):
        QMessageBox.critical(self, "エラー", f"ダウンロードに失敗しました:\n{err}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec_())
