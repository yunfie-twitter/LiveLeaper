"""
初期設定ウィザードモジュール
PyQt5を使用したセットアップウィザード
"""
import sys
import os
import subprocess
from pathlib import Path
from typing import Dict, Any

from PyQt5.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QCheckBox, QGroupBox,
    QFormLayout, QProgressBar, QTextEdit, QFileDialog,
    QMessageBox, QApplication, QFrame, QGridLayout, QSpacerItem,
    QSizePolicy
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt5.QtGui import QFont, QPixmap, QIcon

class DependencyCheckThread(QThread):
    """依存関係確認スレッド"""
    check_completed = pyqtSignal(dict)
    
    def run(self):
        """依存関係をチェック"""
        results = {}
        
        # ffmpeg確認
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=5)
            results['ffmpeg'] = result.returncode == 0
        except:
            results['ffmpeg'] = False
            
        # yt-dlp確認
        try:
            import yt_dlp
            results['yt_dlp'] = True
        except ImportError:
            results['yt_dlp'] = False
            
        # PyQt5確認
        try:
            from PyQt5 import QtCore
            results['pyqt5'] = True
        except ImportError:
            results['pyqt5'] = False
            
        self.check_completed.emit(results)

class WelcomePage(QWizardPage):
    """ウェルカムページ"""
    
    def __init__(self):
        super().__init__()
        self.setTitle("LiveLeaper へようこそ")
        self.setSubTitle("初期設定を行います。数分で完了します。")
        
        layout = QVBoxLayout()
        
        # ウェルカムメッセージ
        welcome_label = QLabel("""
        <h2>LiveLeaper</h2>
        <p>動画・音声のダウンロードと変換を行うツールです。</p>
        <p>初回起動のため、基本設定を行います。</p>
        
        <p><b>主な機能:</b></p>
        <ul>
            <li>YouTube、ニコニコ動画などからの動画・音声ダウンロード</li>
            <li>動画・音声ファイルの形式変換</li>
            <li>バッチ処理による一括ダウンロード</li>
            <li>字幕・メタデータの自動取得</li>
        </ul>
        
        <p>設定は後から変更できます。</p>
        """)
        welcome_label.setWordWrap(True)
        layout.addWidget(welcome_label)
        
        layout.addStretch()
        self.setLayout(layout)

class DependencyPage(QWizardPage):
    """依存関係確認ページ"""
    
    def __init__(self):
        super().__init__()
        self.setTitle("依存関係の確認")
        self.setSubTitle("必要なソフトウェアの確認を行います")
        
        layout = QVBoxLayout()
        
        # 説明
        info_label = QLabel("動作に必要なソフトウェアを確認しています...")
        layout.addWidget(info_label)
        
        # 確認結果表示エリア
        self.results_group = QGroupBox("確認結果")
        results_layout = QGridLayout()
        
        # 各項目のラベル
        self.ffmpeg_label = QLabel("FFmpeg:")
        self.ffmpeg_status = QLabel("確認中...")
        results_layout.addWidget(self.ffmpeg_label, 0, 0)
        results_layout.addWidget(self.ffmpeg_status, 0, 1)
        
        self.ytdlp_label = QLabel("yt-dlp:")
        self.ytdlp_status = QLabel("確認中...")
        results_layout.addWidget(self.ytdlp_label, 1, 0)
        results_layout.addWidget(self.ytdlp_status, 1, 1)
        
        self.pyqt_label = QLabel("PyQt5:")
        self.pyqt_status = QLabel("確認中...")
        results_layout.addWidget(self.pyqt_label, 2, 0)
        results_layout.addWidget(self.pyqt_status, 2, 1)
        
        self.results_group.setLayout(results_layout)
        layout.addWidget(self.results_group)
        
        # 進捗バー
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # 不定進捗
        layout.addWidget(self.progress_bar)
        
        # インストール手順表示エリア
        self.install_instructions = QTextEdit()
        self.install_instructions.setMaximumHeight(150)
        self.install_instructions.hide()
        layout.addWidget(self.install_instructions)
        
        layout.addStretch()
        self.setLayout(layout)
        
        # 依存関係チェック開始
        self.check_thread = DependencyCheckThread()
        self.check_thread.check_completed.connect(self.on_check_completed)
        
    def initializePage(self):
        """ページ初期化時に依存関係チェック開始"""
        self.check_thread.start()
        
    def on_check_completed(self, results: Dict[str, bool]):
        """依存関係チェック完了"""
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        
        # 結果表示
        self.ffmpeg_status.setText("✓ 利用可能" if results['ffmpeg'] else "✗ 見つかりません")
        self.ytdlp_status.setText("✓ 利用可能" if results['yt_dlp'] else "✗ 見つかりません")
        self.pyqt_status.setText("✓ 利用可能" if results['pyqt5'] else "✗ 見つかりません")
        
        # 不足しているものがある場合の手順表示
        missing = []
        if not results['ffmpeg']:
            missing.append("FFmpeg")
        if not results['yt_dlp']:
            missing.append("yt-dlp")
            
        if missing:
            instructions = f"""
不足しているソフトウェア: {', '.join(missing)}

インストール手順:
"""
            if not results['ffmpeg']:
                instructions += """
1. FFmpeg のインストール:
   - https://ffmpeg.org/download.html からダウンロード
   - 実行ファイルをPATHに追加するか、このアプリと同じフォルダに配置
"""
            if not results['yt_dlp']:
                instructions += """
2. yt-dlp のインストール:
   - コマンドプロンプトで: pip install yt-dlp
"""
            
            instructions += "\nインストール後、このウィザードを再実行してください。"
            self.install_instructions.setText(instructions)
            self.install_instructions.show()
        
        # ページの完了状態を更新
        self.completeChanged.emit()
        
    def isComplete(self):
        """ページが完了しているかチェック"""
        return hasattr(self, 'check_thread') and self.check_thread.isFinished()

class OutputSettingsPage(QWizardPage):
    """出力設定ページ"""
    
    def __init__(self):
        super().__init__()
        self.setTitle("出力設定")
        self.setSubTitle("ダウンロードしたファイルの保存先を設定します")
        
        layout = QVBoxLayout()
        
        # デフォルト保存先設定
        save_group = QGroupBox("デフォルト保存先")
        save_layout = QFormLayout()
        
        # 保存先ディレクトリ
        dir_layout = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        
        # デフォルト値を設定
        default_dir = str(Path.home() / "Downloads" / "MediaDownloader")
        self.output_dir_edit.setText(default_dir)
        
        dir_browse_btn = QPushButton("参照")
        dir_browse_btn.clicked.connect(self.browse_output_dir)
        
        dir_layout.addWidget(self.output_dir_edit)
        dir_layout.addWidget(dir_browse_btn)
        save_layout.addRow("保存先フォルダ:", dir_layout)
        
        # ディレクトリ自動作成
        self.auto_create_dir = QCheckBox("存在しない場合は自動作成")
        self.auto_create_dir.setChecked(True)
        save_layout.addRow(self.auto_create_dir)
        
        save_group.setLayout(save_layout)
        layout.addWidget(save_group)
        
        # ファイル名設定
        filename_group = QGroupBox("ファイル名設定")
        filename_layout = QFormLayout()
        
        self.auto_rename = QCheckBox("重複時に自動リネーム")
        self.auto_rename.setChecked(True)
        filename_layout.addRow(self.auto_rename)
        
        self.sanitize_filename = QCheckBox("不正文字を自動修正")
        self.sanitize_filename.setChecked(True)
        filename_layout.addRow(self.sanitize_filename)
        
        filename_group.setLayout(filename_layout)
        layout.addWidget(filename_group)
        
        layout.addStretch()
        self.setLayout(layout)
        
        # フィールド登録
        self.registerField("output_dir*", self.output_dir_edit)
        self.registerField("auto_create_dir", self.auto_create_dir)
        self.registerField("auto_rename", self.auto_rename)
        self.registerField("sanitize_filename", self.sanitize_filename)
        
    def browse_output_dir(self):
        """出力ディレクトリ選択"""
        directory = QFileDialog.getExistingDirectory(
            self, "保存先フォルダを選択", self.output_dir_edit.text()
        )
        if directory:
            self.output_dir_edit.setText(directory)

class FormatSettingsPage(QWizardPage):
    """形式設定ページ"""
    
    def __init__(self):
        super().__init__()
        self.setTitle("ファイル形式設定")
        self.setSubTitle("デフォルトのファイル形式を設定します")
        
        layout = QVBoxLayout()
        
        # 動画形式設定
        video_group = QGroupBox("動画設定")
        video_layout = QFormLayout()
        
        self.video_format = QComboBox()
        self.video_format.addItems([
            "mp4 (推奨)", "avi", "mkv", "webm", "mov"
        ])
        self.video_format.setCurrentText("mp4 (推奨)")
        video_layout.addRow("デフォルト動画形式:", self.video_format)
        
        self.video_quality = QComboBox()
        self.video_quality.addItems([
            "最高品質", "高品質 (推奨)", "中品質", "低品質", "カスタム"
        ])
        self.video_quality.setCurrentText("高品質 (推奨)")
        video_layout.addRow("動画品質:", self.video_quality)
        
        video_group.setLayout(video_layout)
        layout.addWidget(video_group)
        
        # 音声形式設定
        audio_group = QGroupBox("音声設定")
        audio_layout = QFormLayout()
        
        self.audio_format = QComboBox()
        self.audio_format.addItems([
            "mp3 (推奨)", "aac", "wav", "flac", "ogg"
        ])
        self.audio_format.setCurrentText("mp3 (推奨)")
        audio_layout.addRow("デフォルト音声形式:", self.audio_format)
        
        self.audio_quality = QComboBox()
        self.audio_quality.addItems([
            "320kbps (最高)", "256kbps (推奨)", "192kbps", "128kbps", "96kbps"
        ])
        self.audio_quality.setCurrentText("256kbps (推奨)")
        audio_layout.addRow("音声品質:", self.audio_quality)
        
        audio_group.setLayout(audio_layout)
        layout.addWidget(audio_group)
        
        layout.addStretch()
        self.setLayout(layout)
        
        # フィールド登録
        self.registerField("video_format", self.video_format, "currentText")
        self.registerField("video_quality", self.video_quality, "currentText")
        self.registerField("audio_format", self.audio_format, "currentText")
        self.registerField("audio_quality", self.audio_quality, "currentText")

class DownloadOptionsPage(QWizardPage):
    """ダウンロードオプション設定ページ"""
    
    def __init__(self):
        super().__init__()
        self.setTitle("ダウンロードオプション")
        self.setSubTitle("追加でダウンロードするデータを設定します")
        
        layout = QVBoxLayout()
        
        # メタデータ設定
        metadata_group = QGroupBox("メタデータ・付加情報")
        metadata_layout = QVBoxLayout()
        
        self.download_subtitles = QCheckBox("字幕データをダウンロード")
        self.download_subtitles.setToolTip("利用可能な字幕ファイルを自動ダウンロードします")
        metadata_layout.addWidget(self.download_subtitles)
        
        self.download_metadata = QCheckBox("メタデータをダウンロード")
        self.download_metadata.setChecked(True)
        self.download_metadata.setToolTip("動画情報（タイトル、説明文等）をJSONファイルで保存します")
        metadata_layout.addWidget(self.download_metadata)
        
        self.download_thumbnail = QCheckBox("サムネイルをダウンロード")
        self.download_thumbnail.setToolTip("動画のサムネイル画像を保存します")
        metadata_layout.addWidget(self.download_thumbnail)
        
        metadata_group.setLayout(metadata_layout)
        layout.addWidget(metadata_group)
        
        # 品質・サイズ設定
        quality_group = QGroupBox("品質・サイズ制限")
        quality_layout = QFormLayout()
        
        self.max_filesize = QLineEdit()
        self.max_filesize.setPlaceholderText("例: 1GB, 500MB (空白で制限なし)")
        quality_layout.addRow("最大ファイルサイズ:", self.max_filesize)
        
        self.preferred_quality = QComboBox()
        self.preferred_quality.addItems([
            "最高品質", "1080p以下", "720p以下", "480p以下", "最小サイズ優先"
        ])
        self.preferred_quality.setCurrentText("1080p以下")
        quality_layout.addRow("推奨品質:", self.preferred_quality)
        
        quality_group.setLayout(quality_layout)
        layout.addWidget(quality_group)
        
        # ネットワーク設定
        network_group = QGroupBox("ネットワーク設定")
        network_layout = QFormLayout()
        
        self.max_workers = QComboBox()
        self.max_workers.addItems(["1", "2", "4 (推奨)", "6", "8"])
        self.max_workers.setCurrentText("4 (推奨)")
        network_layout.addRow("同時ダウンロード数:", self.max_workers)
        
        network_group.setLayout(network_layout)
        layout.addWidget(network_group)
        
        layout.addStretch()
        self.setLayout(layout)
        
        # フィールド登録
        self.registerField("download_subtitles", self.download_subtitles)
        self.registerField("download_metadata", self.download_metadata)
        self.registerField("download_thumbnail", self.download_thumbnail)
        self.registerField("max_filesize", self.max_filesize)
        self.registerField("preferred_quality", self.preferred_quality, "currentText")
        self.registerField("max_workers", self.max_workers, "currentText")

class CompletePage(QWizardPage):
    """完了ページ"""
    
    def __init__(self):
        super().__init__()
        self.setTitle("設定完了")
        self.setSubTitle("初期設定が完了しました")
        
        layout = QVBoxLayout()
        
        # 完了メッセージ
        complete_label = QLabel("""
        <h3>設定が完了しました！</h3>
        <p>LiveLeaper の初期設定が完了しました。</p>
        <p>設定内容は後からメニューの「設定」で変更できます。</p>
        
        <p><b>設定された内容:</b></p>
        <ul id="settings-summary">
        </ul>
        
        <p>「完了」ボタンをクリックしてアプリケーションを開始してください。</p>
        """)
        complete_label.setWordWrap(True)
        layout.addWidget(complete_label)
        
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        
        layout.addStretch()
        self.setLayout(layout)
        
    def initializePage(self):
        """ページ表示時に設定内容の要約を作成"""
        wizard = self.wizard()
        
        # 設定内容をまとめる
        summary = "<ul>"
        summary += f"<li>保存先: {wizard.field('output_dir')}</li>"
        summary += f"<li>動画形式: {wizard.field('video_format')}</li>"
        summary += f"<li>音声形式: {wizard.field('audio_format')}</li>"
        
        options = []
        if wizard.field('download_subtitles'):
            options.append("字幕")
        if wizard.field('download_metadata'):
            options.append("メタデータ")
        if wizard.field('download_thumbnail'):
            options.append("サムネイル")
            
        if options:
            summary += f"<li>追加ダウンロード: {', '.join(options)}</li>"
        
        summary += f"<li>同時ダウンロード数: {wizard.field('max_workers')}</li>"
        summary += "</ul>"
        
        self.summary_label.setText(summary)

class SetupWizard(QWizard):
    """セットアップウィザードメインクラス"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Media Downloader & Converter - 初期設定")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setOption(QWizard.HaveHelpButton, False)
        self.setMinimumSize(600, 500)
        
        # ページを追加
        self.setPage(0, WelcomePage())
        self.setPage(1, DependencyPage())
        self.setPage(2, OutputSettingsPage())
        self.setPage(3, FormatSettingsPage())
        self.setPage(4, DownloadOptionsPage())
        self.setPage(5, CompletePage())
        
        # ウィザード完了時の処理
        self.finished.connect(self.on_finished)
        
    def on_finished(self, result):
        """ウィザード完了時の処理"""
        if result == QWizard.Accepted:
            self.save_settings()
            
    def save_settings(self):
        """設定を保存"""
        settings = QSettings("MediaDownloader", "Settings")
        
        # 出力設定
        settings.setValue("download/output_dir", self.field("output_dir"))
        settings.setValue("download/auto_create_dir", self.field("auto_create_dir"))
        settings.setValue("download/auto_rename", self.field("auto_rename"))
        settings.setValue("download/sanitize_filename", self.field("sanitize_filename"))
        
        # 形式設定
        video_format = self.field("video_format").split(" ")[0]  # "(推奨)"を除去
        audio_format = self.field("audio_format").split(" ")[0]
        settings.setValue("download/video_format", video_format)
        settings.setValue("download/audio_format", audio_format)
        settings.setValue("download/video_quality", self.field("video_quality"))
        settings.setValue("download/audio_quality", self.field("audio_quality"))
        
        # ダウンロードオプション
        settings.setValue("download/subtitles", self.field("download_subtitles"))
        settings.setValue("download/metadata", self.field("download_metadata"))
        settings.setValue("download/thumbnail", self.field("download_thumbnail"))
        settings.setValue("download/max_filesize", self.field("max_filesize"))
        settings.setValue("download/preferred_quality", self.field("preferred_quality"))
        
        # 並列処理設定
        max_workers = int(self.field("max_workers").split(" ")[0])
        settings.setValue("parallel/max_workers", max_workers)
        
        # 設定完了フラグ
        settings.setValue("setup_completed", True)
        
        # config.yamlも更新
        try:
            from config import config
            config.set("download.output_dir", self.field("output_dir"))
            config.set("download.format", video_format)
            config.set("download.audio_format", audio_format)
            config.set("download.subtitles", self.field("download_subtitles"))
            config.set("download.metadata", self.field("download_metadata"))
            config.set("parallel.max_workers", max_workers)
            config.save_config()
        except Exception as e:
            print(f"config.yaml の更新に失敗しました: {e}")

def main():
    """セットアップウィザード単体実行用"""
    app = QApplication(sys.argv)
    wizard = SetupWizard()
    sys.exit(wizard.exec_())

if __name__ == "__main__":
    main()
