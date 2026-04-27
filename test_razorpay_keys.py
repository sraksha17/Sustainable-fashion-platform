# test_razorpay_keys.py
import razorpay

# Paste your Test Mode Key ID and Secret here
key_id = "rzp_test_SZpcD7kU9W6Eh5"      # Replace with your actual Key ID
key_secret = "c7JnjH53lf97u0I7pJ4Zt61L" # Replace with your actual Key Secret

client = razorpay.Client(auth=(key_id, key_secret))

try:
    # Attempt to create a dummy order of ₹1 (100 paise)
    order = client.order.create({
        'amount': 100,
        'currency': 'INR',
        'payment_capture': '1'
    })
    print(" API Authentication Successful! Order created:", order['id'])
except Exception as e:
    print(" API Authentication Failed:", e)