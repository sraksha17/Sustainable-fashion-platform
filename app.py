import os
from datetime import timedelta
from flask import Flask, render_template, redirect, url_for, session
from dotenv import load_dotenv
from blueprints.auth import auth_bp
from blueprints.donor import donor_bp
from blueprints.designer import designer_bp
from blueprints.buyer import buyer_bp
from blueprints.payment import payment_bp

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# Razorpay configuration
app.config['RAZORPAY_KEY_ID'] = os.getenv('RAZORPAY_KEY_ID')
app.config['RAZORPAY_KEY_SECRET'] = os.getenv('RAZORPAY_KEY_SECRET')

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(donor_bp)
app.register_blueprint(designer_bp)
app.register_blueprint(buyer_bp)
app.register_blueprint(payment_bp)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'user_email' not in session:
        return redirect(url_for('auth.login'))
    active_role = session.get('active_role')
    if active_role == 'donor':
        return redirect(url_for('donor.dashboard'))
    elif active_role == 'designer':
        return redirect(url_for('designer.dashboard'))
    elif active_role == 'buyer':
        return redirect(url_for('buyer.dashboard'))
    else:
        return redirect(url_for('auth.login'))

@app.route('/waste-info')
def waste_info():
    # The template name matches the file you renamed: waste-info.html
    return render_template('waste-info.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)