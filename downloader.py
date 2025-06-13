"""
ダウンロード処理モジュール
yt-dlpを使用した動画・音声のダウンロード機能
URL修正機能付き
"""
import yt_dlp
import logging
import threading
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from urllib.parse import urlparse, parse_qs, urlunparse

from config import config
from utils import sanitize_filename, get_unique_filename, format_bytes

logger = logging.getLogger(__name__)

class URLCleaner:
    """URL修正・正規化クラス"""
    
    @staticmethod
    def clean_youtube_url(url: str) -> str:
        """YouTube URLをクリーンアップ"""
        try:
            # YouTube Shorts を通常形式に変換
            if '/shorts/' in url:
                video_id = url.split('/shorts/')[-1].split('?')[0].split('&')[0]
                return f"https://www.youtube.com/watch?v={video_id}"
            
            # youtu.be 短縮URLを展開
            if 'youtu.be/' in url:
                video_id = url.split('youtu.be/')[-1].split('?')[0].split('&')[0]
                return f"https://www.youtube.com/watch?v={video_id}"
            
            # 通常のYouTube URLから不要なパラメータを除去
            if 'youtube.com/watch' in url:
                parsed = urlparse(url)
                query_params = parse_qs(parsed.query)
                
                if 'v' in query_params:
                    video_id = query_params['v'][0]
                    return f"https://www.youtube.com/watch?v={video_id}"
            
            return url
            
        except Exception as e:
            logger.warning(f"YouTube URL修正エラー: {e}")
            return url
    
    @staticmethod
    def clean_niconico_url(url: str) -> str:
        """ニコニコ動画URLをクリーンアップ"""
        try:
            if 'nicovideo.jp/watch/' in url:
                # URLから動画IDを抽出
                match = re.search(r'/watch/([a-z0-9]+)', url)
                if match:
                    video_id = match.group(1)
                    return f"https://www.nicovideo.jp/watch/{video_id}"
            
            return url
            
        except Exception as e:
            logger.warning(f"ニコニコ動画URL修正エラー: {e}")
            return url
    
    @staticmethod
    def clean_url(url: str) -> str:
        """URLを自動判定してクリーンアップ"""
        url = url.strip()
        
        if 'youtube.com' in url or 'youtu.be' in url:
            return URLCleaner.clean_youtube_url(url)
        elif 'nicovideo.jp' in url:
            return URLCleaner.clean_niconico_url(url)
        else:
            return url

class DownloadProgress:
    """ダウンロード進捗管理クラス"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """進捗情報をリセット"""
        self.total_bytes = 0
        self.downloaded_bytes = 0
        self.speed = 0
        self.eta = 0
        self.status = "preparing"
        self.filename = ""
        
    def update(self, info: Dict[str, Any]):
        """進捗情報を更新"""
        self.total_bytes = info.get('total_bytes', 0) or info.get('total_bytes_estimate', 0)
        self.downloaded_bytes = info.get('downloaded_bytes', 0)
        self.speed = info.get('speed', 0)
        self.eta = info.get('eta', 0)
        self.status = info.get('status', 'downloading')
        self.filename = info.get('filename', '')
        
    def get_percentage(self) -> float:
        """進捗率を取得"""
        if self.total_bytes > 0:
            return (self.downloaded_bytes / self.total_bytes) * 100
        return 0.0
        
    def get_info_dict(self) -> Dict[str, Any]:
        """進捗情報を辞書で取得"""
        return {
            'total_bytes': self.total_bytes,
            'downloaded_bytes': self.downloaded_bytes,
            'speed': self.speed,
            'eta': self.eta,
            'status': self.status,
            'filename': self.filename,
            'percentage': self.get_percentage()
        }

class VideoDownloader:
    """動画ダウンローダークラス"""
    
    def __init__(self, progress_callback: Optional[Callable] = None):
        """
        ダウンローダーの初期化
        
        Args:
            progress_callback: 進捗コールバック関数
        """
        self.progress_callback = progress_callback
        self.progress = DownloadProgress()
        self._current_download = None
        self._stop_event = threading.Event()
        
    def _progress_hook(self, d: Dict[str, Any]):
        """yt-dlpの進捗フック"""
        try:
            self.progress.update(d)
            
            if self.progress_callback:
                self.progress_callback(self.progress.get_info_dict())
                
            # ログ出力
            if d['status'] == 'downloading':
                if self.progress.total_bytes > 0:
                    percent = self.progress.get_percentage()
                    speed = format_bytes(self.progress.speed) if self.progress.speed else "N/A"
                    logger.debug(f"ダウンロード進捗: {percent:.1f}% ({speed}/s)")
            elif d['status'] == 'finished':
                logger.info(f"ダウンロード完了: {Path(d['filename']).name}")
                
        except Exception as e:
            logger.error(f"進捗フック処理エラー: {e}")

    def _parse_filesize(self, size_str: str) -> int:
        """
        ファイルサイズ文字列を数値に変換（修正版）
        
        Args:
            size_str: ファイルサイズ文字列（例: '2G', '2GB', '100M', '100MB'）
            
        Returns:
            バイト数
        """
        if not size_str:
            return 0
            
        units = {
            'B': 1, 
            'K': 1024, 'KB': 1024,
            'M': 1024**2, 'MB': 1024**2,
            'G': 1024**3, 'GB': 1024**3,
            'T': 1024**4, 'TB': 1024**4
        }
        
        size_str = size_str.upper().strip()
        
        # 単位を検索して変換
        for unit, multiplier in sorted(units.items(), key=lambda x: len(x[0]), reverse=True):
            if size_str.endswith(unit):
                try:
                    number_part = size_str[:-len(unit)].strip()
                    return int(float(number_part) * multiplier)
                except ValueError:
                    logger.warning(f"無効なファイルサイズ形式: {size_str}")
                    return 0
        
        # 数値のみの場合
        try:
            return int(float(size_str))
        except ValueError:
            logger.warning(f"無効なファイルサイズ形式: {size_str}")
            return 0

    def _get_ydl_opts(self, output_dir: str, **kwargs) -> Dict[str, Any]:
        """yt-dlpオプションの生成"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 基本オプション
        opts = {
            'outtmpl': str(output_path / '%(title)s.%(ext)s'),
            'progress_hooks': [self._progress_hook],
            'no_warnings': False,
            'ignoreerrors': False,
            'extract_flat': False,
            'writethumbnail': config.get('download.thumbnail', False),
            'writeinfojson': config.get('download.metadata', True),
            'writesubtitles': config.get('download.subtitles', False),
            'writeautomaticsub': config.get('download.subtitles', False),
            'retries': 3,
            'fragment_retries': 3,
        }
        
        # フォーマット指定
        format_str = kwargs.get('format') or config.get('download.format', 'bestvideo+bestaudio/best')
        opts['format'] = format_str
        
        # ファイルサイズ制限
        max_filesize = config.get('download.max_filesize')
        if max_filesize:
            opts['max_filesize'] = self._parse_filesize(max_filesize)
        
        # 字幕言語設定
        if opts['writesubtitles']:
            opts['subtitleslangs'] = ['ja', 'en', 'all']
        
        # その他のオプション
        opts.update(kwargs)
        
        return opts

    def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """動画情報の取得"""
        try:
            # URLをクリーンアップ
            clean_url = URLCleaner.clean_url(url)
            logger.debug(f"URL修正: {url} -> {clean_url}")
            
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(clean_url, download=False)
                
                if info:
                    return {
                        'title': info.get('title', 'Unknown'),
                        'duration': info.get('duration', 0),
                        'uploader': info.get('uploader', 'Unknown'),
                        'upload_date': info.get('upload_date', ''),
                        'view_count': info.get('view_count', 0),
                        'formats': len(info.get('formats', [])),
                        'thumbnail': info.get('thumbnail', ''),
                        'description': info.get('description', ''),
                        'url': clean_url
                    }
        except Exception as e:
            logger.error(f"動画情報の取得に失敗しました: {e}")
        return None

    def download_video(self, url: str, output_dir: str = None, 
                      format_selector: str = None, retries: int = 3) -> Optional[str]:
        """
        動画のダウンロード（リトライ機能付き）
        
        Args:
            url: ダウンロードURL
            output_dir: 出力ディレクトリ
            format_selector: フォーマット指定
            retries: リトライ回数
            
        Returns:
            ダウンロードしたファイルパス
        """
        # URLをクリーンアップ
        clean_url = URLCleaner.clean_url(url)
        logger.debug(f"URL修正: {url} -> {clean_url}")
        
        for attempt in range(retries):
            try:
                self.progress.reset()
                self._stop_event.clear()
                
                output_dir = output_dir or config.get('download.output_dir', './downloads')
                
                ydl_opts = self._get_ydl_opts(output_dir, format=format_selector)
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # ダウンロード実行
                    info = ydl.extract_info(clean_url, download=True)
                    
                    if info and not self._stop_event.is_set():
                        # ダウンロードされたファイルを特定
                        if 'requested_downloads' in info:
                            downloaded_file = info['requested_downloads'][0]['filepath']
                        else:
                            # ファイルパスを推測
                            filename = ydl.prepare_filename(info)
                            downloaded_file = filename
                        
                        # ファイル名のリネーム処理
                        if config.get('download.auto_rename', True):
                            downloaded_file = self._handle_filename_conflicts(downloaded_file)
                        
                        logger.info(f"ダウンロード成功: {downloaded_file}")
                        return downloaded_file
                        
            except Exception as e:
                logger.warning(f"ダウンロード試行 {attempt + 1}/{retries} 失敗: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # 指数バックオフ
                else:
                    logger.error(f"全 {retries} 回の試行が失敗しました")
                    
        return None

    def download_audio(self, url: str, output_dir: str = None, 
                      audio_format: str = 'mp3', retries: int = 3) -> Optional[str]:
        """
        音声のダウンロード・抽出（リトライ機能付き）
        
        Args:
            url: ダウンロードURL
            output_dir: 出力ディレクトリ
            audio_format: 音声フォーマット
            retries: リトライ回数
            
        Returns:
            ダウンロードしたファイルパス
        """
        # URLをクリーンアップ
        clean_url = URLCleaner.clean_url(url)
        logger.debug(f"URL修正: {url} -> {clean_url}")
        
        for attempt in range(retries):
            try:
                self.progress.reset()
                self._stop_event.clear()
                
                output_dir = output_dir or config.get('download.output_dir', './downloads')
                
                ydl_opts = self._get_ydl_opts(
                    output_dir,
                    format='bestaudio/best',
                    postprocessors=[{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': audio_format,
                        'preferredquality': config.get('convert.audio_bitrate', '320').replace('k', ''),
                    }]
                )
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(clean_url, download=True)
                    
                    if info and not self._stop_event.is_set():
                        # 変換後のファイルパスを取得
                        base_filename = ydl.prepare_filename(info)
                        audio_filename = Path(base_filename).with_suffix(f'.{audio_format}')
                        
                        if config.get('download.auto_rename', True):
                            audio_filename = self._handle_filename_conflicts(str(audio_filename))
                        
                        logger.info(f"音声抽出成功: {audio_filename}")
                        return str(audio_filename)
                        
            except Exception as e:
                logger.warning(f"音声ダウンロード試行 {attempt + 1}/{retries} 失敗: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # 指数バックオフ
                else:
                    logger.error(f"全 {retries} 回の試行が失敗しました")
                    
        return None

    def download_playlist(self, url: str, output_dir: str = None, 
                         audio_only: bool = False) -> List[str]:
        """
        プレイリストのダウンロード
        
        Args:
            url: プレイリストURL
            output_dir: 出力ディレクトリ
            audio_only: 音声のみ抽出
            
        Returns:
            ダウンロードしたファイルのリスト
        """
        downloaded_files = []
        
        try:
            # URLをクリーンアップ
            clean_url = URLCleaner.clean_url(url)
            logger.debug(f"URL修正: {url} -> {clean_url}")
            
            # プレイリスト情報を取得
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                playlist_info = ydl.extract_info(clean_url, download=False)
                
                if not playlist_info or 'entries' not in playlist_info:
                    logger.error("プレイリストの解析に失敗しました")
                    return downloaded_files
                
                entries = list(playlist_info['entries'])
                logger.info(f"プレイリスト検出: {len(entries)}件の動画")
                
                # 各動画をダウンロード
                for i, entry in enumerate(entries, 1):
                    if self._stop_event.is_set():
                        break
                        
                    if not entry:
                        continue
                        
                    entry_url = entry.get('webpage_url') or entry.get('url')
                    if not entry_url:
                        continue
                    
                    logger.info(f"ダウンロード中 ({i}/{len(entries)}): {entry.get('title', 'Unknown')}")
                    
                    try:
                        if audio_only:
                            result = self.download_audio(entry_url, output_dir)
                        else:
                            result = self.download_video(entry_url, output_dir)
                        
                        if result:
                            downloaded_files.append(result)
                    except Exception as e:
                        logger.error(f"個別ダウンロードエラー ({i}/{len(entries)}): {e}")
                        continue
                
        except Exception as e:
            logger.error(f"プレイリストダウンロードエラー: {e}")
        
        return downloaded_files

    def _handle_filename_conflicts(self, filepath: str) -> str:
        """ファイル名の競合処理"""
        return get_unique_filename(filepath)

    def stop_download(self):
        """ダウンロードを停止"""
        self._stop_event.set()
        logger.info("ダウンロード停止要求を受信しました")

    def is_supported_url(self, url: str) -> bool:
        """URLが対応しているかチェック"""
        try:
            clean_url = URLCleaner.clean_url(url)
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                extractors = ydl.list_extractors()
                for extractor in extractors:
                    if hasattr(extractor, '_VALID_URL'):
                        import re
                        if re.match(extractor._VALID_URL, clean_url):
                            return True
            return False
        except Exception:
            return False

class BatchDownloader:
    """バッチダウンロードクラス"""
    
    def __init__(self, progress_callback: Optional[Callable] = None):
        self.downloader = VideoDownloader(progress_callback)
        self.progress_callback = progress_callback
        
    def download_urls(self, urls: List[str], output_dir: str = None, 
                     audio_only: bool = False) -> Dict[str, Any]:
        """
        複数URLの一括ダウンロード
        
        Args:
            urls: URLリスト
            output_dir: 出力ディレクトリ
            audio_only: 音声のみ抽出
            
        Returns:
            処理結果の辞書
        """
        results = {
            'success': [],
            'failed': [],
            'total': len(urls)
        }
        
        for i, url in enumerate(urls, 1):
            try:
                logger.info(f"処理中 ({i}/{len(urls)}): {url}")
                
                if audio_only:
                    result = self.downloader.download_audio(url, output_dir)
                else:
                    result = self.downloader.download_video(url, output_dir)
                
                if result:
                    results['success'].append({'url': url, 'file': result})
                else:
                    results['failed'].append({'url': url, 'error': 'Download failed'})
                    
            except Exception as e:
                logger.error(f"URL処理エラー: {url} - {e}")
                results['failed'].append({'url': url, 'error': str(e)})
        
        return results

def test_url_cleaner():
    """URL修正機能のテスト"""
    test_urls = [
        "https://www.youtube.com/watch?v=JC-uvbOfag4&t=127s&ab_channel=Sayx",
        "https://www.youtube.com/shorts/W5Q63oB3HJs",
        "https://youtu.be/ABC123DEF456",
        "https://www.nicovideo.jp/watch/sm33593693?rf=nvpc&rp=watch&ra=share&rd=x",
    ]
    
    expected_results = [
        "https://www.youtube.com/watch?v=JC-uvbOfag4",
        "https://www.youtube.com/watch?v=W5Q63oB3HJs",
        "https://www.youtube.com/watch?v=ABC123DEF456",
        "https://www.nicovideo.jp/watch/sm33593693",
    ]
    
    print("URL修正機能テスト:")
    for original, expected in zip(test_urls, expected_results):
        cleaned = URLCleaner.clean_url(original)
        status = "✓" if cleaned == expected else "✗"
        print(f"{status} {original}")
        print(f"  -> {cleaned}")
        if cleaned != expected:
            print(f"  期待値: {expected}")
        print()

if __name__ == "__main__":
    test_url_cleaner()
