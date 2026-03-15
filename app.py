import os
from datetime import datetime
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Use /app/data/app.db in production (Docker), or local path in dev
db_path = os.environ.get('DB_PATH', os.path.join(basedir, 'app.db'))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


def calc_bmi(weight, height_cm):
    if not weight or not height_cm or height_cm == 0:
        return None
    h_m = height_cm / 100.0
    return round(weight / (h_m ** 2), 1)


def bmi_category(bmi):
    if bmi is None:
        return 'Unknown'
    if bmi < 18.5:
        return 'Underweight'
    elif bmi < 25.0:
        return 'Normal'
    elif bmi < 30.0:
        return 'Overweight'
    else:
        return 'Obese'


def calc_bmr(weight, height_cm, age, gender):
    """Mifflin-St Jeor Equation"""
    if not weight or not height_cm or not age:
        return 1500  # safe default
    base = (10 * weight) + (6.25 * height_cm) - (5 * age)
    if gender == 'Female':
        return base - 161
    return base + 5  # Male default


ACTIVITY_MULTIPLIERS = {
    'Sedentary': 1.2,
    'Lightly Active': 1.375,
    'Moderately Active': 1.55,
    'Very Active': 1.725,
    'Extra Active': 1.9
}

GOAL_ADJUSTMENTS = {
    'Weight Loss': -500,
    'Maintenance': 0,
    'Muscle Gain': 500
}


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer, default=25)
    gender = db.Column(db.String(10), default='Male')
    weight = db.Column(db.Float, default=70.0)
    height = db.Column(db.Float, default=170.0)
    fitness_goal = db.Column(db.String(50), default='Maintenance')
    activity_level = db.Column(db.String(50), default='Moderately Active')
    body_type = db.Column(db.String(50), default='Mesomorph')
    is_active = db.Column(db.Boolean, default=True)
    meals = db.relationship('Meal', backref='user', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        bmi = calc_bmi(self.weight, self.height)
        return {
            'id': self.id,
            'username': self.username,
            'name': self.name,
            'age': self.age,
            'gender': self.gender,
            'weight': self.weight,
            'height': self.height,
            'fitness_goal': self.fitness_goal,
            'activity_level': self.activity_level,
            'body_type': self.body_type,
            'is_active': self.is_active,
            'bmi': bmi,
            'bmi_category': bmi_category(bmi)
        }


class Meal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    meal_name = db.Column(db.String(100), nullable=False)
    calories = db.Column(db.Integer, nullable=False)
    protein = db.Column(db.Float, nullable=False)
    carbs = db.Column(db.Float, nullable=False)
    fats = db.Column(db.Float, nullable=False)
    date_logged = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'meal_name': self.meal_name,
            'calories': self.calories,
            'protein': self.protein,
            'carbs': self.carbs,
            'fats': self.fats,
            'date_logged': self.date_logged.isoformat()
        }


with app.app_context():
    db.create_all()


@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    if not username:
        return jsonify({'error': 'Username is required'}), 400
    user = User.query.filter_by(username=username).first()
    if not user:
        user = User(username=username, name=username)
        db.session.add(user)
        db.session.commit()
    return jsonify({'message': 'Logged in successfully', 'user': user.to_dict()}), 200


@app.route('/api/users', methods=['GET'])
def get_users():
    return jsonify([u.to_dict() for u in User.query.all()]), 200


@app.route('/api/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    return jsonify(User.query.get_or_404(user_id).to_dict()), 200


@app.route('/api/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.json
    user.name = data.get('name', user.name)
    user.age = data.get('age', user.age)
    user.gender = data.get('gender', user.gender)
    user.weight = data.get('weight', user.weight)
    user.height = data.get('height', user.height)
    user.fitness_goal = data.get('fitness_goal', user.fitness_goal)
    user.activity_level = data.get('activity_level', user.activity_level)
    user.body_type = data.get('body_type', user.body_type)
    db.session.commit()
    return jsonify(user.to_dict()), 200


@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return jsonify({'message': 'User deleted'}), 200


@app.route('/api/meals', methods=['POST'])
def create_meal():
    data = request.json
    if not all([data.get('user_id'), data.get('meal_name'),
                data.get('calories') is not None, data.get('protein') is not None,
                data.get('carbs') is not None, data.get('fats') is not None]):
        return jsonify({'error': 'Missing required fields'}), 400
    meal = Meal(
        user_id=data['user_id'], meal_name=data['meal_name'],
        calories=data['calories'], protein=data['protein'],
        carbs=data['carbs'], fats=data['fats']
    )
    db.session.add(meal)
    db.session.commit()
    return jsonify(meal.to_dict()), 201


@app.route('/api/meals', methods=['GET'])
def get_all_meals():
    return jsonify([m.to_dict() for m in Meal.query.all()]), 200


@app.route('/api/meals/user/<int:user_id>', methods=['GET'])
def get_user_meals(user_id):
    meals = Meal.query.filter_by(user_id=user_id).order_by(Meal.date_logged.desc()).all()
    return jsonify([m.to_dict() for m in meals]), 200


@app.route('/api/meals/<int:meal_id>', methods=['PUT'])
def update_meal(meal_id):
    meal = Meal.query.get_or_404(meal_id)
    data = request.json
    meal.meal_name = data.get('meal_name', meal.meal_name)
    meal.calories = data.get('calories', meal.calories)
    meal.protein = data.get('protein', meal.protein)
    meal.carbs = data.get('carbs', meal.carbs)
    meal.fats = data.get('fats', meal.fats)
    db.session.commit()
    return jsonify(meal.to_dict()), 200


@app.route('/api/meals/<int:meal_id>', methods=['DELETE'])
def delete_meal(meal_id):
    meal = Meal.query.get_or_404(meal_id)
    db.session.delete(meal)
    db.session.commit()
    return jsonify({'message': 'Meal deleted'}), 200


@app.route('/api/dashboard/<int:user_id>', methods=['GET'])
def get_dashboard(user_id):
    user = User.query.get_or_404(user_id)
    meals = Meal.query.filter_by(user_id=user_id).all()

    total_calories = sum(m.calories for m in meals)
    total_protein = sum(m.protein for m in meals)
    total_carbs = sum(m.carbs for m in meals)
    total_fats = sum(m.fats for m in meals)

    bmi = calc_bmi(user.weight, user.height)
    bmr = calc_bmr(user.weight, user.height, user.age, user.gender)
    tdee = round(bmr * ACTIVITY_MULTIPLIERS.get(user.activity_level, 1.2))
    goal_adj = GOAL_ADJUSTMENTS.get(user.fitness_goal, 0)
    target_calories = tdee + goal_adj

    balance = total_calories - target_calories
    if abs(balance) <= 50:
        status = 'On Target'
        rec = 'You are right on target! Great work maintaining your daily intake.'
    elif balance < 0:
        status = 'Deficit'
        rec = f'You are in a {abs(balance)} kcal deficit.'
        if user.fitness_goal == 'Weight Loss':
            rec += ' This is excellent — keep it up for steady fat loss! 🔥'
        elif user.fitness_goal == 'Muscle Gain':
            rec += ' Consider eating more to fuel muscle growth. 💪'
        else:
            rec += ' Try to eat a bit more to meet your maintenance goal.'
    else:
        status = 'Surplus'
        rec = f'You are in a {balance} kcal surplus.'
        if user.fitness_goal == 'Muscle Gain':
            rec += ' Great for muscle building! Just keep protein high. 💪'
        elif user.fitness_goal == 'Weight Loss':
            rec += ' You may want to reduce portions to stay on track. 🥗'
        else:
            rec += ' Slightly over for today — balance it out tomorrow.'

    return jsonify({
        'user': user.to_dict(),
        'nutrition': {
            'total_calories': total_calories,
            'total_protein': round(total_protein, 1),
            'total_carbs': round(total_carbs, 1),
            'total_fats': round(total_fats, 1),
            'meal_count': len(meals),
            'bmr': round(bmr),
            'tdee': tdee,
            'target_calories': target_calories,
            'calorie_balance': balance,
            'balance_status': status,
            'recommendation': rec,
            'bmi': bmi,
            'bmi_category': bmi_category(bmi)
        }
    }), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=port)
