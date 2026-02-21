from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Doctor(db.Model):
    __tablename__ = 'doctors'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    specialty = db.Column(db.String(100), default='Thyroid Specialist')
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    patients = db.relationship('Patient', backref='doctor', lazy=True, cascade='all, delete-orphan')
    cases = db.relationship('Case', backref='doctor', lazy=True, cascade='all, delete-orphan')
    appointments = db.relationship('Appointment', backref='doctor', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'specialty': self.specialty,
            'phone': self.phone,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Patient(db.Model):
    __tablename__ = 'patients'

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.String(200))
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    cases = db.relationship('Case', backref='patient', lazy=True, cascade='all, delete-orphan')
    appointments = db.relationship('Appointment', backref='patient', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'name': self.name,
            'age': self.age,
            'gender': self.gender,
            'phone': self.phone,
            'email': self.email,
            'address': self.address,
            'doctor_id': self.doctor_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Case(db.Model):
    __tablename__ = 'cases'

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.String(50), unique=True, nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'))
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'))

    # Thyroid specific
    nodule_size = db.Column(db.String(20))
    location = db.Column(db.String(50))
    tirads_score = db.Column(db.Integer)
    bethesda_category = db.Column(db.String(10))

    # Clinical data
    symptoms = db.Column(db.Text)
    diagnosis = db.Column(db.Text)
    notes = db.Column(db.Text)

    # Status
    status = db.Column(db.String(20), default='active')  # active, completed, follow-up

    # Images
    image_path = db.Column(db.String(200))
    enhanced_image_path = db.Column(db.String(200))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    def to_dict(self):
        patient = Patient.query.get(self.patient_id)
        return {
            'id': self.id,
            'case_id': self.case_id,
            'patient_id': self.patient_id,
            'patient_name': patient.name if patient else None,
            'doctor_id': self.doctor_id,
            'nodule_size': self.nodule_size,
            'location': self.location,
            'tirads_score': self.tirads_score,
            'bethesda_category': self.bethesda_category,
            'symptoms': self.symptoms,
            'diagnosis': self.diagnosis,
            'notes': self.notes,
            'status': self.status,
            'image_path': self.image_path,
            'enhanced_image_path': self.enhanced_image_path,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class Appointment(db.Model):
    __tablename__ = 'appointments'

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=True)
    patient_name = db.Column(db.String(100), nullable=False)
    patient_phone = db.Column(db.String(20))
    patient_id_number = db.Column(db.String(50))

    appointment_date = db.Column(db.Date, nullable=False)
    appointment_time = db.Column(db.Time, nullable=False)
    appointment_type = db.Column(db.String(50), default='Consultation')  # Consultation, Follow-up, Ultrasound, Biopsy
    duration = db.Column(db.Integer, default=30)  # بالدقائق
    status = db.Column(db.String(20), default='Pending')  # Pending, Confirmed, Completed, Cancelled
    case_id = db.Column(db.String(50))
    notes = db.Column(db.Text)

    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'patient_name': self.patient_name,
            'patient_phone': self.patient_phone,
            'patient_id_number': self.patient_id_number,
            'appointment_time': self.appointment_time.strftime('%H:%M') if self.appointment_time else None,
            'appointment_date': self.appointment_date.isoformat() if self.appointment_date else None,
            'appointment_type': self.appointment_type,
            'duration': self.duration,
            'status': self.status,
            'case_id': self.case_id,
            'notes': self.notes,
            'doctor_id': self.doctor_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }