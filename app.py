import os
import sqlite3
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

# ==========================================
# ⚠️ CONFIGURATION - CHANGE THIS PATH
# ==========================================
# This must match the location of your SQLite database on Render.
# If you put the database in the same folder as this app.py, use:
DATABASE_FILE = os.path.join(os.path.dirname(__file__), "hotel1_database.db")

# ==========================================
# CALLBACK ENDPOINT
# ==========================================
@app.route('/mpesa/callback', methods=['POST'])
def mpesa_callback():
    try:
        # Get the JSON data sent by Safaricom
        data = request.get_json()
        print("Callback received:", data)

        # Safaricom sends the result inside the Body -> stkCallback
        stk_callback = data.get('Body', {}).get('stkCallback', {})
        
        merchant_request_id = stk_callback.get('MerchantRequestID')
        checkout_request_id = stk_callback.get('CheckoutRequestID')
        result_code = stk_callback.get('ResultCode')
        result_desc = stk_callback.get('ResultDesc')

        # If ResultCode is 0, the payment was successful
        if result_code == 0:
            callback_metadata = stk_callback.get('CallbackMetadata', {}).get('Item', [])
            
            # Extract metadata (Amount, MpesaReceiptNumber, PhoneNumber, etc.)
            amount = None
            mpesa_receipt = None
            phone_number = None
            transaction_date = None
            
            for item in callback_metadata:
                if item.get('Name') == 'Amount':
                    amount = item.get('Value')
                elif item.get('Name') == 'MpesaReceiptNumber':
                    mpesa_receipt = item.get('Value')
                elif item.get('Name') == 'PhoneNumber':
                    phone_number = item.get('Value')
                elif item.get('Name') == 'TransactionDate':
                    transaction_date = item.get('Value')

            print(f"✅ SUCCESS: Receipt {mpesa_receipt}, Amount {amount}, Phone {phone_number}")

            # ==========================================
            # UPDATE YOUR SQLITE DATABASE
            # ==========================================
            try:
                conn = sqlite3.connect(DATABASE_FILE)
                cursor = conn.cursor()
                
                # Update the status of the transaction from 'pending' to 'completed'
                # We match using the CheckoutRequestID (which we saved as receipt_no)
                cursor.execute('''
                    UPDATE mpesa_transactions 
                    SET status = 'completed', receipt_no = ?
                    WHERE receipt_no = ? AND status = 'pending'
                ''', (mpesa_receipt, checkout_request_id))
                
                conn.commit()
                print(f"Database updated. Rows affected: {cursor.rowcount}")
                conn.close()
                
            except Exception as db_error:
                print(f"❌ Database Error: {str(db_error)}")
                # We still return success to Safaricom so they don't keep retrying

        else:
            # Payment failed or was cancelled by user
            print(f"❌ FAILED: {result_desc}")
            
            # Update database to mark as failed
            try:
                conn = sqlite3.connect(DATABASE_FILE)
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE mpesa_transactions 
                    SET status = 'failed'
                    WHERE receipt_no = ? AND status = 'pending'
                ''', (checkout_request_id,))
                conn.commit()
                conn.close()
            except Exception as db_error:
                print(f"❌ Database Error: {str(db_error)}")

        # Always return this to Safaricom to acknowledge receipt
        return jsonify({"ResultCode": 0, "ResultDesc": "Success"})

    except Exception as e:
        print(f"❌ Server Error: {str(e)}")
        # Return an error code if something goes wrong on your end
        return jsonify({"ResultCode": 1, "ResultDesc": "Internal Server Error"}), 500


# ==========================================
# HEALTH CHECK ENDPOINT
# ==========================================
@app.route('/', methods=['GET'])
def health_check():
    """Simple endpoint to check if the server is running."""
    return "M-Pesa Callback Server is Running!"


if __name__ == '__main__':
    # Render sets the PORT environment variable automatically
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)