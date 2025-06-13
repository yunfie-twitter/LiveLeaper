"""
設定管理モジュール
JSON/YAML設定ファイルの読み書きと管理
初期設定ウィザード対応
"""
import json
import yaml
import logging
from pathlib import Path
from typing import Any, Dict, Union, Optional

logger = logging.getLogger(__name__)

class Config:
    """設定管理クラス"""
    
    DEFAULT_CONFIG = {
        "app": {
            "version": "1.0.0",
            "name": "Media Downloader & Converter"
        },
        "download": {
            "output_dir": "./downloads",
            "format": "bestvideo+bestaudio/best",
            "audio_format": "mp3",
            "subtitles": False,
            "metadata": True,
            "thumbnail": False,
            "auto_rename": True,
            "max_filesize": "",
            "preferred_quality": "1080p以下"
        },
        "convert": {
            "use_hardware": True,
            "video_codec": "h264",
            "audio_codec": "aac",
            "video_bitrate": "8000k",
            "audio_bitrate": "320k",
            "resolution": "original",
            "hardware_encoder": "auto"
        },
        
        "parallel": {
            "max_workers": 4,
            "use_multiprocessing": True
        },
        "api": {
            "host": "0.0.0.0",
            "port": 8000,
            "cors_origins": ["*"]
        },
        "logging": {
            "level": "INFO",
            "file": "app.log",
            "max_bytes": 10485760,
            "backup_count": 5
        },
        "gui": {
            "theme": "default",
            "window_size": [900, 700],
            "auto_save_settings": True
        },
        "setup": {
            "completed": False,
            "wizard_version": "1.0"
        }
    }

    def __init__(self, config_file: Union[str, Path] = "config.yaml"):
        """
        設定管理の初期化
        
        Args:
            config_file: 設定ファイルのパス
        """
        self.config_file = Path(config_file)
        self.config_data = {}
        self.load_config()

    def load_config(self):
        """設定ファイルの読み込み"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    if self.config_file.suffix.lower() == '.json':
                        self.config_data = json.load(f)
                    else:  # YAML
                        self.config_data = yaml.safe_load(f) or {}
                
                # デフォルト設定とマージ
                self.config_data = self._merge_config(self.DEFAULT_CONFIG, self.config_data)
                logger.info(f"設定ファイルを読み込みました: {self.config_file}")
            else:
                # デフォルト設定で初期化（初回起動時）
                self.config_data = self.DEFAULT_CONFIG.copy()
                logger.info(f"設定ファイルが見つかりません。デフォルト設定を使用します: {self.config_file}")
                
        except Exception as e:
            logger.error(f"設定ファイルの読み込みに失敗しました: {e}")
            self.config_data = self.DEFAULT_CONFIG.copy()

    def save_config(self):
        """設定ファイルの保存"""
        try:
            # 設定ディレクトリの作成
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                if self.config_file.suffix.lower() == '.json':
                    json.dump(self.config_data, f, indent=2, ensure_ascii=False)
                else:  # YAML
                    yaml.dump(self.config_data, f, default_flow_style=False, 
                             allow_unicode=True, indent=2)
            
            logger.info(f"設定ファイルを保存しました: {self.config_file}")
            
        except Exception as e:
            logger.error(f"設定ファイルの保存に失敗しました: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        設定値の取得（ドット記法対応）
        
        Args:
            key: 設定キー（例: "download.output_dir"）
            default: デフォルト値
            
        Returns:
            設定値
        """
        try:
            keys = key.split('.')
            value = self.config_data
            
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
                    
            return value
        except Exception:
            return default

    def set(self, key: str, value: Any):
        """
        設定値の設定（ドット記法対応）
        
        Args:
            key: 設定キー
            value: 設定値
        """
        try:
            keys = key.split('.')
            config = self.config_data
            
            # 階層構造を作成
            for k in keys[:-1]:
                if k not in config:
                    config[k] = {}
                config = config[k]
            
            config[keys[-1]] = value
            logger.debug(f"設定を更新しました: {key} = {value}")
            
        except Exception as e:
            logger.error(f"設定の更新に失敗しました: {e}")

    def _merge_config(self, default: Dict, user: Dict) -> Dict:
        """
        デフォルト設定とユーザー設定をマージ
        
        Args:
            default: デフォルト設定
            user: ユーザー設定
            
        Returns:
            マージされた設定
        """
        result = default.copy()
        
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
                
        return result

    def is_first_run(self) -> bool:
        """初回起動かどうかを判定"""
        return not self.get('setup.completed', False)
    
    def mark_setup_completed(self):
        """初期設定完了をマーク"""
        self.set('setup.completed', True)
        self.save_config()

    def load_from_wizard_settings(self):
        """ウィザードの設定をQSettingsから読み込み"""
        try:
            from PyQt5.QtCore import QSettings
            
            settings = QSettings("MediaDownloader", "Settings")
            
            # QSettingsから設定を読み込んでconfig.yamlに反映
            if settings.value("setup_completed", False, type=bool):
                # 出力設定
                output_dir = settings.value("download/output_dir")
                if output_dir:
                    self.set("download.output_dir", output_dir)
                
                # 形式設定
                video_format = settings.value("download/video_format")
                if video_format:
                    self.set("download.format", video_format)
                
                audio_format = settings.value("download/audio_format")
                if audio_format:
                    self.set("download.audio_format", audio_format)
                
                # オプション設定
                subtitles = settings.value("download/subtitles", type=bool)
                if subtitles is not None:
                    self.set("download.subtitles", subtitles)
                
                metadata = settings.value("download/metadata", type=bool)
                if metadata is not None:
                    self.set("download.metadata", metadata)
                
                thumbnail = settings.value("download/thumbnail", type=bool)
                if thumbnail is not None:
                    self.set("download.thumbnail", thumbnail)
                
                # 並列処理設定
                max_workers = settings.value("parallel/max_workers", type=int)
                if max_workers:
                    self.set("parallel.max_workers", max_workers)
                
                # 設定完了マーク
                self.mark_setup_completed()
                
                logger.info("ウィザード設定をconfig.yamlに反映しました")
                
        except ImportError:
            logger.warning("PyQt5が利用できないため、QSettingsの読み込みをスキップします")
        except Exception as e:
            logger.error(f"ウィザード設定の読み込みに失敗しました: {e}")

    def reset_to_default(self):
        """設定をデフォルトにリセット"""
        self.config_data = self.DEFAULT_CONFIG.copy()
        self.save_config()
        logger.info("設定をデフォルトにリセットしました")

    def validate_config(self) -> Dict[str, str]:
        """
        設定値の検証
        
        Returns:
            エラーメッセージの辞書
        """
        errors = {}
        
        # 出力ディレクトリの検証
        output_dir = Path(self.get('download.output_dir', './downloads'))
        try:
            output_dir.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            errors['download.output_dir'] = f"ディレクトリ作成エラー: {e}"
        
        # ポート番号の検証
        port = self.get('api.port', 8000)
        if not isinstance(port, int) or port < 1 or port > 65535:
            errors['api.port'] = f"無効なポート番号: {port}"
        
        # 並列数の検証
        max_workers = self.get('parallel.max_workers', 4)
        if not isinstance(max_workers, int) or max_workers < 1:
            errors['parallel.max_workers'] = f"無効な並列数: {max_workers}"
        
        return errors

    def get_download_options(self) -> Dict[str, Any]:
        """ダウンロード用設定の取得"""
        return {
            'output_dir': self.get('download.output_dir'),
            'format': self.get('download.format'),
            'audio_format': self.get('download.audio_format'),
            'subtitles': self.get('download.subtitles'),
            'metadata': self.get('download.metadata'),
            'thumbnail': self.get('download.thumbnail'),
            'auto_rename': self.get('download.auto_rename'),
            'max_filesize': self.get('download.max_filesize'),
            'preferred_quality': self.get('download.preferred_quality')
        }

    def get_convert_options(self) -> Dict[str, Any]:
        """変換用設定の取得"""
        return {
            'use_hardware': self.get('convert.use_hardware'),
            'video_codec': self.get('convert.video_codec'),
            'audio_codec': self.get('convert.audio_codec'),
            'video_bitrate': self.get('convert.video_bitrate'),
            'audio_bitrate': self.get('convert.audio_bitrate'),
            'resolution': self.get('convert.resolution'),
            'hardware_encoder': self.get('convert.hardware_encoder')
        }

    def __str__(self) -> str:
        """設定内容の文字列表現"""
        return json.dumps(self.config_data, indent=2, ensure_ascii=False)

# グローバル設定インスタンス
config = Config()

# 初回起動時のウィザード設定読み込み
config.load_from_wizard_settings()

def reload_config(config_file: Optional[str] = None):
    """設定の再読み込み"""
    global config
    if config_file:
        config = Config(config_file)
    else:
        config.load_config()
