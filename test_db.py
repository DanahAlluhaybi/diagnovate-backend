# test_db.py
'''from app import create_app
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
        print("-" * 50)'''



from app import create_app
from app.models import db, Doctor, Admin
import sqlalchemy as sa

app = create_app()

with app.app_context():

    with db.engine.connect() as conn:
        try:
            conn.execute(sa.text('ALTER TABLE doctors ADD COLUMN status VARCHAR(20) DEFAULT "pending"'))
            print("✅ Added status column")
        except:
            print("ℹ️ status column already exists")
        conn.commit()


    ADMINS = [
        {"name": "Renad Hamed Almazroi",   "email": "renad@test.com",  "password": "Admin@1234"},
        {"name": "Jana Mohammed Alghamdi", "email": "jana@test.com",   "password": "Admin@1234"},
        {"name": "Danah Saleem Alluhaybi", "email": "danah@test.com",  "password": "Admin@1234"},
        {"name": "Reena Hamadi Aljahdali", "email": "reena@test.com",  "password": "Admin@1234"},
        {"name": "Sarah Alghamdi",         "email": "sarah@test.com",  "password": "Admin@1234"},
    ]

    for admin_info in ADMINS:
        existing = Admin.query.filter_by(email=admin_info["email"]).first()
        if existing:
            print(f"ℹ️ Already exists: {admin_info['name']}")
        else:
            admin = Admin(
                name=admin_info["name"],
                email=admin_info["email"]
            )
            admin.set_password(admin_info["password"])
            db.session.add(admin)
            print(f"✅ Created admin: {admin_info['name']}")

    db.session.commit()

    # ──  عرض كل الأدمن للتحقق─
    print("\n── All Admins ─────")
    admins = Admin.query.all()
    print(f"Total admins: {len(admins)}")
    for a in admins:
        print(f"ID: {a.id} | {a.name} | {a.email}")