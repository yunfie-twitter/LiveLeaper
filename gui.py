"""
PyQt5ベースのGUIモジュール - 完全統合版
動画・音声ダウンロード変換ソフトウェア
全機能統合版（初期設定ウィザード、URL修正、変換、圧縮、バッチ処理対応）
"""
import sys
import os
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, QSpinBox,
    QFileDialog, QGroupBox, QProgressBar, QTextEdit, QListWidget,
    QTabWidget, QFormLayout, QSlider, QSplitter, QMessageBox,
    QSystemTrayIcon, QMenu, QAction, QStatusBar, QListWidgetItem,
    QDialog, QDialogButtonBox, QGridLayout, QFrame, QSpacerItem,
    QSizePolicy, QButtonGroup, QRadioButton
)
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal, QSettings, QTimer, QSize, QUrl
)
from PyQt5.QtGui import QIcon, QPixmap, QFont, QPalette

# 依存モジュールのインポート（エラーハンドリング付き）
try:
    from config import config
    from downloader import VideoDownloader, BatchDownloader, URLCleaner
    from converter import VideoConverter
    from task_manager import TaskManager, TaskStatus
    from utils import format_bytes, format_duration, parse_url_list_file
    from setup_wizard import SetupWizard
except ImportError as e:
    print(f"依存モジュールのインポートエラー: {e}")
    # デフォルト値での動作を可能にする
    config = type('Config', (), {
        'get': lambda self, key, default=None: default
    })()

logger = logging.getLogger(__name__)

class DownloadThread(QThread):
    """ダウンロードスレッド"""
    progress_updated = pyqtSignal(dict)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, url: str, options: Dict[str, Any]):
        super().__init__()
        self.url = url
        self.options = options
        try:
            self.downloader = VideoDownloader(self.progress_callback)
        except Exception as e:
            logger.error(f"VideoDownloaderの初期化エラー: {e}")
            self.downloader = None
    
    def progress_callback(self, progress_info: Dict[str, Any]):
        """進捗コールバック"""
        self.progress_updated.emit(progress_info)
    
    def run(self):
        """ダウンロード実行"""
        try:
            if not self.downloader:
                self.finished.emit(False, "ダウンローダーの初期化に失敗しました")
                return
            
            # URLを自動修正
            clean_url = URLCleaner.clean_url(self.url)
            logger.info(f"URL修正: {self.url} -> {clean_url}")
                
            if self.options.get('audio_only', False):
                result = self.downloader.download_audio(
                    clean_url,
                    self.options.get('output_dir', './downloads'),
                    self.options.get('audio_format', 'mp3')
                )
            else:
                result = self.downloader.download_video(
                    clean_url,
                    self.options.get('output_dir', './downloads'),
                    self.options.get('format', 'bestvideo+bestaudio/best')
                )
            
            self.finished.emit(True, result or "ダウンロード完了")
            
        except Exception as e:
            logger.error(f"ダウンロードエラー: {e}")
            self.finished.emit(False, str(e))

class ConvertThread(QThread):
    """変換スレッド"""
    progress_updated = pyqtSignal(dict)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, input_file: str, output_file: str, options: Dict[str, Any]):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.options = options
        try:
            self.converter = VideoConverter(self.progress_callback)
        except Exception as e:
            logger.error(f"VideoConverterの初期化エラー: {e}")
            self.converter = None
    
    def progress_callback(self, progress_info: Dict[str, Any]):
        """進捗コールバック"""
        self.progress_updated.emit(progress_info)
    
    def run(self):
        """変換実行"""
        try:
            if not self.converter:
                self.finished.emit(False, "変換器の初期化に失敗しました")
                return
                
            # ファイル拡張子に基づいて変換方法を決定
            input_suffix = Path(self.input_file).suffix.lower()
            output_suffix = Path(self.output_file).suffix.lower()
            
            if output_suffix in ['.mp3', '.aac', '.ogg', '.flac', '.wav']:
                if input_suffix in ['.mp4', '.avi', '.mkv', '.webm', '.mov']:
                    # 動画から音声抽出
                    result = self.converter.extract_audio(
                        self.input_file, self.output_file,
                        output_suffix[1:], **self.options
                    )
                else:
                    # 音声形式変換
                    result = self.converter.convert_audio(
                        self.input_file, self.output_file,
                        output_suffix[1:], **self.options
                    )
            else:
                # 動画変換
                result = self.converter.convert_video(
                    self.input_file, self.output_file, **self.options
                )
            
            self.finished.emit(True, result or "変換完了")
            
        except Exception as e:
            logger.error(f"変換エラー: {e}")
            self.finished.emit(False, str(e))

class BatchDownloadThread(QThread):
    """バッチダウンロードスレッド"""
    progress_updated = pyqtSignal(int, int, str)  # current, total, status
    item_finished = pyqtSignal(str, bool, str)  # url, success, result
    finished = pyqtSignal(dict)
    
    def __init__(self, urls: List[str], options: Dict[str, Any]):
        super().__init__()
        self.urls = urls
        self.options = options
        self.downloader = VideoDownloader()
        self.stopped = False
    
    def stop(self):
        """処理停止"""
        self.stopped = True
    
    def run(self):
        """バッチダウンロード実行"""
        results = {'success': [], 'failed': [], 'total': len(self.urls)}
        
        for i, url in enumerate(self.urls):
            if self.stopped:
                break
                
            self.progress_updated.emit(i + 1, len(self.urls), f"処理中: {url}")
            
            try:
                clean_url = URLCleaner.clean_url(url)
                
                if self.options.get('audio_only', False):
                    result = self.downloader.download_audio(
                        clean_url,
                        self.options.get('output_dir', './downloads'),
                        self.options.get('audio_format', 'mp3')
                    )
                else:
                    result = self.downloader.download_video(
                        clean_url,
                        self.options.get('output_dir', './downloads'),
                        self.options.get('format', 'bestvideo+bestaudio/best')
                    )
                
                if result:
                    results['success'].append({'url': url, 'file': result})
                    self.item_finished.emit(url, True, result)
                else:
                    results['failed'].append({'url': url, 'error': 'Download failed'})
                    self.item_finished.emit(url, False, 'Download failed')
                    
            except Exception as e:
                error_msg = str(e)
                results['failed'].append({'url': url, 'error': error_msg})
                self.item_finished.emit(url, False, error_msg)
        
        self.finished.emit(results)

class AdvancedSettingsDialog(QDialog):
    """詳細設定ダイアログ"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("詳細設定")
        self.setModal(True)
        self.resize(700, 600)
        self.init_ui()
        self.load_settings()
    
    def init_ui(self):
        """UI初期化"""
        layout = QVBoxLayout()
        
        # タブウィジェット
        tab_widget = QTabWidget()
        
        # ダウンロード設定タブ
        download_tab = self.create_download_tab()
        tab_widget.addTab(download_tab, "ダウンロード")
        
        # 変換設定タブ
        convert_tab = self.create_convert_tab()
        tab_widget.addTab(convert_tab, "変換")
        
        # 音声圧縮設定タブ
        audio_tab = self.create_audio_tab()
        tab_widget.addTab(audio_tab, "音声圧縮")
        
        # 一般設定タブ
        general_tab = self.create_general_tab()
        tab_widget.addTab(general_tab, "一般")
        
        layout.addWidget(tab_widget)
        
        # ボタン
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
        )
        button_box.accepted.connect(self.accept_settings)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.Apply).clicked.connect(self.apply_settings)
        
        layout.addWidget(button_box)
        self.setLayout(layout)
    
    def create_download_tab(self) -> QWidget:
        """ダウンロード設定タブを作成"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # 出力設定
        output_group = QGroupBox("出力設定")
        output_layout = QFormLayout()
        
        self.output_dir_edit = QLineEdit()
        dir_browse_btn = QPushButton("参照")
        dir_browse_btn.clicked.connect(self.browse_output_dir)
        
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.output_dir_edit)
        dir_row.addWidget(dir_browse_btn)
        
        output_layout.addRow("保存先:", dir_row)
        
        self.auto_rename_check = QCheckBox("重複時自動リネーム")
        output_layout.addRow(self.auto_rename_check)
        
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)
        
        # フォーマット設定
        format_group = QGroupBox("フォーマット設定")
        format_layout = QFormLayout()
        
        self.video_format_combo = QComboBox()
        self.video_format_combo.addItems([
            "bestvideo+bestaudio/best", "best", "worst", "mp4", "webm", "avi", "mkv"
        ])
        format_layout.addRow("動画形式:", self.video_format_combo)
        
        self.audio_format_combo = QComboBox()
        self.audio_format_combo.addItems(["mp3", "aac", "wav", "flac", "ogg"])
        format_layout.addRow("音声形式:", self.audio_format_combo)
        
        format_group.setLayout(format_layout)
        layout.addWidget(format_group)
        
        # 品質設定
        quality_group = QGroupBox("品質設定")
        quality_layout = QFormLayout()
        
        self.video_quality_combo = QComboBox()
        self.video_quality_combo.addItems([
            "最高品質", "1080p以下", "720p以下", "480p以下", "最小サイズ優先"
        ])
        quality_layout.addRow("動画品質:", self.video_quality_combo)
        
        self.max_filesize_edit = QLineEdit()
        self.max_filesize_edit.setPlaceholderText("例: 1GB, 500MB (空白で制限なし)")
        quality_layout.addRow("最大ファイルサイズ:", self.max_filesize_edit)
        
        quality_group.setLayout(quality_layout)
        layout.addWidget(quality_group)
        
        # 追加オプション
        option_group = QGroupBox("追加オプション")
        option_layout = QVBoxLayout()
        
        self.subtitle_check = QCheckBox("字幕をダウンロード")
        option_layout.addWidget(self.subtitle_check)
        
        self.metadata_check = QCheckBox("メタデータを保存")
        option_layout.addWidget(self.metadata_check)
        
        self.thumbnail_check = QCheckBox("サムネイルを保存")
        option_layout.addWidget(self.thumbnail_check)
        
        option_group.setLayout(option_layout)
        layout.addWidget(option_group)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def create_convert_tab(self) -> QWidget:
        """変換設定タブを作成"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # ハードウェアアクセラレーション
        hw_group = QGroupBox("ハードウェアアクセラレーション")
        hw_layout = QFormLayout()
        
        self.hw_accel_combo = QComboBox()
        self.hw_accel_combo.addItems([
            "自動検出", "NVIDIA NVENC", "Intel QSV", "AMD AMF", "CPU（無効）"
        ])
        hw_layout.addRow("エンコーダー:", self.hw_accel_combo)
        
        hw_group.setLayout(hw_layout)
        layout.addWidget(hw_group)
        
        # 動画設定
        video_group = QGroupBox("動画設定")
        video_layout = QFormLayout()
        
        self.video_codec_combo = QComboBox()
        self.video_codec_combo.addItems(["h264", "h265", "vp9", "av1"])
        video_layout.addRow("動画コーデック:", self.video_codec_combo)
        
        self.video_bitrate_edit = QLineEdit()
        self.video_bitrate_edit.setPlaceholderText("例: 8000k, 10M")
        video_layout.addRow("動画ビットレート:", self.video_bitrate_edit)
        
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems([
            "オリジナル", "3840x2160", "2560x1440", "1920x1080", 
            "1280x720", "854x480", "640x360"
        ])
        video_layout.addRow("解像度:", self.resolution_combo)
        
        video_group.setLayout(video_layout)
        layout.addWidget(video_group)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def create_audio_tab(self) -> QWidget:
        """音声圧縮設定タブを作成"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # 音声コーデック設定
        codec_group = QGroupBox("音声コーデック設定")
        codec_layout = QGridLayout()
        
        codec_layout.addWidget(QLabel("コーデック:"), 0, 0)
        self.audio_codec_combo = QComboBox()
        self.audio_codec_combo.addItems(["mp3", "aac", "opus", "flac", "wav", "ogg"])
        codec_layout.addWidget(self.audio_codec_combo, 0, 1)
        
        codec_layout.addWidget(QLabel("ビットレート:"), 1, 0)
        self.audio_bitrate_combo = QComboBox()
        self.audio_bitrate_combo.addItems([
            "64k", "96k", "128k", "160k", "192k", "256k", "320k", "可変ビットレート"
        ])
        codec_layout.addWidget(self.audio_bitrate_combo, 1, 1)
        
        codec_layout.addWidget(QLabel("サンプルレート:"), 2, 0)
        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.addItems([
            "オリジナル維持", "8000 Hz", "16000 Hz", "22050 Hz", "44100 Hz", "48000 Hz", "96000 Hz"
        ])
        codec_layout.addWidget(self.sample_rate_combo, 2, 1)
        
        codec_layout.addWidget(QLabel("チャンネル:"), 3, 0)
        self.channel_combo = QComboBox()
        self.channel_combo.addItems([
            "オリジナル維持", "モノラル", "ステレオ", "5.1ch"
        ])
        codec_layout.addWidget(self.channel_combo, 3, 1)
        
        codec_group.setLayout(codec_layout)
        layout.addWidget(codec_group)
        
        # 圧縮品質設定
        quality_group = QGroupBox("圧縮品質設定")
        quality_layout = QVBoxLayout()
        
        self.quality_slider = QSlider(Qt.Horizontal)
        self.quality_slider.setRange(0, 100)
        self.quality_slider.setValue(80)
        self.quality_slider.valueChanged.connect(self.update_quality_label)
        
        self.quality_label = QLabel("圧縮品質: 80% (高品質)")
        
        quality_layout.addWidget(QLabel("品質設定:"))
        quality_layout.addWidget(self.quality_slider)
        quality_layout.addWidget(self.quality_label)
        
        # 品質プリセット
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("プリセット:"))
        
        low_btn = QPushButton("低品質 (小サイズ)")
        low_btn.clicked.connect(lambda: self.quality_slider.setValue(30))
        preset_layout.addWidget(low_btn)
        
        med_btn = QPushButton("中品質 (バランス)")
        med_btn.clicked.connect(lambda: self.quality_slider.setValue(60))
        preset_layout.addWidget(med_btn)
        
        high_btn = QPushButton("高品質 (大サイズ)")
        high_btn.clicked.connect(lambda: self.quality_slider.setValue(90))
        preset_layout.addWidget(high_btn)
        
        quality_layout.addLayout(preset_layout)
        quality_group.setLayout(quality_layout)
        layout.addWidget(quality_group)
        
        # 高度な設定
        advanced_group = QGroupBox("高度な設定")
        advanced_layout = QFormLayout()
        
        self.normalize_audio_check = QCheckBox("音量正規化")
        advanced_layout.addRow(self.normalize_audio_check)
        
        self.noise_reduction_check = QCheckBox("ノイズ除去")
        advanced_layout.addRow(self.noise_reduction_check)
        
        self.fade_in_spin = QSpinBox()
        self.fade_in_spin.setRange(0, 10)
        self.fade_in_spin.setSuffix(" 秒")
        advanced_layout.addRow("フェードイン:", self.fade_in_spin)
        
        self.fade_out_spin = QSpinBox()
        self.fade_out_spin.setRange(0, 10)
        self.fade_out_spin.setSuffix(" 秒")
        advanced_layout.addRow("フェードアウト:", self.fade_out_spin)
        
        advanced_group.setLayout(advanced_layout)
        layout.addWidget(advanced_group)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def create_general_tab(self) -> QWidget:
        """一般設定タブを作成"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # 並列処理設定
        parallel_group = QGroupBox("並列処理設定")
        parallel_layout = QFormLayout()
        
        self.max_workers_spin = QSpinBox()
        self.max_workers_spin.setRange(1, 16)
        self.max_workers_spin.setValue(4)
        parallel_layout.addRow("最大並列数:", self.max_workers_spin)
        
        parallel_group.setLayout(parallel_layout)
        layout.addWidget(parallel_group)
        
        # ネットワーク設定
        network_group = QGroupBox("ネットワーク設定")
        network_layout = QFormLayout()
        
        self.retry_count_spin = QSpinBox()
        self.retry_count_spin.setRange(1, 10)
        self.retry_count_spin.setValue(3)
        network_layout.addRow("リトライ回数:", self.retry_count_spin)
        
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 300)
        self.timeout_spin.setValue(60)
        self.timeout_spin.setSuffix(" 秒")
        network_layout.addRow("タイムアウト:", self.timeout_spin)
        
        network_group.setLayout(network_layout)
        layout.addWidget(network_group)
        
        # 初期設定ウィザード
        setup_group = QGroupBox("初期設定")
        setup_layout = QVBoxLayout()
        
        setup_wizard_btn = QPushButton("初期設定ウィザードを再実行")
        setup_wizard_btn.clicked.connect(self.run_setup_wizard)
        setup_layout.addWidget(setup_wizard_btn)
        
        reset_settings_btn = QPushButton("設定をリセット")
        reset_settings_btn.clicked.connect(self.reset_settings)
        setup_layout.addWidget(reset_settings_btn)
        
        setup_group.setLayout(setup_layout)
        layout.addWidget(setup_group)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def update_quality_label(self, value):
        """品質ラベル更新"""
        if value < 40:
            quality_text = "低品質"
        elif value < 70:
            quality_text = "中品質"
        else:
            quality_text = "高品質"
        
        self.quality_label.setText(f"圧縮品質: {value}% ({quality_text})")
    
    def browse_output_dir(self):
        """出力ディレクトリ選択"""
        directory = QFileDialog.getExistingDirectory(
            self, "出力ディレクトリを選択", self.output_dir_edit.text()
        )
        if directory:
            self.output_dir_edit.setText(directory)
    
    def run_setup_wizard(self):
        """初期設定ウィザードを実行"""
        try:
            wizard = SetupWizard()
            if wizard.exec_() == wizard.Accepted:
                QMessageBox.information(self, "完了", "初期設定が更新されました。")
                self.load_settings()  # 設定を再読み込み
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"初期設定ウィザードの実行に失敗しました:\n{e}")
    
    def reset_settings(self):
        """設定をリセット"""
        reply = QMessageBox.question(
            self, "確認", "すべての設定をデフォルトに戻しますか？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            settings = QSettings("MediaDownloader", "Settings")
            settings.clear()
            self.load_settings()
            QMessageBox.information(self, "完了", "設定をリセットしました。")
    
    def load_settings(self):
        """設定を読み込み"""
        settings = QSettings("MediaDownloader", "Settings")
        
        # ダウンロード設定
        self.output_dir_edit.setText(
            settings.value("download/output_dir", "./downloads")
        )
        self.auto_rename_check.setChecked(
            settings.value("download/auto_rename", True, type=bool)
        )
        self.video_format_combo.setCurrentText(
            settings.value("download/video_format", "bestvideo+bestaudio/best")
        )
        self.audio_format_combo.setCurrentText(
            settings.value("download/audio_format", "mp3")
        )
        self.video_quality_combo.setCurrentText(
            settings.value("download/video_quality", "1080p以下")
        )
        self.max_filesize_edit.setText(
            settings.value("download/max_filesize", "")
        )
        self.subtitle_check.setChecked(
            settings.value("download/subtitles", False, type=bool)
        )
        self.metadata_check.setChecked(
            settings.value("download/metadata", True, type=bool)
        )
        self.thumbnail_check.setChecked(
            settings.value("download/thumbnail", False, type=bool)
        )
        
        # 変換設定
        self.hw_accel_combo.setCurrentText(
            settings.value("convert/hw_accel", "自動検出")
        )
        self.video_codec_combo.setCurrentText(
            settings.value("convert/video_codec", "h264")
        )
        self.video_bitrate_edit.setText(
            settings.value("convert/video_bitrate", "8000k")
        )
        self.resolution_combo.setCurrentText(
            settings.value("convert/resolution", "オリジナル")
        )
        
        # 音声圧縮設定
        self.audio_codec_combo.setCurrentText(
            settings.value("audio/codec", "mp3")
        )
        self.audio_bitrate_combo.setCurrentText(
            settings.value("audio/bitrate", "192k")
        )
        self.sample_rate_combo.setCurrentText(
            settings.value("audio/sample_rate", "オリジナル維持")
        )
        self.channel_combo.setCurrentText(
            settings.value("audio/channels", "オリジナル維持")
        )
        self.quality_slider.setValue(
            settings.value("audio/quality", 80, type=int)
        )
        self.normalize_audio_check.setChecked(
            settings.value("audio/normalize", False, type=bool)
        )
        self.noise_reduction_check.setChecked(
            settings.value("audio/noise_reduction", False, type=bool)
        )
        self.fade_in_spin.setValue(
            settings.value("audio/fade_in", 0, type=int)
        )
        self.fade_out_spin.setValue(
            settings.value("audio/fade_out", 0, type=int)
        )
        
        # 一般設定
        self.max_workers_spin.setValue(
            settings.value("general/max_workers", 4, type=int)
        )
        self.retry_count_spin.setValue(
            settings.value("network/retry_count", 3, type=int)
        )
        self.timeout_spin.setValue(
            settings.value("network/timeout", 60, type=int)
        )
    
    def save_settings(self):
        """設定を保存"""
        settings = QSettings("MediaDownloader", "Settings")
        
        # ダウンロード設定
        settings.setValue("download/output_dir", self.output_dir_edit.text())
        settings.setValue("download/auto_rename", self.auto_rename_check.isChecked())
        settings.setValue("download/video_format", self.video_format_combo.currentText())
        settings.setValue("download/audio_format", self.audio_format_combo.currentText())
        settings.setValue("download/video_quality", self.video_quality_combo.currentText())
        settings.setValue("download/max_filesize", self.max_filesize_edit.text())
        settings.setValue("download/subtitles", self.subtitle_check.isChecked())
        settings.setValue("download/metadata", self.metadata_check.isChecked())
        settings.setValue("download/thumbnail", self.thumbnail_check.isChecked())
        
        # 変換設定
        settings.setValue("convert/hw_accel", self.hw_accel_combo.currentText())
        settings.setValue("convert/video_codec", self.video_codec_combo.currentText())
        settings.setValue("convert/video_bitrate", self.video_bitrate_edit.text())
        settings.setValue("convert/resolution", self.resolution_combo.currentText())
        
        # 音声圧縮設定
        settings.setValue("audio/codec", self.audio_codec_combo.currentText())
        settings.setValue("audio/bitrate", self.audio_bitrate_combo.currentText())
        settings.setValue("audio/sample_rate", self.sample_rate_combo.currentText())
        settings.setValue("audio/channels", self.channel_combo.currentText())
        settings.setValue("audio/quality", self.quality_slider.value())
        settings.setValue("audio/normalize", self.normalize_audio_check.isChecked())
        settings.setValue("audio/noise_reduction", self.noise_reduction_check.isChecked())
        settings.setValue("audio/fade_in", self.fade_in_spin.value())
        settings.setValue("audio/fade_out", self.fade_out_spin.value())
        
        # 一般設定
        settings.setValue("general/max_workers", self.max_workers_spin.value())
        settings.setValue("network/retry_count", self.retry_count_spin.value())
        settings.setValue("network/timeout", self.timeout_spin.value())
    
    def get_download_options(self) -> Dict[str, Any]:
        """ダウンロードオプション取得"""
        return {
            'output_dir': self.output_dir_edit.text(),
            'format': self.video_format_combo.currentText(),
            'audio_format': self.audio_format_combo.currentText(),
            'video_quality': self.video_quality_combo.currentText(),
            'max_filesize': self.max_filesize_edit.text(),
            'subtitles': self.subtitle_check.isChecked(),
            'metadata': self.metadata_check.isChecked(),
            'thumbnail': self.thumbnail_check.isChecked(),
            'auto_rename': self.auto_rename_check.isChecked()
        }
    
    def get_convert_options(self) -> Dict[str, Any]:
        """変換オプション取得"""
        return {
            'hw_accel': self.hw_accel_combo.currentText(),
            'video_codec': self.video_codec_combo.currentText(),
            'video_bitrate': self.video_bitrate_edit.text(),
            'resolution': self.resolution_combo.currentText(),
            'use_hardware': self.hw_accel_combo.currentText() != "CPU（無効）"
        }
    
    def get_audio_options(self) -> Dict[str, Any]:
        """音声オプション取得"""
        return {
            'audio_codec': self.audio_codec_combo.currentText(),
            'audio_bitrate': self.audio_bitrate_combo.currentText(),
            'sample_rate': self.sample_rate_combo.currentText(),
            'channels': self.channel_combo.currentText(),
            'quality': self.quality_slider.value(),
            'normalize': self.normalize_audio_check.isChecked(),
            'noise_reduction': self.noise_reduction_check.isChecked(),
            'fade_in': self.fade_in_spin.value(),
            'fade_out': self.fade_out_spin.value()
        }
    
    def apply_settings(self):
        """設定を適用"""
        self.save_settings()
        QMessageBox.information(self, "設定", "設定を適用しました")
    
    def accept_settings(self):
        """設定を保存して閉じる"""
        self.save_settings()
        self.accept()

class MediaDownloaderGUI(QMainWindow):
    """メインGUIクラス（完全統合版）"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LiveLeaper")
        self.setGeometry(100, 100, 1200, 800)
        
        # インスタンス変数
        self.download_thread = None
        self.convert_thread = None
        self.batch_thread = None
        self.settings_dialog = None
        
        # TaskManagerの初期化（エラーハンドリング付き）
        try:
            self.task_manager = TaskManager()
        except Exception as e:
            logger.error(f"TaskManagerの初期化エラー: {e}")
            self.task_manager = None
        
        # UI初期化
        self.init_ui()
        self.init_menus()
        self.init_status_bar()
        
        # 設定読み込み
        self.load_window_settings()
        
        # 定期更新タイマー
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_status)
        self.update_timer.start(1000)  # 1秒間隔
        
        # 初回起動チェック
        self.check_first_run()
    
    def init_ui(self):
        """UI初期化"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # メインレイアウト
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # タブウィジェット
        tab_widget = QTabWidget()
        main_layout.addWidget(tab_widget)
        
        # ダウンロードタブ
        download_tab = self.create_download_tab()
        tab_widget.addTab(download_tab, "ダウンロード")
        
        # 変換タブ
        convert_tab = self.create_convert_tab()
        tab_widget.addTab(convert_tab, "変換・圧縮")
        
        # バッチタブ
        batch_tab = self.create_batch_tab()
        tab_widget.addTab(batch_tab, "バッチ処理")
        
        # ログタブ
        log_tab = self.create_log_tab()
        tab_widget.addTab(log_tab, "ログ")
    
    def create_download_tab(self) -> QWidget:
        """ダウンロードタブを作成"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # URL入力エリア
        url_group = QGroupBox("URL入力（自動修正対応）")
        url_layout = QVBoxLayout()
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("動画URLを入力してください（YouTube、ニコニコ動画対応）...")
        url_layout.addWidget(self.url_input)
        
        # URL例表示
        url_examples = QLabel("""
        対応URL例:
        • YouTube: https://www.youtube.com/watch?v=...
        • YouTube Shorts: https://www.youtube.com/shorts/...
        • ニコニコ動画: https://www.nicovideo.jp/watch/...
        """)
        url_examples.setStyleSheet("color: #666; font-size: 10px;")
        url_layout.addWidget(url_examples)
        
        # URL入力ボタン
        url_buttons = QHBoxLayout()
        
        self.download_video_btn = QPushButton("動画ダウンロード")
        self.download_video_btn.clicked.connect(self.download_video)
        url_buttons.addWidget(self.download_video_btn)
        
        self.download_audio_btn = QPushButton("音声抽出")
        self.download_audio_btn.clicked.connect(self.download_audio)
        url_buttons.addWidget(self.download_audio_btn)
        
        self.get_info_btn = QPushButton("動画情報取得")
        self.get_info_btn.clicked.connect(self.get_video_info)
        url_buttons.addWidget(self.get_info_btn)
        
        url_layout.addLayout(url_buttons)
        url_group.setLayout(url_layout)
        layout.addWidget(url_group)
        
        # 簡易設定
        quick_settings_group = QGroupBox("簡易設定")
        quick_layout = QFormLayout()
        
        self.quick_output_dir = QLineEdit()
        quick_browse_btn = QPushButton("参照")
        quick_browse_btn.clicked.connect(self.browse_quick_output)
        
        quick_dir_layout = QHBoxLayout()
        quick_dir_layout.addWidget(self.quick_output_dir)
        quick_dir_layout.addWidget(quick_browse_btn)
        quick_layout.addRow("保存先:", quick_dir_layout)
        
        self.quick_quality_combo = QComboBox()
        self.quick_quality_combo.addItems(["最高品質", "高品質", "中品質", "低品質"])
        quick_layout.addRow("品質:", self.quick_quality_combo)
        
        quick_settings_group.setLayout(quick_layout)
        layout.addWidget(quick_settings_group)
        
        # 進捗表示
        progress_group = QGroupBox("進捗")
        progress_layout = QVBoxLayout()
        
        self.download_progress = QProgressBar()
        progress_layout.addWidget(self.download_progress)
        
        self.download_status_label = QLabel("待機中")
        progress_layout.addWidget(self.download_status_label)
        
        # 進捗詳細
        progress_details_layout = QHBoxLayout()
        self.speed_label = QLabel("速度: -")
        self.eta_label = QLabel("残り時間: -")
        self.size_label = QLabel("サイズ: -")
        progress_details_layout.addWidget(self.speed_label)
        progress_details_layout.addWidget(self.eta_label)
        progress_details_layout.addWidget(self.size_label)
        progress_layout.addLayout(progress_details_layout)
        
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
        # 動画情報表示
        info_group = QGroupBox("動画情報")
        info_layout = QFormLayout()
        
        self.video_title_label = QLabel("-")
        self.video_title_label.setWordWrap(True)
        info_layout.addRow("タイトル:", self.video_title_label)
        
        self.video_duration_label = QLabel("-")
        info_layout.addRow("再生時間:", self.video_duration_label)
        
        self.video_uploader_label = QLabel("-")
        info_layout.addRow("投稿者:", self.video_uploader_label)
        
        self.video_view_count_label = QLabel("-")
        info_layout.addRow("再生回数:", self.video_view_count_label)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def create_convert_tab(self) -> QWidget:
        """変換・圧縮タブを作成"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # ファイル選択
        file_group = QGroupBox("ファイル選択")
        file_layout = QFormLayout()
        
        # 入力ファイル
        input_layout = QHBoxLayout()
        self.input_file_edit = QLineEdit()
        input_browse_btn = QPushButton("参照")
        input_browse_btn.clicked.connect(self.browse_input_file)
        input_layout.addWidget(self.input_file_edit)
        input_layout.addWidget(input_browse_btn)
        file_layout.addRow("入力ファイル:", input_layout)
        
        # 出力ファイル
        output_layout = QHBoxLayout()
        self.output_file_edit = QLineEdit()
        output_browse_btn = QPushButton("参照")
        output_browse_btn.clicked.connect(self.browse_output_file)
        output_layout.addWidget(self.output_file_edit)
        output_layout.addWidget(output_browse_btn)
        file_layout.addRow("出力ファイル:", output_layout)
        
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)
        
        # 変換モード選択
        mode_group = QGroupBox("変換モード")
        mode_layout = QVBoxLayout()
        
        self.mode_button_group = QButtonGroup()
        self.video_convert_radio = QRadioButton("動画変換")
        self.audio_extract_radio = QRadioButton("音声抽出")
        self.audio_convert_radio = QRadioButton("音声変換・圧縮")
        
        self.video_convert_radio.setChecked(True)
        
        self.mode_button_group.addButton(self.video_convert_radio, 0)
        self.mode_button_group.addButton(self.audio_extract_radio, 1)
        self.mode_button_group.addButton(self.audio_convert_radio, 2)
        
        mode_layout.addWidget(self.video_convert_radio)
        mode_layout.addWidget(self.audio_extract_radio)
        mode_layout.addWidget(self.audio_convert_radio)
        
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)
        
        # 音声圧縮設定（詳細版）
        audio_group = QGroupBox("音声設定")
        audio_layout = QGridLayout()
        
        audio_layout.addWidget(QLabel("形式:"), 0, 0)
        self.convert_audio_format_combo = QComboBox()
        self.convert_audio_format_combo.addItems(["mp3", "aac", "opus", "flac", "wav", "ogg"])
        audio_layout.addWidget(self.convert_audio_format_combo, 0, 1)
        
        audio_layout.addWidget(QLabel("品質:"), 0, 2)
        self.convert_audio_quality_combo = QComboBox()
        self.convert_audio_quality_combo.addItems(["最高品質", "高品質", "中品質", "低品質", "カスタム"])
        audio_layout.addWidget(self.convert_audio_quality_combo, 0, 3)
        
        audio_layout.addWidget(QLabel("ビットレート:"), 1, 0)
        self.convert_bitrate_combo = QComboBox()
        self.convert_bitrate_combo.addItems(["64k", "96k", "128k", "160k", "192k", "256k", "320k"])
        audio_layout.addWidget(self.convert_bitrate_combo, 1, 1)
        
        audio_layout.addWidget(QLabel("サンプルレート:"), 1, 2)
        self.convert_sample_rate_combo = QComboBox()
        self.convert_sample_rate_combo.addItems(["オリジナル", "22050 Hz", "44100 Hz", "48000 Hz"])
        audio_layout.addWidget(self.convert_sample_rate_combo, 1, 3)
        
        audio_group.setLayout(audio_layout)
        layout.addWidget(audio_group)
        
        # 圧縮詳細設定
        compress_group = QGroupBox("圧縮設定")
        compress_layout = QVBoxLayout()
        
        # 品質スライダー
        quality_layout = QHBoxLayout()
        quality_layout.addWidget(QLabel("圧縮強度:"))
        self.compress_quality_slider = QSlider(Qt.Horizontal)
        self.compress_quality_slider.setRange(0, 100)
        self.compress_quality_slider.setValue(70)
        self.compress_quality_slider.valueChanged.connect(self.update_compress_quality_label)
        quality_layout.addWidget(self.compress_quality_slider)
        
        self.compress_quality_label = QLabel("70% (バランス)")
        quality_layout.addWidget(self.compress_quality_label)
        compress_layout.addLayout(quality_layout)
        
        # 追加オプション
        options_layout = QHBoxLayout()
        self.normalize_check = QCheckBox("音量正規化")
        self.trim_silence_check = QCheckBox("無音部分カット")
        options_layout.addWidget(self.normalize_check)
        options_layout.addWidget(self.trim_silence_check)
        compress_layout.addLayout(options_layout)
        
        compress_group.setLayout(compress_layout)
        layout.addWidget(compress_group)
        
        # 変換ボタン
        convert_buttons = QHBoxLayout()
        
        self.convert_btn = QPushButton("変換開始")
        self.convert_btn.clicked.connect(self.start_conversion)
        convert_buttons.addWidget(self.convert_btn)
        
        self.stop_convert_btn = QPushButton("変換停止")
        self.stop_convert_btn.clicked.connect(self.stop_conversion)
        self.stop_convert_btn.setEnabled(False)
        convert_buttons.addWidget(self.stop_convert_btn)
        
        self.preview_btn = QPushButton("プレビュー（10秒）")
        self.preview_btn.clicked.connect(self.preview_conversion)
        convert_buttons.addWidget(self.preview_btn)
        
        layout.addLayout(convert_buttons)
        
        # 変換進捗
        convert_progress_group = QGroupBox("変換進捗")
        convert_progress_layout = QVBoxLayout()
        
        self.convert_progress = QProgressBar()
        convert_progress_layout.addWidget(self.convert_progress)
        
        self.convert_status_label = QLabel("待機中")
        convert_progress_layout.addWidget(self.convert_status_label)
        
        # 変換詳細情報
        convert_details_layout = QHBoxLayout()
        self.convert_fps_label = QLabel("FPS: -")
        self.convert_bitrate_label = QLabel("ビットレート: -")
        self.convert_time_label = QLabel("処理時間: -")
        convert_details_layout.addWidget(self.convert_fps_label)
        convert_details_layout.addWidget(self.convert_bitrate_label)
        convert_details_layout.addWidget(self.convert_time_label)
        convert_progress_layout.addLayout(convert_details_layout)
        
        convert_progress_group.setLayout(convert_progress_layout)
        layout.addWidget(convert_progress_group)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def create_batch_tab(self) -> QWidget:
        """バッチ処理タブを作成"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # URLリスト管理
        list_group = QGroupBox("URLリスト管理")
        list_layout = QVBoxLayout()
        
        # URLリスト操作ボタン
        list_buttons = QHBoxLayout()
        
        load_list_btn = QPushButton("リスト読み込み")
        load_list_btn.clicked.connect(self.load_url_list)
        list_buttons.addWidget(load_list_btn)
        
        save_list_btn = QPushButton("リスト保存")
        save_list_btn.clicked.connect(self.save_url_list)
        list_buttons.addWidget(save_list_btn)
        
        clear_list_btn = QPushButton("リストクリア")
        clear_list_btn.clicked.connect(self.clear_url_list)
        list_buttons.addWidget(clear_list_btn)
        
        validate_btn = QPushButton("URL検証")
        validate_btn.clicked.connect(self.validate_urls)
        list_buttons.addWidget(validate_btn)
        
        list_layout.addLayout(list_buttons)
        
        # URLリストウィジェット
        self.url_list_widget = QListWidget()
        self.url_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.url_list_widget.customContextMenuRequested.connect(self.show_url_context_menu)
        list_layout.addWidget(self.url_list_widget)
        
        # URL追加
        add_layout = QHBoxLayout()
        self.add_url_edit = QLineEdit()
        self.add_url_edit.setPlaceholderText("URLを入力して追加...")
        add_url_btn = QPushButton("追加")
        add_url_btn.clicked.connect(self.add_url_to_list)
        add_layout.addWidget(self.add_url_edit)
        add_layout.addWidget(add_url_btn)
        list_layout.addLayout(add_layout)
        
        # URL統計
        self.url_stats_label = QLabel("URL数: 0")
        list_layout.addWidget(self.url_stats_label)
        
        list_group.setLayout(list_layout)
        layout.addWidget(list_group)
        
        # バッチ処理設定
        batch_group = QGroupBox("バッチ処理設定")
        batch_layout = QFormLayout()
        
        self.batch_mode_combo = QComboBox()
        self.batch_mode_combo.addItems(["動画ダウンロード", "音声抽出", "混在（自動判定）"])
        batch_layout.addRow("処理モード:", self.batch_mode_combo)
        
        self.batch_workers_spin = QSpinBox()
        self.batch_workers_spin.setRange(1, 8)
        self.batch_workers_spin.setValue(2)
        batch_layout.addRow("並列数:", self.batch_workers_spin)
        
        self.batch_retry_check = QCheckBox("失敗時リトライ")
        self.batch_retry_check.setChecked(True)
        batch_layout.addRow(self.batch_retry_check)
        
        self.batch_continue_check = QCheckBox("エラー時継続")
        self.batch_continue_check.setChecked(True)
        batch_layout.addRow(self.batch_continue_check)
        
        batch_group.setLayout(batch_layout)
        layout.addWidget(batch_group)
        
        # バッチ処理ボタン
        batch_buttons = QHBoxLayout()
        
        self.start_batch_btn = QPushButton("バッチ処理開始")
        self.start_batch_btn.clicked.connect(self.start_batch_download)
        batch_buttons.addWidget(self.start_batch_btn)
        
        self.stop_batch_btn = QPushButton("バッチ処理停止")
        self.stop_batch_btn.clicked.connect(self.stop_batch_download)
        self.stop_batch_btn.setEnabled(False)
        batch_buttons.addWidget(self.stop_batch_btn)
        
        self.pause_batch_btn = QPushButton("一時停止")
        self.pause_batch_btn.setEnabled(False)
        batch_buttons.addWidget(self.pause_batch_btn)
        
        layout.addLayout(batch_buttons)
        
        # バッチ進捗
        batch_progress_group = QGroupBox("バッチ進捗")
        batch_progress_layout = QVBoxLayout()
        
        self.batch_progress = QProgressBar()
        batch_progress_layout.addWidget(self.batch_progress)
        
        self.batch_status_label = QLabel("待機中")
        batch_progress_layout.addWidget(self.batch_status_label)
        
        # バッチ詳細統計
        batch_stats_layout = QGridLayout()
        
        self.batch_total_label = QLabel("総数: 0")
        self.batch_completed_label = QLabel("完了: 0")
        self.batch_failed_label = QLabel("失敗: 0")
        self.batch_remaining_label = QLabel("残り: 0")
        
        batch_stats_layout.addWidget(self.batch_total_label, 0, 0)
        batch_stats_layout.addWidget(self.batch_completed_label, 0, 1)
        batch_stats_layout.addWidget(self.batch_failed_label, 1, 0)
        batch_stats_layout.addWidget(self.batch_remaining_label, 1, 1)
        
        batch_progress_layout.addLayout(batch_stats_layout)
        
        batch_progress_group.setLayout(batch_progress_layout)
        layout.addWidget(batch_progress_group)
        
        widget.setLayout(layout)
        return widget
    
    def create_log_tab(self) -> QWidget:
        """ログタブを作成"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # ログ操作ボタン
        log_buttons = QHBoxLayout()
        
        clear_log_btn = QPushButton("ログクリア")
        clear_log_btn.clicked.connect(self.clear_log)
        log_buttons.addWidget(clear_log_btn)
        
        save_log_btn = QPushButton("ログ保存")
        save_log_btn.clicked.connect(self.save_log)
        log_buttons.addWidget(save_log_btn)
        
        export_log_btn = QPushButton("エラーログ抽出")
        export_log_btn.clicked.connect(self.export_error_log)
        log_buttons.addWidget(export_log_btn)
        
        # ログレベルフィルター
        log_buttons.addWidget(QLabel("フィルター:"))
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["すべて", "エラーのみ", "警告以上", "情報以上"])
        self.log_level_combo.currentTextChanged.connect(self.filter_log)
        log_buttons.addWidget(self.log_level_combo)
        
        log_buttons.addStretch()
        layout.addLayout(log_buttons)
        
        # ログ表示
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_text)
        
        # ログ統計
        log_stats_layout = QHBoxLayout()
        self.log_stats_label = QLabel("ログ行数: 0")
        self.log_errors_label = QLabel("エラー: 0")
        self.log_warnings_label = QLabel("警告: 0")
        
        log_stats_layout.addWidget(self.log_stats_label)
        log_stats_layout.addWidget(self.log_errors_label)
        log_stats_layout.addWidget(self.log_warnings_label)
        log_stats_layout.addStretch()
        
        layout.addLayout(log_stats_layout)
        
        widget.setLayout(layout)
        return widget
    
    def init_menus(self):
        """メニュー初期化"""
        menubar = self.menuBar()
        
        # ファイルメニュー
        file_menu = menubar.addMenu("ファイル")
        
        setup_action = QAction("初期設定ウィザード", self)
        setup_action.triggered.connect(self.run_setup_wizard)
        file_menu.addAction(setup_action)
        
        settings_action = QAction("詳細設定", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.show_settings)
        file_menu.addAction(settings_action)
        
        file_menu.addSeparator()
        
        import_action = QAction("URLリストインポート", self)
        import_action.setShortcut("Ctrl+I")
        import_action.triggered.connect(self.load_url_list)
        file_menu.addAction(import_action)
        
        export_action = QAction("URLリストエクスポート", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self.save_url_list)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("終了", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # ツールメニュー
        tools_menu = menubar.addMenu("ツール")
        
        url_cleaner_action = QAction("URL修正テスト", self)
        url_cleaner_action.triggered.connect(self.test_url_cleaner)
        tools_menu.addAction(url_cleaner_action)
        
        dependency_action = QAction("依存関係チェック", self)
        dependency_action.triggered.connect(self.check_dependencies)
        tools_menu.addAction(dependency_action)
        
        benchmark_action = QAction("変換性能テスト", self)
        benchmark_action.triggered.connect(self.run_benchmark)
        tools_menu.addAction(benchmark_action)
        
        # ヘルプメニュー
        help_menu = menubar.addMenu("ヘルプ")
        
        about_action = QAction("バージョン情報", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        help_action = QAction("使い方", self)
        help_action.triggered.connect(self.show_help)
        help_menu.addAction(help_action)
    
    def init_status_bar(self):
        """ステータスバー初期化"""
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("準備完了")
        
        # 右側の情報表示
        self.task_count_label = QLabel("タスク: 0")
        self.status_bar.addPermanentWidget(self.task_count_label)
        
        self.memory_label = QLabel("メモリ: -")
        self.status_bar.addPermanentWidget(self.memory_label)
    
    def check_first_run(self):
        """初回起動チェック"""
        settings = QSettings("MediaDownloader", "Settings")
        if not settings.value("setup_completed", False, type=bool):
            reply = QMessageBox.question(
                self, "初回起動", 
                "初回起動のようです。初期設定ウィザードを実行しますか？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                self.run_setup_wizard()
    
    def run_setup_wizard(self):
        """初期設定ウィザードを実行"""
        try:
            wizard = SetupWizard()
            if wizard.exec_() == wizard.Accepted:
                QMessageBox.information(self, "完了", "初期設定が完了しました。")
                self.load_quick_settings()
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"初期設定ウィザードの実行に失敗しました:\n{e}")
    
    def load_quick_settings(self):
        """簡易設定の読み込み"""
        settings = QSettings("MediaDownloader", "Settings")
        self.quick_output_dir.setText(
            settings.value("download/output_dir", "./downloads")
        )
    
    def browse_quick_output(self):
        """簡易出力ディレクトリ選択"""
        directory = QFileDialog.getExistingDirectory(
            self, "出力ディレクトリを選択", self.quick_output_dir.text()
        )
        if directory:
            self.quick_output_dir.setText(directory)
    
    def download_video(self):
        """動画ダウンロード"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "警告", "URLを入力してください")
            return
        
        options = self.get_download_options()
        options['audio_only'] = False
        
        self.start_download_thread(url, options)
    
    def download_audio(self):
        """音声ダウンロード"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "警告", "URLを入力してください")
            return
        
        options = self.get_download_options()
        options['audio_only'] = True
        
        self.start_download_thread(url, options)
    
    def start_download_thread(self, url: str, options: Dict[str, Any]):
        """ダウンロードスレッド開始"""
        if self.download_thread and self.download_thread.isRunning():
            QMessageBox.warning(self, "警告", "ダウンロードが既に実行中です")
            return
        
        self.download_thread = DownloadThread(url, options)
        self.download_thread.progress_updated.connect(self.update_download_progress)
        self.download_thread.finished.connect(self.download_finished)
        self.download_thread.start()
        
        self.download_video_btn.setEnabled(False)
        self.download_audio_btn.setEnabled(False)
        self.log_message(f"ダウンロード開始: {URLCleaner.clean_url(url)}")
    
    def update_download_progress(self, progress_info: Dict[str, Any]):
        """ダウンロード進捗更新"""
        percentage = progress_info.get('percentage', 0)
        status = progress_info.get('status', 'downloading')
        filename = progress_info.get('filename', '')
        speed = progress_info.get('speed', 0)
        eta = progress_info.get('eta', 0)
        total_bytes = progress_info.get('total_bytes', 0)
        
        self.download_progress.setValue(int(percentage))
        self.download_status_label.setText(f"{status}: {Path(filename).name if filename else ''}")
        
        # 詳細情報更新
        if speed:
            self.speed_label.setText(f"速度: {format_bytes(speed)}/s")
        if eta:
            self.eta_label.setText(f"残り時間: {format_duration(eta)}")
        if total_bytes:
            self.size_label.setText(f"サイズ: {format_bytes(total_bytes)}")
    
    def download_finished(self, success: bool, result: str):
        """ダウンロード完了"""
        self.download_video_btn.setEnabled(True)
        self.download_audio_btn.setEnabled(True)
        
        if success:
            self.log_message(f"ダウンロード完了: {result}")
            self.download_progress.setValue(100)
            self.download_status_label.setText("完了")
            QMessageBox.information(self, "完了", f"ダウンロードが完了しました\n{result}")
        else:
            self.log_message(f"ダウンロードエラー: {result}")
            self.download_progress.setValue(0)
            self.download_status_label.setText("エラー")
            QMessageBox.critical(self, "エラー", f"ダウンロードに失敗しました\n{result}")
    
    def get_video_info(self):
        """動画情報取得"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "警告", "URLを入力してください")
            return
        
        try:
            downloader = VideoDownloader()
            clean_url = URLCleaner.clean_url(url)
            info = downloader.get_video_info(clean_url)
            
            if info:
                self.video_title_label.setText(info.get('title', '-'))
                duration = info.get('duration', 0)
                self.video_duration_label.setText(format_duration(duration) if duration else '-')
                self.video_uploader_label.setText(info.get('uploader', '-'))
                
                view_count = info.get('view_count', 0)
                if view_count:
                    self.video_view_count_label.setText(f"{view_count:,}")
                else:
                    self.video_view_count_label.setText('-')
                
                self.log_message(f"動画情報取得完了: {info.get('title', 'Unknown')}")
                
                # URL修正の表示
                if clean_url != url:
                    self.log_message(f"URL修正: {url} -> {clean_url}")
            else:
                QMessageBox.warning(self, "警告", "動画情報の取得に失敗しました")
                
        except Exception as e:
            self.log_message(f"動画情報取得エラー: {e}")
            QMessageBox.critical(self, "エラー", f"動画情報の取得に失敗しました\n{e}")
    
    def browse_input_file(self):
        """入力ファイル選択"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "入力ファイルを選択",
            "", "メディアファイル (*.mp4 *.avi *.mkv *.webm *.mov *.mp3 *.aac *.wav *.flac *.ogg);;すべてのファイル (*)"
        )
        if file_path:
            self.input_file_edit.setText(file_path)
            # 出力ファイル名を自動生成
            self.auto_generate_output_filename()
    
    def auto_generate_output_filename(self):
        """出力ファイル名の自動生成"""
        input_path = self.input_file_edit.text()
        if not input_path:
            return
        
        input_file = Path(input_path)
        
        if self.audio_extract_radio.isChecked() or self.audio_convert_radio.isChecked():
            # 音声形式の場合
            audio_format = self.convert_audio_format_combo.currentText()
            output_path = input_file.with_suffix(f'.{audio_format}')
        else:
            # 動画変換の場合
            output_path = input_file.with_suffix('.mp4')
        
        self.output_file_edit.setText(str(output_path))
    
    def browse_output_file(self):
        """出力ファイル選択"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "出力ファイルを選択",
            "", "メディアファイル (*.mp4 *.avi *.mkv *.webm *.mov *.mp3 *.aac *.wav *.flac *.ogg);;すべてのファイル (*)"
        )
        if file_path:
            self.output_file_edit.setText(file_path)
    
    def update_compress_quality_label(self, value):
        """圧縮品質ラベル更新"""
        if value < 30:
            quality_text = "低品質（小サイズ）"
        elif value < 60:
            quality_text = "中品質（バランス）"
        elif value < 85:
            quality_text = "高品質（大サイズ）"
        else:
            quality_text = "最高品質（無損失近似）"
        
        self.compress_quality_label.setText(f"{value}% ({quality_text})")
    
    def start_conversion(self):
        """変換開始"""
        input_file = self.input_file_edit.text().strip()
        output_file = self.output_file_edit.text().strip()
        
        if not input_file or not output_file:
            QMessageBox.warning(self, "警告", "入力ファイルと出力ファイルを指定してください")
            return
        
        if not Path(input_file).exists():
            QMessageBox.warning(self, "警告", "入力ファイルが見つかりません")
            return
        
        options = self.get_convert_options()
        options.update(self.get_audio_conversion_options())
        
        if self.convert_thread and self.convert_thread.isRunning():
            QMessageBox.warning(self, "警告", "変換が既に実行中です")
            return
        
        self.convert_thread = ConvertThread(input_file, output_file, options)
        self.convert_thread.progress_updated.connect(self.update_convert_progress)
        self.convert_thread.finished.connect(self.convert_finished)
        self.convert_thread.start()
        
        self.convert_btn.setEnabled(False)
        self.stop_convert_btn.setEnabled(True)
        self.log_message(f"変換開始: {input_file} -> {output_file}")
    
    def stop_conversion(self):
        """変換停止"""
        if self.convert_thread and self.convert_thread.isRunning():
            self.convert_thread.terminate()
            self.convert_thread.wait()
            self.convert_btn.setEnabled(True)
            self.stop_convert_btn.setEnabled(False)
            self.log_message("変換を停止しました")
    
    def preview_conversion(self):
        """変換プレビュー（10秒）"""
        input_file = self.input_file_edit.text().strip()
        if not input_file or not Path(input_file).exists():
            QMessageBox.warning(self, "警告", "有効な入力ファイルを指定してください")
            return
        
        # プレビュー用の一時ファイル作成
        preview_file = Path(input_file).with_name("preview_" + Path(input_file).name)
        
        options = self.get_convert_options()
        options.update(self.get_audio_conversion_options())
        options['preview'] = True
        options['duration'] = 10  # 10秒のプレビュー
        
        self.convert_thread = ConvertThread(input_file, str(preview_file), options)
        self.convert_thread.finished.connect(
            lambda success, result: self.preview_finished(success, result, str(preview_file))
        )
        self.convert_thread.start()
        
        self.log_message("プレビュー変換を開始しました（10秒）")
    
    def preview_finished(self, success: bool, result: str, preview_file: str):
        """プレビュー変換完了"""
        if success:
            reply = QMessageBox.question(
                self, "プレビュー完了", 
                f"プレビューファイルが作成されました:\n{preview_file}\n\nファイルを開きますか？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                try:
                    os.startfile(preview_file)  # Windows
                except:
                    try:
                        os.system(f'open "{preview_file}"')  # macOS
                    except:
                        os.system(f'xdg-open "{preview_file}"')  # Linux
        else:
            QMessageBox.critical(self, "エラー", f"プレビュー変換に失敗しました:\n{result}")
    
    def update_convert_progress(self, progress_info: Dict[str, Any]):
        """変換進捗更新"""
        percentage = progress_info.get('percentage', 0)
        status = progress_info.get('status', 'converting')
        fps = progress_info.get('fps', 0)
        bitrate = progress_info.get('bitrate', '')
        processed_time = progress_info.get('processed_time', 0)
        
        self.convert_progress.setValue(int(percentage))
        self.convert_status_label.setText(f"{status}: {percentage:.1f}%")
        
        # 詳細情報更新
        if fps:
            self.convert_fps_label.setText(f"FPS: {fps:.1f}")
        if bitrate:
            self.convert_bitrate_label.setText(f"ビットレート: {bitrate}")
        if processed_time:
            self.convert_time_label.setText(f"処理時間: {format_duration(processed_time)}")
    
    def convert_finished(self, success: bool, result: str):
        """変換完了"""
        self.convert_btn.setEnabled(True)
        self.stop_convert_btn.setEnabled(False)
        
        if success:
            self.log_message(f"変換完了: {result}")
            self.convert_progress.setValue(100)
            self.convert_status_label.setText("完了")
            QMessageBox.information(self, "完了", f"変換が完了しました\n{result}")
        else:
            self.log_message(f"変換エラー: {result}")
            self.convert_progress.setValue(0)
            self.convert_status_label.setText("エラー")
            QMessageBox.critical(self, "エラー", f"変換に失敗しました\n{result}")
    
    def load_url_list(self):
        """URLリスト読み込み"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "URLリストファイルを選択",
            "", "テキストファイル (*.txt);;すべてのファイル (*)"
        )
        if file_path:
            try:
                urls = parse_url_list_file(file_path)
                self.url_list_widget.clear()
                for url in urls:
                    self.url_list_widget.addItem(url)
                self.update_url_stats()
                self.log_message(f"URLリスト読み込み完了: {len(urls)}件")
            except Exception as e:
                QMessageBox.critical(self, "エラー", f"URLリストの読み込みに失敗しました\n{e}")
    
    def save_url_list(self):
        """URLリスト保存"""
        if self.url_list_widget.count() == 0:
            QMessageBox.warning(self, "警告", "保存するURLがありません")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "URLリストファイルを保存",
            "urls.txt", "テキストファイル (*.txt);;すべてのファイル (*)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    for i in range(self.url_list_widget.count()):
                        f.write(self.url_list_widget.item(i).text() + '\n')
                self.log_message(f"URLリスト保存完了: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "エラー", f"URLリストの保存に失敗しました\n{e}")
    
    def clear_url_list(self):
        """URLリストクリア"""
        if self.url_list_widget.count() > 0:
            reply = QMessageBox.question(
                self, "確認", "URLリストをクリアしますか？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.url_list_widget.clear()
                self.update_url_stats()
                self.log_message("URLリストをクリアしました")
    
    def validate_urls(self):
        """URL検証"""
        valid_count = 0
        invalid_urls = []
        
        for i in range(self.url_list_widget.count()):
            url = self.url_list_widget.item(i).text()
            try:
                downloader = VideoDownloader()
                if downloader.is_supported_url(url):
                    valid_count += 1
                else:
                    invalid_urls.append(url)
            except:
                invalid_urls.append(url)
        
        message = f"検証結果:\n有効: {valid_count}件\n無効: {len(invalid_urls)}件"
        if invalid_urls:
            message += f"\n\n無効なURL:\n" + "\n".join(invalid_urls[:5])
            if len(invalid_urls) > 5:
                message += f"\n...他{len(invalid_urls) - 5}件"
        
        QMessageBox.information(self, "URL検証結果", message)
    
    def add_url_to_list(self):
        """URLをリストに追加"""
        url = self.add_url_edit.text().strip()
        if url:
            # URL重複チェック
            for i in range(self.url_list_widget.count()):
                if self.url_list_widget.item(i).text() == url:
                    QMessageBox.warning(self, "警告", "このURLは既にリストに存在します")
                    return
            
            self.url_list_widget.addItem(url)
            self.add_url_edit.clear()
            self.update_url_stats()
            self.log_message(f"URLを追加: {URLCleaner.clean_url(url)}")
    
    def show_url_context_menu(self, position):
        """URLリストコンテキストメニュー"""
        if self.url_list_widget.itemAt(position):
            menu = QMenu()
            
            delete_action = QAction("削除", self)
            delete_action.triggered.connect(self.delete_selected_url)
            menu.addAction(delete_action)
            
            clean_action = QAction("URL修正", self)
            clean_action.triggered.connect(self.clean_selected_url)
            menu.addAction(clean_action)
            
            info_action = QAction("動画情報表示", self)
            info_action.triggered.connect(self.show_selected_url_info)
            menu.addAction(info_action)
            
            menu.exec_(self.url_list_widget.mapToGlobal(position))
    
    def delete_selected_url(self):
        """選択されたURLを削除"""
        current_row = self.url_list_widget.currentRow()
        if current_row >= 0:
            item = self.url_list_widget.takeItem(current_row)
            if item:
                self.update_url_stats()
                self.log_message(f"URLを削除: {item.text()}")
    
    def clean_selected_url(self):
        """選択されたURLを修正"""
        current_row = self.url_list_widget.currentRow()
        if current_row >= 0:
            item = self.url_list_widget.item(current_row)
            if item:
                original_url = item.text()
                clean_url = URLCleaner.clean_url(original_url)
                if clean_url != original_url:
                    item.setText(clean_url)
                    self.log_message(f"URL修正: {original_url} -> {clean_url}")
                else:
                    QMessageBox.information(self, "情報", "このURLは既に修正済みです")
    
    def show_selected_url_info(self):
        """選択されたURLの動画情報表示"""
        current_row = self.url_list_widget.currentRow()
        if current_row >= 0:
            item = self.url_list_widget.item(current_row)
            if item:
                url = item.text()
                try:
                    downloader = VideoDownloader()
                    info = downloader.get_video_info(URLCleaner.clean_url(url))
                    if info:
                        info_text = f"""
タイトル: {info.get('title', 'Unknown')}
投稿者: {info.get('uploader', 'Unknown')}
再生時間: {format_duration(info.get('duration', 0))}
再生回数: {info.get('view_count', 0):,}
                        """
                        QMessageBox.information(self, "動画情報", info_text)
                    else:
                        QMessageBox.warning(self, "警告", "動画情報の取得に失敗しました")
                except Exception as e:
                    QMessageBox.critical(self, "エラー", f"動画情報取得エラー:\n{e}")
    
    def update_url_stats(self):
        """URL統計更新"""
        count = self.url_list_widget.count()
        self.url_stats_label.setText(f"URL数: {count}")
        
        # バッチ進捗の総数更新
        self.batch_total_label.setText(f"総数: {count}")
        self.batch_remaining_label.setText(f"残り: {count}")
    
    def start_batch_download(self):
        """バッチダウンロード開始"""
        if self.url_list_widget.count() == 0:
            QMessageBox.warning(self, "警告", "ダウンロードするURLがありません")
            return
        
        # URLリストを取得
        urls = []
        for i in range(self.url_list_widget.count()):
            urls.append(self.url_list_widget.item(i).text())
        
        # バッチオプション設定
        options = self.get_download_options()
        mode = self.batch_mode_combo.currentText()
        if mode == "音声抽出":
            options['audio_only'] = True
        elif mode == "動画ダウンロード":
            options['audio_only'] = False
        # 混在モードは個別判定
        
        self.batch_thread = BatchDownloadThread(urls, options)
        self.batch_thread.progress_updated.connect(self.update_batch_progress)
        self.batch_thread.item_finished.connect(self.batch_item_finished)
        self.batch_thread.finished.connect(self.batch_finished)
        self.batch_thread.start()
        
        self.start_batch_btn.setEnabled(False)
        self.stop_batch_btn.setEnabled(True)
        self.pause_batch_btn.setEnabled(True)
        
        self.log_message(f"バッチダウンロード開始: {len(urls)}件")
    
    def stop_batch_download(self):
        """バッチダウンロード停止"""
        if self.batch_thread and self.batch_thread.isRunning():
            self.batch_thread.stop()
            self.batch_thread.wait()
            
            self.start_batch_btn.setEnabled(True)
            self.stop_batch_btn.setEnabled(False)
            self.pause_batch_btn.setEnabled(False)
            
            self.log_message("バッチダウンロードを停止しました")
    
    def update_batch_progress(self, current: int, total: int, status: str):
        """バッチ進捗更新"""
        if total > 0:
            percentage = (current / total) * 100
            self.batch_progress.setValue(int(percentage))
        
        self.batch_status_label.setText(status)
        self.batch_remaining_label.setText(f"残り: {total - current}")
    
    def batch_item_finished(self, url: str, success: bool, result: str):
        """バッチアイテム完了"""
        completed = int(self.batch_completed_label.text().split(': ')[1]) if ': ' in self.batch_completed_label.text() else 0
        failed = int(self.batch_failed_label.text().split(': ')[1]) if ': ' in self.batch_failed_label.text() else 0
        
        if success:
            completed += 1
            self.log_message(f"バッチ完了: {url} -> {result}")
        else:
            failed += 1
            self.log_message(f"バッチ失敗: {url} - {result}")
        
        self.batch_completed_label.setText(f"完了: {completed}")
        self.batch_failed_label.setText(f"失敗: {failed}")
    
    def batch_finished(self, results: Dict):
        """バッチ処理完了"""
        self.start_batch_btn.setEnabled(True)
        self.stop_batch_btn.setEnabled(False)
        self.pause_batch_btn.setEnabled(False)
        
        success_count = len(results['success'])
        failed_count = len(results['failed'])
        total = results['total']
        
        message = f"""バッチ処理完了:
        
総数: {total}
成功: {success_count}
失敗: {failed_count}
成功率: {(success_count/total*100):.1f}%"""
        
        QMessageBox.information(self, "バッチ処理完了", message)
        self.log_message(f"バッチ処理完了: 成功 {success_count}件, 失敗 {failed_count}件")
    
    def get_download_options(self) -> Dict[str, Any]:
        """ダウンロードオプション取得"""
        settings = QSettings("MediaDownloader", "Settings")
        
        return {
            'output_dir': self.quick_output_dir.text() or settings.value("download/output_dir", './downloads'),
            'format': settings.value("download/video_format", 'bestvideo+bestaudio/best'),
            'audio_format': settings.value("download/audio_format", 'mp3'),
            'subtitles': settings.value("download/subtitles", False, type=bool),
            'metadata': settings.value("download/metadata", True, type=bool),
            'thumbnail': settings.value("download/thumbnail", False, type=bool),
            'auto_rename': settings.value("download/auto_rename", True, type=bool),
            'max_filesize': settings.value("download/max_filesize", ""),
            'video_quality': self.quick_quality_combo.currentText()
        }
    
    def get_convert_options(self) -> Dict[str, Any]:
        """変換オプション取得"""
        settings = QSettings("MediaDownloader", "Settings")
        
        return {
            'use_hardware': settings.value("convert/hw_accel", "自動検出") != "CPU（無効）",
            'video_codec': settings.value("convert/video_codec", 'h264'),
            'video_bitrate': settings.value("convert/video_bitrate", '8000k'),
            'resolution': settings.value("convert/resolution", 'オリジナル')
        }
    
    def get_audio_conversion_options(self) -> Dict[str, Any]:
        """音声変換オプション取得"""
        return {
            'audio_codec': self.convert_audio_format_combo.currentText(),
            'audio_bitrate': self.convert_bitrate_combo.currentText(),
            'sample_rate': self.convert_sample_rate_combo.currentText(),
            'quality': self.compress_quality_slider.value(),
            'normalize': self.normalize_check.isChecked(),
            'trim_silence': self.trim_silence_check.isChecked()
        }
    
    def show_settings(self):
        """詳細設定ダイアログ表示"""
        if not self.settings_dialog:
            self.settings_dialog = AdvancedSettingsDialog(self)
        
        self.settings_dialog.exec_()
    
    def test_url_cleaner(self):
        """URL修正テスト"""
        test_urls = [
            "https://www.youtube.com/watch?v=JC-uvbOfag4&t=127s&ab_channel=Sayx",
            "https://www.youtube.com/shorts/W5Q63oB3HJs",
            "https://youtu.be/ABC123DEF456",
            "https://www.nicovideo.jp/watch/sm33593693?rf=nvpc&rp=watch&ra=share&rd=x",
        ]
        
        results = []
        for url in test_urls:
            clean_url = URLCleaner.clean_url(url)
            results.append(f"元: {url}\n修正後: {clean_url}\n")
        
        QMessageBox.information(self, "URL修正テスト結果", "\n".join(results))
    
    def check_dependencies(self):
        """依存関係チェック"""
        results = []
        
        # ffmpeg確認
        try:
            import subprocess
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
            results.append("✓ ffmpeg: 利用可能")
        except:
            results.append("✗ ffmpeg: 見つかりません")
        
        # yt-dlp確認
        try:
            import yt_dlp
            results.append("✓ yt-dlp: 利用可能")
        except ImportError:
            results.append("✗ yt-dlp: インストールされていません")
        
        # PyQt5確認
        try:
            from PyQt5 import QtCore
            results.append("✓ PyQt5: 利用可能")
        except ImportError:
            results.append("✗ PyQt5: インストールされていません")
        
        QMessageBox.information(self, "依存関係チェック結果", "\n".join(results))
    
    def run_benchmark(self):
        """変換性能テスト"""
        QMessageBox.information(self, "性能テスト", "変換性能テスト機能は実装予定です")
    
    def show_about(self):
        """バージョン情報表示"""
        about_text = """
LiveLeaper
バージョン: 2.0.0

PyQt5ベースの高機能動画・音声ダウンロード変換ツール
yt-dlpとffmpegを使用

主な機能:
• YouTube・ニコニコ動画等からのダウンロード
• URL自動修正機能
• 高度な音声変換・圧縮機能
• バッチ処理・並列ダウンロード
• ハードウェアエンコード対応
• 初期設定ウィザード
• 詳細なログ機能

開発: Python + PyQt5
エンジン: yt-dlp + FFmpeg
        """
        QMessageBox.about(self, "バージョン情報", about_text)
    
    def show_help(self):
        """使い方表示"""
        help_text = """
【基本的な使い方】

1. ダウンロード:
   - URLを入力して「動画ダウンロード」または「音声抽出」をクリック
   - YouTube Shortsやニコニコ動画のURLは自動修正されます

2. 変換・圧縮:
   - 入力ファイルと出力ファイルを選択
   - 変換モードを選択（動画変換/音声抽出/音声変換）
   - 品質スライダーで圧縮レベルを調整

3. バッチ処理:
   - URLリストを作成・読み込み
   - 並列数を設定してバッチ処理を開始

4. 設定:
   - 初回起動時は初期設定ウィザードが実行されます
   - 詳細設定でより細かな設定が可能です

【対応URL】
• YouTube: 通常URL、Shorts、短縮URL
• ニコニコ動画: 通常URL、共有URL
• その他: yt-dlp対応サイト

【対応形式】
• 動画: MP4, AVI, MKV, WebM, MOV
• 音声: MP3, AAC, Opus, FLAC, WAV, OGG
        """
        QMessageBox.information(self, "使い方", help_text)
    
    def log_message(self, message: str):
        """ログメッセージ追加"""
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        formatted_message = f"{timestamp} {message}"
        self.log_text.append(formatted_message)
        
        # ログ統計更新
        self.update_log_stats()
    
    def clear_log(self):
        """ログクリア"""
        self.log_text.clear()
        self.update_log_stats()
    
    def save_log(self):
        """ログ保存"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "ログファイルを保存",
            f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", 
            "テキストファイル (*.txt);;すべてのファイル (*)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.toPlainText())
                self.log_message(f"ログ保存完了: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "エラー", f"ログの保存に失敗しました\n{e}")
    
    def export_error_log(self):
        """エラーログ抽出"""
        log_text = self.log_text.toPlainText()
        error_lines = [line for line in log_text.split('\n') if 'エラー' in line or 'ERROR' in line]
        
        if not error_lines:
            QMessageBox.information(self, "情報", "エラーログが見つかりませんでした")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "エラーログを保存",
            f"error_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", 
            "テキストファイル (*.txt);;すべてのファイル (*)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(error_lines))
                QMessageBox.information(self, "完了", f"エラーログを抽出しました:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "エラー", f"エラーログの保存に失敗しました\n{e}")
    
    def filter_log(self, filter_text: str):
        """ログフィルター"""
        # 簡易実装 - 実際のフィルタリングは複雑になるため省略
        self.log_message(f"ログフィルター変更: {filter_text}")
    
    def update_log_stats(self):
        """ログ統計更新"""
        log_text = self.log_text.toPlainText()
        lines = log_text.split('\n')
        total_lines = len([line for line in lines if line.strip()])
        error_count = len([line for line in lines if 'エラー' in line or 'ERROR' in line])
        warning_count = len([line for line in lines if '警告' in line or 'WARNING' in line])
        
        self.log_stats_label.setText(f"ログ行数: {total_lines}")
        self.log_errors_label.setText(f"エラー: {error_count}")
        self.log_warnings_label.setText(f"警告: {warning_count}")
    
    def update_status(self):
        """ステータス更新（定期実行）"""
        # タスク数更新
        if self.task_manager:
            try:
                stats = self.task_manager.get_statistics()
                self.task_count_label.setText(f"タスク: {stats.get('running_tasks', 0)}")
            except Exception:
                self.task_count_label.setText("タスク: N/A")
        else:
            self.task_count_label.setText("タスク: N/A")
        
        # メモリ使用量更新
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            self.memory_label.setText(f"メモリ: {memory_mb:.1f}MB")
        except:
            self.memory_label.setText("メモリ: N/A")
    
    def load_window_settings(self):
        """ウィンドウ設定読み込み"""
        settings = QSettings("MediaDownloader", "Settings")
        geometry = settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        
        # 簡易設定の読み込み
        self.load_quick_settings()
    
    def save_window_settings(self):
        """ウィンドウ設定保存"""
        settings = QSettings("MediaDownloader", "Settings")
        settings.setValue("window/geometry", self.saveGeometry())
    
    def closeEvent(self, event):
        """ウィンドウ閉じるイベント"""
        # 実行中のスレッドを停止
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.terminate()
            self.download_thread.wait()
        
        if self.convert_thread and self.convert_thread.isRunning():
            self.convert_thread.terminate()
            self.convert_thread.wait()
        
        if self.batch_thread and self.batch_thread.isRunning():
            self.batch_thread.stop()
            self.batch_thread.wait()
        
        # タスクマネージャー終了
        if self.task_manager:
            try:
                self.task_manager.shutdown()
            except Exception as e:
                logger.error(f"TaskManager終了エラー: {e}")
        
        # ウィンドウ設定保存
        self.save_window_settings()
        
        event.accept()

def main():
    """GUIアプリケーション起動"""
    app = QApplication(sys.argv)
    app.setApplicationName("LiveLeaper")
    app.setOrganizationName("MediaDownloader")
    
    # ダークテーマ適用（オプション）
    app.setStyle("Fusion")
    
    # 高DPI対応
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    window = MediaDownloaderGUI()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
