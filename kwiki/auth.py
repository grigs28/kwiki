"""kwiki/auth.py — yz-login SSO 认证模块"""
import os
import logging
import requests as http_requests
from functools import wraps
from flask import Blueprint, session, request, jsonify, redirect, current_app

logger = logging.getLogger("kwiki.auth")

auth_bp = Blueprint("kwiki_auth", __name__)

# 默认配置
DEFAULT_YZ_LOGIN_URL = "http://192.168.0.19:5555"

# 需要管理员权限的写操作路径
ADMIN_PATHS = {
    "/api/ingest", "/api/upload", "/api/compile",
    "/api/lint/fix", "/api/wiki/clean", "/api/index/rebuild",
    "/api/entities/extract", "/api/taxonomy/update",
}

# 不需要任何认证的路径前缀
PUBLIC_PREFIXES = ("/api/auth/", "/api/branding", "/api/tones")


def get_auth_config() -> dict:
    """从 current_app 获取 auth 配置"""
    return current_app.config.get("kwiki_auth", {})


def is_auth_enabled() -> bool:
    return get_auth_config().get("enabled", False)


# ── Blueprint 路由 ──────────────────────────────────────────

@auth_bp.route("/api/auth/login")
def login():
    """跳转到 yz-login 登录页"""
    cfg = get_auth_config()
    yz_url = cfg.get("yz_login_url", DEFAULT_YZ_LOGIN_URL)
    callback_url = cfg.get("callback_url", "")
    if not callback_url:
        # 自动检测：用当前请求的 host
        scheme = request.scheme
        host = request.host
        callback_url = f"{scheme}://{host}/api/auth/callback"
    return redirect(f"{yz_url}/login?from={callback_url}")


@auth_bp.route("/api/auth/callback")
def callback():
    """yz-login 登录成功后的回调"""
    ticket = request.args.get("ticket")
    if not ticket:
        return redirect("/?error=no_ticket")

    cfg = get_auth_config()
    yz_url = cfg.get("yz_login_url", DEFAULT_YZ_LOGIN_URL)

    # 用 ticket 换取用户信息
    try:
        resp = http_requests.get(
            f"{yz_url}/api/ticket/verify",
            params={"ticket": ticket},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning(f"ticket 验证失败: HTTP {resp.status_code}")
            return redirect("/?error=verify_failed")

        data = resp.json()
        if not data.get("ok"):
            logger.warning(f"ticket 无效: {data.get('msg', '')}")
            return redirect("/?error=invalid_ticket")

        # 写入 session
        session["kwiki_user"] = {
            "id": data["id"],
            "username": data["username"],
            "display_name": data.get("display_name", data["username"]),
            "is_admin": data.get("is_admin", 0),
        }
        session.permanent = True
        logger.info(f"用户登录成功: {data.get('display_name', data['username'])} (admin={data.get('is_admin', 0)})")
        return redirect("/")

    except Exception as e:
        logger.error(f"ticket 验证异常: {e}")
        return redirect("/?error=verify_error")


@auth_bp.route("/api/auth/logout")
def logout():
    """退出登录"""
    user = session.pop("kwiki_user", None)
    if user:
        logger.info(f"用户退出: {user.get('display_name', '')}")
    # 跳转到首页（不做 yz-login 的 logout，避免影响其他系统）
    return redirect("/")


@auth_bp.route("/api/auth/status")
def auth_status():
    """返回当前登录状态"""
    if not is_auth_enabled():
        return jsonify({
            "logged_in": True,
            "auth_enabled": False,
            "user": {"id": 0, "username": "anonymous", "display_name": "匿名", "is_admin": 1},
        })
    user = session.get("kwiki_user")
    if user:
        return jsonify({"logged_in": True, "auth_enabled": True, "user": user})
    return jsonify({"logged_in": False, "auth_enabled": True, "user": None})


# ── 权限检查 before_request hook ────────────────────────────

def auth_before_request():
    """Flask before_request 钩子：检查写操作权限"""
    # 认证未启用 → 全部放行
    if not is_auth_enabled():
        return None

    path = request.path

    # 公开路径放行
    for prefix in PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return None

    # GET 请求放行（读操作）
    if request.method == "GET":
        # 但 admin 路径不放行
        if path not in ADMIN_PATHS:
            return None

    # 静态文件和 SPA 放行
    if path.startswith("/assets/") or path.startswith("/favicon") or path == "/":
        return None

    # 写操作需要管理员
    if path in ADMIN_PATHS or request.method == "POST":
        user = session.get("kwiki_user")
        if not user:
            return jsonify({"status": "error", "message": "请先登录"}), 401
        if not user.get("is_admin"):
            return jsonify({"status": "error", "message": "需要管理员权限"}), 403

    return None


# ── 辅助函数 ─────────────────────────────────────────────────

def register_auth(app, auth_config: dict):
    """在 Flask app 上注册认证模块"""
    app.config["kwiki_auth"] = auth_config

    # 设置 Flask session 密钥
    secret = auth_config.get("secret_key", "kwiki-default-secret")
    if not app.secret_key:
        app.secret_key = secret

    # 注册蓝图
    app.register_blueprint(auth_bp)

    # 注册 before_request 钩子
    app.before_request(auth_before_request)

    # 配置 session 过期时间（7 天）
    from datetime import timedelta
    app.permanent_session_lifetime = timedelta(days=7)

    logger.info(f"认证模块已注册 (enabled={auth_config.get('enabled', False)})")
