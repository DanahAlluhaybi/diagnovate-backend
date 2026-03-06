from flask import Flask, request, jsonify

app = Flask(__name__)


requests = [

]


@app.route('/api/requests', methods=['GET'])
def get_requests():
    return jsonify(requests)


@app.route('/api/requests', methods=['POST'])
def add_request():
    data = request.get_json()
    new_request = {
        'id': len(requests) + 1,
        'name': data['name'],
        'email': data['email'],
        'specialty': data['specialty'],
        'status': 'Pending'
    }
    requests.append(new_request)
    return jsonify(new_request)


@app.route('/api/requests', methods=['PUT'])
def update_request():
    data = request.get_json()
    for req in requests:
        if req['id'] == data['id']:
            req['status'] = data['status']
            return jsonify({'success': True})
    return jsonify({'success': False}), 404

if name == '__main__':
    app.run(debug=True)