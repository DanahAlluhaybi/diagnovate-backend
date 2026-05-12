import logging
import threading
import uuid
import os
from datetime import timedelta
from dotenv import load_dotenv
from flask import Flask, jsonify, g, request
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.models import db

load_dotenv()

# ── Module-level limiter (imported by route blueprints) ───────────────────────
limiter = Limiter(
    get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=os.environ.get("REDIS_URL") or "memory://",
)

# ── Structured logging ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%SZ',
)
logger = logging.getLogger('diagnovate')
logger.info("PORT=%s", os.getenv('PORT', 'NOT SET'))

# ── ML loading state (checked by /health) ────────────────────────────────────
_ml_status = {"ready": False, "loading": False}
ml_ready = False

_WEAK_SECRETS = {
    'super-secret-key-change-in-production',
    'flask-secret-key-change-in-production',
    '',
}


def create_app():
    app = Flask(__name__)

    # ── Database ──────────────────────────────────────────────────────────────
    db_url = os.getenv('DATABASE_URL', 'sqlite:///diagnovate.db')
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI']    = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS']  = {
        'pool_pre_ping': True,
        'pool_recycle':  300,
    }

    # ── Secrets ───────────────────────────────────────────────────────────────
    jwt_secret = os.getenv('JWT_SECRET_KEY', 'super-secret-key-change-in-production')
    secret_key = os.getenv('SECRET_KEY',     'flask-secret-key-change-in-production')
    dev_mode   = os.getenv('DEV_MODE', 'false').lower() == 'true'

    if not dev_mode and (jwt_secret in _WEAK_SECRETS or secret_key in _WEAK_SECRETS):
        raise RuntimeError(
            "FATAL: JWT_SECRET_KEY and SECRET_KEY must be set to strong random values in production.\n"
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"\n"
            "Set DEV_MODE=true only in local development."
        )
    if dev_mode:
        logger.warning("DEV_MODE=true — OTP is DISABLED. Never use this in production.")

    app.config['JWT_SECRET_KEY']          = jwt_secret
    app.config['SECRET_KEY']              = secret_key
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=8)
    app.config['MAX_CONTENT_LENGTH']       = 16 * 1024 * 1024

    # ── Request lifecycle ─────────────────────────────────────────────────────
    @app.before_request
    def _set_request_id():
        g.request_id = request.headers.get('X-Request-ID', str(uuid.uuid4())[:8])

    @app.after_request
    def _after(response):
        response.headers['X-Request-ID'] = g.get('request_id', '-')
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        app.logger.info('%s %s %s rid=%s',
                        request.method, request.path,
                        response.status_code, g.get('request_id', '-'))
        return response

    # ── Health check — always responds immediately ────────────────────────────
    @app.route('/health')
    def health():
        if _ml_status['ready']:
            return jsonify({'status': 'ok', 'models_ready': True}), 200
        return jsonify({'status': 'ok', 'models_ready': False,
                        'message': 'Models loading in background'}), 200

    @app.route('/api/<path:path>', methods=['OPTIONS'])
    def options_handler(path=None):
        return jsonify({}), 200

    # ── Global error handlers ─────────────────────────────────────────────────
    from werkzeug.exceptions import HTTPException

    @app.errorhandler(HTTPException)
    def http_error(e):
        return jsonify({'error': e.description}), e.code

    @app.errorhandler(429)
    def rate_limited(e):
        return jsonify({'error': 'Too many requests. Please slow down and try again.'}), 429

    @app.errorhandler(Exception)
    def unhandled(e):
        if isinstance(e, HTTPException):
            return jsonify({'error': e.description}), e.code
        app.logger.exception('Unhandled exception rid=%s', g.get('request_id', '-'))
        return jsonify({'error': 'An internal error occurred'}), 500

    # ── Extensions ────────────────────────────────────────────────────────────
    from flask_cors import CORS
    _ALLOWED_ORIGINS = [
        o.strip()
        for o in os.getenv(
            'ALLOWED_ORIGINS',
            'https://diagnovate-plum.vercel.app,http://localhost:3000'
        ).split(',')
        if o.strip()
    ]
    CORS(app,
         origins=_ALLOWED_ORIGINS,
         supports_credentials=False,
         methods=['GET', 'PUT', 'PATCH', 'POST', 'DELETE', 'OPTIONS'],
         allow_headers=['Content-Type', 'Authorization', 'Accept'])
    db.init_app(app)
    Migrate(app, db)
    JWTManager(app)
    limiter.init_app(app)

    # ── Talisman security headers ─────────────────────────────────────────────
    try:
        from flask_talisman import Talisman
        Talisman(
            app,
            force_https=False,
            strict_transport_security=True,
            strict_transport_security_max_age=31536000,
            content_security_policy=False,
            x_content_type_options=True,
            frame_options='DENY',
        )
        logger.info("Flask-Talisman security headers enabled")
    except ImportError:
        logger.warning("flask-talisman not installed — security headers limited")

    # ── Blueprints ────────────────────────────────────────────────────────────
    from app.routes.auth            import auth_bp
    from app.routes.dashboard       import dashboard_bp
    from app.routes.enhancement     import enhancement_bp
    from app.routes.profile         import profile_bp
    from app.routes.patients        import patients_bp
    from app.routes.diagnosis       import diagnosis_bp
    from app.routes.cases           import cases_bp
    from app.routes.admin           import admin_bp
    from app.routes.forgot_password import forgot_password_bp
    from app.routes.reports         import reports_bp
    from app.routes.report          import report_bp
    from app.routes.auto_diagnosis  import auto_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(enhancement_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(patients_bp)
    app.register_blueprint(diagnosis_bp)
    app.register_blueprint(cases_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(forgot_password_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(auto_bp)

    # ── ML loading in background thread — app serves immediately ─────────────
    def _load_all_models():
        _ml_status['loading'] = True
        with app.app_context():
            logger.info("Background ML load started")
            from app.ml import load_ml_artifacts
            try:
                load_ml_artifacts()
            except Exception as e:
                logger.warning("ML artifacts failed: %s", e)

            for name, mod_path, fn_name in [
                ('Swin',              'app.services.swin_service',              'preload_swin'),
                ('DenseNet',          'app.services.densenet_service',           'preload_densenet'),
                ('EfficientNet+YOLO', 'app.services.efficientnet_yolo_service', 'preload_efficientnet_yolo'),
            ]:
                try:
                    mod = __import__(mod_path, fromlist=[fn_name])
                    getattr(mod, fn_name)()
                except Exception as e:
                    logger.warning("%s preload skipped: %s", name, e)

            _ml_status['ready']   = True
            global ml_ready
            ml_ready = True
            _ml_status['loading'] = False
            logger.info("Background ML load complete — all models ready")

    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "600")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    t = threading.Thread(target=_load_all_models, name='ml-loader', daemon=True)
    t.start()

    return app
