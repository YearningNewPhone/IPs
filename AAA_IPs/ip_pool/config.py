"""配置文件"""
import os


class Config:
    # Redis配置
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_DB = int(os.getenv('REDIS_DB', 0))
    REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

    # IP池Redis键名
    POOL_KEY = 'ip_pool:proxies'
    POOL_STATS_KEY = 'ip_pool:stats'

    # 验证配置
    VALIDATE_TIMEOUT = 10
    VALIDATE_URLS = [
        'http://httpbin.org/ip',
        'http://icanhazip.com',
        'http://ifconfig.me/ip',
    ]

    # 分数配置
    MAX_SCORE = 100
    MIN_SCORE = 0
    INIT_SCORE = 50
    SCORE_DECREASE = 10
    SCORE_INCREASE = 10

    # 调度配置（秒）
    FETCH_INTERVAL = 300      # 5分钟采集一次
    VALIDATE_INTERVAL = 120   # 2分钟验证一次
    STATS_INTERVAL = 10       # 10秒统计一次
    VALIDATE_BATCH_SIZE = 30

    # Web配置
    WEB_HOST = '0.0.0.0'
    WEB_PORT = 5000
    SECRET_KEY = 'ip-pool-secret-key-2024'