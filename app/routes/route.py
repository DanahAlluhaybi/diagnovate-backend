from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy


app = Flask(__name__)


app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///requests.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class Request(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    specialty = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='Pending')

    def __repr__(self):
        return f"<Request {self.name}>"


@app.route('/api/requests', methods=['GET'])
def get_requests():
    requests = Request.query.all()
    return jsonify([{
        'id': req.id,
        'name': req.name,
        'email': req.email,
        'specialty': req.specialty,
        'status': req.status
    } for req in requests])


@app.route('/api/requests', methods=['POST'])
def add_request():
    data = request.get_json()
    new_request = Request(
        name=data['name'],
        email=data['email'],
        specialty=data['specialty']
    )
    db.session.add(new_request)
    db.session.commit()
    return jsonify({
        'id': new_request.id,
        'name': new_request.name,
        'email': new_request.email,
        'specialty': new_request.specialty,
        'status': new_request.status
    })

@app.route('/api/requests', methods=['PUT'])
def update_request():
    data = request.get_json()
    req = Request.query.get(data['id'])
    if req:
        req.status = data['status']
        db.session.commit()
        return jsonify({'success': True, 'status': req.status})
    return jsonify({'success': False}), 404

if name == '__main__':
    app.run(debug=True)
