from flask import Flask
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

    CORS(app, origins=["http://localhost:3000"], supports_credentials=True)
    db.init_app(app)
    jwt = JWTManager(app)

    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.appointments import appointments_bp
    from app.routes.enhancement import enhancement_bp
    from app.routes.profile import profile_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(appointments_bp)
    app.register_blueprint(enhancement_bp)
    app.register_blueprint(profile_bp)

    with app.app_context():
        db.create_all()
        print("Database created!")

    return app