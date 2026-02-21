# test_db.py
from app import create_app
from app.models import db, Doctor

app = create_app()

with app.app_context():
    # شوف كل الدكاترة
    doctors = Doctor.query.all()
    print(f"عدد الدكاترة: {len(doctors)}")

    for doctor in doctors:
        print(f"ID: {doctor.id}")
        print(f"Name: {doctor.name}")
        print(f"Email: {doctor.email}")
        print(f"Password Hash: {doctor.password_hash[:50]}...")
        print("-" * 50)