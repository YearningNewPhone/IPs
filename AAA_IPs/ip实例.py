import requests

# 获取一个代理
resp = requests.get('http://localhost:5000/api/proxy/random')
proxy_url = resp.text  # 例如: http://1.2.3.4:8080

# 使用代理
proxies = {'http': proxy_url, 'https': proxy_url}
resp = requests.get('http://httpbin.org/ip', proxies=proxies, timeout=10)
print(resp.json())