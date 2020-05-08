import re
import logging

from flask import flash, redirect, url_for, request, render_template
from flask_login import current_user, LoginManager, login_required, login_user, logout_user

from spades.dbobjects import User, Game
from spades.exceptions import UserAlreadyExistsException
from . import app

USERNAME_REGEX = re.compile(r'^\w+$')
PASSWORD_REGEX = re.compile(r'^[-=+!@#$%^&*()\w]+$')

retries = 0
logger = logging.getLogger('spades')
hdlr = logging.FileHandler(app.config['LOGFILE'])
logger.addHandler(hdlr)
login_manager = LoginManager()
login_manager.init_app(app)


@app.route('/', methods=["GET", "POST"])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # Validate input
        failed_validation = False
        if not isinstance(username, str) or not isinstance(password, str) or len(username) < 1 or len(password) < 1:
            flash('You must provide both a username and password.')
            failed_validation = True
        if len(username) > 32:
            flash("Usernames can not be longer than 32 characters.")
            failed_validation = True
        if not USERNAME_REGEX.match(username):
            flash("Usernames may only contain letters, numbers, and underscore.")
            failed_validation = True
        # Don't check password length here in case requirements have changed.
        # We don't want to lock out legacy users!
        if not PASSWORD_REGEX.match(password):
            flash("Passwords are limited to letters, numbers, and the following characters: -=+!@#$%^&*()_")
            failed_validation = True
        if failed_validation:
            return redirect(url_for('login'))

        user = User.get_user(username, password)
        if user is None:
            flash('The provided credentials do not match any registered user.')
            return redirect(url_for('login'))
        else:
            user.name = username
            login_user(user)
            return redirect(url_for('home'))
    else:
        return render_template('login.html')


@app.route('/home')
@login_required
def home():
    data = {
        'name': current_user.username,
        'user_is_in_game': current_user.get_active_game() is not None
    }
    return render_template('home.html', **data)


# callback to reload the user object
@login_manager.user_loader
def load_user(userid):
    return User.query.get(userid)


# handle login failed
@app.errorhandler(401)
def page_not_found(e):
    return render_template('error.html'), 401


@app.route("/logout", methods=['GET'])
@login_required
def logout():
    logger.info(request.method)
    logout_user()
    return redirect(url_for('login'))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    logger.info(request.method)
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # Validate input
        failed_validation = False
        if not isinstance(username, str) or not isinstance(password, str) or len(username) < 1 or len(password) < 1:
            flash('You must provide both a username and password.')
            failed_validation = True
        if len(username) > 32:
            flash("Usernames can not be longer than 32 characters.")
            failed_validation = True
        if not USERNAME_REGEX.match(username):
            flash("Usernames may only contain letters, numbers, and underscore.")
            failed_validation = True
        if len(password) < app.config['MIN_PASSWORD_LENGTH'] or len(password) > app.config['MAX_PASSWORD_LENGTH']:
            flash("Passwords must be no fewer than {min} and no greater than {max} characters.".format(
                min=app.config['MIN_PASSWORD_LENGTH'],
                max=app.config['MAX_PASSWORD_LENGTH']
            ))
            failed_validation = True
        if not PASSWORD_REGEX.match(password):
            flash("Passwords are limited to letters, numbers, and the following characters: -=+!@#$%^&*()_")
            failed_validation = True
        if failed_validation:
            return redirect(url_for('signup'))

        try:
            User.create_user(username, password)
        except UserAlreadyExistsException:
            flash("Username already exists. Please choose a different username.")
            return redirect(url_for('signup'))
        else:
            flash("You may now login with your new username and password.")
            return redirect(url_for('login'))
    elif request.method == 'GET':
        return render_template("signup.html")


@app.route('/joingame', methods=['GET'])
@login_required
def join_game():
    if current_user.get_active_game() is None:
        # Join a new/filling game
        Game.join_game(current_user.user_id)
    return redirect(url_for('game'))
