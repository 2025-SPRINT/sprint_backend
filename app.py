from flask import Flask, jsonify

from gemini_main import 

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "success",
        "message": "Hello, World! Flask server is running."
    })

############# 순호 추가 #############



############# 현석 추가 #############



############# 승언 추가 #############



############# 도현 추가 #############



###################################

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy"
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
