from flask import Flask, jsonify, request
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


# GET
@app.route('/api/requests', methods=['GET'])
def get_requests():
    try:
        requests_list = Request.query.all()
        return jsonify({
            'success': True,
            'data': [{
                'id': req.id,
                'name': req.name,
                'email': req.email,
                'specialty': req.specialty,
                'status': req.status
            } for req in requests_list]
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# POST ✅
@app.route('/api/requests', methods=['POST'])
def add_request():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        if not all(k in data for k in ['name', 'email', 'specialty']):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400

        new_request = Request(
            name=data['name'],
            email=data['email'],
            specialty=data['specialty']
        )
        db.session.add(new_request)
        db.session.commit()
        return jsonify({
            'success': True,
            'data': {
                'id': new_request.id,
                'name': new_request.name,
                'email': new_request.email,
                'specialty': new_request.specialty,
                'status': new_request.status
            }
        }), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# PUT ✅
@app.route('/api/requests/<int:id>', methods=['PUT'])
def update_request(id):
    try:
        req = Request.query.get(id)
        if not req:
            return jsonify({'success': False, 'error': 'Request not found'}), 404

        data = request.get_json()
        if 'status' in data:
            req.status = data['status']
        if 'name' in data:
            req.name = data['name']
        if 'email' in data:
            req.email = data['email']
        if 'specialty' in data:
            req.specialty = data['specialty']

        db.session.commit()
        return jsonify({
            'success': True,
            'data': {
                'id': req.id,
                'name': req.name,
                'email': req.email,
                'specialty': req.specialty,
                'status': req.status
            }
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("Database created!")
    app.run(debug=True)