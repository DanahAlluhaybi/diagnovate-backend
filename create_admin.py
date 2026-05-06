import os
import sys
from app import create_app
from app.models import db, Admin

app = create_app()

with app.app_context():
    email    = os.getenv('ADMIN_EMAIL', 'admin@diagnovate.org')
    name     = os.getenv('ADMIN_NAME', 'Admin')
    password = os.getenv('ADMIN_PASSWORD')

    if not password:
        print("ERROR: Set ADMIN_PASSWORD environment variable before running this script.")
        sys.exit(1)

    if Admin.query.filter_by(email=email).first():
        print(f"Admin with email '{email}' already exists — skipping.")
        sys.exit(0)

    admin = Admin(name=name, email=email)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    print(f"Admin '{name}' ({email}) created successfully.")
