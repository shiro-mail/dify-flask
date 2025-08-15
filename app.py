from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello_world():
    return '<h1>Hello, Flask!</h1><p>Flaskアプリケーションが正常に動作しています。</p>'

@app.route('/about')
def about():
    return '<h1>About</h1><p>これはFlaskの練習用アプリケーションです。</p>'

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
