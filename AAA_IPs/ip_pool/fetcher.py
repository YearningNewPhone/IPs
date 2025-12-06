"""IP采集器"""
import requests
import re
import time
from abc import ABC, abstractmethod
from typing import List
from bs4 import BeautifulSoup
from models import Proxy, RedisClient
from config import Config

# 尝试导入fake_useragent，失败则使用默认UA
try:
    from fake_useragent import UserAgent
    ua = UserAgent()
    def get_random_ua():
        return ua.random
except Exception:
    def get_random_ua():
        return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'


class BaseFetcher(ABC):
    """采集器基类"""

    def __init__(self):
        self.redis = RedisClient()
        self.timeout = 15

    def get_headers(self) -> dict:
        return {
            'User-Agent': get_random_ua(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'close',
        }

    @property
    @abstractmethod
    def name(self) -> str:
        """采集器名称"""
        pass

    @abstractmethod
    def fetch(self) -> List[Proxy]:
        """采集代理"""
        pass

    def save(self, proxies: List[Proxy]) -> int:
        """保存代理"""
        saved = 0
        for proxy in proxies:
            if not self.redis.exists(proxy):
                proxy.create_time = time.time()
                if self.redis.add_proxy(proxy):
                    saved += 1
        return saved


class IP89Fetcher(BaseFetcher):
    """89IP - 比较稳定的免费代理源"""

    @property
    def name(self) -> str:
        return "89IP"

    def fetch(self) -> List[Proxy]:
        proxies = []

        for page in range(1, 4):
            try:
                url = f'https://www.89ip.cn/index_{page}.html' if page > 1 else 'https://www.89ip.cn/'
                resp = requests.get(url, headers=self.get_headers(), timeout=self.timeout)
                resp.encoding = 'utf-8'
                soup = BeautifulSoup(resp.text, 'lxml')

                table = soup.find('table', class_='layui-table')
                if not table:
                    continue

                for tr in table.find_all('tr')[1:]:  # 跳过表头
                    tds = tr.find_all('td')
                    if len(tds) >= 2:
                        ip = tds[0].get_text(strip=True)
                        port_text = tds[1].get_text(strip=True)

                        if ip and port_text and port_text.isdigit():
                            proxy = Proxy(
                                ip=ip,
                                port=int(port_text),
                                protocol='http',
                                source='89ip'
                            )
                            proxies.append(proxy)

                time.sleep(1)

            except Exception as e:
                print(f"  [89IP] 第{page}页采集失败: {e}")

        return proxies


class IP66Fetcher(BaseFetcher):
    """66IP代理"""

    @property
    def name(self) -> str:
        return "66IP"

    def fetch(self) -> List[Proxy]:
        proxies = []

        try:
            url = 'http://www.66ip.cn/mo.php?sxb=&tqsl=100&port=&export=&ktip=&sxa=&submit=%CC%E1++%C8%A1&textarea='
            resp = requests.get(url, headers=self.get_headers(), timeout=self.timeout)
            resp.encoding = 'gbk'

            # 使用正则提取IP和端口
            pattern = r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d+)'
            matches = re.findall(pattern, resp.text)

            for ip, port in matches:
                proxy = Proxy(
                    ip=ip,
                    port=int(port),
                    protocol='http',
                    source='66ip'
                )
                proxies.append(proxy)

        except Exception as e:
            print(f"  [66IP] 采集失败: {e}")

        return proxies


class FreeProxyListFetcher(BaseFetcher):
    """Free Proxy List - 国外代理源"""

    @property
    def name(self) -> str:
        return "FreeProxyList"

    def fetch(self) -> List[Proxy]:
        proxies = []

        try:
            url = 'https://free-proxy-list.net/'
            resp = requests.get(url, headers=self.get_headers(), timeout=self.timeout)
            soup = BeautifulSoup(resp.text, 'lxml')

            table = soup.find('table', class_='table')
            if table:
                rows = table.find('tbody').find_all('tr') if table.find('tbody') else []

                for tr in rows[:50]:  # 只取前50个
                    tds = tr.find_all('td')
                    if len(tds) >= 7:
                        ip = tds[0].get_text(strip=True)
                        port = tds[1].get_text(strip=True)
                        https = tds[6].get_text(strip=True).lower() == 'yes'

                        if ip and port and port.isdigit():
                            proxy = Proxy(
                                ip=ip,
                                port=int(port),
                                protocol='https' if https else 'http',
                                source='free-proxy-list'
                            )
                            proxies.append(proxy)

        except Exception as e:
            print(f"  [FreeProxyList] 采集失败: {e}")

        return proxies


class KuaiDailiFetcher(BaseFetcher):
    """快代理"""

    @property
    def name(self) -> str:
        return "快代理"

    def fetch(self) -> List[Proxy]:
        proxies = []
        urls = [
            'https://www.kuaidaili.com/free/inha/',
            'https://www.kuaidaili.com/free/intr/',
        ]

        for url in urls:
            try:
                resp = requests.get(url, headers=self.get_headers(), timeout=self.timeout)
                soup = BeautifulSoup(resp.text, 'lxml')

                table = soup.find('table', class_='table')
                if not table:
                    continue

                for tr in table.find_all('tr')[1:]:
                    tds = tr.find_all('td')
                    if len(tds) >= 4:
                        ip = tds[0].get_text(strip=True)
                        port = tds[1].get_text(strip=True)
                        protocol = tds[3].get_text(strip=True).lower()

                        if ip and port and port.isdigit():
                            proxy = Proxy(
                                ip=ip,
                                port=int(port),
                                protocol=protocol if protocol in ['http', 'https'] else 'http',
                                source='kuaidaili'
                            )
                            proxies.append(proxy)

                time.sleep(2)

            except Exception as e:
                print(f"  [快代理] 采集失败: {e}")

        return proxies


class ProxyListDownloadFetcher(BaseFetcher):
    """Proxy List Download - 纯文本代理列表"""

    @property
    def name(self) -> str:
        return "ProxyListDownload"

    def fetch(self) -> List[Proxy]:
        proxies = []
        urls = [
            'https://www.proxy-list.download/api/v1/get?type=http',
            'https://www.proxy-list.download/api/v1/get?type=https',
        ]

        for url in urls:
            try:
                protocol = 'https' if 'https' in url else 'http'
                resp = requests.get(url, headers=self.get_headers(), timeout=self.timeout)

                lines = resp.text.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if ':' in line:
                        parts = line.split(':')
                        if len(parts) == 2:
                            ip, port = parts
                            if port.isdigit():
                                proxy = Proxy(
                                    ip=ip.strip(),
                                    port=int(port),
                                    protocol=protocol,
                                    source='proxy-list-download'
                                )
                                proxies.append(proxy)

            except Exception as e:
                print(f"  [ProxyListDownload] 采集失败: {e}")

        return proxies


class ProxyFetcher:
    """代理采集管理器"""

    def __init__(self):
        self.fetchers = [
            IP89Fetcher(),
            IP66Fetcher(),
            FreeProxyListFetcher(),
            KuaiDailiFetcher(),
            ProxyListDownloadFetcher(),
        ]
        self.redis = RedisClient()

    def fetch_all(self) -> dict:
        """执行所有采集器"""
        results = {
            'total_fetched': 0,
            'total_saved': 0,
            'details': [],
            'time': time.strftime('%Y-%m-%d %H:%M:%S')
        }

        print(f"\n{'='*50}")
        print(f"开始采集任务 - {results['time']}")
        print('='*50)

        for fetcher in self.fetchers:
            try:
                print(f"\n▶ 正在采集: {fetcher.name}")

                proxies = fetcher.fetch()
                saved = fetcher.save(proxies)

                results['total_fetched'] += len(proxies)
                results['total_saved'] += saved
                results['details'].append({
                    'source': fetcher.name,
                    'fetched': len(proxies),
                    'saved': saved
                })

                print(f"  ✓ {fetcher.name}: 采集 {len(proxies)} 个, 新增 {saved} 个")

            except Exception as e:
                print(f"  ✗ {fetcher.name}: 失败 - {e}")
                results['details'].append({
                    'source': fetcher.name,
                    'fetched': 0,
                    'saved': 0,
                    'error': str(e)
                })

        print(f"\n{'='*50}")
        print(f"采集完成: 共采集 {results['total_fetched']} 个, 新增 {results['total_saved']} 个")
        print(f"当前池中共有 {self.redis.get_count()} 个代理")
        print('='*50)

        return results