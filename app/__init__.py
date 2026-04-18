from flask import Flask, jsonify
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from app.models import db
import os
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()


def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///diagnovate.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['JWT_SECRET_KEY']                 = os.getenv('JWT_SECRET_KEY', 'super-secret-key')
    app.config['SECRET_KEY']                     = os.getenv('SECRET_KEY', 'secret-key')
    app.config['JWT_ACCESS_TOKEN_EXPIRES']       = timedelta(days=7)
    app.config['MAX_CONTENT_LENGTH']             = 16 * 1024 * 1024

    CORS(app, resources={r"/api/*": {
        "origins":       "*",
        "methods":       ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "Accept"]
    }})

    db.init_app(app)
    jwt = JWTManager(app)

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({'error': 'Token has expired. Please log in again.'}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({'error': 'Invalid token. Please log in again.'}), 401

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({'error': 'Authorization token is missing.'}), 401

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'error': 'Endpoint not found'}), 404

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({'error': 'Internal server error'}), 500

    from app.routes.auth            import auth_bp
    from app.routes.dashboard       import dashboard_bp
    from app.routes.enhancement     import enhancement_bp
    from app.routes.profile         import profile_bp
    from app.routes.patients        import patients_bp
    from app.routes.diagnosis       import diagnosis_bp
    from app.routes.admin           import admin_bp
    from app.routes.forgot_password import forgot_password_bp
    from app.routes.cases           import cases_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(enhancement_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(patients_bp)
    app.register_blueprint(diagnosis_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(forgot_password_bp)
    app.register_blueprint(cases_bp)

    @app.route('/api/health', methods=['GET'])
    def health():
        return jsonify({'status': 'ok', 'message': 'Diagnovate backend is running'}), 200

    with app.app_context():
        db.create_all()
        print("✅ Database tables ready!")

    return app