import os
from datetime import datetime, timedelta
from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from bson import ObjectId
from werkzeug.utils import secure_filename
from utils import user_has_role, get_user_by_email, create_notification
from models import get_db

designer_bp = Blueprint('designer', __name__, url_prefix='/designer')

def require_designer():
    if 'user_email' not in session:
        return redirect(url_for('auth.login'))
    user = get_user_by_email(session['user_email'])
    if not user or not user_has_role(user, 'designer'):
        return "Access denied", 403
    return None

@designer_bp.route('/dashboard')
def dashboard():
    check = require_designer()
    if check:
        return check
    return render_template('designer/dashboard.html')

# ---------- API ENDPOINTS ----------

@designer_bp.route('/api/stats')
def api_stats():
    check = require_designer()
    if check:
        return check
    email = session['user_email']
    db = get_db()
    active_projects = db.designer_projects.count_documents({
        'designer_email': email,
        'status': 'in_progress'
    })
    completed_projects = db.designer_projects.count_documents({
        'designer_email': email,
        'status': 'completed'
    })
    earnings = 0
    pipeline = [
        {'$match': {'designer_email': email}},
        {'$group': {'_id': None, 'total': {'$sum': '$designer_earnings'}}}
    ]
    result = list(db.sales.aggregate(pipeline))
    if result:
        earnings = result[0]['total']
    return jsonify({
        'active_projects': active_projects,
        'completed_projects': completed_projects,
        'total_earnings': earnings
    })

@designer_bp.route('/api/available-clothes')
def api_available_clothes():
    check = require_designer()
    if check:
        return check
    db = get_db()
    donations = list(db.donations.find({
        'status': 'collected',
        '$or': [
            {'claimed_by': None},
            {'claimed_by': ''}
        ]
    }).sort('submission_date', -1))
    for d in donations:
        d['_id'] = str(d['_id'])
        d['images'] = [f"/static/uploads/{img.split('/')[-1]}" for img in d.get('images', [])]
    return jsonify(donations)

@designer_bp.route('/api/claim', methods=['POST'])
def api_claim():
    check = require_designer()
    if check:
        return check
    data = request.get_json()
    donation_id = data.get('donation_id')
    period = data.get('period', '1_month')

    period_days = {
        '1_week': 7,
        '2_weeks': 14,
        '3_weeks': 21,
        '1_month': 30,
        '2_months': 60,
        '3_months': 90,
        '4_months': 120,
        '5_months': 150,
        '6_months': 180
    }
    days = period_days.get(period, 30)

    db = get_db()
    donation = db.donations.find_one({'_id': ObjectId(donation_id)})
    if not donation or donation.get('status') != 'collected':
        return jsonify({'success': False, 'error': 'Invalid donation'}), 400
    if donation.get('claimed_by'):
        return jsonify({'success': False, 'error': 'Already claimed'}), 400

    project = {
        'donation_id': donation_id,
        'donation_name': donation.get('item_name', 'Unnamed'),
        'designer_email': session['user_email'],
        'claimed_at': datetime.utcnow(),
        'deadline': datetime.utcnow() + timedelta(days=days),
        'status': 'in_progress',
        'completed_at': None,
        'finished_design_id': None
    }
    db.designer_projects.insert_one(project)

    db.donations.update_one(
        {'_id': ObjectId(donation_id)},
        {'$set': {'claimed_by': session['user_email'], 'claimed_at': datetime.utcnow()}}
    )

    donor_email = donation.get('donor_email')
    if donor_email:
        create_notification(
            donor_email,
            f"Your donation '{donation.get('item_name')}' has been claimed by designer {session['user_email']}. "
            f"They have {days} days to upcycle it.",
            'info'
        )
    return jsonify({'success': True})

@designer_bp.route('/api/projects')
def api_projects():
    check = require_designer()
    if check:
        return check
    email = session['user_email']
    db = get_db()
    projects = list(db.designer_projects.find({'designer_email': email}).sort('claimed_at', -1))
    
    for p in projects:
        # Convert all ObjectId fields to strings
        p['_id'] = str(p['_id'])
        p['donation_id'] = str(p['donation_id'])
        if p.get('finished_design_id'):
            p['finished_design_id'] = str(p['finished_design_id'])
        
        # Convert datetime fields to ISO strings
        p['claimed_at'] = p['claimed_at'].isoformat() if p.get('claimed_at') else None
        p['deadline'] = p['deadline'].isoformat() if p.get('deadline') else None
        p['completed_at'] = p['completed_at'].isoformat() if p.get('completed_at') else None

        # Add image URL from the donation
        donation = db.donations.find_one({'_id': ObjectId(p['donation_id'])})
        if donation and donation.get('images'):
            first_img = donation['images'][0]
            if first_img.startswith('/static/uploads/'):
                p['image_url'] = first_img
            else:
                p['image_url'] = f"/static/uploads/{first_img.split('/')[-1]}"
        else:
            p['image_url'] = '/static/images/default-cloth.jpg'
    
    return jsonify(projects)

@designer_bp.route('/api/active-projects')
def api_active_projects():
    """Return list of in-progress projects for dropdown."""
    check = require_designer()
    if check:
        return check
    email = session['user_email']
    db = get_db()
    projects = list(db.designer_projects.find(
        {'designer_email': email, 'status': 'in_progress'},
        {'_id': 1, 'donation_name': 1}
    ))
    for p in projects:
        p['_id'] = str(p['_id'])
    return jsonify(projects)

@designer_bp.route('/api/upload-design', methods=['POST'])
def api_upload_design():
    check = require_designer()
    if check:
        return check

    name = request.form.get('name')
    source_material = request.form.get('source_material')
    size = request.form.get('size')
    style = request.form.get('style')
    price = float(request.form.get('price', 0))
    phone = request.form.get('phone')
    description = request.form.get('description', '')
    project_id = request.form.get('project_id')

    # Handle images
    images = request.files.getlist('images')
    filenames = []
    for img in images:
        if img and img.filename:
            filename = secure_filename(img.filename)
            name_part, ext = os.path.splitext(filename)
            timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
            new_filename = f"{name_part}_{timestamp}{ext}"
            img.save(os.path.join('static/design_uploads', new_filename))
            filenames.append(new_filename)

    db = get_db()
    user = get_user_by_email(session['user_email'])

    # Create design document
    design = {
        'designer_email': session['user_email'],
        'designer_name': user.get('name', ''),
        'designer_phone': phone,
        'name': name,
        'source_material': source_material,
        'size': size,
        'style': style,
        'price': price,
        'description': description,
        'images': filenames,
        'status': 'available',
        'created_at': datetime.utcnow()
    }
    result = db.finished_designs.insert_one(design)
    design_id = str(result.inserted_id)

    # If linked to a project, mark project completed and donation upcycled
    if project_id:
        try:
            # Verify project exists, belongs to this designer, and is still in progress
            project = db.designer_projects.find_one({'_id': ObjectId(project_id)})
            if not project:
                print(f"Project {project_id} not found")
                return jsonify({'success': False, 'message': 'Project not found'}), 400

            if project['designer_email'] != session['user_email']:
                print(f"Project {project_id} does not belong to {session['user_email']}")
                return jsonify({'success': False, 'message': 'Unauthorized'}), 403

            if project['status'] != 'in_progress':
                print(f"Project {project_id} already completed")
                return jsonify({'success': False, 'message': 'Project already completed'}), 400

            # Update project
            update_result = db.designer_projects.update_one(
                {'_id': ObjectId(project_id)},
                {
                    '$set': {
                        'status': 'completed',
                        'completed_at': datetime.utcnow(),
                        'finished_design_id': result.inserted_id
                    }
                }
            )
            if update_result.modified_count == 0:
                print(f"Failed to update project {project_id}")
                return jsonify({'success': False, 'message': 'Failed to update project'}), 500

            # Update original donation
            donation_id = project['donation_id']
            donation_update = db.donations.update_one(
                {'_id': ObjectId(donation_id)},
                {'$set': {'status': 'upcycled'}}
            )
            if donation_update.modified_count == 0:
                print(f"Failed to update donation {donation_id}")
                # Not critical, but log

            # Notify donor
            donation = db.donations.find_one({'_id': ObjectId(donation_id)})
            if donation and donation.get('donor_email'):
                create_notification(
                    donation['donor_email'],
                    f"Your donated item '{donation.get('item_name')}' has been upcycled into a new design!",
                    'upcycled'
                )
            print(f"Project {project_id} marked completed, design {design_id} linked")
        except Exception as e:
            print(f"Error updating project: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500

    return jsonify({'success': True, 'design_id': design_id})

@designer_bp.route('/api/sales')
def api_sales():
    check = require_designer()
    if check:
        return check
    email = session['user_email']
    db = get_db()
    sales = list(db.sales.find({'designer_email': email}).sort('sold_at', -1))
    for s in sales:
        s['_id'] = str(s['_id'])
        s['design_id'] = str(s['design_id'])
        s['sold_at'] = s['sold_at'].isoformat() if s.get('sold_at') else None
    return jsonify(sales)

@designer_bp.route('/api/notifications')
def api_notifications():
    check = require_designer()
    if check:
        return check
    email = session['user_email']
    db = get_db()
    notifications = list(db.notifications.find({'user_email': email}).sort('created_at', -1))
    for n in notifications:
        n['_id'] = str(n['_id'])
    return jsonify(notifications)

@designer_bp.route('/api/notifications/mark-read', methods=['POST'])
def api_mark_read():
    check = require_designer()
    if check:
        return check
    data = request.get_json()
    notif_id = data.get('notification_id')
    db = get_db()
    db.notifications.update_one({'_id': ObjectId(notif_id)}, {'$set': {'read': True}})
    return jsonify({'success': True})

@designer_bp.route('/api/current')
def api_current():
    check = require_designer()
    if check:
        return check
    user = get_user_by_email(session['user_email'])
    return jsonify({
        'status': 'success',
        'user': {
            'name': user.get('name', ''),
            'email': user['email']
        }
    })