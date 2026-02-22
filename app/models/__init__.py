from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date

db = SQLAlchemy()


class Doctor(db.Model):
    __tablename__ = 'doctors'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    specialty = db.Column(db.String(100), default='Thyroid Specialist')

    cases = db.relationship('Case', backref='doctor', lazy=True)
    patients = db.relationship('Patient', backref='doctor', lazy=True)
    appointments = db.relationship('Appointment', backref='doctor', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Patient(db.Model):
    __tablename__ = 'patients'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    date_of_birth = db.Column(db.Date)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    cases = db.relationship('Case', backref='patient', lazy=True)
    appointments = db.relationship('Appointment', backref='patient', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'date_of_birth': self.date_of_birth.isoformat() if self.date_of_birth else None,
            'doctor_id': self.doctor_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Case(db.Model):
    __tablename__ = 'cases'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(50), default='active')
    bethesda_category = db.Column(db.String(10))
    notes = db.Column(db.Text)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'status': self.status,
            'bethesda_category': self.bethesda_category,
            'notes': self.notes,
            'doctor_id': self.doctor_id,
            'patient_id': self.patient_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class Appointment(db.Model):
    __tablename__ = 'appointments'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    appointment_date = db.Column(db.Date, nullable=False)
    appointment_time = db.Column(db.Time)
    status = db.Column(db.String(50), default='scheduled')
    notes = db.Column(db.Text)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'appointment_date': self.appointment_date.isoformat() if self.appointment_date else None,
            'appointment_time': self.appointment_time.strftime('%H:%M') if self.appointment_time else None,
            'status': self.status,
            'notes': self.notes,
            'doctor_id': self.doctor_id,
            'patient_id': self.patient_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }