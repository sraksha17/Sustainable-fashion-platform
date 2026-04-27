import os
from datetime import datetime
from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from bson import ObjectId
from utils import user_has_role, get_user_by_email, create_notification
from models import get_db

buyer_bp = Blueprint('buyer', __name__, url_prefix='/buyer')

def require_buyer():
    if 'user_email' not in session:
        return redirect(url_for('auth.login'))
    user = get_user_by_email(session['user_email'])
    if not user or not user_has_role(user, 'buyer'):
        return "Access denied", 403
    return None

@buyer_bp.route('/dashboard')
def dashboard():
    check = require_buyer()
    if check:
        return check
    user = get_user_by_email(session['user_email'])
    db = get_db()
    purchases = list(db.sales.find({'buyer_email': session['user_email']}).sort('sold_at', -1))
    for p in purchases:
        p['_id'] = str(p['_id'])
    return render_template('buyer/dashboard.html', user=user, purchases=purchases)

@buyer_bp.route('/marketplace')
def marketplace():
    check = require_buyer()
    if check:
        return check
    return render_template('buyer/marketplace.html')

@buyer_bp.route('/cart')
def cart():
    check = require_buyer()
    if check:
        return check
    return render_template('buyer/cart.html')

# ---------- API: Get available products with reward points ----------
@buyer_bp.route('/api/products')
def api_products():
    check = require_buyer()
    if check:
        return check
    db = get_db()
    designs = list(db.finished_designs.find({'status': 'available'}).sort('created_at', -1))
    for d in designs:
        d['_id'] = str(d['_id'])
        d['image_urls'] = [f"/static/design_uploads/{img}" for img in d.get('images', [])]
        d['reward_points'] = d.get('reward_points', 0)
    return jsonify(designs)

@buyer_bp.route('/api/product/<design_id>')
def api_product(design_id):
    check = require_buyer()
    if check:
        return check
    db = get_db()
    design = db.finished_designs.find_one({'_id': ObjectId(design_id)})
    if not design:
        return jsonify({'error': 'Product not found'}), 404
    design['_id'] = str(design['_id'])
    design['image_urls'] = [f"/static/design_uploads/{img}" for img in design.get('images', [])]
    design['reward_points'] = design.get('reward_points', 0)
    return jsonify(design)

# ---------- Cart APIs (unchanged but enriched with points) ----------
@buyer_bp.route('/api/cart', methods=['GET', 'POST', 'DELETE'])
def api_cart():
    check = require_buyer()
    if check:
        return check
    if 'cart' not in session:
        session['cart'] = []
    if request.method == 'GET':
        db = get_db()
        cart = session['cart']
        enriched = []
        for item in cart:
            design = db.finished_designs.find_one({'_id': ObjectId(item['design_id'])})
            if design and design.get('status') == 'available':
                enriched.append({
                    'design_id': item['design_id'],
                    'name': design['name'],
                    'price': design['price'],
                    'image_url': f"/static/design_uploads/{design['images'][0]}" if design.get('images') else None,
                    'designer_name': design.get('designer_name'),
                    'reward_points': design.get('reward_points', 0),
                    'quantity': item['quantity']
                })
        return jsonify(enriched)
    elif request.method == 'POST':
        data = request.get_json()
        design_id = data.get('design_id')
        quantity = data.get('quantity', 1)
        db = get_db()
        design = db.finished_designs.find_one({'_id': ObjectId(design_id), 'status': 'available'})
        if not design:
            return jsonify({'error': 'Product not available'}), 400
        cart = session['cart']
        found = False
        for item in cart:
            if item['design_id'] == design_id:
                item['quantity'] += quantity
                found = True
                break
        if not found:
            cart.append({'design_id': design_id, 'quantity': quantity})
        session['cart'] = cart
        session.modified = True
        return jsonify({'success': True})
    elif request.method == 'DELETE':
        data = request.get_json()
        design_id = data.get('design_id')
        cart = session['cart']
        cart = [item for item in cart if item['design_id'] != design_id]
        session['cart'] = cart
        session.modified = True
        return jsonify({'success': True})
@buyer_bp.route('/api/prepare-checkout', methods=['POST'])
def prepare_checkout():
    check = require_buyer()
    if check:
        return check
    data = request.get_json()
    use_points = data.get('use_points', False)
    
    cart = session.get('cart', [])
    if not cart:
        return jsonify({'error': 'Cart is empty'}), 400
    
    db = get_db()
    user = get_user_by_email(session['user_email'])
    user_points = user.get('reward_points', 0)
    
    # Calculate totals
    total = 0
    cart_items = []
    for item in cart:
        design = db.finished_designs.find_one({'_id': ObjectId(item['design_id'])})
        if not design or design['status'] != 'available':
            return jsonify({'error': f'Product not available'}), 400
        item_total = design['price'] * item['quantity']
        total += item_total
        cart_items.append({
            'design_id': item['design_id'],
            'name': design['name'],
            'price': design['price'],
            'quantity': item['quantity'],
            'reward_points': design.get('reward_points', 0)
        })
    
    discount = 0
    points_used = 0
    if use_points and user_points > 0:
        discount = min(user_points, total)
        points_used = discount
        total -= discount
    
    if total < 0:
        total = 0
    
    # Store checkout data in session (address will be added later)
    session['checkout_data'] = {
        'cart_items': cart_items,
        'original_total': total + discount,
        'discount': discount,
        'points_used': points_used,
        'final_total': total,
        'use_points': use_points,
        'shipping_address': None  # will be set in checkout page
    }
    session.modified = True
    
    return jsonify({'success': True})

@buyer_bp.route('/api/cart/update', methods=['POST'])
def api_cart_update():
    check = require_buyer()
    if check:
        return check
    data = request.get_json()
    design_id = data.get('design_id')
    quantity = data.get('quantity')
    if quantity < 1:
        return jsonify({'error': 'Quantity must be at least 1'}), 400
    cart = session.get('cart', [])
    for item in cart:
        if item['design_id'] == design_id:
            item['quantity'] = quantity
            break
    session['cart'] = cart
    session.modified = True
    return jsonify({'success': True})

# ---------- Points Redemption Checkout ----------
@buyer_bp.route('/api/checkout-with-points', methods=['POST'])
def api_checkout_with_points():
    check = require_buyer()
    if check:
        return check
    data = request.get_json()
    use_points = data.get('use_points', False)
    shipping_address = data.get('shipping_address', '')
    
    cart = session.get('cart', [])
    if not cart:
        return jsonify({'error': 'Cart is empty'}), 400
    
    db = get_db()
    user = get_user_by_email(session['user_email'])
    user_points = user.get('reward_points', 0)
    
    # Calculate total and collect product details
    total = 0
    cart_items = []
    for item in cart:
        design = db.finished_designs.find_one({'_id': ObjectId(item['design_id'])})
        if not design or design['status'] != 'available':
            return jsonify({'error': f'Product {item["design_id"]} no longer available'}), 400
        item_total = design['price'] * item['quantity']
        total += item_total
        cart_items.append({
            'design_id': item['design_id'],
            'name': design['name'],
            'price': design['price'],
            'quantity': item['quantity'],
            'reward_points': design.get('reward_points', 0)
        })
    
    # Apply points discount if requested
    discount = 0
    points_used = 0
    if use_points and user_points > 0:
        # 1 point = ₹1 discount (or any rate you prefer)
        discount = min(user_points, total)
        points_used = discount
        total -= discount
    
    if total < 0:
        total = 0
    
    # Store checkout info in session for payment verification
    session['checkout_data'] = {
        'cart_items': cart_items,
        'original_total': total + discount,
        'discount': discount,
        'points_used': points_used,
        'final_total': total,
        'shipping_address': shipping_address,
        'use_points': use_points
    }
    session.modified = True
    
    return jsonify({
        'success': True,
        'original_total': total + discount,
        'discount': discount,
        'final_total': total,
        'points_used': points_used,
        'user_points_remaining': user_points - points_used
    })