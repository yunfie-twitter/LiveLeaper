#!/usr/bin/env python3
"""
メイン制御モジュール
各モードの起動制御（CLI/API/GUI/バッチ）
初回起動時の設定ウィザード対応
"""
import sys
import argparse
import logging
from pathlib import Path

from config import config
from utils import setup_logging

def setup_argument_parser():
    """コマンドライン引数パーサーの設定"""
    parser = argparse.ArgumentParser(
        description="LiveLeaper 動画・音声ダウンロード変換ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  %(prog)s gui                                    # GUIモードで起動
  %(prog)s api                                    # APIサーバーモードで起動
  %(prog)s download "https://youtube.com/..."     # 単発ダウンロード
  %(prog)s batch urls.txt                         # バッチ処理
  %(prog)s convert input.mp4 output.mp3           # ファイル変換
  %(prog)s setup                                  # 初期設定ウィザード
        """
    )

    # サブコマンド
    subparsers = parser.add_subparsers(dest='mode', help='動作モード')

    # GUIモード
    gui_parser = subparsers.add_parser('gui', help='GUIモードで起動')

    # セットアップモード
    setup_parser = subparsers.add_parser('setup', help='初期設定ウィザードを起動')

    # APIサーバーモード
    api_parser = subparsers.add_parser('api', help='APIサーバーモードで起動')
    api_parser.add_argument('--host', default=config.get('api.host', '0.0.0.0'),
                           help='APIサーバーのホスト')
    api_parser.add_argument('--port', type=int, default=config.get('api.port', 8000),
                           help='APIサーバーのポート')
    api_parser.add_argument('--debug', action='store_true',
                           help='デバッグモードで起動')

    # ダウンロードモード
    download_parser = subparsers.add_parser('download', help='動画・音声をダウンロード')
    download_parser.add_argument('url', help='ダウンロードするURL')
    download_parser.add_argument('-o', '--output', help='出力ディレクトリ')
    download_parser.add_argument('-f', '--format', help='出力形式')
    download_parser.add_argument('--audio-only', action='store_true',
                                help='音声のみ抽出')
    download_parser.add_argument('--audio-format', default='mp3',
                                choices=['mp3', 'aac', 'wav', 'flac'],
                                help='音声形式')

    # バッチ処理モード
    batch_parser = subparsers.add_parser('batch', help='バッチ処理モード')
    batch_parser.add_argument('file', help='URLリストファイル')
    batch_parser.add_argument('-o', '--output', help='出力ディレクトリ')
    batch_parser.add_argument('--audio-only', action='store_true',
                             help='音声のみ抽出')
    batch_parser.add_argument('--max-workers', type=int,
                             help='最大並列数')

    # 変換モード
    convert_parser = subparsers.add_parser('convert', help='ファイル形式変換')
    convert_parser.add_argument('input', help='入力ファイル')
    convert_parser.add_argument('output', help='出力ファイル')
    convert_parser.add_argument('--video-codec', help='動画コーデック')
    convert_parser.add_argument('--audio-codec', help='音声コーデック')
    convert_parser.add_argument('--no-hardware', action='store_true',
                               help='ハードウェアエンコーディングを無効化')

    # 共通オプション
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='詳細ログを出力')
    parser.add_argument('--config', help='設定ファイルパス')
    parser.add_argument('--log-file', help='ログファイルパス')
    parser.add_argument('--skip-setup', action='store_true',
                       help='初期設定をスキップ')

    return parser

def check_first_run():
    """初回起動かどうかをチェック"""
    try:
        from PyQt5.QtCore import QSettings
        settings = QSettings("MediaDownloader", "Settings")
        return not settings.value("setup_completed", False, type=bool)
    except ImportError:
        # PyQt5がない場合はconfig.yamlの存在で判定
        config_file = Path("config.yaml")
        return not config_file.exists()

def run_setup_wizard():
    """初期設定ウィザードを実行"""
    try:
        from PyQt5.QtWidgets import QApplication
        from setup_wizard import SetupWizard
        
        app = QApplication(sys.argv)
        wizard = SetupWizard()
        
        if wizard.exec_() == wizard.Accepted:
            logging.info("初期設定が完了しました")
            return True
        else:
            logging.info("初期設定がキャンセルされました")
            return False
            
    except ImportError as e:
        logging.error(f"セットアップウィザードの起動に失敗しました: {e}")
        logging.error("pip install PyQt5 でGUIライブラリをインストールしてください")
        return False

def run_gui_mode():
    """GUIモード実行"""
    try:
        from PyQt5.QtWidgets import QApplication
        from gui import MediaDownloaderGUI
        
        app = QApplication(sys.argv)
        window = MediaDownloaderGUI()
        window.show()
        sys.exit(app.exec_())
    except ImportError as e:
        logging.error(f"GUI関連ライブラリのインポートに失敗しました: {e}")
        logging.error("pip install PyQt5 でGUIライブラリをインストールしてください")
        sys.exit(1)

def run_api_mode(host: str, port: int, debug: bool = False):
    """APIサーバーモード実行"""
    try:
        import uvicorn
        from api_server import app

        logging.info(f"APIサーバーを起動します: http://{host}:{port}")
        uvicorn.run(app, host=host, port=port, debug=debug)
    except ImportError as e:
        logging.error(f"API関連ライブラリのインポートに失敗しました: {e}")
        logging.error("pip install fastapi uvicorn でAPIライブラリをインストールしてください")
        sys.exit(1)

def run_download_mode(url: str, output: str = None, format: str = None,
                     audio_only: bool = False, audio_format: str = 'mp3'):
    """ダウンロードモード実行"""
    from downloader import VideoDownloader

    output_dir = output or config.get('download.output_dir', './downloads')
    downloader = VideoDownloader()

    try:
        if audio_only:
            result = downloader.download_audio(url, output_dir, audio_format)
        else:
            result = downloader.download_video(url, output_dir, format)

        if result:
            logging.info(f"ダウンロード完了: {result}")
        else:
            logging.error("ダウンロードに失敗しました")
            sys.exit(1)

    except Exception as e:
        logging.error(f"ダウンロード中にエラーが発生しました: {e}")
        sys.exit(1)

def run_batch_mode(file_path: str, output: str = None, audio_only: bool = False,
                  max_workers: int = None):
    """バッチ処理モード実行"""
    from downloader import VideoDownloader
    from task_manager import TaskManager
    from utils import parse_url_list_file

    # URLリストファイルの読み込み
    try:
        urls = parse_url_list_file(file_path)
        if not urls:
            logging.error("有効なURLが見つかりませんでした")
            sys.exit(1)

        logging.info(f"バッチ処理開始: {len(urls)}件のURL")
    except Exception as e:
        logging.error(f"URLリストファイルの読み込みに失敗しました: {e}")
        sys.exit(1)

    # 並列処理設定
    workers = max_workers or config.get('parallel.max_workers', 4)
    task_manager = TaskManager(max_workers=workers)
    downloader = VideoDownloader()

    output_dir = output or config.get('download.output_dir', './downloads')

    # タスクの実行
    try:
        with task_manager:
            tasks = []
            for url in urls:
                if audio_only:
                    task = task_manager.submit(downloader.download_audio, url, output_dir)
                else:
                    task = task_manager.submit(downloader.download_video, url, output_dir)
                tasks.append(task)

            # 結果の収集
            completed = 0
            failed = 0
            for task in tasks:
                try:
                    result = task.result()
                    if result:
                        completed += 1
                        logging.info(f"完了: {result}")
                    else:
                        failed += 1
                        logging.warning("ダウンロードに失敗しました")
                except Exception as e:
                    failed += 1
                    logging.error(f"タスクエラー: {e}")

            logging.info(f"バッチ処理完了: 成功 {completed}件, 失敗 {failed}件")

    except Exception as e:
        logging.error(f"バッチ処理中にエラーが発生しました: {e}")
        sys.exit(1)

def run_convert_mode(input_file: str, output_file: str, video_codec: str = None,
                    audio_codec: str = None, no_hardware: bool = False):
    """変換モード実行"""
    from converter import VideoConverter

    # 入力ファイルの存在確認
    if not Path(input_file).exists():
        logging.error(f"入力ファイルが見つかりません: {input_file}")
        sys.exit(1)

    converter = VideoConverter()

    try:
        result = converter.convert_file(
            input_file=input_file,
            output_file=output_file,
            video_codec=video_codec,
            audio_codec=audio_codec,
            use_hardware=not no_hardware
        )

        if result:
            logging.info(f"変換完了: {result}")
        else:
            logging.error("変換に失敗しました")
            sys.exit(1)

    except Exception as e:
        logging.error(f"変換中にエラーが発生しました: {e}")
        sys.exit(1)

def main():
    """メイン関数"""
    parser = setup_argument_parser()
    args = parser.parse_args()

    # 設定ファイルの読み込み
    if args.config:
        from config import Config
        global config
        config = Config(args.config)

    # ロギング設定
    setup_logging()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # ログファイルの変更
    if args.log_file:
        config.set('logging.file', args.log_file)
        setup_logging()  # 再設定

    # 初回起動チェック（セットアップモード以外）
    if args.mode != 'setup' and not args.skip_setup and check_first_run():
        logging.info("初回起動を検出しました。初期設定ウィザードを開始します。")
        if not run_setup_wizard():
            logging.warning("初期設定が完了していません。")
            if args.mode == 'gui' or args.mode is None:
                logging.info("GUIモードで起動しますが、設定メニューから初期設定を行ってください。")
            else:
                logging.error("初期設定が必要です。'python main.py setup' で設定を行ってください。")
                sys.exit(1)

    # モードに応じた処理実行
    if args.mode == 'setup':
        if run_setup_wizard():
            logging.info("初期設定が完了しました")
        else:
            logging.error("初期設定に失敗しました")
            sys.exit(1)
    elif args.mode == 'gui' or args.mode is None:
        run_gui_mode()
    elif args.mode == 'api':
        run_api_mode(args.host, args.port, args.debug)
    elif args.mode == 'download':
        run_download_mode(args.url, args.output, args.format,
                         args.audio_only, args.audio_format)
    elif args.mode == 'batch':
        run_batch_mode(args.file, args.output, args.audio_only, args.max_workers)
    elif args.mode == 'convert':
        run_convert_mode(args.input, args.output, args.video_codec,
                        args.audio_codec, args.no_hardware)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
