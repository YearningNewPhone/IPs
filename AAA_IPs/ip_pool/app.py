"""Flask Web应用 - 主入口"""
from flask import Flask, render_template, jsonify, request, Response
from flask_socketio import SocketIO
from models import RedisClient, Proxy
from scheduler import PoolScheduler
from config import Config
import time

# 创建Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY

# 创建SocketIO
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='gevent',
    ping_timeout=60,
    ping_interval=25
)

# 初始化组件
redis_client = RedisClient()
scheduler = PoolScheduler(socketio)


# ==================== 页面路由 ====================

@app.route('/')
def index():
    """首页"""
    return render_template('index.html')


# ==================== API路由 ====================

@app.route('/api/stats')
def api_get_stats():
    """获取统计信息"""
    stats = redis_client.get_stats()
    return jsonify(stats)


@app.route('/api/proxies')
def api_get_proxies():
    """获取代理列表（分页）"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    protocol = request.args.get('protocol', '')

    proxies = redis_client.get_all_proxies()

    # 过滤协议
    if protocol:
        proxies = [p for p in proxies if p.protocol == protocol]

    total = len(proxies)
    pages = (total + per_page - 1) // per_page if total > 0 else 1

    # 分页
    start = (page - 1) * per_page
    end = start + per_page
    paginated = proxies[start:end]

    return jsonify({
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': pages,
        'items': [p.to_dict() for p in paginated]
    })


@app.route('/api/proxy')
def api_get_proxy():
    """获取一个可用代理（JSON格式）"""
    protocol = request.args.get('protocol')
    proxy = redis_client.get_proxy(protocol)

    if proxy:
        return jsonify({
            'success': True,
            'proxy': proxy.to_dict(),
            'proxy_url': proxy.proxy_url
        })

    return jsonify({
        'success': False,
        'message': '没有可用的代理'
    }), 404


@app.route('/api/proxy/random')
def api_get_random_proxy():
    """获取随机代理（纯文本格式，方便直接使用）"""
    protocol = request.args.get('protocol')
    fmt = request.args.get('format', 'url')  # url 或 json

    proxy = redis_client.get_proxy(protocol)

    if proxy:
        if fmt == 'json':
            return jsonify(proxy.to_dict())
        else:
            return Response(proxy.proxy_url, mimetype='text/plain')

    return Response('No proxy available', status=404, mimetype='text/plain')


@app.route('/api/proxy/<ip>/<int:port>', methods=['DELETE'])
def api_delete_proxy(ip, port):
    """删除指定代理"""
    proxy = Proxy(ip=ip, port=port)
    success = redis_client.remove_proxy(proxy)
    return jsonify({
        'success': success,
        'message': '删除成功' if success else '删除失败'
    })


@app.route('/api/fetch', methods=['POST'])
def api_trigger_fetch():
    """手动触发采集"""
    try:
        results = scheduler.run_fetch_now()
        return jsonify({
            'success': True,
            'data': results
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/validate', methods=['POST'])
def api_trigger_validate():
    """手动触发验证"""
    try:
        results = scheduler.run_validate_now()
        return jsonify({
            'success': True,
            'data': results
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/stats/history')
def api_get_stats_history():
    """获取统计历史"""
    limit = request.args.get('limit', 60, type=int)
    history = redis_client.get_stats_history(limit)
    return jsonify(history)


@app.route('/api/jobs')
def api_get_jobs():
    """获取调度任务状态"""
    return jsonify({
        'jobs': scheduler.get_jobs()
    })


@app.route('/api/clear', methods=['POST'])
def api_clear_all():
    """清空所有代理"""
    success = redis_client.clear_all()
    return jsonify({
        'success': success,
        'message': '已清空所有代理' if success else '清空失败'
    })


# ==================== WebSocket事件 ====================

@socketio.on('connect')
def handle_connect():
    """客户端连接"""
    print(f"[WebSocket] 客户端已连接")
    # 发送当前统计信息
    stats = redis_client.get_stats()
    socketio.emit('stats_update', stats)


@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开"""
    print(f"[WebSocket] 客户端已断开")


@socketio.on('request_stats')
def handle_request_stats():
    """客户端请求统计"""
    stats = redis_client.get_stats()
    socketio.emit('stats_update', stats)


# ==================== 启动应用 ====================

def create_app():
    """工厂函数"""
    return app


if __name__ == '__main__':
    print("""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║           🌐 IP代理池监控系统 v1.0                         ║
║                                                           ║
╠═══════════════════════════════════════════════════════════╣
║  Web界面:  http://localhost:5000                          ║
║  API文档:                                                 ║
║    GET  /api/stats         - 获取统计信息                  ║
║    GET  /api/proxies       - 获取代理列表                  ║
║    GET  /api/proxy         - 获取一个代理(JSON)            ║
║    GET  /api/proxy/random  - 获取一个代理(文本)            ║
║    POST /api/fetch         - 触发采集                     ║
║    POST /api/validate      - 触发验证                     ║
╚═══════════════════════════════════════════════════════════╝
    """)

    # 启动调度器
    scheduler.start()

    # 启动Web服务
    try:
        socketio.run(
            app,
            host=Config.WEB_HOST,
            port=Config.WEB_PORT,
            debug=False,
            use_reloader=False
        )
    except KeyboardInterrupt:
        print("\n正在关闭...")
        scheduler.stop()