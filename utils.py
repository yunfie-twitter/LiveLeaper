"""
ユーティリティ関数モジュール
ファイル操作、文字列処理、ログ設定などの共通機能
"""
import os
import re
import logging
import logging.handlers
from pathlib import Path
from typing import List, Optional, Union, Dict, Any
from urllib.parse import urlparse
import hashlib
import mimetypes
from datetime import datetime, timedelta
import unicodedata

from config import config

def setup_logging():
    """ロギング設定"""
    log_level = getattr(logging, config.get('logging.level', 'INFO'))
    log_file = config.get('logging.file', 'app.log')
    max_bytes = config.get('logging.max_bytes', 10485760)  # 10MB
    backup_count = config.get('logging.backup_count', 5)
    
    # ロガーの設定
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # 既存のハンドラーをクリア
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # フォーマッター
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # コンソールハンドラー
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # ファイルハンドラー（ローテーション）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

def sanitize_filename(filename: str, replacement: str = '_') -> str:
    """
    ファイル名をサニタイズ
    
    Args:
        filename: 元のファイル名
        replacement: 無効文字の置換文字
        
    Returns:
        サニタイズされたファイル名
    """
    # Windowsで無効な文字を除去
    invalid_chars = r'[<>:"/\\|?*]'
    filename = re.sub(invalid_chars, replacement, filename)
    
    # 制御文字を除去
    filename = ''.join(char for char in filename if ord(char) >= 32)
    
    # Unicode正規化
    filename = unicodedata.normalize('NFKC', filename)
    
    # 先頭・末尾の空白とピリオドを除去
    filename = filename.strip(' .')
    
    # 予約語の回避（Windows）
    reserved_names = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    
    name_part = Path(filename).stem.upper()
    if name_part in reserved_names:
        filename = f"_{filename}"
    
    # 最大長制限（Windows: 255文字）
    if len(filename) > 255:
        name = Path(filename).stem
        ext = Path(filename).suffix
        max_name_len = 255 - len(ext)
        filename = name[:max_name_len] + ext
    
    return filename if filename else 'untitled'

def get_unique_filename(filepath: str) -> str:
    """
    重複しないファイル名を生成
    
    Args:
        filepath: 元のファイルパス
        
    Returns:
        ユニークなファイルパス
    """
    path = Path(filepath)
    
    if not path.exists():
        return filepath
    
    # ファイル名と拡張子を分離
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    
    counter = 1
    while True:
        new_name = f"{stem}_{counter}{suffix}"
        new_path = parent / new_name
        
        if not new_path.exists():
            return str(new_path)
        
        counter += 1
        
        # 無限ループ防止
        if counter > 9999:
            # タイムスタンプを追加
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_name = f"{stem}_{timestamp}{suffix}"
            return str(parent / new_name)

def format_bytes(bytes_count: Union[int, float], decimal_places: int = 1) -> str:
    """
    バイト数を人間が読みやすい形式に変換
    
    Args:
        bytes_count: バイト数
        decimal_places: 小数点以下の桁数
        
    Returns:
        フォーマットされた文字列
    """
    if bytes_count == 0:
        return "0 B"
    
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    unit_index = 0
    size = float(bytes_count)
    
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
    
    return f"{size:.{decimal_places}f} {units[unit_index]}"

def format_duration(seconds: Union[int, float]) -> str:
    """
    秒数を時間形式に変換
    
    Args:
        seconds: 秒数
        
    Returns:
        時間形式の文字列（HH:MM:SS）
    """
    if seconds < 0:
        return "00:00:00"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def parse_url_list_file(file_path: str) -> List[str]:
    """
    URLリストファイルを解析
    
    Args:
        file_path: ファイルパス
        
    Returns:
        URLのリスト
    """
    urls = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # 空行やコメント行をスキップ
                if not line or line.startswith('#'):
                    continue
                
                # URL形式の簡易チェック
                if is_valid_url(line):
                    urls.append(line)
                else:
                    logging.warning(f"無効なURL (行{line_num}): {line}")
    
    except FileNotFoundError:
        logging.error(f"URLリストファイルが見つかりません: {file_path}")
    except UnicodeDecodeError:
        logging.error(f"ファイルエンコーディングエラー: {file_path}")
    except Exception as e:
        logging.error(f"URLリストファイル読み込みエラー: {e}")
    
    return urls

def is_valid_url(url: str) -> bool:
    """
    URLの妥当性をチェック
    
    Args:
        url: チェックするURL
        
    Returns:
        有効な場合True
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False

def get_file_hash(file_path: str, algorithm: str = 'md5') -> Optional[str]:
    """
    ファイルのハッシュ値を計算
    
    Args:
        file_path: ファイルパス
        algorithm: ハッシュアルゴリズム
        
    Returns:
        ハッシュ値（16進数文字列）
    """
    try:
        hash_obj = hashlib.new(algorithm)
        
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_obj.update(chunk)
        
        return hash_obj.hexdigest()
    
    except Exception as e:
        logging.error(f"ハッシュ計算エラー: {e}")
        return None

def get_mime_type(file_path: str) -> str:
    """
    ファイルのMIMEタイプを取得
    
    Args:
        file_path: ファイルパス
        
    Returns:
        MIMEタイプ
    """
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or 'application/octet-stream'

def ensure_directory(directory: Union[str, Path]) -> Path:
    """
    ディレクトリの存在を確認し、必要に応じて作成
    
    Args:
        directory: ディレクトリパス
        
    Returns:
        Pathオブジェクト
    """
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    return path

def clean_old_files(directory: str, max_age_days: int = 30, pattern: str = "*") -> int:
    """
    古いファイルを削除
    
    Args:
        directory: 対象ディレクトリ
        max_age_days: 最大保持日数
        pattern: ファイルパターン
        
    Returns:
        削除されたファイル数
    """
    deleted_count = 0
    cutoff_time = datetime.now() - timedelta(days=max_age_days)
    
    try:
        for file_path in Path(directory).glob(pattern):
            if file_path.is_file():
                file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                
                if file_time < cutoff_time:
                    file_path.unlink()
                    deleted_count += 1
                    logging.debug(f"古いファイルを削除: {file_path}")
    
    except Exception as e:
        logging.error(f"ファイル削除エラー: {e}")
    
    return deleted_count

def extract_metadata_from_filename(filename: str) -> Dict[str, Any]:
    """
    ファイル名からメタデータを抽出
    
    Args:
        filename: ファイル名
        
    Returns:
        メタデータ辞書
    """
    metadata = {
        'title': Path(filename).stem,
        'extension': Path(filename).suffix.lower(),
        'date': None,
        'resolution': None,
        'quality': None
    }
    
    # 日付パターンを検索
    date_patterns = [
        r'(\d{4}-\d{2}-\d{2})',
        r'(\d{4}\d{2}\d{2})',
        r'(\d{2}-\d{2}-\d{4})'
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, filename)
        if match:
            metadata['date'] = match.group(1)
            break
    
    # 解像度パターンを検索
    resolution_pattern = r'(\d{3,4}[xX]\d{3,4})'
    match = re.search(resolution_pattern, filename)
    if match:
        metadata['resolution'] = match.group(1).lower()
    
    # 品質パターンを検索
    quality_patterns = ['720p', '1080p', '4k', 'hd', 'full hd', 'uhd']
    filename_lower = filename.lower()
    
    for quality in quality_patterns:
        if quality in filename_lower:
            metadata['quality'] = quality
            break
    
    return metadata

def create_directory_structure(base_path: str, structure: Dict[str, Any]) -> Dict[str, Path]:
    """
    ディレクトリ構造を作成
    
    Args:
        base_path: ベースパス
        structure: ディレクトリ構造の辞書
        
    Returns:
        作成されたパスの辞書
    """
    created_paths = {}
    base = Path(base_path)
    
    def create_recursive(current_path: Path, current_structure: Dict[str, Any], prefix: str = ""):
        for name, value in current_structure.items():
            full_name = f"{prefix}.{name}" if prefix else name
            new_path = current_path / name
            
            if isinstance(value, dict):
                # ディレクトリ
                new_path.mkdir(parents=True, exist_ok=True)
                created_paths[full_name] = new_path
                create_recursive(new_path, value, full_name)
            else:
                # ファイル（空ファイル作成）
                new_path.parent.mkdir(parents=True, exist_ok=True)
                new_path.touch()
                created_paths[full_name] = new_path
    
    create_recursive(base, structure)
    return created_paths

class ProgressReporter:
    """進捗レポートクラス"""
    
    def __init__(self, total: int = 100, prefix: str = "Progress"):
        self.total = total
        self.current = 0
        self.prefix = prefix
        self.start_time = datetime.now()
    
    def update(self, progress: int):
        """進捗を更新"""
        self.current = min(progress, self.total)
        percentage = (self.current / self.total) * 100
        
        # 経過時間と推定残り時間
        elapsed = datetime.now() - self.start_time
        if self.current > 0:
            eta = elapsed * (self.total - self.current) / self.current
        else:
            eta = timedelta(0)
        
        logging.info(f"{self.prefix}: {percentage:.1f}% ({self.current}/{self.total}) "
                    f"経過: {self._format_timedelta(elapsed)} "
                    f"残り: {self._format_timedelta(eta)}")
    
    def _format_timedelta(self, td: timedelta) -> str:
        """timedelta を文字列に変換"""
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def finish(self):
        """進捗完了"""
        self.update(self.total)
        elapsed = datetime.now() - self.start_time
        logging.info(f"{self.prefix}: 完了 (総時間: {self._format_timedelta(elapsed)})")

def validate_config_paths() -> List[str]:
    """設定ファイルのパスを検証"""
    errors = []
    
    # ダウンロードディレクトリ
    download_dir = config.get('download.output_dir', './downloads')
    try:
        ensure_directory(download_dir)
    except Exception as e:
        errors.append(f"ダウンロードディレクトリ作成エラー: {e}")
    
    # ログディレクトリ
    log_file = config.get('logging.file')
    if log_file:
        try:
            ensure_directory(Path(log_file).parent)
        except Exception as e:
            errors.append(f"ログディレクトリ作成エラー: {e}")
    
    return errors

def get_system_info() -> Dict[str, Any]:
    """システム情報を取得"""
    import platform
    import psutil
    
    return {
        'platform': platform.platform(),
        'python_version': platform.python_version(),
        'cpu_count': os.cpu_count(),
        'memory_total': psutil.virtual_memory().total,
        'memory_available': psutil.virtual_memory().available,
        'disk_usage': psutil.disk_usage('.').free
    }

# 設定検証の実行（モジュール読み込み時）
if __name__ != "__main__":
    try:
        setup_logging()
        validation_errors = validate_config_paths()
        if validation_errors:
            for error in validation_errors:
                logging.warning(error)
    except Exception as e:
        print(f"初期化エラー: {e}")
