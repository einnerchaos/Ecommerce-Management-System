from flask import Flask, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, timedelta
import stripe
from sqlalchemy import or_, and_, cast, String
from sqlalchemy.types import JSON
from sqlalchemy import extract
from collections import Counter
import io
import openpyxl
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///ecommerce.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'jwt-secret-key'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)

db = SQLAlchemy(app)
jwt = JWTManager(app)
CORS(app)

# Stripe configuration
stripe.api_key = 'sk_test_your_stripe_key_here'

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='customer')  # admin, customer
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, default=0)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    image_url = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    original_price = db.Column(db.Float, nullable=True)  # New: store original/sample price
    price_change_history = db.Column(JSON, default=list)  # New: store last 5 price changes

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    total = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, paid, shipped, delivered
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)

class ProductImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    image_url = db.Column(db.String(300), nullable=False)

Product.images = db.relationship('ProductImage', backref='product', lazy=True, cascade='all, delete-orphan')

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Authentication routes
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email already exists'}), 400
    
    hashed_password = generate_password_hash(data['password'])
    user = User(
        email=data['email'],
        password=hashed_password,
        name=data['name'],
        role=data.get('role', 'customer')
    )
    
    db.session.add(user)
    db.session.commit()
    
    return jsonify({'message': 'User created successfully'}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data['email']).first()
    
    if user and check_password_hash(user.password, data['password']):
        access_token = create_access_token(identity=user.id)
        return jsonify({
            'access_token': access_token,
            'user': {
                'id': user.id,
                'email': user.email,
                'name': user.name,
                'role': user.role
            }
        })
    
    return jsonify({'error': 'Invalid credentials'}), 401

# Product routes
@app.route('/api/products', methods=['GET'])
def get_products():
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    search = request.args.get('search', '').strip()
    query = Product.query
    if search:
        terms = [t for t in search.split() if t]
        for term in terms:
            like_term = f"%{term.lower()}%"
            query = query.filter(
                or_(
                    cast(Product.id, String).ilike(like_term),
                    Product.name.ilike(like_term),
                    Product.description.ilike(like_term),
                    cast(Product.price, String).ilike(like_term),
                    cast(Product.stock, String).ilike(like_term),
                    cast(Product.category_id, String).ilike(like_term),
                    Product.image_url.ilike(like_term)
                )
            )
    total = query.count()
    products = query.offset((page - 1) * per_page).limit(per_page).all()
    print(f"==> [Diagnostics] /api/products called. Returning {len(products)} products (page {page}, per_page {per_page}, total {total}).")
    for p in products:
        print(f"    Product: id={p.id}, name={p.name}, image_url={p.image_url}")
    return jsonify({
        'items': [{
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'price': p.price,
            'stock': p.stock,
            'category_id': p.category_id,
            'image_url': p.image_url
        } for p in products],
        'total': total
    })

@app.route('/api/products', methods=['POST'])
def create_product():
    import traceback
    print("==> [Diagnostics] /api/products POST called")
    try:
        if request.content_type and request.content_type.startswith('multipart/form-data'):
            print(f"    Content-Type: {request.content_type}")
            print(f"    Form: {dict(request.form)}")
            print(f"    Files: {[f.filename for f in request.files.getlist('images')]}")
            form = request.form
            files = request.files.getlist('images')
            try:
                price = float(form.get('price')) if form.get('price') else 0
            except Exception as e:
                print(f"    Error parsing price: {form.get('price')}, {e}")
                return jsonify({'error': f'Invalid price: {form.get('price')}', 'details': str(e)}), 422
            try:
                stock = int(form.get('stock')) if form.get('stock') else 0
            except Exception as e:
                print(f"    Error parsing stock: {form.get('stock')}, {e}")
                return jsonify({'error': f'Invalid stock: {form.get('stock')}', 'details': str(e)}), 422
            try:
                category_id = int(form.get('category_id')) if form.get('category_id') else None
            except Exception as e:
                print(f"    Error parsing category_id: {form.get('category_id')}, {e}")
                return jsonify({'error': f'Invalid category_id: {form.get('category_id')}', 'details': str(e)}), 422
            product = Product(
                name=form.get('name'),
                description=form.get('description'),
                price=price,
                stock=stock,
                category_id=category_id
            )
            db.session.add(product)
            db.session.commit()
            image_urls = []
            first_image_url = None
            for idx, file in enumerate(files):
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    save_path = os.path.join(UPLOAD_FOLDER, f'{product.id}_{filename}')
                    file.save(save_path)
                    url = f'/static/uploads/{product.id}_{filename}'
                    img = ProductImage(product_id=product.id, image_url=url)
                    db.session.add(img)
                    image_urls.append(url)
                    if first_image_url is None:
                        first_image_url = url
            if first_image_url:
                product.image_url = first_image_url
                db.session.commit()
            else:
                db.session.commit()
            print(f"    Product created: id={product.id}, image_urls={image_urls}")
            return jsonify({'message': 'Product created successfully', 'id': product.id, 'image_urls': image_urls}), 201
        else:
            print(f"    Content-Type: {request.content_type}")
            data = request.get_json()
            print(f"    JSON: {data}")
            product = Product(
                name=data['name'],
                description=data['description'],
                price=data['price'],
                stock=data['stock'],
                category_id=data.get('category_id')
            )
            db.session.add(product)
            db.session.commit()
            print(f"    Product created: id={product.id}")
            return jsonify({'message': 'Product created successfully', 'id': product.id}), 201
    except Exception as e:
        print(f"    Exception: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500

@app.route('/api/products/<int:product_id>', methods=['PUT'])
@jwt_required()
def update_product(product_id):
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    if user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    product = Product.query.get_or_404(product_id)
    data = request.get_json()
    
    product.name = data.get('name', product.name)
    product.description = data.get('description', product.description)
    product.price = data.get('price', product.price)
    product.stock = data.get('stock', product.stock)
    product.category_id = data.get('category_id', product.category_id)
    
    db.session.commit()
    return jsonify({'message': 'Product updated successfully'})

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    return jsonify({'message': 'Product deleted successfully'})

@app.route('/api/products/bulk-update-prices', methods=['POST'])
def bulk_update_prices():
    data = request.get_json()
    percent = float(data.get('percent', 0))
    if percent == 0:
        return jsonify({'error': 'Percent must not be zero.'}), 400
    products = Product.query.all()
    for p in products:
        p.price = round(p.price * (1 + percent / 100), 2)
    db.session.commit()
    return jsonify({'message': f'Updated {len(products)} products.'})

def ensure_original_price():
    for p in Product.query.all():
        if p.original_price is None:
            p.original_price = p.price
    db.session.commit()

@app.route('/api/products/reset-prices', methods=['POST'])
def reset_prices():
    products = Product.query.all()
    for p in products:
        if p.original_price is not None:
            # Save to history
            if not p.price_change_history:
                p.price_change_history = []
            p.price_change_history.append({'old': p.price, 'new': p.original_price, 'ts': datetime.utcnow().isoformat()})
            p.price_change_history = p.price_change_history[-5:]
            p.price = p.original_price
    db.session.commit()
    return jsonify({'message': 'All prices reset to original sample values.'})

@app.route('/api/products/bulk-discount', methods=['POST'])
def bulk_discount():
    data = request.get_json()
    amount = float(data.get('amount', 0))
    if amount == 0:
        return jsonify({'error': 'Discount amount must not be zero.'}), 400
    products = Product.query.all()
    for p in products:
        new_price = max(0, round(p.price - amount, 2))
        if not p.price_change_history:
            p.price_change_history = []
        p.price_change_history.append({'old': p.price, 'new': new_price, 'ts': datetime.utcnow().isoformat()})
        p.price_change_history = p.price_change_history[-5:]
        p.price = new_price
    db.session.commit()
    return jsonify({'message': f'Applied discount to {len(products)} products.'})

@app.route('/api/products/price-history', methods=['GET'])
def price_history():
    products = Product.query.all()
    history = []
    for p in products:
        if p.price_change_history:
            for h in p.price_change_history:
                history.append({'product_id': p.id, 'name': p.name, **h})
    # Sort by timestamp desc, return last 5
    history = sorted(history, key=lambda x: x['ts'], reverse=True)[:5]
    return jsonify({'history': history})

@app.route('/api/products/undo-last-price-change', methods=['POST'])
def undo_last_price_change():
    products = Product.query.all()
    undone = 0
    for p in products:
        if p.price_change_history:
            last = p.price_change_history.pop()
            p.price = last['old']
            undone += 1
    db.session.commit()
    return jsonify({'message': f'Undid last price change for {undone} products.'})

# Order routes
@app.route('/api/orders', methods=['GET'])
def get_orders():
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    search = request.args.get('search', '').strip()
    query = Order.query
    if search:
        terms = [t for t in search.split() if t]
        for term in terms:
            like_term = f"%{term.lower()}%"
            query = query.filter(
                or_(
                    cast(Order.id, String).ilike(like_term),
                    cast(Order.user_id, String).ilike(like_term),
                    cast(Order.total, String).ilike(like_term),
                    Order.status.ilike(like_term),
                    cast(Order.created_at, String).ilike(like_term)
                )
            )
    total = query.count()
    orders = query.order_by(Order.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    print(f"==> [Diagnostics] /api/orders called (no auth). Returning {len(orders)} orders (page {page}, per_page {per_page}, total {total}).")
    for o in orders:
        print(f"    Order: id={o.id}, total={o.total}, status={o.status}, created_at={o.created_at}")
    return jsonify({
        'items': [{
            'id': o.id,
            'user_id': o.user_id,
            'total': o.total,
            'status': o.status,
            'created_at': o.created_at.isoformat()
        } for o in orders],
        'total': total
    })

@app.route('/api/orders', methods=['POST'])
@jwt_required()
def create_order():
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    order = Order(
        user_id=current_user_id,
        total=data['total'],
        status='pending'
    )
    
    db.session.add(order)
    db.session.commit()
    
    # Add order items
    for item in data['items']:
        order_item = OrderItem(
            order_id=order.id,
            product_id=item['product_id'],
            quantity=item['quantity'],
            price=item['price']
        )
        db.session.add(order_item)
        
        # Update product stock
        product = Product.query.get(item['product_id'])
        product.stock -= item['quantity']
    
    db.session.commit()
    
    return jsonify({'message': 'Order created successfully', 'order_id': order.id}), 201

@app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
@jwt_required()
def update_order_status(order_id):
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    if user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    order = Order.query.get_or_404(order_id)
    data = request.get_json()
    order.status = data['status']
    db.session.commit()
    
    return jsonify({'message': 'Order status updated successfully'})

# Category routes
@app.route('/api/categories', methods=['GET'])
def get_categories():
    categories = Category.query.all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'description': c.description
    } for c in categories])

@app.route('/api/categories', methods=['POST'])
@jwt_required()
def create_category():
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    if user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    category = Category(
        name=data['name'],
        description=data.get('description', '')
    )
    
    db.session.add(category)
    db.session.commit()
    
    return jsonify({'message': 'Category created successfully', 'id': category.id}), 201

# Dashboard analytics
@app.route('/api/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    # For demo: always return stats
    total_products = Product.query.count()
    total_orders = Order.query.count()
    total_users = User.query.filter_by(role='customer').count()
    total_revenue = db.session.query(db.func.sum(Order.total)).filter_by(status='paid').scalar() or 0
    print(f"==> [Diagnostics] /api/dashboard/stats called (no auth). Products: {total_products}, Orders: {total_orders}, Users: {total_users}, Revenue: {total_revenue}")
    return jsonify({
        'total_products': total_products,
        'total_orders': total_orders,
        'total_users': total_users,
        'total_revenue': total_revenue
    })

@app.route('/api/dashboard/last-orders', methods=['GET'])
def dashboard_last_orders():
    orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    result = []
    for o in orders:
        user = User.query.get(o.user_id)
        result.append({
            'id': o.id,
            'user': user.email if user else 'N/A',
            'total': o.total,
            'status': o.status,
            'created_at': o.created_at.isoformat() if o.created_at else ''
        })
    return jsonify({'orders': result})

@app.route('/api/dashboard/active-times', methods=['GET'])
def dashboard_active_times():
    # Group orders by hour of day
    orders = Order.query.all()
    hours = [o.created_at.hour for o in orders if o.created_at]
    counts = Counter(hours)
    # Return as list of {hour: int, count: int}
    result = [{'hour': h, 'count': counts.get(h, 0)} for h in range(24)]
    return jsonify({'active_times': result})

@app.route('/api/reports/products', methods=['GET'])
def report_products():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Products'
    ws.append(['ID', 'Name', 'Description', 'Price', 'Stock', 'Category', 'Image URL'])
    for p in Product.query.all():
        category = Category.query.get(p.category_id)
        ws.append([
            p.id, p.name, p.description, p.price, p.stock,
            category.name if category else '', p.image_url
        ])
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name='products_report.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/api/reports/orders', methods=['GET'])
def report_orders():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Orders'
    ws.append(['Order ID', 'User', 'Total', 'Status', 'Created At', 'Items'])
    for o in Order.query.order_by(Order.created_at.desc()).all():
        user = User.query.get(o.user_id)
        items = ', '.join([f"{item.product.name} x{item.quantity}" for item in o.items])
        ws.append([
            o.id, user.email if user else '', o.total, o.status,
            o.created_at.isoformat() if o.created_at else '', items
        ])
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name='orders_report.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def initialize_database():
    with app.app_context():
        print('==> [Diagnostics] Creating all tables if not exist...')
        db.create_all()
        ensure_original_price()

        # Only add sample data if the database is empty (no products, categories, or orders)
        if Product.query.count() == 0 and Category.query.count() == 0 and Order.query.count() == 0:
            print('==> [Diagnostics] Inserting sample data (admin, customer, categories, products, orders)...')
            # Create admin user
            admin = User(
                email='admin@example.com',
                password=generate_password_hash('admin123'),
                name='Admin User',
                role='admin'
            )
            db.session.add(admin)

            # Create sample customer user
            customer = User(
                email='customer@example.com',
                password=generate_password_hash('customer123'),
                name='Customer User',
                role='customer'
            )
            db.session.add(customer)

            # Create sample categories
            categories = [
                Category(name='Electronics', description='Electronic devices and gadgets'),
                Category(name='Clothing', description='Fashion and apparel'),
                Category(name='Books', description='Books and literature')
            ]
            for category in categories:
                db.session.add(category)
            db.session.commit()  # Commit to assign IDs

            # Create sample products
            products = [
                Product(name='iPhone 13', description='Latest iPhone model', price=999.99, stock=50, category_id=categories[0].id, image_url='https://images.pexels.com/photos/788946/pexels-photo-788946.jpeg?auto=compress&w=400'),
                Product(name='Samsung Galaxy S21', description='Android flagship phone', price=899.99, stock=30, category_id=categories[0].id, image_url='https://images.pexels.com/photos/404280/pexels-photo-404280.jpeg?auto=compress&w=400'),
                Product(name='Nike Air Max', description='Comfortable running shoes', price=129.99, stock=100, category_id=categories[1].id, image_url='https://images.pexels.com/photos/2529148/pexels-photo-2529148.jpeg?auto=compress&w=400'),
                Product(name='Python Programming Book', description='Learn Python programming', price=49.99, stock=200, category_id=categories[2].id, image_url='https://images.pexels.com/photos/590493/pexels-photo-590493.jpeg?auto=compress&w=400')
            ]
            for product in products:
                db.session.add(product)
            db.session.commit()  # Commit to assign product IDs

            # Create sample orders for the customer
            from datetime import datetime, timedelta
            order1 = Order(user_id=customer.id, total=1049.98, status='paid', created_at=datetime.utcnow() - timedelta(days=2))
            db.session.add(order1)
            db.session.commit()
            order1_items = [
                OrderItem(order_id=order1.id, product_id=products[0].id, quantity=1, price=999.99),
                OrderItem(order_id=order1.id, product_id=products[3].id, quantity=1, price=49.99)
            ]
            for item in order1_items:
                db.session.add(item)

            order2 = Order(user_id=customer.id, total=129.99, status='pending', created_at=datetime.utcnow() - timedelta(days=1))
            db.session.add(order2)
            db.session.commit()
            order2_items = [
                OrderItem(order_id=order2.id, product_id=products[2].id, quantity=1, price=129.99)
            ]
            for item in order2_items:
                db.session.add(item)

            db.session.commit()
            print('==> [Diagnostics] Sample data inserted.')

            # Add more demo products (at least 50 total, all with working images)
            extra_product_images = [
                'https://images.pexels.com/photos/276528/pexels-photo-276528.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/2983464/pexels-photo-2983464.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/461198/pexels-photo-461198.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/267394/pexels-photo-267394.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/325153/pexels-photo-325153.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/1092644/pexels-photo-1092644.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/845434/pexels-photo-845434.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/18105/pexels-photo.jpg?auto=compress&w=400',
                'https://images.pexels.com/photos/461382/pexels-photo-461382.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/267350/pexels-photo-267350.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/265087/pexels-photo-265087.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/265087/pexels-photo-265087.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/267394/pexels-photo-267394.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/845434/pexels-photo-845434.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/18105/pexels-photo.jpg?auto=compress&w=400',
                'https://images.pexels.com/photos/461382/pexels-photo-461382.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/267350/pexels-photo-267350.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/265087/pexels-photo-265087.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/325153/pexels-photo-325153.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/1092644/pexels-photo-1092644.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/2983464/pexels-photo-2983464.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/276528/pexels-photo-276528.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/461198/pexels-photo-461198.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/267394/pexels-photo-267394.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/325153/pexels-photo-325153.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/1092644/pexels-photo-1092644.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/845434/pexels-photo-845434.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/18105/pexels-photo.jpg?auto=compress&w=400',
                'https://images.pexels.com/photos/461382/pexels-photo-461382.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/267350/pexels-photo-267350.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/265087/pexels-photo-265087.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/265087/pexels-photo-265087.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/267394/pexels-photo-267394.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/845434/pexels-photo-845434.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/18105/pexels-photo.jpg?auto=compress&w=400',
                'https://images.pexels.com/photos/461382/pexels-photo-461382.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/267350/pexels-photo-267350.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/265087/pexels-photo-265087.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/325153/pexels-photo-325153.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/1092644/pexels-photo-1092644.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/2983464/pexels-photo-2983464.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/276528/pexels-photo-276528.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/461198/pexels-photo-461198.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/267394/pexels-photo-267394.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/325153/pexels-photo-325153.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/1092644/pexels-photo-1092644.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/845434/pexels-photo-845434.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/18105/pexels-photo.jpg?auto=compress&w=400',
                'https://images.pexels.com/photos/461382/pexels-photo-461382.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/267350/pexels-photo-267350.jpeg?auto=compress&w=400',
                'https://images.pexels.com/photos/265087/pexels-photo-265087.jpeg?auto=compress&w=400',
            ]
            for i in range(5, 55):
                products.append(Product(
                    name=f'Demo Product {i}',
                    description=f'Description for demo product {i}',
                    price=round(10 + i * 2.5, 2),
                    stock=100 + i,
                    category_id=categories[(i % 3)].id,
                    image_url=extra_product_images[i % len(extra_product_images)]
                ))
            db.session.add_all(products[4:])
            db.session.commit()

            # Add at least 50 more orders
            from random import randint, choice
            all_products = Product.query.all()
            for i in range(3, 53):
                order = Order(
                    user_id=customer.id,
                    total=0,
                    status=choice(['pending', 'paid', 'shipped', 'delivered']),
                    created_at=datetime.utcnow() - timedelta(days=randint(0, 30))
                )
                db.session.add(order)
                db.session.commit()
                num_items = randint(1, 4)
                order_total = 0
                used_products = set()
                for _ in range(num_items):
                    product = choice(all_products)
                    if product.id in used_products:
                        continue
                    used_products.add(product.id)
                    quantity = randint(1, 3)
                    order_item = OrderItem(
                        order_id=order.id,
                        product_id=product.id,
                        quantity=quantity,
                        price=product.price
                    )
                    db.session.add(order_item)
                    order_total += product.price * quantity
                order.total = order_total
                db.session.commit()
        else:
            print('==> [Diagnostics] Sample data NOT inserted (DB not empty).')

    print('==> [Diagnostics] Backend startup complete. Ready to serve requests.')

@app.before_first_request
def initialization():
    initialize_database()
    app.run(debug=True, host='0.0.0.0', port=5000)

if __name__ == '__main__':
    initialization()