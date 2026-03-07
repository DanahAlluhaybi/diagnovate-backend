from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)

# تكوين قاعدة البيانات
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///requests.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# تعريف نموذج البيانات
class Request(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    specialty = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='Pending')

    def __repr__(self):
        return f"<Request {self.name}>"

# routes.py تابع هذه الأكواد
@app.route('/api/requests', methods=['GET'])
def get_requests():
    try:
        requests = Request.query.all()
        return jsonify({
            'success': True,
            'data': [req.name for req in requests]
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__  == '__main__':
    with app.app_context():
        db.create_all()  # إنشاء الجداول في قاعدة البيانات
    app.run(debug=True)
