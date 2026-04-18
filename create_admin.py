from app import create_app
from app.models import db, Admin

app = create_app()
with app.app_context():
    admin = Admin(
        name="Admin",
        email="admin@diagnovate.org"
    )
    admin.set_password("Admin@1234")
    db.session.add(admin)
    db.session.commit()
    print("✅ Admin created successfully")
