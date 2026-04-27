from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "Root works"

@app.route('/admin/login')
def admin_login():
    return "Admin login page"

if __name__ == '__main__':
    app.run(debug=True, port=5002)