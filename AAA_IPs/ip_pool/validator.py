"""IP验证器"""
import asyncio
import aiohttp
import time
import random
from typing import List, Tuple
from models import Proxy, RedisClient
from config import Config


class ProxyValidator:
    """代理验证器"""

    def __init__(self):
        self.redis = RedisClient()
        self.validate_urls = Config.VALIDATE_URLS
        self.timeout = Config.VALIDATE_TIMEOUT

    async def validate_single(
        self,
        proxy: Proxy,
        session: aiohttp.ClientSession
    ) -> Tuple[bool, float]:
        """验证单个代理"""

        # 随机选择一个验证URL
        validate_url = random.choice(self.validate_urls)

        try:
            start_time = time.time()

            async with session.get(
                validate_url,
                proxy=proxy.proxy_url,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                ssl=False
            ) as response:

                if response.status == 200:
                    await response.text()
                    response_time = (time.time() - start_time) * 1000
                    return True, response_time

        except asyncio.TimeoutError:
            pass
        except aiohttp.ClientError:
            pass
        except Exception:
            pass

        return False, 0

    async def validate_and_update(
        self,
        proxy: Proxy,
        session: aiohttp.ClientSession
    ) -> bool:
        """验证并更新代理状态"""

        success, response_time = await self.validate_single(proxy, session)

        proxy.last_check = time.time()

        if success:
            proxy.response_time = round(response_time, 2)
            proxy.success_count += 1
            proxy.score = min(proxy.score + Config.SCORE_INCREASE, Config.MAX_SCORE)
            self.redis.update_proxy(proxy)
            return True
        else:
            proxy.fail_count += 1
            proxy.score = max(proxy.score - Config.SCORE_DECREASE, Config.MIN_SCORE)

            if proxy.score <= Config.MIN_SCORE:
                self.redis.remove_proxy(proxy)
                return False

            self.redis.update_proxy(proxy)
            return False

    async def validate_batch(self, proxies: List[Proxy]) -> dict:
        """批量验证"""
        results = {
            'total': len(proxies),
            'success': 0,
            'fail': 0
        }

        if not proxies:
            return results

        connector = aiohttp.TCPConnector(
            limit=50,
            force_close=True,
            enable_cleanup_closed=True
        )

        timeout = aiohttp.ClientTimeout(total=self.timeout + 5)

        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
        ) as session:

            tasks = [
                self.validate_and_update(proxy, session)
                for proxy in proxies
            ]

            completed = await asyncio.gather(*tasks, return_exceptions=True)

            for result in completed:
                if result is True:
                    results['success'] += 1
                else:
                    results['fail'] += 1

        return results

    def validate_all(self) -> dict:
        """验证所有代理"""
        proxies = self.redis.get_all_proxies()

        if not proxies:
            print("没有代理需要验证")
            return {'total': 0, 'success': 0, 'fail': 0}

        print(f"\n{'='*50}")
        print(f"开始验证任务 - {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"待验证代理数: {len(proxies)}")
        print('='*50)

        all_results = {
            'total': 0,
            'success': 0,
            'fail': 0
        }

        batch_size = Config.VALIDATE_BATCH_SIZE

        # 创建新的事件循环
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        try:
            for i in range(0, len(proxies), batch_size):
                batch = proxies[i:i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (len(proxies) + batch_size - 1) // batch_size

                print(f"\n▶ 验证批次 {batch_num}/{total_batches} ({len(batch)}个代理)")

                results = loop.run_until_complete(self.validate_batch(batch))

                all_results['total'] += results['total']
                all_results['success'] += results['success']
                all_results['fail'] += results['fail']

                print(f"  ✓ 成功: {results['success']}, 失败: {results['fail']}")

        except Exception as e:
            print(f"验证过程出错: {e}")

        print(f"\n{'='*50}")
        print(f"验证完成: 成功 {all_results['success']}/{all_results['total']}")
        print(f"当前池中共有 {self.redis.get_count()} 个代理")
        print('='*50)

        return all_results