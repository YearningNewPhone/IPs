"""数据模型和Redis操作"""
import redis
import json
import time
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict, field
from config import Config


@dataclass
class Proxy:
    """代理数据模型"""
    ip: str
    port: int
    protocol: str = 'http'
    source: str = 'unknown'
    score: int = field(default_factory=lambda: Config.INIT_SCORE)
    response_time: float = 0.0
    last_check: float = 0.0
    create_time: float = field(default_factory=time.time)
    success_count: int = 0
    fail_count: int = 0

    @property
    def proxy_url(self) -> str:
        """返回代理URL格式"""
        return f"{self.protocol}://{self.ip}:{self.port}"

    @property
    def key(self) -> str:
        """唯一标识"""
        return f"{self.ip}:{self.port}"

    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Proxy':
        """从字典创建实例"""
        # 过滤掉不存在的字段
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)


class RedisClient:
    """Redis客户端单例"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_redis()
        return cls._instance

    def _init_redis(self):
        """初始化Redis连接"""
        try:
            self.conn = redis.Redis(
                host=Config.REDIS_HOST,
                port=Config.REDIS_PORT,
                db=Config.REDIS_DB,
                password=Config.REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=5
            )
            # 测试连接
            self.conn.ping()
            print(f"✅ Redis连接成功: {Config.REDIS_HOST}:{Config.REDIS_PORT}")
        except redis.ConnectionError as e:
            print(f"❌ Redis连接失败: {e}")
            raise

    def add_proxy(self, proxy: Proxy) -> bool:
        """添加代理"""
        try:
            pipe = self.conn.pipeline()
            pipe.hset(
                f"{Config.POOL_KEY}:detail",
                proxy.key,
                json.dumps(proxy.to_dict())
            )
            pipe.zadd(Config.POOL_KEY, {proxy.key: proxy.score})
            pipe.execute()
            return True
        except Exception as e:
            print(f"添加代理失败: {e}")
            return False

    def get_proxy(self, protocol: str = None) -> Optional[Proxy]:
        """获取一个高分代理"""
        try:
            # 获取分数最高的前10个代理
            top_proxies = self.conn.zrevrange(Config.POOL_KEY, 0, 9)
            if not top_proxies:
                return None

            import random
            random.shuffle(top_proxies)

            for key in top_proxies:
                data = self.conn.hget(f"{Config.POOL_KEY}:detail", key)
                if data:
                    proxy = Proxy.from_dict(json.loads(data))
                    if protocol is None or proxy.protocol == protocol:
                        return proxy
            return None
        except Exception as e:
            print(f"获取代理失败: {e}")
            return None

    def get_all_proxies(self) -> List[Proxy]:
        """获取所有代理"""
        try:
            all_data = self.conn.hgetall(f"{Config.POOL_KEY}:detail")
            proxies = []
            for key, value in all_data.items():
                try:
                    proxy = Proxy.from_dict(json.loads(value))
                    proxies.append(proxy)
                except Exception:
                    continue
            return sorted(proxies, key=lambda x: x.score, reverse=True)
        except Exception as e:
            print(f"获取所有代理失败: {e}")
            return []

    def update_proxy(self, proxy: Proxy) -> bool:
        """更新代理"""
        try:
            pipe = self.conn.pipeline()
            pipe.hset(
                f"{Config.POOL_KEY}:detail",
                proxy.key,
                json.dumps(proxy.to_dict())
            )
            pipe.zadd(Config.POOL_KEY, {proxy.key: proxy.score})
            pipe.execute()
            return True
        except Exception as e:
            print(f"更新代理失败: {e}")
            return False

    def remove_proxy(self, proxy: Proxy) -> bool:
        """删除代理"""
        try:
            pipe = self.conn.pipeline()
            pipe.hdel(f"{Config.POOL_KEY}:detail", proxy.key)
            pipe.zrem(Config.POOL_KEY, proxy.key)
            pipe.execute()
            return True
        except Exception as e:
            print(f"删除代理失败: {e}")
            return False

    def exists(self, proxy: Proxy) -> bool:
        """检查代理是否已存在"""
        return self.conn.hexists(f"{Config.POOL_KEY}:detail", proxy.key)

    def get_count(self) -> int:
        """获取代理总数"""
        return self.conn.zcard(Config.POOL_KEY)

    def get_stats(self) -> Dict:
        """获取统计信息"""
        proxies = self.get_all_proxies()
        total = len(proxies)

        if total == 0:
            return {
                'total': 0,
                'available': 0,
                'high_score': 0,
                'medium_score': 0,
                'low_score': 0,
                'protocols': {},
                'sources': {},
                'avg_response_time': 0,
                'update_time': time.strftime('%Y-%m-%d %H:%M:%S')
            }

        available = sum(1 for p in proxies if p.score >= 50)
        high_score = sum(1 for p in proxies if p.score >= 80)
        medium_score = sum(1 for p in proxies if 50 <= p.score < 80)
        low_score = sum(1 for p in proxies if p.score < 50)

        protocols = {}
        sources = {}
        total_response_time = 0
        valid_response_count = 0

        for proxy in proxies:
            protocols[proxy.protocol] = protocols.get(proxy.protocol, 0) + 1
            sources[proxy.source] = sources.get(proxy.source, 0) + 1
            if proxy.response_time > 0:
                total_response_time += proxy.response_time
                valid_response_count += 1

        avg_response = round(total_response_time / valid_response_count, 2) if valid_response_count > 0 else 0

        return {
            'total': total,
            'available': available,
            'high_score': high_score,
            'medium_score': medium_score,
            'low_score': low_score,
            'protocols': protocols,
            'sources': sources,
            'avg_response_time': avg_response,
            'update_time': time.strftime('%Y-%m-%d %H:%M:%S')
        }

    def save_stats_history(self, stats: Dict):
        """保存统计历史"""
        stats_copy = stats.copy()
        stats_copy['timestamp'] = time.time()
        self.conn.lpush(Config.POOL_STATS_KEY, json.dumps(stats_copy))
        self.conn.ltrim(Config.POOL_STATS_KEY, 0, 999)

    def get_stats_history(self, limit: int = 60) -> List[Dict]:
        """获取统计历史"""
        try:
            data = self.conn.lrange(Config.POOL_STATS_KEY, 0, limit - 1)
            return [json.loads(item) for item in data]
        except Exception:
            return []

    def clear_all(self) -> bool:
        """清空所有代理"""
        try:
            self.conn.delete(Config.POOL_KEY)
            self.conn.delete(f"{Config.POOL_KEY}:detail")
            return True
        except Exception:
            return False