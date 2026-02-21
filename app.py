import os
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename
from datetime import date
from flask import jsonify
import requests
from flask import jsonify

app = Flask(__name__)
# Secret key is essential for session security
app.secret_key = 'kisan_connect_secure_key' 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# IMAGE UPLOAD CONFIGURATION
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

# ----- DATABASE MODELS -----
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_type = db.Column(db.String(10), nullable=False)
    fullname = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    state = db.Column(db.String(50), nullable=False)
    password = db.Column(db.String(100), nullable=False)
    wallet_address = db.Column(db.String(200), nullable=True)
    products = db.relationship('Product', backref='farmer', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    farmer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=False)
    image_filename = db.Column(db.String(255), nullable=True)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    consumer_id = db.Column(db.Integer, nullable=False)
    farmer_id = db.Column(db.Integer, nullable=False)
    product_id = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    tx_hash = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), default="Pending")


class MandiPrice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    crop = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    avg_price = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, default=date.today)
    
# ----- AI MARKET INTELLIGENCE FUNCTIONS -----

def get_platform_avg(crop, state):
    products = Product.query.filter_by(name=crop, state=state).all()
    if not products:
        return 0
    return sum(p.price for p in products) / len(products)


def get_mandi_avg(crop, state):
    mandi = MandiPrice.query.filter_by(crop=crop, state=state)\
        .order_by(MandiPrice.date.desc()).first()
    if mandi:
        return mandi.avg_price
    return 0
# Insert this before your "if __name__ == '__main__':"

import os
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

@app.route('/chat', methods=['POST'])
def chat():
    user_data = request.json
    user_message = user_data.get('message')
    user_name = session.get('fullname', 'User')

    # The new active model to replace the decommissioned one
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    system_instructions = (
        "You are the agriFlow AI Assistant. Your goal is to help farmers navigate their dashboard. "
        "Here are the specific directions and features available to them:\n"
        "1. Add Product: Tell farmers to click the 'Add product' card to list new vegetables or fruits. "
        "They need to provide name, price per kg, quantity, and a photo.\n"
        "2. View Shop: This is their online storefront where they can see or delete current listings.\n"
        "3. Market Analysis: Guide them here for crop demand, suggested pricing, and profit gaps.\n"
        "4. Compare Prices: This helps them check local vs regional rates to price their harvest better.\n"
        "5. Transactions & Profit: These sections show their financial history and seasonal revenue.\n"
        "Always respond in the user's language (Hindi, Marathi, or English). "
        "Keep responses very short and action-oriented."
    )

    payload = {
        "model": "llama-3.3-70b-versatile", 
        "messages": [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.5 # Lower temperature makes the AI more factual/direct
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def calculate_demand(crop):
    total_products = Product.query.filter_by(name=crop).count()

    if total_products > 10:
        return "High"
    elif total_products > 5:
        return "Medium"
    else:
        return "Low"

@app.route('/get_price_suggestion')
def get_price_suggestion():
    crop = request.args.get('crop', '').strip().capitalize()
    
    # HARDCODED PRICES
    # Tomato: 50, Potato: 30, Wheat: 60
    mandi_rates = {
        "Tomato": 50.0,
        "Potato": 30.0,
        "Wheat": 60.0,
        "Rice": 45.0  # Optional fallback
    }
    
    # Get the rate for the crop, default to 0 if not found
    mandi_avg = mandi_rates.get(crop, 0)
    
    return jsonify({
        "mandi_avg": mandi_avg,
        "suggested": mandi_avg  # Suggesting the market rate directly
    })

def suggest_price(platform_avg, mandi_avg):
    if mandi_avg > platform_avg:
        return mandi_avg - 1
    return platform_avg    
# ----- ROUTES -----


@app.route('/cart')
def cart_page():
    if 'user_id' not in session or session.get('user_type') != 'consumer':
        return redirect(url_for('login_page'))
    
    # Passing name and lang for consistency
    return render_template('cart.html', name=session['fullname'], lang=session.get('lang', 'en'))

@app.route('/')
def index():
    return render_template('language.html')

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    # Persist language selection
    lang = request.args.get('lang')
    if lang:
        session['lang'] = lang
    else:
        lang = session.get('lang', 'en')

    if request.method == 'POST':
        phone = request.form.get('phone')
        password = request.form.get('password')
        user = User.query.filter_by(phone=phone, password=password).first()

        if user:
            session['user_id'] = user.id
            session['fullname'] = user.fullname
            session['user_type'] = user.user_type
            
            if user.user_type == 'farmer':
                return redirect(url_for('farmer_dashboard'))
            return redirect(url_for('consumer_dashboard'))
        
        return "Invalid Credentials", 401

    return render_template('login.html', role=request.args.get('role', 'farmer'), lang=lang)

@app.route('/signup', methods=['POST'])
def signup():
    user_type = request.form.get('user_type')
    fullname = request.form.get('fullname')
    phone = request.form.get('phone')
    state = request.form.get('state')
    password = request.form.get('password')
    lang = request.form.get('lang', 'en')
    session['lang'] = lang 
    
    try:
        new_user = User(
            user_type=user_type,
            fullname=fullname,
            phone=phone,
            state=state,
            password=password
        )
        db.session.add(new_user)
        db.session.commit()
        
        session['user_id'] = new_user.id
        session['fullname'] = fullname
        session['user_type'] = user_type
        
        if user_type == 'farmer':
            return redirect(url_for('farmer_dashboard'))
        return redirect(url_for('consumer_dashboard'))

    except IntegrityError:
        db.session.rollback()
        return "<h1>Phone number already registered.</h1>"

# ----- FARMER PORTAL -----

@app.route('/farmer')
def farmer_dashboard():
    if 'user_id' not in session or session.get('user_type') != 'farmer':
        return redirect(url_for('login_page'))
    
    return render_template('farmer.html', name=session['fullname'], lang=session.get('lang', 'en'))

@app.route('/add_product', methods=['POST'])
def add_product():
    if session.get('user_type') != 'farmer':
        return redirect(url_for('login_page'))

    file = request.files.get('product_image')
    filename = secure_filename(file.filename) if file else None
    if file:
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    try:
        new_product = Product(
            farmer_id=session['user_id'],
            name=request.form.get('product_name'),
            state=request.form.get('state'),
            city=request.form.get('city'),
            price=float(request.form.get('price')),
            quantity=int(request.form.get('quantity')),
            description=request.form.get('description'),
            image_filename=filename
        )
        db.session.add(new_product)
        db.session.commit()
        return redirect(url_for('view_shop'))
    except Exception as e:
        return f"Error: {str(e)}"

@app.route('/shop')
def view_shop():
    if session.get('user_type') != 'farmer':
        return redirect(url_for('login_page'))
    
    products = Product.query.filter_by(farmer_id=session['user_id']).all()
    return render_template('shop.html', products=products, name=session['fullname'], lang=session.get('lang', 'en'))

@app.route('/delete_product/<int:id>')
def delete_product(id):
    if session.get('user_type') != 'farmer':
        return redirect(url_for('login_page'))
        
    product = Product.query.get_or_404(id)
    if product.farmer_id == session['user_id']:
        db.session.delete(product)
        db.session.commit()
    return redirect(url_for('view_shop'))

@app.route('/compare')
def compare_prices():
    if session.get('user_type') != 'farmer':
        return redirect(url_for('login_page'))
    
    search_query = request.args.get('product', '').strip()
    state_query = request.args.get('state', 'All India')
    proximity_filter = request.args.get('proximity', 'All')
    
    user_id = session.get('user_id')
    current_user = User.query.get(user_id)
    
    # Get user's own price for comparison
    user_listing = Product.query.filter(
        Product.farmer_id == user_id, 
        Product.name.ilike(f"%{search_query}%")
    ).first()
    my_price = user_listing.price if user_listing else None

    results = []
    if search_query:
        query = Product.query.filter(Product.name.ilike(f"%{search_query}%"))
        if proximity_filter == "Nearby":
            query = query.filter_by(state=current_user.state)
        elif state_query != "All India":
            query = query.filter_by(state=state_query)
            
        results = query.order_by(Product.price.asc()).all()

    return render_template('compare.html', results=results, my_price=my_price, 
                           current_user_id=user_id, name=session['fullname'], 
                           lang=session.get('lang', 'en'), search_query=search_query, 
                           state_query=state_query, proximity_filter=proximity_filter)
    
@app.route('/market-analysis')
def market_analysis():
    if session.get('user_type') != 'farmer':
        return redirect(url_for('login_page'))

    user_id = session.get('user_id')
    user = User.query.get(user_id)

    # Get farmer's products
    products = Product.query.filter_by(farmer_id=user_id).all()

    if not products:
        return "No products added yet. Please add a product first."

    # Take first product (for demo simplicity)
    crop = products[0].name
    state = user.state

    platform_avg = get_platform_avg(crop, state)
    mandi_avg = get_mandi_avg(crop, state)
    demand = calculate_demand(crop)
    suggested = suggest_price(platform_avg, mandi_avg)
    gap = mandi_avg - platform_avg

    return render_template(
        "market_analysis.html",
        crop=crop,
        state=state,
        platform_avg=platform_avg,
        mandi_avg=mandi_avg,
        demand=demand,
        suggested=suggested,
        gap=gap,
        name=session['fullname']
    )

# ----- CONSUMER PORTAL -----

@app.route('/consumer')
def consumer_dashboard():
    if 'user_id' not in session or session.get('user_type') != 'consumer':
        return redirect(url_for('login_page'))

    # Fetch all products from all farmers across India
    all_products = Product.query.all()
    return render_template('consumer.html', products=all_products, 
                           name=session['fullname'], lang=session.get('lang', 'en'))

# ----- LOGOUT -----

@app.route('/create-order', methods=['POST'])
def create_order():
    if 'user_id' not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    cart_items = data.get('cart')

    if not cart_items:
        return jsonify({"error": "Cart empty"}), 400

    item = cart_items[0]  # single item for now

    product = Product.query.get(item['id'])
    if not product:
        return jsonify({"error": "Product not found"}), 404

    total = product.price * item['cartQty']

    new_order = Order(
        consumer_id=session['user_id'],
        farmer_id=product.farmer_id,
        product_id=product.id,
        quantity=item['cartQty'],
        total_amount=total
    )

    db.session.add(new_order)
    db.session.commit()

    return jsonify({"order_id": new_order.id})

@app.route('/payment/<int:order_id>')
def payment_page(order_id):
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    order = Order.query.get_or_404(order_id)
    product = Product.query.get(order.product_id)
    farmer = User.query.get(order.farmer_id)

    # TEMPORARY: Hardcoded farmer wallet for demo
    farmer_wallet = "0xE4DA514EC43Cab0172280664BaD0eb3d642a5917"

    # Demo conversion ₹ to ETH
    amount_eth = round(order.total_amount / 200000, 5)

    return render_template(
        'payment.html',
        order_id=order.id,
        product_name=product.name,
        farmer_name=farmer.fullname,
        farmer_wallet=farmer_wallet,
        amount_eth=amount_eth
    )
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    order = Order.query.get_or_404(order_id)
    product = Product.query.get(order.product_id)
    farmer = User.query.get(order.farmer_id)

    if not farmer.wallet_address:
        return "Farmer wallet not set!"

    # Demo conversion ₹ to ETH
    amount_eth = round(order.total_amount / 200000, 5)

    return render_template(
        'payment.html',
        order_id=order.id,
        product_name=product.name,
        farmer_name=farmer.fullname,
        farmer_wallet=farmer.wallet_address,
        amount_eth=amount_eth
    )

@app.route('/save-transaction', methods=['POST'])
def save_transaction():
    data = request.get_json()
    order_id = data.get('order_id')
    tx_hash = data.get('tx_hash')

    order = Order.query.get(order_id)
    if order:
        order.tx_hash = tx_hash
        order.status = "Paid"
        db.session.commit()

    return jsonify({"status": "success"})


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        # Insert sample mandi data only if empty
        if not MandiPrice.query.first():
            sample = MandiPrice(
                crop="Tomato",
                state="Rajasthan",
                avg_price=22
            )
            db.session.add(sample)
            db.session.commit()

    app.run(debug=True)