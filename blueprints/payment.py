import os
from datetime import datetime
from flask import Blueprint, request, jsonify, session, current_app, render_template, redirect, url_for
import razorpay
from bson import ObjectId
from models import get_db
from utils import login_required, create_notification

payment_bp = Blueprint('payment', __name__, url_prefix='/payment')

@payment_bp.route('/checkout')
@login_required
def checkout():
    """Show checkout page (address and payment)"""
    checkout_data = session.get('checkout_data', {})
    if not checkout_data:
        return redirect(url_for('buyer.cart'))
    return render_template('checkout.html')

@payment_bp.route('/checkout-data')
@login_required
def checkout_data():
    """Return checkout summary for display"""
    checkout = session.get('checkout_data', {})
    if not checkout:
        return jsonify({'success': False}), 400
    return jsonify({
        'success': True,
        'original_total': checkout.get('original_total', 0),
        'discount': checkout.get('discount', 0),
        'points_used': checkout.get('points_used', 0),
        'final_total': checkout.get('final_total', 0)
    })

@payment_bp.route('/update-address', methods=['POST'])
@login_required
def update_address():
    """Store shipping address in session"""
    data = request.get_json()
    address = data.get('shipping_address')
    checkout = session.get('checkout_data', {})
    if checkout:
        checkout['shipping_address'] = address
        session['checkout_data'] = checkout
        session.modified = True
    return jsonify({'success': True})

@payment_bp.route('/create-order', methods=['POST'])
@login_required
def create_order():
    """Create Razorpay order for positive amount"""
    checkout = session.get('checkout_data', {})
    if not checkout:
        return jsonify({'error': 'No checkout data'}), 400
    
    final_total = checkout.get('final_total', 0)
    if final_total <= 0:
        return jsonify({'error': 'Amount is zero, use /place-zero-amount-order instead'}), 400
    
    amount_paise = int(final_total * 100)
    client = razorpay.Client(auth=(
        current_app.config['RAZORPAY_KEY_ID'],
        current_app.config['RAZORPAY_KEY_SECRET']
    ))
    try:
        order = client.order.create({
            'amount': amount_paise,
            'currency': 'INR',
            'payment_capture': '1'
        })
        db = get_db()
        db.orders.insert_one({
            'order_id': order['id'],
            'buyer_email': session['user_email'],
            'amount': amount_paise,
            'status': 'created',
            'cart_items': checkout.get('cart_items', []),
            'shipping_address': checkout.get('shipping_address', ''),
            'use_points': checkout.get('use_points', False),
            'points_used': checkout.get('points_used', 0),
            'original_total': checkout.get('original_total', 0),
            'discount': checkout.get('discount', 0),
            'created_at': datetime.now()
        })
        return jsonify({
            'success': True,
            'order_id': order['id'],
            'amount': order['amount'],
            'currency': order['currency']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@payment_bp.route('/place-zero-amount-order', methods=['POST'])
@login_required
def place_zero_amount_order():
    """Handle order where final total is zero (fully paid by points)"""
    data = request.get_json()
    address = data.get('shipping_address')
    checkout = session.get('checkout_data', {})
    if not checkout:
        return jsonify({'success': False, 'error': 'No checkout data'}), 400
    
    checkout['shipping_address'] = address
    session['checkout_data'] = checkout
    session.modified = True
    
    return handle_zero_amount_checkout(checkout)

def handle_zero_amount_checkout(checkout):
    """Process order without payment (fully covered by points)"""
    db = get_db()
    mock_order_id = f"mock_{datetime.now().timestamp()}"
    
    # Insert a fake order
    db.orders.insert_one({
        'order_id': mock_order_id,
        'buyer_email': session['user_email'],
        'amount': 0,
        'status': 'paid',
        'cart_items': checkout.get('cart_items', []),
        'shipping_address': checkout.get('shipping_address', ''),
        'use_points': checkout.get('use_points', False),
        'points_used': checkout.get('points_used', 0),
        'original_total': checkout.get('original_total', 0),
        'discount': checkout.get('discount', 0),
        'created_at': datetime.now(),
        'paid_at': datetime.now(),
        'payment_id': 'points_only'
    })
    
    # Create sale records and mark products sold
    for item in checkout.get('cart_items', []):
        design = db.finished_designs.find_one({'_id': ObjectId(item['design_id'])})
        if design and design['status'] == 'available':
            commission = design['price'] * 0.2
            designer_earnings = design['price'] - commission
            sale = {
                'design_id': item['design_id'],
                'design_name': design['name'],
                'designer_email': design['designer_email'],
                'buyer_email': session['user_email'],
                'price': design['price'],
                'commission': commission,
                'designer_earnings': designer_earnings,
                'payment_status': 'paid',
                'payment_id': 'points_only',
                'sold_at': datetime.now(),
                'shipping_address': checkout.get('shipping_address', '')
            }
            db.sales.insert_one(sale)
            db.finished_designs.update_one(
                {'_id': ObjectId(item['design_id'])},
                {'$set': {'status': 'sold'}}
            )
            create_notification(
                design['designer_email'],
                f"Your design '{design['name']}' was purchased using reward points (₹{design['price']}).",
                'sale'
            )
    
    # Deduct points from buyer
    if checkout.get('use_points') and checkout.get('points_used', 0) > 0:
        db.users.update_one(
            {'email': session['user_email']},
            {'$inc': {'reward_points': -checkout['points_used']}}
        )
        # Record redemption
        db.points_redemptions.insert_one({
            'user_email': session['user_email'],
            'points_used': checkout['points_used'],
            'discount_amount': checkout.get('discount', 0),
            'order_id': mock_order_id,
            'created_at': datetime.now()
        })
    
    # Clear session
    session.pop('cart', None)
    session.pop('checkout_data', None)
    
    return jsonify({'success': True, 'zero_amount': True})

@payment_bp.route('/verify', methods=['POST'])
@login_required
def verify_payment():
    """Verify Razorpay payment and finalize order"""
    data = request.get_json()
    client = razorpay.Client(auth=(
        current_app.config['RAZORPAY_KEY_ID'],
        current_app.config['RAZORPAY_KEY_SECRET']
    ))
    try:
        # Verify signature
        params = {
            'razorpay_order_id': data['razorpay_order_id'],
            'razorpay_payment_id': data['razorpay_payment_id'],
            'razorpay_signature': data['razorpay_signature']
        }
        client.utility.verify_payment_signature(params)
        
        db = get_db()
        order = db.orders.find_one({'order_id': data['razorpay_order_id']})
        if not order:
            return jsonify({'success': False, 'error': 'Order not found'}), 404
        
        # Update order status
        db.orders.update_one(
            {'order_id': data['razorpay_order_id']},
            {'$set': {
                'payment_id': data['razorpay_payment_id'],
                'status': 'paid',
                'paid_at': datetime.now()
            }}
        )
        
        # Create sale records
        for item in order.get('cart_items', []):
            design = db.finished_designs.find_one({'_id': ObjectId(item['design_id'])})
            if design and design['status'] == 'available':
                commission = design['price'] * 0.2
                designer_earnings = design['price'] - commission
                sale = {
                    'design_id': item['design_id'],
                    'design_name': design['name'],
                    'designer_email': design['designer_email'],
                    'buyer_email': session['user_email'],
                    'price': design['price'],
                    'commission': commission,
                    'designer_earnings': designer_earnings,
                    'payment_status': 'paid',
                    'payment_id': data['razorpay_payment_id'],
                    'sold_at': datetime.now(),
                    'shipping_address': order.get('shipping_address', '')
                }
                db.sales.insert_one(sale)
                db.finished_designs.update_one(
                    {'_id': ObjectId(item['design_id'])},
                    {'$set': {'status': 'sold'}}
                )
                create_notification(
                    design['designer_email'],
                    f"Your design '{design['name']}' was purchased for ₹{design['price']}.",
                    'sale'
                )
        
        # Deduct points if used
        if order.get('use_points') and order.get('points_used', 0) > 0:
            db.users.update_one(
                {'email': session['user_email']},
                {'$inc': {'reward_points': -order['points_used']}}
            )
            db.points_redemptions.insert_one({
                'user_email': session['user_email'],
                'points_used': order['points_used'],
                'discount_amount': order.get('discount', 0),
                'order_id': data['razorpay_order_id'],
                'created_at': datetime.now()
            })
        
        # Clear session
        session.pop('cart', None)
        session.pop('checkout_data', None)
        
        return jsonify({'success': True})
    except Exception as e:
        print("Verification error:", str(e))
        return jsonify({'success': False, 'error': str(e)}), 400

@payment_bp.route('/success')
@login_required
def success():
    """Order success page"""
    return render_template('order_success.html')