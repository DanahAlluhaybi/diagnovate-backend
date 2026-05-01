# Pre-deployment sanity checker — validates Python syntax and checks blueprint registrations.
import ast
import os
import sys

ROOT    = os.path.dirname(__file__)
ERRORS  = []
PASSING = []

def check_file(path):
    rel = os.path.relpath(path, ROOT)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            source = f.read()
        ast.parse(source)
        PASSING.append(f"  {rel}")
    except SyntaxError as e:
        ERRORS.append(f"  {rel}  ->  line {e.lineno}: {e.msg}")

for dirpath, _, filenames in os.walk(ROOT):
    if any(skip in dirpath for skip in ['__pycache__', '.git', 'venv', '.venv']):
        continue
    for fname in filenames:
        if fname.endswith('.py'):
            check_file(os.path.join(dirpath, fname))

print("\n── SYNTAX CHECK ─────────────────────────────────")
for line in sorted(PASSING):
    print(line)

if ERRORS:
    print("\n── ERRORS ───────────────────────────────────────")
    for line in ERRORS:
        print(line)
    print(f"\n{len(ERRORS)} error(s) found.")
    sys.exit(1)
else:
    print(f"\nAll {len(PASSING)} files passed syntax check.")

print("\n── CROSS-FILE CHECKS ────────────────────────────")

INIT = open(os.path.join(ROOT, 'app', '__init__.py')).read()
blueprints = [
    ('auth_bp',            'app/routes/auth.py'),
    ('dashboard_bp',       'app/routes/dashboard.py'),
    ('appointments_bp',    'app/routes/appointments.py'),
    ('enhancement_bp',     'app/routes/enhancement.py'),
    ('profile_bp',         'app/routes/profile.py'),
    ('patients_bp',        'app/routes/patients.py'),
    ('diagnosis_bp',       'app/routes/diagnosis.py'),
    ('admin_bp',           'app/routes/admin.py'),
    ('forgot_password_bp', 'app/routes/forgot_password.py'),
    ('cases_bp',           'app/routes/cases.py'),
]

for bp_name, bp_file in blueprints:
    file_exists = os.path.exists(os.path.join(ROOT, bp_file))
    registered  = f'register_blueprint({bp_name})' in INIT
    imported    = bp_name in INIT

    status = "OK  " if (file_exists and registered and imported) else "FAIL"
    issues = []
    if not file_exists: issues.append("FILE MISSING")
    if not imported:    issues.append("NOT IMPORTED")
    if not registered:  issues.append("NOT REGISTERED")

    detail = f"  [{', '.join(issues)}]" if issues else ""
    print(f"{status}  {bp_name:25s} ({bp_file}){detail}")

env_ok = os.path.exists(os.path.join(ROOT, '.env.example'))
print(f"\n{'OK  ' if env_ok else 'FAIL'}  .env.example exists")

req_ok = os.path.exists(os.path.join(ROOT, 'requirements.txt'))
print(f"{'OK  ' if req_ok else 'FAIL'}  requirements.txt exists")

git_ok = os.path.exists(os.path.join(ROOT, '.gitignore'))
print(f"{'OK  ' if git_ok else 'FAIL'}  .gitignore exists")

ml_dir = os.path.exists(os.path.join(ROOT, 'app', 'ml'))
print(f"{'OK  ' if ml_dir else 'WARN'}  app/ml/ directory exists {'(model files needed)' if not ml_dir else ''}")

print("\n── DONE ─────────────────────────────────────────\n")
