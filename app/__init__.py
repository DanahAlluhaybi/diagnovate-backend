from flask import Flask, jsonify
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.models import db
from datetime import timedelta
import os
from dotenv import load_dotenv

load_dotenv()

limiter = Limiter(get_remote_address, default_limits=["200 per day", "50 per hour"])

import os as _os
print(f"[startup] PORT env var = {_os.getenv('PORT', 'NOT SET')}")
print(f"[startup] DATABASE_URL = {_os.getenv('DATABASE_URL', 'NOT SET')[:30]}...")


def create_app():
    app = Flask(__name__)

    db_url = os.getenv('DATABASE_URL', 'sqlite:///diagnovate.db')
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['JWT_SECRET_KEY']           = os.getenv('JWT_SECRET_KEY', 'super-secret-key-change-in-production')
    app.config['SECRET_KEY']               = os.getenv('SECRET_KEY', 'flask-secret-key-change-in-production')
    app.config['JWT_ACCESS_TOKEN_EXPIRES']  = timedelta(days=7)
    app.config['MAX_CONTENT_LENGTH']        = 16 * 1024 * 1024   # 16 MB max upload

    allowed_origins = os.getenv('ALLOWED_ORIGINS', '*')

    @app.route('/health')
    def health():
        return jsonify({'status': 'ok', 'message': 'Diagnovate API is running'}), 200

    @app.route('/api/<path:path>', methods=['OPTIONS'])
    def options_handler(path=None):
        return jsonify({}), 200

    @app.after_request
    def after_request(response):
        response.headers.add('Access-Control-Allow-Origin',  allowed_origins)
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,Accept')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,PATCH,POST,DELETE,OPTIONS')
        return response

    db.init_app(app)
    Migrate(app, db)
    JWTManager(app)
    limiter.init_app(app)

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
    from app.routes.auto_diagnosis import auto_bp

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


    with app.app_context():
        print("✅ App initialized.")
        from app.ml import load_ml_artifacts
        try:
            load_ml_artifacts()
        except Exception as e:
            print(f"⚠️  ML artifacts failed: {e} — app will start without ML.")

        def _preload_ml():
            print("\n🔄 Preloading ML models...")
            try:
                from app.services.swin_service import preload_swin
                preload_swin()
            except Exception as e:
                print(f"⚠️  Swin preload skipped: {e}")
            try:
                from app.services.densenet_service import preload_densenet
                preload_densenet()
            except Exception as e:
                print(f"⚠️  DenseNet preload skipped: {e}")
            try:
                from app.services.efficientnet_yolo_service import preload_efficientnet_yolo
                preload_efficientnet_yolo()
            except Exception as e:
                print(f"⚠️  EfficientNet+YOLO preload skipped: {e}")
            print("✅ ML preload complete\n")

        _preload_ml()

    return app


