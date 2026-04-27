# admin.py – complete with image serving for design_uploads
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timezone
import hashlib
import os
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, template_folder='templates')
CORS(app)
app.secret_key = os.getenv('SECRET_KEY', 'admin-secret-key-2024')

# MongoDB Connection
username = os.getenv('MONGO_USER', 'revive_threads_user')
password = os.getenv('MONGO_PASSWORD', 'revivethread2025')
encoded_password = urllib.parse.quote_plus(password)
mongodb_uri = os.getenv('MONGO_URI', f"mongodb+srv://{username}:{encoded_password}@cluster0.diclaks.mongodb.net/revive_threads?retryWrites=true&w=majority")

client = MongoClient(mongodb_uri)
db = client.revive_threads

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOADS_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
UPLOADS_FOLDER = os.path.abspath(UPLOADS_FOLDER)

print("="*60)
print("ADMIN APP RUNNING on http://localhost:5001")
print("Admin login: http://localhost:5001/admin/login")
print("Credentials: admin@restyle.com / admin123")
print("="*60)

# Helper functions
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_image_url(image_data):
    if not image_data:
        return '/static/images/default-cloth.jpg'
    if isinstance(image_data, str):
        filename = os.path.basename(image_data)
    elif isinstance(image_data, list) and len(image_data) > 0:
        filename = os.path.basename(image_data[0])
    else:
        return '/static/images/default-cloth.jpg'
    local_path = os.path.join(UPLOADS_FOLDER, filename)
    if os.path.exists(local_path):
        return f"/uploads/{filename}"
    else:
        return f"http://localhost:5000/static/uploads/{filename}"

def format_date(date_obj):
    if not date_obj:
        return "Unknown"
    if isinstance(date_obj, str):
        try:
            date_obj = datetime.fromisoformat(date_obj.replace('Z', '+00:00'))
        except:
            return date_obj
    return date_obj.strftime('%B %d, %Y')

# ==================== FILE SERVING ====================
@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(UPLOADS_FOLDER, filename)

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/static/design_uploads/<path:filename>')
def serve_design_upload(filename):
    """Serve product images from static/design_uploads"""
    return send_from_directory('static/design_uploads', filename)

# ==================== ADMIN AUTH ====================
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = db.users.find_one({"email": email})
        if not user or user.get('user_type') != 'admin':
            return render_template('admin/login.html', error="Invalid admin credentials")
        if hash_password(password) != user['password']:
            return render_template('admin/login.html', error="Invalid password")
        session['admin_logged_in'] = True
        session['admin_email'] = user['email']
        session['admin_name'] = user.get('name', 'Admin')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

@app.route('/admin/')
@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    total_donations = db.donations.count_documents({})
    total_products = db.finished_designs.count_documents({})
    total_sales = db.sales.count_documents({})
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$price"}}}]
    result = list(db.sales.aggregate(pipeline))
    total_revenue = result[0]['total'] if result else 0
    return render_template('admin/dashboard.html',
                         total_donations=total_donations,
                         total_products=total_products,
                         total_sales=total_sales,
                         total_revenue=total_revenue)

# ==================== DONATIONS ====================
@app.route('/admin/donations')
def admin_donations():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    return render_template('admin/donations.html')

@app.route('/api/admin/donations', methods=['GET'])
def get_all_donations():
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    status_filter = request.args.get('status', 'all')
    query = {}
    if status_filter != 'all':
        query['status'] = status_filter
    donations = list(db.donations.find(query).sort("submission_date", -1))
    donation_list = []
    for donation in donations:
        images = donation.get('images', [])
        image_url = get_image_url(images)
        donor_name = donation.get('donor_name', '')
        if not donor_name and donation.get('donor_email'):
            donor = db.users.find_one({"email": donation['donor_email']})
            donor_name = donor.get('name', 'Anonymous') if donor else 'Anonymous'
        donation_list.append({
            '_id': str(donation['_id']),
            'donor_email': donation.get('donor_email', ''),
            'donor_name': donor_name,
            'item_name': donation.get('item_name', 'Unnamed Item'),
            'cloth_type': donation.get('cloth_type', 'General'),
            'condition': donation.get('condition', 'Unknown'),
            'quantity': donation.get('quantity', 1),
            'status': donation.get('status', 'pending'),
            'image_url': image_url,
            'points': donation.get('actual_points', 0),
            'date': format_date(donation.get('submission_date'))
        })
    return jsonify({"status": "success", "donations": donation_list})

@app.route('/api/admin/update-status', methods=['POST'])
def update_donation_status():
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    data = request.json
    donation_id = data.get('donation_id')
    new_status = data.get('status')
    if not donation_id or not new_status:
        return jsonify({"status": "error", "message": "Missing data"}), 400
    donation = db.donations.find_one({"_id": ObjectId(donation_id)})
    if not donation:
        return jsonify({"status": "error", "message": "Donation not found"}), 404
    old_status = donation.get('status')
    donor_email = donation['donor_email']
    base_points = donation.get('actual_points', 0)
    db.donations.update_one({"_id": ObjectId(donation_id)}, {"$set": {"status": new_status}})
    if new_status == 'collected' and old_status != 'collected':
        db.users.update_one({"email": donor_email}, {"$inc": {"reward_points": base_points}})
        db.notifications.insert_one({
            'user_email': donor_email,
            'message': f'Your donation "{donation["item_name"]}" has been collected. You earned {base_points} points!',
            'type': 'donation_update',
            'read': False,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    elif new_status == 'upcycled' and old_status != 'upcycled':
        if old_status == 'collected':
            bonus_points = int(base_points * 0.5)
            db.users.update_one({"email": donor_email}, {"$inc": {"reward_points": bonus_points}})
            db.donations.update_one({"_id": ObjectId(donation_id)}, {"$set": {"actual_points": base_points + bonus_points}})
            db.notifications.insert_one({
                'user_email': donor_email,
                'message': f'Your donation "{donation["item_name"]}" has been upcycled! You earned a bonus of {bonus_points} points.',
                'type': 'donation_update',
                'read': False,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        else:
            db.users.update_one({"email": donor_email}, {"$inc": {"reward_points": base_points}})
    elif new_status == 'rejected' and old_status == 'pending':
        db.notifications.insert_one({
            'user_email': donor_email,
            'message': f'Your donation "{donation["item_name"]}" has been rejected.',
            'type': 'donation_update',
            'read': False,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    return jsonify({"status": "success"})

# ==================== PRODUCTS (Marketplace) ====================
@app.route('/admin/products')
def admin_products():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    return render_template('admin/products.html')

@app.route('/admin/products/add', methods=['GET', 'POST'])
def admin_add_product():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    if request.method == 'POST':
        name = request.form.get('name')
        price = float(request.form.get('price', 0))
        description = request.form.get('description', '')
        size = request.form.get('size', '')
        style = request.form.get('style', '')
        source_material = request.form.get('source_material', '')
        designer_name = request.form.get('designer_name', 'Admin')
        designer_email = request.form.get('designer_email', 'admin@restyle.com')
        reward_points = int(request.form.get('reward_points', 0))
        images = []
        if 'images' in request.files:
            for file in request.files.getlist('images'):
                if file and file.filename:
                    filename = f"{datetime.now().timestamp()}_{file.filename}"
                    file.save(os.path.join('static/design_uploads', filename))
                    images.append(filename)
        db.finished_designs.insert_one({
            'name': name, 'price': price, 'description': description,
            'size': size, 'style': style, 'source_material': source_material,
            'designer_name': designer_name, 'designer_email': designer_email,
            'images': images, 'status': 'available', 'created_at': datetime.now(),
            'reward_points': reward_points
        })
        flash('Product added', 'success')
        return redirect(url_for('admin_products'))
    return render_template('admin/product_form.html')

@app.route('/admin/products/edit/<product_id>', methods=['GET', 'POST'])
def admin_edit_product(product_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    product = db.finished_designs.find_one({'_id': ObjectId(product_id)})
    if not product:
        flash('Product not found', 'error')
        return redirect(url_for('admin_products'))
    if request.method == 'POST':
        update_data = {
            'name': request.form.get('name'),
            'price': float(request.form.get('price', 0)),
            'description': request.form.get('description', ''),
            'size': request.form.get('size', ''),
            'style': request.form.get('style', ''),
            'source_material': request.form.get('source_material', ''),
            'designer_name': request.form.get('designer_name', 'Admin'),
            'designer_email': request.form.get('designer_email', 'admin@restyle.com'),
            'reward_points': int(request.form.get('reward_points', 0))
        }
        if 'images' in request.files:
            existing = product.get('images', [])
            for file in request.files.getlist('images'):
                if file and file.filename:
                    filename = f"{datetime.now().timestamp()}_{file.filename}"
                    file.save(os.path.join('static/design_uploads', filename))
                    existing.append(filename)
            update_data['images'] = existing
        db.finished_designs.update_one({'_id': ObjectId(product_id)}, {'$set': update_data})
        flash('Product updated', 'success')
        return redirect(url_for('admin_products'))
    product['_id'] = str(product['_id'])
    return render_template('admin/product_form.html', product=product)

@app.route('/api/admin/products', methods=['GET'])
def admin_products_list():
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    products = list(db.finished_designs.find().sort("created_at", -1))
    products_list = []
    for p in products:
        image_url = None
        if p.get('images') and len(p['images']) > 0:
            image_url = f"/static/design_uploads/{p['images'][0]}"
        products_list.append({
            '_id': str(p['_id']),
            'name': p.get('name', 'Unnamed'),
            'price': p.get('price', 0),
            'designer_name': p.get('designer_name', 'Unknown'),
            'status': p.get('status', 'available'),
            'image_url': image_url,
            'reward_points': p.get('reward_points', 0),
            'created_at': p.get('created_at').strftime('%Y-%m-%d') if p.get('created_at') else 'Unknown'
        })
    return jsonify({"status": "success", "products": products_list})

@app.route('/api/admin/products/update', methods=['POST'])
def admin_update_product():
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    data = request.json
    product_id = data.get('product_id')
    new_status = data.get('status')
    if not product_id or not new_status:
        return jsonify({"status": "error", "message": "Missing data"}), 400
    db.finished_designs.update_one({"_id": ObjectId(product_id)}, {"$set": {"status": new_status}})
    return jsonify({"status": "success"})

@app.route('/api/admin/products/delete', methods=['POST'])
def admin_delete_product():
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    data = request.json
    product_id = data.get('product_id')
    if not product_id:
        return jsonify({"status": "error", "message": "Missing product_id"}), 400
    db.finished_designs.delete_one({"_id": ObjectId(product_id)})
    return jsonify({"status": "success"})

@app.route('/api/admin/products/update-details', methods=['POST'])
def admin_update_product_details():
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    data = request.json
    product_id = data.get('product_id')
    if not product_id:
        return jsonify({"status": "error", "message": "Missing product_id"}), 400
    update_fields = {}
    for field in ['name', 'description', 'size', 'style', 'source_material', 'designer_name']:
        if field in data:
            update_fields[field] = data[field]
    if 'price' in data:
        update_fields['price'] = float(data['price'])
    if 'reward_points' in data:
        update_fields['reward_points'] = int(data['reward_points'])
    if not update_fields:
        return jsonify({"status": "error", "message": "No fields to update"}), 400
    db.finished_designs.update_one({"_id": ObjectId(product_id)}, {"$set": update_fields})
    return jsonify({"status": "success"})

@app.route('/api/admin/product-details/<product_id>', methods=['GET'])
def get_product_details(product_id):
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    product = db.finished_designs.find_one({"_id": ObjectId(product_id)})
    if not product:
        return jsonify({"status": "error", "message": "Product not found"}), 404
    product['_id'] = str(product['_id'])
    product['image_urls'] = [f"/static/design_uploads/{img}" for img in product.get('images', [])]
    product['reward_points'] = product.get('reward_points', 0)
    return jsonify({"status": "success", "product": product})

# ==================== ORDERS (SALES) ====================
@app.route('/admin/orders')
def admin_orders():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    return render_template('admin/orders.html')

@app.route('/api/admin/sales', methods=['GET'])
def admin_sales():
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    sales = list(db.sales.find().sort("sold_at", -1))
    sales_list = []
    for sale in sales:
        sales_list.append({
            '_id': str(sale['_id']),
            'design_name': sale.get('design_name', 'Unknown'),
            'buyer_email': sale.get('buyer_email', ''),
            'designer_email': sale.get('designer_email', ''),
            'price': sale.get('price', 0),
            'commission': sale.get('commission', 0),
            'designer_earnings': sale.get('designer_earnings', 0),
            'sold_at': sale.get('sold_at').strftime('%Y-%m-%d %H:%M:%S') if sale.get('sold_at') else 'Unknown'
        })
    return jsonify({"status": "success", "sales": sales_list})

# ==================== STATS API ====================
@app.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    total_donations = db.donations.count_documents({})
    total_products = db.finished_designs.count_documents({})
    total_sales = db.sales.count_documents({})
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$price"}}}]
    result = list(db.sales.aggregate(pipeline))
    total_revenue = result[0]['total'] if result else 0
    return jsonify({
        "status": "success",
        "stats": {
            "total_donations": total_donations,
            "total_products": total_products,
            "total_sales": total_sales,
            "total_revenue": total_revenue
        }
    })

# ==================== FIX DATABASE ====================
@app.route('/api/admin/fix-database', methods=['GET'])
def fix_admin_database():
    db.donations.update_many({"status": {"$exists": False}}, {"$set": {"status": "pending"}})
    admin_exists = db.users.find_one({"email": "admin@restyle.com"})
    if not admin_exists:
        db.users.insert_one({
            "name": "Admin User",
            "email": "admin@restyle.com",
            "password": hash_password('admin123'),
            "user_type": "admin",
            "reward_points": 0,
            "total_donations": 0,
            "created_at": datetime.now(timezone.utc)
        })
    return jsonify({"status": "success", "message": "Database fixed"})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)