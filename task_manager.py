"""
並列処理管理モジュール
ThreadPoolとProcessPoolを使用したタスク管理
"""
import threading
import multiprocessing
import concurrent.futures
import logging
import time
from enum import Enum
from typing import Dict, List, Any, Callable, Optional, Union
from dataclasses import dataclass, field
from queue import Queue, Empty
import uuid

from config import config

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    """タスクステータス"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class TaskInfo:
    """タスク情報クラス"""
    task_id: str
    function_name: str
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    progress: float = 0.0
    
    @property
    def duration(self) -> Optional[float]:
        """実行時間を取得"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        elif self.start_time:
            return time.time() - self.start_time
        return None

class TaskManager:
    """タスク管理クラス"""
    
    def __init__(self, max_workers: int = None, use_processes: bool = False):
        """
        タスクマネージャーの初期化
        
        Args:
            max_workers: 最大ワーカー数
            use_processes: プロセスプールを使用するか（デフォルト: スレッドプール）
        """
        self.max_workers = max_workers or config.get('parallel.max_workers', 4)
        self.use_processes = use_processes or config.get('parallel.use_multiprocessing', False)
        
        # タスク管理
        self.tasks: Dict[str, TaskInfo] = {}
        self.task_lock = threading.Lock()
        
        # プール管理
        self.executor: Optional[concurrent.futures.Executor] = None
        self.futures: Dict[str, concurrent.futures.Future] = {}
        
        # 進捗管理
        self.progress_callbacks: Dict[str, Callable] = {}
        
        # 統計情報
        self.stats = {
            'total_tasks': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'cancelled_tasks': 0
        }
        
        logger.info(f"TaskManager初期化: max_workers={self.max_workers}, use_processes={self.use_processes}")

    def __enter__(self):
        """コンテキストマネージャー開始"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャー終了"""
        self.shutdown()

    def start(self):
        """エグゼキューターを開始"""
        if self.executor is not None:
            logger.warning("TaskManagerは既に開始されています")
            return
        
        try:
            if self.use_processes:
                self.executor = concurrent.futures.ProcessPoolExecutor(
                    max_workers=self.max_workers
                )
                logger.info(f"ProcessPoolExecutor開始: {self.max_workers}プロセス")
            else:
                self.executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=self.max_workers
                )
                logger.info(f"ThreadPoolExecutor開始: {self.max_workers}スレッド")
        except Exception as e:
            logger.error(f"エグゼキューター開始エラー: {e}")
            raise

    def shutdown(self, wait: bool = True):
        """エグゼキューターを終了"""
        if self.executor is None:
            return
        
        try:
            logger.info("TaskManagerを終了しています...")
            
            # 未完了タスクのキャンセル
            cancelled_count = 0
            for task_id, future in self.futures.items():
                if not future.done():
                    future.cancel()
                    with self.task_lock:
                        if task_id in self.tasks:
                            self.tasks[task_id].status = TaskStatus.CANCELLED
                    cancelled_count += 1
            
            if cancelled_count > 0:
                logger.info(f"{cancelled_count}個のタスクをキャンセルしました")
            
            # エグゼキューター終了
            self.executor.shutdown(wait=wait)
            self.executor = None
            
            logger.info("TaskManager終了完了")
            
        except Exception as e:
            logger.error(f"TaskManager終了エラー: {e}")

    def submit(self, fn: Callable, *args, progress_callback: Optional[Callable] = None, **kwargs) -> str:
        """
        タスクを投入
        
        Args:
            fn: 実行する関数
            *args: 関数の引数
            progress_callback: 進捗コールバック関数
            **kwargs: 関数のキーワード引数
            
        Returns:
            タスクID
        """
        if self.executor is None:
            self.start()
        
        task_id = str(uuid.uuid4())
        
        # タスク情報を作成
        task_info = TaskInfo(
            task_id=task_id,
            function_name=fn.__name__,
            args=args,
            kwargs=kwargs
        )
        
        try:
            # タスクを投入
            future = self.executor.submit(self._execute_task, task_id, fn, *args, **kwargs)
            
            with self.task_lock:
                self.tasks[task_id] = task_info
                self.futures[task_id] = future
                self.stats['total_tasks'] += 1
            
            # 進捗コールバックを登録
            if progress_callback:
                self.progress_callbacks[task_id] = progress_callback
            
            # 完了コールバックを設定
            future.add_done_callback(lambda f: self._task_completed(task_id, f))
            
            logger.debug(f"タスク投入: {task_id} - {fn.__name__}")
            return task_id
            
        except Exception as e:
            logger.error(f"タスク投入エラー: {e}")
            with self.task_lock:
                task_info.status = TaskStatus.FAILED
                task_info.error = str(e)
                self.tasks[task_id] = task_info
            raise

    def _execute_task(self, task_id: str, fn: Callable, *args, **kwargs) -> Any:
        """タスクを実行（ワーカー内で実行）"""
        try:
            # タスク開始を記録
            with self.task_lock:
                if task_id in self.tasks:
                    self.tasks[task_id].status = TaskStatus.RUNNING
                    self.tasks[task_id].start_time = time.time()
            
            logger.debug(f"タスク開始: {task_id} - {fn.__name__}")
            
            # 進捗コールバックをラップ
            if task_id in self.progress_callbacks:
                original_callback = self.progress_callbacks[task_id]
                
                def progress_wrapper(progress_info):
                    # 進捗情報を更新
                    with self.task_lock:
                        if task_id in self.tasks:
                            self.tasks[task_id].progress = progress_info.get('percentage', 0)
                    # 元のコールバックを呼び出し
                    original_callback(progress_info)
                
                # 進捗コールバックを関数に注入
                if 'progress_callback' in fn.__code__.co_varnames:
                    kwargs['progress_callback'] = progress_wrapper
            
            # 関数を実行
            result = fn(*args, **kwargs)
            
            logger.debug(f"タスク完了: {task_id} - {fn.__name__}")
            return result
            
        except Exception as e:
            logger.error(f"タスク実行エラー: {task_id} - {e}")
            raise

    def _task_completed(self, task_id: str, future: concurrent.futures.Future):
        """タスク完了時のコールバック"""
        try:
            with self.task_lock:
                if task_id not in self.tasks:
                    return
                
                task_info = self.tasks[task_id]
                task_info.end_time = time.time()
                
                if future.cancelled():
                    task_info.status = TaskStatus.CANCELLED
                    self.stats['cancelled_tasks'] += 1
                    logger.debug(f"タスクキャンセル: {task_id}")
                elif future.exception():
                    task_info.status = TaskStatus.FAILED
                    task_info.error = str(future.exception())
                    self.stats['failed_tasks'] += 1
                    logger.error(f"タスク失敗: {task_id} - {task_info.error}")
                else:
                    task_info.status = TaskStatus.COMPLETED
                    task_info.result = future.result()
                    task_info.progress = 100.0
                    self.stats['completed_tasks'] += 1
                    logger.debug(f"タスク成功: {task_id}")
                
                # Futureを削除
                if task_id in self.futures:
                    del self.futures[task_id]
                
                # 進捗コールバックを削除
                if task_id in self.progress_callbacks:
                    del self.progress_callbacks[task_id]
                    
        except Exception as e:
            logger.error(f"タスク完了処理エラー: {e}")

    def get_task_status(self, task_id: str) -> Optional[TaskInfo]:
        """タスクステータスを取得"""
        with self.task_lock:
            return self.tasks.get(task_id)

    def get_all_tasks(self) -> Dict[str, TaskInfo]:
        """全タスクの状態を取得"""
        with self.task_lock:
            return self.tasks.copy()

    def cancel_task(self, task_id: str) -> bool:
        """タスクをキャンセル"""
        try:
            if task_id in self.futures:
                future = self.futures[task_id]
                cancelled = future.cancel()
                
                if cancelled:
                    with self.task_lock:
                        if task_id in self.tasks:
                            self.tasks[task_id].status = TaskStatus.CANCELLED
                    logger.info(f"タスクキャンセル成功: {task_id}")
                else:
                    logger.warning(f"タスクキャンセル失敗（実行中）: {task_id}")
                
                return cancelled
            else:
                logger.warning(f"タスクが見つかりません: {task_id}")
                return False
                
        except Exception as e:
            logger.error(f"タスクキャンセルエラー: {e}")
            return False

    def wait_for_completion(self, task_ids: List[str] = None, timeout: float = None) -> Dict[str, TaskInfo]:
        """
        タスクの完了を待機
        
        Args:
            task_ids: 待機するタスクIDのリスト（None なら全タスク）
            timeout: タイムアウト時間（秒）
            
        Returns:
            完了したタスクの情報
        """
        if task_ids is None:
            task_ids = list(self.futures.keys())
        
        # 該当するFutureを取得
        futures_to_wait = {
            task_id: self.futures[task_id] 
            for task_id in task_ids 
            if task_id in self.futures
        }
        
        if not futures_to_wait:
            return {}
        
        try:
            # 完了を待機
            completed_futures = concurrent.futures.as_completed(
                futures_to_wait.values(), 
                timeout=timeout
            )
            
            completed_tasks = {}
            for future in completed_futures:
                # Futureに対応するタスクIDを特定
                task_id = None
                for tid, fut in futures_to_wait.items():
                    if fut is future:
                        task_id = tid
                        break
                
                if task_id:
                    completed_tasks[task_id] = self.get_task_status(task_id)
            
            return completed_tasks
            
        except concurrent.futures.TimeoutError:
            logger.warning(f"タスク完了待機がタイムアウトしました: {timeout}秒")
            return {}
        except Exception as e:
            logger.error(f"タスク完了待機エラー: {e}")
            return {}

    def get_statistics(self) -> Dict[str, Any]:
        """統計情報を取得"""
        with self.task_lock:
            running_tasks = sum(1 for task in self.tasks.values() if task.status == TaskStatus.RUNNING)
            pending_tasks = sum(1 for task in self.tasks.values() if task.status == TaskStatus.PENDING)
            
            stats = self.stats.copy()
            stats.update({
                'running_tasks': running_tasks,
                'pending_tasks': pending_tasks,
                'active_workers': len(self.futures),
                'max_workers': self.max_workers,
                'executor_type': 'ProcessPool' if self.use_processes else 'ThreadPool'
            })
            
            return stats

class ProgressTracker:
    """進捗追跡クラス"""
    
    def __init__(self, task_manager: TaskManager):
        self.task_manager = task_manager
        self.tracking_tasks: Dict[str, Dict[str, Any]] = {}
        self.callbacks: List[Callable] = []
    
    def add_callback(self, callback: Callable):
        """進捗コールバックを追加"""
        self.callbacks.append(callback)
    
    def start_tracking(self, task_id: str):
        """タスクの進捗追跡を開始"""
        self.tracking_tasks[task_id] = {
            'start_time': time.time(),
            'last_update': time.time(),
            'progress': 0.0
        }
    
    def update_progress(self, task_id: str, progress: float):
        """進捗を更新"""
        if task_id in self.tracking_tasks:
            self.tracking_tasks[task_id].update({
                'progress': progress,
                'last_update': time.time()
            })
            
            # コールバックを呼び出し
            for callback in self.callbacks:
                try:
                    callback(task_id, progress)
                except Exception as e:
                    logger.error(f"進捗コールバックエラー: {e}")
    
    def get_overall_progress(self) -> float:
        """全体の進捗率を取得"""
        if not self.tracking_tasks:
            return 0.0
        
        total_progress = sum(task['progress'] for task in self.tracking_tasks.values())
        return total_progress / len(self.tracking_tasks)
    
    def stop_tracking(self, task_id: str):
        """タスクの進捗追跡を停止"""
        if task_id in self.tracking_tasks:
            del self.tracking_tasks[task_id]

class BatchProcessor:
    """バッチ処理クラス"""
    
    def __init__(self, task_manager: TaskManager):
        self.task_manager = task_manager
        self.progress_tracker = ProgressTracker(task_manager)
    
    def process_batch(self, items: List[Any], processor_func: Callable, 
                     batch_size: int = None, **kwargs) -> Dict[str, Any]:
        """
        バッチ処理を実行
        
        Args:
            items: 処理対象アイテムのリスト
            processor_func: 処理関数
            batch_size: バッチサイズ
            **kwargs: 処理関数への追加引数
            
        Returns:
            処理結果
        """
        batch_size = batch_size or self.task_manager.max_workers
        
        results = {
            'completed': [],
            'failed': [],
            'total': len(items)
        }
        
        # バッチに分割
        batches = [items[i:i + batch_size] for i in range(0, len(items), batch_size)]
        
        for batch_idx, batch in enumerate(batches):
            logger.info(f"バッチ処理 {batch_idx + 1}/{len(batches)}: {len(batch)}アイテム")
            
            # バッチ内のタスクを投入
            task_ids = []
            for item in batch:
                try:
                    task_id = self.task_manager.submit(
                        processor_func, item, **kwargs
                    )
                    task_ids.append(task_id)
                    self.progress_tracker.start_tracking(task_id)
                except Exception as e:
                    logger.error(f"バッチアイテム投入エラー: {e}")
                    results['failed'].append({'item': item, 'error': str(e)})
            
            # バッチ完了を待機
            completed_tasks = self.task_manager.wait_for_completion(task_ids)
            
            # 結果を集計
            for task_id, task_info in completed_tasks.items():
                self.progress_tracker.stop_tracking(task_id)
                
                if task_info.status == TaskStatus.COMPLETED:
                    results['completed'].append({
                        'task_id': task_id,
                        'result': task_info.result
                    })
                else:
                    results['failed'].append({
                        'task_id': task_id,
                        'error': task_info.error
                    })
        
        return results
