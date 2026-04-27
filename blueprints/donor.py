from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from utils import user_has_role, get_user_by_email, create_notification
from models import get_db
from bson import ObjectId
from datetime import datetime
import os
from werkzeug.utils import secure_filename

donor_bp = Blueprint('donor', __name__, url_prefix='/donor')

# Helper to check donor access
def require_donor():
    if 'user_email' not in session:
        return redirect(url_for('auth.login'))
    user = get_user_by_email(session['user_email'])
    if not user or not user_has_role(user, 'donor'):
        return "Access denied", 403
    return None

@donor_bp.route('/dashboard')
def dashboard():
    check = require_donor()
    if check:
        return check
    return render_template('donor/dashboard.html')

# API endpoints (same logic as before, but now under /donor/api/)
@donor_bp.route('/api/stats')
def api_stats():
    check = require_donor()
    if check:
        return check
    email = session['user_email']
    db = get_db()
    # Total donations
    total_donations = db.donations.count_documents({'donor_email': email})
    # Reward points from user
    user = get_user_by_email(email)
    reward_points = user.get('reward_points', 0)
    # Items upcycled: count of donations with status 'upcycled'
    upcycled = db.donations.count_documents({'donor_email': email, 'status': 'upcycled'})
    return jsonify({
        'total_donations': total_donations,
        'reward_points': reward_points,
        'items_upcycled': upcycled
    })

@donor_bp.route('/api/recent-donations')
def api_recent_donations():
    check = require_donor()
    if check:
        return check
    email = session['user_email']
    db = get_db()
    donations = list(db.donations.find({'donor_email': email}).sort('submission_date', -1).limit(3))
    for d in donations:
        d['_id'] = str(d['_id'])
        # Convert images to full URLs (relative to /static/uploads/)
        d['images'] = [f"/static/uploads/{img.split('/')[-1]}" for img in d.get('images', [])]
    return jsonify(donations)

@donor_bp.route('/api/donations')
def api_donations():
    check = require_donor()
    if check:
        return check
    email = session['user_email']
    db = get_db()
    donations = list(db.donations.find({'donor_email': email}).sort('submission_date', -1))
    for d in donations:
        d['_id'] = str(d['_id'])
        d['images'] = [f"/static/uploads/{img.split('/')[-1]}" for img in d.get('images', [])]
    return jsonify(donations)

@donor_bp.route('/api/upload', methods=['POST'])
def api_upload():
    check = require_donor()
    if check:
        return check
    # Extract form data
    item_name = request.form.get('item_name')
    cloth_type = request.form.get('cloth_type')
    condition = request.form.get('condition')
    quantity = int(request.form.get('quantity', 1))
    description = request.form.get('description', '')
    # Calculate points based on condition and quantity
    points_map = {'excellent': 25, 'good': 20, 'fair': 15, 'poor': 10}
    points_per_unit = points_map.get(condition, 0)
    actual_points = points_per_unit * quantity
    # Handle images
    images = request.files.getlist('images')
    filenames = []
    for img in images:
        if img and img.filename:
            filename = secure_filename(img.filename)
            # Avoid collisions by adding timestamp
            name, ext = os.path.splitext(filename)
            timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
            filename = f"{name}_{timestamp}{ext}"
            img.save(os.path.join('static/uploads', filename))
            filenames.append(f"/static/uploads/{filename}")
    # Create donation document
    db = get_db()
    donation = {
        'donor_email': session['user_email'],
        'donor_name': session.get('user_name', ''),
        'item_name': item_name,
        'cloth_type': cloth_type,
        'condition': condition,
        'quantity': quantity,
        'description': description,
        'images': filenames,
        'actual_points': actual_points,
        'status': 'pending',  # default pending
        'claimed_by': None,
        'claimed_at': None,
        'submission_date': datetime.utcnow()
    }
    result = db.donations.insert_one(donation)
    # Don't award points yet; admin will award when approved
    # Notify admin? (optional)
    return jsonify({'success': True, 'donation_id': str(result.inserted_id)})

@donor_bp.route('/api/notifications')
def api_notifications():
    check = require_donor()
    if check:
        return check
    email = session['user_email']
    db = get_db()
    notifications = list(db.notifications.find({'user_email': email}).sort('created_at', -1))
    for n in notifications:
        n['_id'] = str(n['_id'])
    return jsonify(notifications)
@donor_bp.route('/api/current')
def api_current():
    check = require_donor()
    if check:
        return check
    user = get_user_by_email(session['user_email'])
    return jsonify({
        'status': 'success',
        'user': {
            'name': user.get('name', ''),
            'email': user['email'],
            'reward_points': user.get('reward_points', 0)
        }
    })

@donor_bp.route('/api/notifications/mark-read', methods=['POST'])
def api_mark_read():
    check = require_donor()
    if check:
        return check
    data = request.get_json()
    notif_id = data.get('notification_id')
    db = get_db()
    db.notifications.update_one({'_id': ObjectId(notif_id)}, {'$set': {'read': True}})
    return jsonify({'success': True})