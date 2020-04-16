import bcrypt
from getpass import getpass
from pathlib import Path
from passlib.hash import sha256_crypt
from flask import Flask, Response, flash, redirect, url_for, request, render_template, session, abort
from flask_login import LoginManager, UserMixin, \
									login_required, login_user, logout_user, current_user


app = Flask(__name__)
login_manager = LoginManager()
login_manager.init_app(app)

# config
app.config.update(
    DEBUG = True,
    EXPLAIN_TEMPLATE_LOADING = True,
    SECRET_KEY = b'_5#y2L"F4Q8z\n\xec]/'
)

@app.route('/')
def hello_world():
	return render_template('login.html')

@app.route('/', methods=["GET", "POST"])
def my_form_post():
	if request.method == 'POST':
		username = request.form['username']
		password = request.form['password']

		if (__verifyUser(username, password)):
			user = User(3)
			user.name = username
			login_user(user)
			flash('Logged in successfully.')
			return redirect(url_for('home', name=user.name))
		else:
			return abort(401)

@app.route('/home')
@app.route('/home/<name>')
def home(name=None):
	return render_template('home.html', name=name)

# callback to reload the user object
@login_manager.user_loader
def load_user(userid):
    return User(userid)

# handle login failed
@app.errorhandler(401)
def page_not_found(e):
    return render_template('error.html'), 401

@app.route("/logout", methods=['GET', 'POST'])
@login_required
def logout():
    print(request.method)
    logout_user()
    return redirect(url_for('hello_world'))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    print(request.method)
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if (__verifyExistingUser(username) == False):
            print("User already exists.")
            return abort(401)
        __registerUser(username, password)
        return redirect(url_for('hello_world'))
    elif request.method == 'GET':
        return render_template("signup.html")


def __verifyUser(username, password):
	users = __getUsers()
	if (username in users):
		return sha256_crypt.verify(password, users[username])
	else:
		return False

def __getUsers():
	users = { }
	with open("database.txt") as f:
		for line in f:
			(key, val) = line.split()
			users[key] = val
	return users

def __verifyExistingUser(username):
    users = __getUsers()
    return username not in users

def __registerUser(username, password):
    hashedPassword = sha256_crypt.encrypt(password)

    # TODO Point to database instead of a text file
    with open("database.txt", "a") as file:
        file.write(username + " " + hashedPassword + "\n")

# silly user model
class User(UserMixin):
    def __init__(self, id):
        self.id = id
        self.name = "user" + str(id)
        self.password = self.name + "_secret"

    def __repr__(self):
        return "%d/%s/%s" % (self.id, self.name, self.password)