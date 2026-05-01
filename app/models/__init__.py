from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


# ── Admin ──────────────────────────────────────────────────────────────────
class Admin(db.Model):
    __tablename__ = 'admins'

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False)
    email         = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id':         self.id,
            'name':       self.name,
            'email':      self.email,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ── Doctor ─────────────────────────────────────────────────────────────────
class Doctor(db.Model):
    __tablename__ = 'doctors'

    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(100), nullable=False)
    email           = db.Column(db.String(100), unique=True, nullable=False)
    password_hash   = db.Column(db.String(200), nullable=False)
    specialty       = db.Column(db.String(100), default='Thyroid Specialist')
    phone           = db.Column(db.String(20))
    license_number  = db.Column(db.String(50))
    status          = db.Column(db.String(20), default='pending')
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    failed_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until    = db.Column(db.DateTime, nullable=True)
    last_login      = db.Column(db.DateTime, nullable=True)
    last_ip         = db.Column(db.String(45), nullable=True)

    patients = db.relationship('Patient', backref='doctor', lazy=True, cascade='all, delete-orphan')
    cases    = db.relationship('Case', backref='doctor', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id':             self.id,
            'name':           self.name,
            'email':          self.email,
            'specialty':      self.specialty,
            'phone':          self.phone,
            'license_number': self.license_number,
            'status':         self.status,
            'created_at':     self.created_at.isoformat() if self.created_at else None,
        }


# ── Patient ────────────────────────────────────────────────────────────────
class Patient(db.Model):
    __tablename__ = 'patients'

    id         = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.String(50), unique=True, nullable=False)
    mrn        = db.Column(db.String(50), unique=True, nullable=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name  = db.Column(db.String(100), nullable=True, default='')
    age        = db.Column(db.Integer, nullable=True)
    gender     = db.Column(db.String(10), nullable=True)
    phone      = db.Column(db.String(20), nullable=True)
    email      = db.Column(db.String(100), nullable=True)
    last_visit = db.Column(db.Date, nullable=True)
    status     = db.Column(db.String(20), default='Active')
    condition  = db.Column(db.String(200), nullable=True)
    address    = db.Column(db.String(200), nullable=True)
    doctor_id  = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    cases = db.relationship('Case', backref='patient', lazy=True, cascade='all, delete-orphan')

    @property
    def name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def to_dict(self):
        return {
            'id':         self.patient_id,
            'mrn':        self.mrn or '',
            'firstName':  self.first_name,
            'lastName':   self.last_name or '',
            'name':       self.name,
            'age':        self.age,
            'gender':     self.gender or '',
            'phone':      self.phone or '',
            'email':      self.email or '',
            'lastVisit':  self.last_visit.strftime('%Y-%m-%d') if self.last_visit else '',
            'status':     self.status,
            'condition':  self.condition or '',
            'address':    self.address or '',
            'doctor_id':  self.doctor_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ── Case ───────────────────────────────────────────────────────────────────
class Case(db.Model):
    __tablename__ = 'cases'

    id                  = db.Column(db.Integer, primary_key=True)
    case_id             = db.Column(db.String(50), unique=True, nullable=False)
    patient_id          = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=True)
    doctor_id           = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=True)
    nodule_size         = db.Column(db.String(20), nullable=True)
    location            = db.Column(db.String(50), nullable=True)
    tirads_score        = db.Column(db.Integer, nullable=True)
    bethesda_category   = db.Column(db.String(10), nullable=True)
    symptoms            = db.Column(db.Text, nullable=True)
    diagnosis           = db.Column(db.Text, nullable=True)
    notes               = db.Column(db.Text, nullable=True)
    status              = db.Column(db.String(20), default='active')
    image_path          = db.Column(db.String(200), nullable=True)
    enhanced_image_path = db.Column(db.String(200), nullable=True)
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at          = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id':                  self.id,
            'case_id':             self.case_id,
            'patient_id':          self.patient_id,
            'patient_name':        self.patient.name if self.patient else None,
            'doctor_id':           self.doctor_id,
            'nodule_size':         self.nodule_size,
            'location':            self.location,
            'tirads_score':        self.tirads_score,
            'bethesda_category':   self.bethesda_category,
            'symptoms':            self.symptoms,
            'diagnosis':           self.diagnosis,
            'notes':               self.notes,
            'status':              self.status,
            'image_path':          self.image_path,
            'enhanced_image_path': self.enhanced_image_path,
            'created_at':          self.created_at.isoformat() if self.created_at else None,
            'updated_at':          self.updated_at.isoformat() if self.updated_at else None,
        }


# ── EmailOTP ───────────────────────────────────────────────────────────────
class EmailOTP(db.Model):
    __tablename__ = 'email_otps'

    id         = db.Column(db.Integer, primary_key=True)
    email      = db.Column(db.String(100), nullable=False, index=True)
    code       = db.Column(db.String(10), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used       = db.Column(db.Boolean, default=False, nullable=False)


# ── PasswordResetToken ─────────────────────────────────────────────────────
class PasswordResetToken(db.Model):
    __tablename__ = 'password_reset_tokens'

    id         = db.Column(db.Integer, primary_key=True)
    email      = db.Column(db.String(100), nullable=False, index=True)
    token      = db.Column(db.String(100), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used       = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)