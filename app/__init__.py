from flask import Flask, jsonify
from flask_jwt_extended import JWTManager
from app.models import db
from datetime import timedelta
import os
from dotenv import load_dotenv

load_dotenv()


def create_app():
    app = Flask(__name__)

    # ── Database ───────────────────────────────────────────────
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
        'DATABASE_URL', 'sqlite:///diagnovate.db'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # ── Security ───────────────────────────────────────────────
    app.config['JWT_SECRET_KEY']           = os.getenv('JWT_SECRET_KEY', 'super-secret-key-change-in-production')
    app.config['SECRET_KEY']               = os.getenv('SECRET_KEY',     'flask-secret-key-change-in-production')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=7)

    # ── CORS preflight catch-all ───────────────────────────────
    @app.route('/api/<path:path>', methods=['OPTIONS'])
    def options_handler(path=None):
        return jsonify({}), 200

    # FIX: allow all origins for production (Vercel frontend)
    @app.after_request
    def after_request(response):
        response.headers.add('Access-Control-Allow-Origin',  '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,Accept')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,PATCH,POST,DELETE,OPTIONS')
        return response

    # ── Extensions ────────────────────────────────────────────
    db.init_app(app)
    JWTManager(app)

    # ── Blueprints ────────────────────────────────────────────
    from app.routes.auth        import auth_bp
    from app.routes.dashboard   import dashboard_bp
    from app.routes.enhancement import enhancement_bp
    from app.routes.profile     import profile_bp
    from app.routes.patients    import patients_bp
    from app.routes.diagnosis   import diagnosis_bp
    from app.routes.cases       import cases_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(enhancement_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(patients_bp)
    app.register_blueprint(diagnosis_bp)
    app.register_blueprint(cases_bp)

    # ── DB init ───────────────────────────────────────────────
    with app.app_context():
        db.create_all()
        print("✅ Database ready.")

    return app