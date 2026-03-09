from flask import Flask, jsonify
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from app.models import db
import os
from dotenv import load_dotenv

load_dotenv()

def create_app():
    app = Flask(__name__)

    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///diagnovate.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'super-secret-key')
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'secret-key')

    @app.route('/api/<path:path>', methods=['OPTIONS'])
    def options_handler(path=None):
        return jsonify({}), 200

    @app.after_request
    def after_request(response):
        response.headers.add('Access-Control-Allow-Origin', 'http://localhost:3000')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,Accept')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response

    db.init_app(app)
    JWTManager(app)

    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.appointments import appointments_bp
    from app.routes.enhancement import enhancement_bp
    from app.routes.profile import profile_bp
    from app.routes.patients import patients_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(appointments_bp)
    app.register_blueprint(enhancement_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(patients_bp)

    with app.app_context():
        db.create_all()
        print("Database created!")

    return app