"""
変換処理モジュール
ffmpegを使用した動画・音声の形式変換機能（修正版）
"""
import ffmpeg
import logging
import subprocess
import platform
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any, Tuple

from config import config
from utils import get_unique_filename, format_duration

logger = logging.getLogger(__name__)

class HardwareAcceleration:
    """ハードウェアアクセラレーション検出・管理クラス"""
    
    @staticmethod
    def detect_nvidia_support() -> bool:
        """NVIDIA NVENC対応を検出"""
        try:
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-encoders'],
                capture_output=True, text=True, timeout=10,
                encoding='utf-8', errors='replace'
            )
            return 'h264_nvenc' in result.stdout
        except Exception:
            return False
    
    @staticmethod
    def detect_intel_qsv_support() -> bool:
        """Intel QSV対応を検出"""
        try:
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-encoders'],
                capture_output=True, text=True, timeout=10,
                encoding='utf-8', errors='replace'
            )
            return 'h264_qsv' in result.stdout
        except Exception:
            return False
    
    @staticmethod
    def detect_amd_support() -> bool:
        """AMD AMF対応を検出（Windows）"""
        if platform.system() != "Windows":
            return False
        try:
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-encoders'],
                capture_output=True, text=True, timeout=10,
                encoding='utf-8', errors='replace'
            )
            return 'h264_amf' in result.stdout
        except Exception:
            return False
    
    @classmethod
    def get_available_encoders(cls) -> Dict[str, bool]:
        """利用可能なハードウェアエンコーダーを取得"""
        return {
            'nvenc': cls.detect_nvidia_support(),
            'qsv': cls.detect_intel_qsv_support(),
            'amf': cls.detect_amd_support()
        }
    
    @classmethod
    def get_best_encoder(cls, codec: str = 'h264') -> str:
        """最適なエンコーダーを自動選択"""
        encoders = cls.get_available_encoders()
        
        if codec == 'h264':
            if encoders['nvenc']:
                return 'h264_nvenc'
            elif encoders['qsv']:
                return 'h264_qsv'
            elif encoders['amf']:
                return 'h264_amf'
            else:
                return 'libx264'  # CPU fallback
        elif codec == 'h265':
            if encoders['nvenc']:
                return 'hevc_nvenc'
            elif encoders['qsv']:
                return 'hevc_qsv'
            elif encoders['amf']:
                return 'hevc_amf'
            else:
                return 'libx265'  # CPU fallback
        
        return f'lib{codec}'  # デフォルト

class AudioConverter:
    """音声変換処理拡張クラス"""
    
    def __init__(self, progress_callback=None):
        self.progress_callback = progress_callback
        
    def convert_audio(self, input_file, output_file, options):
        """音声変換処理（圧縮機能追加）"""
        try:
            codec = options.get('audio_codec', 'mp3').lower()
            bitrate = options.get('bitrate', '192k')
            sample_rate = options.get('sample_rate')
            channels = options.get('channels')
            quality = options.get('quality', 80)
            
            ffmpeg_cmd = [
                'ffmpeg',
                '-y',
                '-i', input_file,
                '-vn'
            ]
            
            # コーデック固有オプション
            if codec == 'mp3':
                ffmpeg_cmd += [
                    '-codec:a', 'libmp3lame',
                    '-q:a', str(quality/10)  # 0-9 scale
                ]
            elif codec == 'aac':
                ffmpeg_cmd += [
                    '-codec:a', 'aac',
                    '-b:a', bitrate,
                    '-vbr', str(quality//20)  # 0-5 scale
                ]
            elif codec == 'opus':
                ffmpeg_cmd += [
                    '-codec:a', 'libopus',
                    '-b:a', bitrate,
                    '-vbr', 'on',
                    '-compression_level', str(quality//10)
                ]
                
            # サンプルレート設定
            if sample_rate and sample_rate != 'オリジナル維持':
                ffmpeg_cmd += ['-ar', sample_rate.replace(' Hz', '')]
                
            # チャンネル設定
            channel_map = {
                'モノラル': '1',
                'ステレオ': '2',
                '5.1ch': '6'
            }
            if channels in channel_map:
                ffmpeg_cmd += ['-ac', channel_map[channels]]
                
            ffmpeg_cmd.append(output_file)
            
            # 実行処理（既存の進捗処理と統合）
            self._run_ffmpeg(ffmpeg_cmd)
            
            return output_file
        except Exception as e:
            logger.error(f"音声変換エラー: {e}")
            return None


class ConversionProgress:
    """変換進捗管理クラス"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """進捗情報をリセット"""
        self.duration = 0
        self.processed_time = 0
        self.fps = 0
        self.bitrate = ""
        self.status = "preparing"
        
    def update_from_ffmpeg_output(self, line: str):
        """ffmpegの出力から進捗を更新"""
        try:
            if "Duration:" in line:
                # Duration: 00:01:23.45, start: 0.000000, bitrate: 1234 kb/s
                duration_str = line.split("Duration:")[1].split(",")[0].strip()
                self.duration = self._parse_time(duration_str)
            elif "time=" in line:
                # frame= 1234 fps= 25 q=28.0 size=    1234kB time=00:00:12.34 bitrate= 123.4kbits/s
                parts = line.split()
                for part in parts:
                    if part.startswith("time="):
                        time_str = part.split("=")[1]
                        self.processed_time = self._parse_time(time_str)
                    elif part.startswith("fps="):
                        try:
                            self.fps = float(part.split("=")[1])
                        except ValueError:
                            self.fps = 0
                    elif part.startswith("bitrate="):
                        self.bitrate = part.split("=")[1]
                self.status = "converting"
        except Exception as e:
            logger.debug(f"進捗解析エラー: {e}")
    
    def _parse_time(self, time_str: str) -> float:
        """時間文字列を秒数に変換"""
        try:
            parts = time_str.split(":")
            hours = float(parts[0])
            minutes = float(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        except Exception:
            return 0.0
    
    def get_percentage(self) -> float:
        """進捗率を取得"""
        if self.duration > 0:
            return min((self.processed_time / self.duration) * 100, 100.0)
        return 0.0
    
    def get_info_dict(self) -> Dict[str, Any]:
        """進捗情報を辞書で取得"""
        return {
            'duration': self.duration,
            'processed_time': self.processed_time,
            'fps': self.fps,
            'bitrate': self.bitrate,
            'status': self.status,
            'percentage': self.get_percentage()
        }

class VideoConverter:
    """動画変換クラス"""
    
    def __init__(self, progress_callback: Optional[Callable] = None):
        """
        変換器の初期化
        
        Args:
            progress_callback: 進捗コールバック関数
        """
        self.progress_callback = progress_callback
        self.progress = ConversionProgress()
        self.hw_accel = HardwareAcceleration()
        
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

    def get_media_info(self, input_file: str) -> Optional[Dict[str, Any]]:
        """メディアファイルの情報を取得"""
        try:
            probe = ffmpeg.probe(input_file)
            
            info = {
                'format': probe['format']['format_name'],
                'duration': float(probe['format']['duration']),
                'size': int(probe['format']['size']),
                'bitrate': int(probe['format']['bit_rate']),
                'streams': []
            }
            
            for stream in probe['streams']:
                stream_info = {
                    'index': stream['index'],
                    'codec_type': stream['codec_type'],
                    'codec_name': stream['codec_name']
                }
                
                if stream['codec_type'] == 'video':
                    stream_info.update({
                        'width': stream.get('width', 0),
                        'height': stream.get('height', 0),
                        'fps': eval(stream.get('r_frame_rate', '0/1')) if stream.get('r_frame_rate') else 0,
                        'pix_fmt': stream.get('pix_fmt', '')
                    })
                elif stream['codec_type'] == 'audio':
                    stream_info.update({
                        'sample_rate': int(stream.get('sample_rate', 0)),
                        'channels': stream.get('channels', 0),
                        'channel_layout': stream.get('channel_layout', '')
                    })
                
                info['streams'].append(stream_info)
            
            return info
            
        except Exception as e:
            logger.error(f"メディア情報の取得に失敗しました: {e}")
            return None

    def convert_video(self, input_file: str, output_file: str, **options) -> Optional[str]:
        """
        動画ファイルの変換
        
        Args:
            input_file: 入力ファイルパス
            output_file: 出力ファイルパス
            **options: 変換オプション
            
        Returns:
            変換後のファイルパス
        """
        try:
            self.progress.reset()
            
            # 入力ファイルの存在確認
            if not Path(input_file).exists():
                raise FileNotFoundError(f"入力ファイルが見つかりません: {input_file}")
            
            # 出力ディレクトリの作成
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            
            # ファイル名の重複チェック
            if Path(output_file).exists() and config.get('download.auto_rename', True):
                output_file = get_unique_filename(output_file)
            
            # ffmpegストリームの構築
            input_stream = ffmpeg.input(input_file)
            
            # 変換オプションの設定
            output_options = self._build_video_options(options)
            
            # 出力ストリームの作成
            output_stream = ffmpeg.output(input_stream, output_file, **output_options)
            
            # 既存ファイルの上書き設定
            output_stream = ffmpeg.overwrite_output(output_stream)
            
            # 変換実行
            self._run_ffmpeg_with_progress(output_stream)
            
            if Path(output_file).exists():
                logger.info(f"動画変換完了: {output_file}")
                return output_file
            else:
                logger.error("変換後のファイルが見つかりません")
                return None
                
        except Exception as e:
            logger.error(f"動画変換エラー: {e}")
            return None

    def extract_audio(self, input_file: str, output_file: str, 
                     audio_format: str = 'mp3', **options) -> Optional[str]:
        """
        動画から音声を抽出
        
        Args:
            input_file: 入力動画ファイル
            output_file: 出力音声ファイル
            audio_format: 音声フォーマット
            **options: 抽出オプション
            
        Returns:
            抽出した音声ファイルパス
        """
        try:
            self.progress.reset()
            
            # 入力ファイルの存在確認
            if not Path(input_file).exists():
                raise FileNotFoundError(f"入力ファイルが見つかりません: {input_file}")
            
            # 出力ディレクトリの作成
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            
            # 音声抽出オプション
            audio_options = self._build_audio_options(audio_format, options)
            
            # ffmpegストリーム構築
            input_stream = ffmpeg.input(input_file)
            output_stream = ffmpeg.output(
                input_stream, output_file,
                vn=None,  # 動画ストリームを無効化
                **audio_options
            )
            
            # 既存ファイルの上書き設定
            output_stream = ffmpeg.overwrite_output(output_stream)
            
            # 抽出実行
            self._run_ffmpeg_with_progress(output_stream)
            
            if Path(output_file).exists():
                logger.info(f"音声抽出完了: {output_file}")
                return output_file
            else:
                logger.error("抽出後のファイルが見つかりません")
                return None
                
        except Exception as e:
            logger.error(f"音声抽出エラー: {e}")
            return None

    def convert_audio(self, input_file: str, output_file: str, 
                     audio_format: str = 'mp3', **options) -> Optional[str]:
        """
        音声ファイルの変換
        
        Args:
            input_file: 入力音声ファイル
            output_file: 出力音声ファイル
            audio_format: 出力音声フォーマット
            **options: 変換オプション
            
        Returns:
            変換後の音声ファイルパス
        """
        try:
            self.progress.reset()
            
            # 入力ファイルの存在確認
            if not Path(input_file).exists():
                raise FileNotFoundError(f"入力ファイルが見つかりません: {input_file}")
            
            # 出力ディレクトリの作成  
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            
            # 音声変換オプション
            audio_options = self._build_audio_options(audio_format, options)
            
            # ffmpegストリーム構築
            input_stream = ffmpeg.input(input_file)
            output_stream = ffmpeg.output(input_stream, output_file, **audio_options)
            
            # 既存ファイルの上書き設定
            output_stream = ffmpeg.overwrite_output(output_stream)
            
            # 変換実行
            self._run_ffmpeg_with_progress(output_stream)
            
            if Path(output_file).exists():
                logger.info(f"音声変換完了: {output_file}")
                return output_file
            else:
                logger.error("変換後のファイルが見つかりません")
                return None
                
        except Exception as e:
            logger.error(f"音声変換エラー: {e}")
            return None

    def _build_video_options(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """動画変換オプションの構築"""
        ffmpeg_opts = {}
        
        # 動画コーデック
        video_codec = options.get('video_codec') or config.get('convert.video_codec', 'h264')
        use_hardware = options.get('use_hardware', config.get('convert.use_hardware', True))
        
        if use_hardware:
            encoder = self.hw_accel.get_best_encoder(video_codec)
        else:
            encoder = f'lib{video_codec}'
        
        ffmpeg_opts['vcodec'] = encoder
        
        # ビットレート
        video_bitrate = options.get('video_bitrate') or config.get('convert.video_bitrate', '8000k')
        ffmpeg_opts['video_bitrate'] = video_bitrate
        
        # 解像度
        resolution = options.get('resolution') or config.get('convert.resolution', 'original')
        if resolution != 'original' and resolution != 'オリジナル':
            if 'x' in resolution:
                width, height = resolution.split('x')
                ffmpeg_opts['s'] = f'{width}x{height}'
        
        # 音声設定
        audio_codec = options.get('audio_codec') or config.get('convert.audio_codec', 'aac')
        audio_bitrate = options.get('audio_bitrate') or config.get('convert.audio_bitrate', '320k')
        
        ffmpeg_opts['acodec'] = audio_codec
        ffmpeg_opts['audio_bitrate'] = audio_bitrate
        
        # プリセット設定（ハードウェアエンコーダー用）
        if 'nvenc' in encoder:
            ffmpeg_opts['preset'] = 'fast'
            ffmpeg_opts['profile'] = 'high'
        elif 'qsv' in encoder:
            ffmpeg_opts['preset'] = 'medium'
        
        return ffmpeg_opts

    def _build_audio_options(self, audio_format: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """音声変換オプションの構築"""
        ffmpeg_opts = {}
        
        # 音声コーデック
        if audio_format == 'mp3':
            ffmpeg_opts['acodec'] = 'libmp3lame'
        elif audio_format == 'aac':
            ffmpeg_opts['acodec'] = 'aac'
        elif audio_format == 'ogg':
            ffmpeg_opts['acodec'] = 'libvorbis'
        elif audio_format == 'flac':
            ffmpeg_opts['acodec'] = 'flac'
        else:
            ffmpeg_opts['acodec'] = audio_format
        
        # ビットレート
        audio_bitrate = options.get('audio_bitrate') or config.get('convert.audio_bitrate', '320k')
        if audio_format != 'flac':  # FLACはロスレスなのでビットレート指定不要
            ffmpeg_opts['audio_bitrate'] = audio_bitrate
        
        # サンプリングレート
        sample_rate = options.get('sample_rate')
        if sample_rate and sample_rate != 'オリジナル':
            ffmpeg_opts['ar'] = sample_rate
        
        # チャンネル数
        channels = options.get('channels')
        if channels:
            ffmpeg_opts['ac'] = channels
        
        return ffmpeg_opts

    def _run_ffmpeg_with_progress(self, stream):
        """進捗付きでffmpegを実行（修正版）"""
        try:
            # ffmpegコマンドを構築
            cmd = ffmpeg.compile(stream)
            logger.debug(f"ffmpegコマンド: {' '.join(cmd)}")
            
            # プロセス実行（エンコーディング対応）
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1
            )
            
            # 出力を監視して進捗を更新
            while True:
                output = process.stdout.read(1024)
                if not output and process.poll() is not None:
                    break
                
                if output:
                    # エンコーディング処理（修正版）
                    try:
                        line = output.decode('utf-8')
                    except UnicodeDecodeError:
                        try:
                            line = output.decode('cp932', errors='replace')
                        except UnicodeDecodeError:
                            line = output.decode('latin-1', errors='replace')
                    
                    # 改行で分割して各行を処理
                    for text_line in line.splitlines():
                        if text_line.strip():
                            self.progress.update_from_ffmpeg_output(text_line)
                            
                            if self.progress_callback:
                                self.progress_callback(self.progress.get_info_dict())
                            
                            # デバッグログ
                            logger.debug(text_line.strip())
            
            # プロセス終了を待機
            return_code = process.wait()
            
            if return_code != 0:
                raise subprocess.CalledProcessError(return_code, cmd)
                
        except Exception as e:
            logger.error(f"ffmpeg実行エラー: {e}")
            raise

    def batch_convert(self, file_list: List[Tuple[str, str]], **options) -> Dict[str, Any]:
        """
        複数ファイルの一括変換
        
        Args:
            file_list: (入力ファイル, 出力ファイル)のタプルリスト
            **options: 変換オプション
            
        Returns:
            変換結果の辞書
        """
        results = {
            'success': [],
            'failed': [],
            'total': len(file_list)
        }
        
        for i, (input_file, output_file) in enumerate(file_list, 1):
            try:
                logger.info(f"変換中 ({i}/{len(file_list)}): {Path(input_file).name}")
                
                # ファイル拡張子に基づいて変換方法を決定
                input_suffix = Path(input_file).suffix.lower()
                output_suffix = Path(output_file).suffix.lower()
                
                if output_suffix in ['.mp3', '.aac', '.ogg', '.flac', '.wav']:
                    # 音声変換または音声抽出
                    if input_suffix in ['.mp4', '.avi', '.mkv', '.webm', '.mov']:
                        # 動画から音声抽出
                        result = self.extract_audio(
                            input_file, output_file, 
                            output_suffix[1:], **options
                        )
                    else:
                        # 音声形式変換
                        result = self.convert_audio(
                            input_file, output_file, 
                            output_suffix[1:], **options
                        )
                else:
                    # 動画変換
                    result = self.convert_video(input_file, output_file, **options)
                
                if result:
                    results['success'].append({
                        'input': input_file, 
                        'output': result
                    })
                else:
                    results['failed'].append({
                        'input': input_file, 
                        'error': 'Conversion failed'
                    })
                    
            except Exception as e:
                logger.error(f"ファイル変換エラー: {input_file} - {e}")
                results['failed'].append({
                    'input': input_file, 
                    'error': str(e)
                })
        
        return results
