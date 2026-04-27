from flask import Flask, session, request, redirect, url_for

app = Flask(__name__)
app.secret_key = 'test-secret'

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email')
        pw = request.form.get('password')
        if email == 'admin@restyle.com' and pw == 'admin123':
            session['admin_logged_in'] = True
            return redirect('/admin/dashboard')
        else:
            return "Invalid credentials"
    return '''
        <form method="post">
            <input name="email" placeholder="admin@restyle.com">
            <input name="password" type="password">
            <button type="submit">Login</button>
        </form>
    '''

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect('/admin/login')
    return "<h1>Dashboard - Working!</h1>"

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect('/admin/login')

if __name__ == '__main__':
    app.run(debug=True, port=5001)