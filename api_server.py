"""
APIサーバーモジュール
FastAPIを使用したRESTful API実装
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, HttpUrl, validator
import uvicorn
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
import asyncio
from datetime import datetime

from config import config
from downloader import VideoDownloader, BatchDownloader
from converter import VideoConverter
from task_manager import TaskManager, TaskStatus
from utils import parse_url_list_file, format_bytes

logger = logging.getLogger(__name__)

# APIアプリケーション
app = FastAPI(
    title="Media Downloader & Converter API",
    description="動画・音声ダウンロード変換API",
    version=config.get('app.version', '1.0.0')
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.get('api.cors_origins', ["*"]),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# グローバルインスタンス
task_manager = TaskManager()
downloader = VideoDownloader()
converter = VideoConverter()
batch_downloader = BatchDownloader()

# リクエストモデル
class DownloadRequest(BaseModel):
    url: HttpUrl
    output_dir: Optional[str] = None
    format: Optional[str] = None
    audio_only: bool = False
    audio_format: str = "mp3"
    
    @validator('audio_format')
    def validate_audio_format(cls, v):
        allowed_formats = ['mp3', 'aac', 'wav', 'flac', 'ogg']
        if v not in allowed_formats:
            raise ValueError(f'audio_format must be one of {allowed_formats}')
        return v

class BatchDownloadRequest(BaseModel):
    urls: List[HttpUrl]
    output_dir: Optional[str] = None
    audio_only: bool = False
    audio_format: str = "mp3"
    max_workers: Optional[int] = None

class ConvertRequest(BaseModel):
    input_file: str
    output_file: str
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    use_hardware: bool = True
    video_bitrate: Optional[str] = None
    audio_bitrate: Optional[str] = None
    resolution: Optional[str] = None

class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: float
    result: Optional[Any] = None
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration: Optional[float] = None

# API エンドポイント
@app.get("/")
async def root():
    """ルートエンドポイント"""
    return {
        "name": config.get('app.name', 'Media Downloader & Converter'),
        "version": config.get('app.version', '1.0.0'),
        "status": "running",
        "endpoints": {
            "download": "/download",
            "batch_download": "/batch-download", 
            "convert": "/convert",
            "tasks": "/tasks",
            "health": "/health"
        }
    }

@app.get("/health")
async def health_check():
    """ヘルスチェック"""
    stats = task_manager.get_statistics()
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "task_manager": stats,
        "config": {
            "max_workers": config.get('parallel.max_workers'),
            "download_dir": config.get('download.output_dir'),
            "use_hardware": config.get('convert.use_hardware')
        }
    }

@app.post("/download", response_model=TaskResponse)
async def download_media(request: DownloadRequest, background_tasks: BackgroundTasks):
    """メディアダウンロード"""
    try:
        def download_task():
            try:
                if request.audio_only:
                    return downloader.download_audio(
                        str(request.url),
                        request.output_dir or config.get('download.output_dir'),
                        request.audio_format
                    )
                else:
                    return downloader.download_video(
                        str(request.url),
                        request.output_dir or config.get('download.output_dir'),
                        request.format
                    )
            except Exception as e:
                logger.error(f"ダウンロードタスクエラー: {e}")
                raise
        
        # バックグラウンドタスクとして実行
        task_id = task_manager.submit(download_task)
        
        return TaskResponse(
            task_id=task_id,
            status="accepted",
            message="ダウンロードタスクが開始されました"
        )
        
    except Exception as e:
        logger.error(f"ダウンロード開始エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/batch-download", response_model=TaskResponse)
async def batch_download_media(request: BatchDownloadRequest):
    """バッチダウンロード"""
    try:
        def batch_task():
            urls = [str(url) for url in request.urls]
            return batch_downloader.download_urls(
                urls,
                request.output_dir or config.get('download.output_dir'),
                request.audio_only
            )
        
        task_id = task_manager.submit(batch_task)
        
        return TaskResponse(
            task_id=task_id,
            status="accepted",
            message=f"{len(request.urls)}件のバッチダウンロードが開始されました"
        )
        
    except Exception as e:
        logger.error(f"バッチダウンロード開始エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/convert", response_model=TaskResponse)
async def convert_media(request: ConvertRequest):
    """メディア変換"""
    try:
        # 入力ファイルの存在確認
        if not Path(request.input_file).exists():
            raise HTTPException(
                status_code=400, 
                detail=f"入力ファイルが見つかりません: {request.input_file}"
            )
        
        def convert_task():
            # 変換オプションの構築
            options = {
                'video_codec': request.video_codec,
                'audio_codec': request.audio_codec,
                'use_hardware': request.use_hardware,
                'video_bitrate': request.video_bitrate,
                'audio_bitrate': request.audio_bitrate,
                'resolution': request.resolution
            }
            
            # ファイル拡張子に基づいて変換方法を決定
            input_suffix = Path(request.input_file).suffix.lower()
            output_suffix = Path(request.output_file).suffix.lower()
            
            if output_suffix in ['.mp3', '.aac', '.ogg', '.flac', '.wav']:
                # 音声変換または音声抽出
                if input_suffix in ['.mp4', '.avi', '.mkv', '.webm', '.mov']:
                    return converter.extract_audio(
                        request.input_file, 
                        request.output_file,
                        output_suffix[1:],
                        **options
                    )
                else:
                    return converter.convert_audio(
                        request.input_file, 
                        request.output_file,
                        output_suffix[1:],
                        **options
                    )
            else:
                return converter.convert_video(
                    request.input_file, 
                    request.output_file,
                    **options
                )
        
        task_id = task_manager.submit(convert_task)
        
        return TaskResponse(
            task_id=task_id,
            status="accepted",
            message="変換タスクが開始されました"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"変換開始エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """タスクステータス取得"""
    task_info = task_manager.get_task_status(task_id)
    
    if not task_info:
        raise HTTPException(status_code=404, detail="タスクが見つかりません")
    
    return TaskStatusResponse(
        task_id=task_info.task_id,
        status=task_info.status.value,
        progress=task_info.progress,
        result=task_info.result,
        error=task_info.error,
        start_time=datetime.fromtimestamp(task_info.start_time) if task_info.start_time else None,
        end_time=datetime.fromtimestamp(task_info.end_time) if task_info.end_time else None,
        duration=task_info.duration
    )

@app.get("/tasks")
async def get_all_tasks():
    """全タスク一覧取得"""
    tasks = task_manager.get_all_tasks()
    
    task_list = []
    for task_id, task_info in tasks.items():
        task_list.append({
            "task_id": task_info.task_id,
            "function_name": task_info.function_name,
            "status": task_info.status.value,
            "progress": task_info.progress,
            "start_time": datetime.fromtimestamp(task_info.start_time) if task_info.start_time else None,
            "end_time": datetime.fromtimestamp(task_info.end_time) if task_info.end_time else None,
            "duration": task_info.duration
        })
    
    return {
        "tasks": task_list,
        "statistics": task_manager.get_statistics()
    }

@app.delete("/tasks/{task_id}")
async def cancel_task(task_id: str):
    """タスクキャンセル"""
    success = task_manager.cancel_task(task_id)
    
    if success:
        return {"message": f"タスク {task_id} をキャンセルしました"}
    else:
        raise HTTPException(status_code=400, detail="タスクのキャンセルに失敗しました")

@app.post("/upload-urls")
async def upload_url_list(file: UploadFile = File(...)):
    """URLリストファイルアップロード"""
    try:
        # ファイル内容を読み取り
        content = await file.read()
        
        # 一時ファイルに保存
        temp_file = Path("temp_urls.txt")
        with open(temp_file, 'wb') as f:
            f.write(content)
        
        # URLリストを解析
        urls = parse_url_list_file(str(temp_file))
        
        # 一時ファイルを削除
        temp_file.unlink()
        
        return {
            "filename": file.filename,
            "urls_count": len(urls),
            "urls": urls[:10],  # 最初の10個のみ表示
            "message": f"{len(urls)}個のURLを検出しました"
        }
        
    except Exception as e:
        logger.error(f"URLファイルアップロードエラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/video-info")
async def get_video_info(url: HttpUrl):
    """動画情報取得"""
    try:
        info = downloader.get_video_info(str(url))
        
        if not info:
            raise HTTPException(status_code=400, detail="動画情報の取得に失敗しました")
        
        return info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"動画情報取得エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/media-info")
async def get_media_info(file_path: str):
    """メディアファイル情報取得"""
    try:
        if not Path(file_path).exists():
            raise HTTPException(status_code=404, detail="ファイルが見つかりません")
        
        info = converter.get_media_info(file_path)
        
        if not info:
            raise HTTPException(status_code=400, detail="メディア情報の取得に失敗しました")
        
        # ファイルサイズを追加
        file_size = Path(file_path).stat().st_size
        info['file_size'] = file_size
        info['file_size_formatted'] = format_bytes(file_size)
        
        return info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"メディア情報取得エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download-file")
async def download_file(file_path: str):
    """ファイルダウンロード"""
    try:
        path = Path(file_path)
        
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="ファイルが見つかりません")
        
        return FileResponse(
            path=str(path),
            filename=path.name,
            media_type='application/octet-stream'
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ファイルダウンロードエラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/list-files")
async def list_files(directory: str = None):
    """ファイル一覧取得"""
    try:
        base_dir = Path(directory or config.get('download.output_dir', './downloads'))
        
        if not base_dir.exists():
            raise HTTPException(status_code=404, detail="ディレクトリが見つかりません")
        
        files = []
        for file_path in base_dir.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "path": str(file_path),
                    "size": stat.st_size,
                    "size_formatted": format_bytes(stat.st_size),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "extension": file_path.suffix.lower()
                })
        
        # ファイル名でソート
        files.sort(key=lambda x: x['name'])
        
        return {
            "directory": str(base_dir),
            "file_count": len(files),
            "files": files
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ファイル一覧取得エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# エラーハンドラー
@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """一般的な例外ハンドラー"""
    logger.error(f"未処理例外: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "内部サーバーエラーが発生しました"}
    )

# 起動時処理
@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時処理"""
    logger.info("APIサーバーを起動しています...")
    
    # タスクマネージャー開始
    task_manager.start()
    
    # 出力ディレクトリの作成
    output_dir = Path(config.get('download.output_dir', './downloads'))
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("APIサーバー起動完了")

# 終了時処理
@app.on_event("shutdown")
async def shutdown_event():
    """アプリケーション終了時処理"""
    logger.info("APIサーバーを終了しています...")
    
    # タスクマネージャー終了
    task_manager.shutdown()
    
    logger.info("APIサーバー終了完了")

def run_api_server(host: str = "0.0.0.0", port: int = 8000, debug: bool = False):
    """APIサーバー実行"""
    uvicorn.run(
        "api_server:app",
        host=host,
        port=port,
        debug=debug,
        reload=debug,
        log_level="info" if not debug else "debug"
    )

if __name__ == "__main__":
    run_api_server()
