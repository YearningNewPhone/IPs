"""调度器"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
import time
from fetcher import ProxyFetcher
from validator import ProxyValidator
from models import RedisClient
from config import Config


class PoolScheduler:
    """IP池调度器"""

    def __init__(self, socketio=None):
        self.fetcher = ProxyFetcher()
        self.validator = ProxyValidator()
        self.redis = RedisClient()
        self.socketio = socketio
        self.is_running = False

        executors = {
            'default': ThreadPoolExecutor(5)
        }

        job_defaults = {
            'coalesce': True,
            'max_instances': 1
        }

        self.scheduler = BackgroundScheduler(
            executors=executors,
            job_defaults=job_defaults
        )

    def _emit(self, event: str, data: dict):
        """发送WebSocket事件"""
        if self.socketio:
            try:
                self.socketio.emit(event, data)
            except Exception as e:
                print(f"WebSocket发送失败: {e}")

    def fetch_job(self):
        """采集任务"""
        if not self.is_running:
            return

        try:
            results = self.fetcher.fetch_all()
            self._emit('fetch_complete', results)
        except Exception as e:
            print(f"采集任务异常: {e}")

    def validate_job(self):
        """验证任务"""
        if not self.is_running:
            return

        try:
            results = self.validator.validate_all()
            self._emit('validate_complete', results)
        except Exception as e:
            print(f"验证任务异常: {e}")

    def stats_job(self):
        """统计任务"""
        if not self.is_running:
            return

        try:
            stats = self.redis.get_stats()
            self.redis.save_stats_history(stats)
            self._emit('stats_update', stats)
        except Exception as e:
            print(f"统计任务异常: {e}")

    def start(self):
        """启动调度器"""
        if self.is_running:
            return

        self.is_running = True

        # 添加定时任务
        self.scheduler.add_job(
            self.fetch_job,
            'interval',
            seconds=Config.FETCH_INTERVAL,
            id='fetch_job',
            name='IP采集任务'
        )

        self.scheduler.add_job(
            self.validate_job,
            'interval',
            seconds=Config.VALIDATE_INTERVAL,
            id='validate_job',
            name='IP验证任务'
        )

        self.scheduler.add_job(
            self.stats_job,
            'interval',
            seconds=Config.STATS_INTERVAL,
            id='stats_job',
            name='统计任务'
        )

        self.scheduler.start()
        print("\n✅ 调度器已启动")
        print(f"   - 采集间隔: {Config.FETCH_INTERVAL}秒")
        print(f"   - 验证间隔: {Config.VALIDATE_INTERVAL}秒")
        print(f"   - 统计间隔: {Config.STATS_INTERVAL}秒")

        # 启动后立即执行一次采集
        print("\n🚀 正在执行初始采集...")
        self.scheduler.add_job(
            self.fetch_job,
            'date',
            id='init_fetch',
            replace_existing=True
        )

    def stop(self):
        """停止调度器"""
        self.is_running = False
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            print("调度器已停止")

    def get_jobs(self) -> list:
        """获取任务列表"""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': str(job.next_run_time) if job.next_run_time else None
            })
        return jobs

    def run_fetch_now(self) -> dict:
        """立即执行采集"""
        return self.fetcher.fetch_all()

    def run_validate_now(self) -> dict:
        """立即执行验证"""
        return self.validator.validate_all()