# Dev utility: adds missing DB columns and seeds test admin accounts, then prints a summary.
from app import create_app
from app.models import db, Doctor, Admin
import sqlalchemy as sa

app = create_app()

with app.app_context():

    with db.engine.connect() as conn:
        try:
            conn.execute(sa.text('ALTER TABLE doctors ADD COLUMN status VARCHAR(20) DEFAULT "pending"'))
            print("Added status column")
        except Exception:
            print("status column already exists")
        conn.commit()

    ADMINS = [
        {"name": "Renad Hamed Almazroi",   "email": "renad@test.com",  "password": "Admin@1234"},
        {"name": "Jana Mohammed Alghamdi", "email": "jana@test.com",   "password": "Admin@1234"},
        {"name": "Danah Saleem Alluhaybi", "email": "danah@test.com",  "password": "Admin@1234"},
        {"name": "Reena Hamadi Aljahdali", "email": "reena@test.com",  "password": "Admin@1234"},
        {"name": "Sarah Alghamdi",         "email": "sarah@test.com",  "password": "Admin@1234"},
    ]

    for admin_info in ADMINS:
        if not Admin.query.filter_by(email=admin_info["email"]).first():
            admin = Admin(name=admin_info["name"], email=admin_info["email"])
            admin.set_password(admin_info["password"])
            db.session.add(admin)
            print(f"Created admin: {admin_info['name']}")
        else:
            print(f"Already exists: {admin_info['name']}")

    db.session.commit()

    print(f"\n── DB Summary ─────────────────")
    print(f"Admins:  {Admin.query.count()}")
    print(f"Doctors: {Doctor.query.count()}")
    print(f"  pending:  {Doctor.query.filter_by(status='pending').count()}")
    print(f"  active:   {Doctor.query.filter_by(status='active').count()}")
    print(f"  rejected: {Doctor.query.filter_by(status='rejected').count()}")
