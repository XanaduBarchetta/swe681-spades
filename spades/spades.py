import re
import logging

from flask import flash, redirect, url_for, request, render_template
from flask_login import current_user, LoginManager, login_required, login_user, logout_user

from spades.dbobjects import User, Game, GameStateEnum, DirectionsEnum, SuitEnum
from spades.exceptions import UserAlreadyExistsException, UserCanNotBidError, BadGameStateError, SpadesNotBrokenError, \
    NotFollowingLeadSuitError, CardNotInHandError
from . import app

USERNAME_REGEX = re.compile(r'^\w+$')
PASSWORD_REGEX = re.compile(r'^[-=+!@#$%^&*()\w]+$')
BID_REGEX = re.compile(r'^(\d|1[0-3])$')
CARD_REGEX = re.compile(r'^(0[2-9]|1[0-4])[SHCD]$')
GAME_ID_REGEX = re.compile(r'^[1-9]\d*$')

logger = logging.getLogger('spades')
hdlr = logging.FileHandler(app.config['LOGFILE'])
logger.addHandler(hdlr)

security = logging.getLogger('audit')
security.setLevel(logging.INFO)
security_formatter = logging.Formatter(
        '%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
shdlr = logging.FileHandler(app.config['AUDITLOGFILE'])
shdlr.setFormatter(security_formatter)
security.addHandler(shdlr)

login_manager = LoginManager()
login_manager.init_app(app)


@app.template_filter('translate_game_state')
def translate_game_state(state: GameStateEnum):
    if state == GameStateEnum.IN_PROGRESS:
        return "in progress"
    return state.value.lower()


@app.template_filter('partner_direction')
def partner_direction(direction: DirectionsEnum):
    return DirectionsEnum.get_partner_direction(direction).value


@app.template_filter('translate_suit')
def translate_suit(suit: SuitEnum):
    return SuitEnum.get_suit_word(suit).title()


@app.route('/', methods=["GET", "POST"])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # Validate input
        failed_validation = False
        if not isinstance(username, str) or not isinstance(password, str) or len(username) < 1 or len(password) < 1:
            flash('You must provide both a username and password.')
            security.info("User has not provided both a username and password")
            failed_validation = True
        if len(username) > 32:
            flash("Usernames can not be longer than 32 characters.")
            security.info("User %s has inputted a name longer than 32 characters.", username)
            failed_validation = True
        if not USERNAME_REGEX.match(username):
            flash("Usernames may only contain letters, numbers, and underscore.")
            security.info(
                "User %s has inputted a name which does not contain letters, numbers, and underscore.",
                username)
            failed_validation = True
        # Don't check password length here in case requirements have changed.
        # We don't want to lock out legacy users!
        if not PASSWORD_REGEX.match(password):
            flash("Passwords are limited to letters, numbers, and the following characters: -=+!@#$%^&*()_")
            security.info("User %s has inputted invalid password which does not meet -=+!@#$%^&*()_", username)
            failed_validation = True
        if failed_validation:
            security.info("There has been a failed validation.")
            return redirect(url_for('login'))

        user = User.get_user(username, password)
        if user is None:
            flash('The provided credentials do not match any registered user.')
            security.info("The provided credentials do not match any registered user for %s.", username)
            return redirect(url_for('login'))
        else:
            user.name = username
            login_user(user)
            security.info("Successful login for user %s.", username)
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
    security.info("Page not found reached. Error: %s", e)
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
            security.info("User has not provided both a username and password")
            failed_validation = True
        if len(username) > 32:
            flash("Usernames can not be longer than 32 characters.")
            security.info("Username was longer than 32 characters.")
            failed_validation = True
        if not USERNAME_REGEX.match(username):
            flash("Usernames may only contain letters, numbers, and underscore.")
            security.info("Username %s was not etters, numbers, or underscore.", username)
            failed_validation = True
        if len(password) < app.config['MIN_PASSWORD_LENGTH'] or len(password) > app.config['MAX_PASSWORD_LENGTH']:
            flash("Passwords must be no fewer than {min} and no greater than {max} characters.".format(
                min=app.config['MIN_PASSWORD_LENGTH'],
                max=app.config['MAX_PASSWORD_LENGTH']
            ))
            security.info("Password did not correct criteria.")
            failed_validation = True
        if not PASSWORD_REGEX.match(password):
            flash("Passwords are limited to letters, numbers, and the following characters: -=+!@#$%^&*()_")
            security.info("Password did not the following characterss: -=+!@#$%^&*()_.")
            failed_validation = True
        if failed_validation:
            return redirect(url_for('signup'))

        try:
            User.create_user(username, password)
        except UserAlreadyExistsException:
            flash("Username already exists. Please choose a different username.")
            security.info("Username %s already exists.", username)
            return redirect(url_for('signup'))
        else:
            flash("You may now login with your new username and password.")
            security.info("Successful creation of username: %s", username)
            return redirect(url_for('login'))
    elif request.method == 'GET':
        return render_template("signup.html")


@app.route('/joingame', methods=['GET'])
@login_required
def join_game():
    if current_user.get_active_game() is None:
        # Join a new/filling game
        Game.join_game(current_user.user_id)
    return redirect(url_for('game_home'))


@app.route('/game', methods=['GET'])
@login_required
def game_home():
    """
    Main endpoint for dealing with game interactions
    """
    game = current_user.get_active_game()
    if game is None:
        game = current_user.get_last_ended_game()
        if game is None:
            flash('If you want to join a game, click the Join button.')
            return redirect(url_for('home'))
        else:
            flash('These are the results from your most recent ended game.')
            return redirect(url_for('game_summary', game_id=game.game_id))
    response_data = {
        'game': game,
        'north_playername': User.get_username_by_id(game.player_north),
        'south_playername': User.get_username_by_id(game.player_south),
        'east_playername': User.get_username_by_id(game.player_east),
        'west_playername': User.get_username_by_id(game.player_west),
        'player_direction': DirectionsEnum.NORTH,  # Default to north, will check below
        'hand': None,
        'cards': {
            'spades': [],
            'hearts': [],
            'clubs': [],
            'diamonds': []
        },
        'trick': None,
        'tricks_taken': None,
        'enable_bidding': False,
    }
    if game.player_is_direction(current_user.user_id, DirectionsEnum.SOUTH):
        response_data['player_direction'] = DirectionsEnum.SOUTH
    if game.player_is_direction(current_user.user_id, DirectionsEnum.EAST):
        response_data['player_direction'] = DirectionsEnum.EAST
    if game.player_is_direction(current_user.user_id, DirectionsEnum.WEST):
        response_data['player_direction'] = DirectionsEnum.WEST
    if game.state == GameStateEnum.FILLING:
        # No need to fetch hand or trick data, as game hasn't started yet
        return render_template('game.html', **response_data)
    elif game.state == GameStateEnum.IN_PROGRESS:
        # Fetch current Hand data
        hand = game.get_latest_hand()
        response_data['hand'] = hand
        response_data['ns_score'], response_data['ew_score'] = hand.get_score_from_previous_hand()
        cards = hand.get_playable_cards_for_user(current_user.user_id)
        cards.sort(key=lambda x: x.card)
        for suit, letter in [('spades', 'S'), ('hearts', 'H'), ('clubs', 'C'), ('diamonds', 'D')]:
            response_data['cards'][suit] = [card for card in cards if card.card.endswith(letter)]
        if None not in [
            hand.north_bid,
            hand.south_bid,
            hand.east_bid,
            hand.west_bid
        ]:
            # All bids have been placed. Fetch trick data.
            response_data['trick'] = hand.get_latest_trick()
            response_data['next_play_direction'] = response_data['trick'].get_next_play_direction()
            response_data['tricks_taken'] = {key.value: value for key, value in hand.get_total_tricks_taken().items()}
        else:
            # Waiting on at least one bid
            response_data['enable_bidding'] = game.can_user_place_bid(current_user.user_id, hand)
        return render_template('game.html', **response_data)
    else:
        # Shouldn't arrive at this state. Log it.
        flash('An unknown error occurred. Please try again.')
        logger.error(
            'Game with id [{game_id}] in bad state while user [{username}] attempted to display game home.'.format(
                game_id=game.game_id,
                username=current_user.username
            )
        )
        return redirect(url_for('home'))


@app.route('/game/bid', methods=['POST'])
@login_required
def game_bid():
    """
    Endpoint for placing a bid
    """
    game = current_user.get_active_game()
    bid = request.form.get('bid', '')

    # Validate bid
    if not isinstance(bid, str):
        # Invalid input for bid, but no need to alert user
        return redirect(url_for('game_home'))
    bid = bid.strip()
    if not BID_REGEX.match(bid):
        flash('Your bid must be an integer bid from zero (0) to thirteen (13).')
        return redirect(url_for('game_home'))

    if game is None:
        flash('If you want to join a game, click the Join button.')
        return redirect(url_for('home'))
    else:
        hand = game.get_latest_hand()
        # Attempt to place the bid
        try:
            hand.place_bid(current_user.user_id, int(bid), game)
        except UserCanNotBidError:
            flash('Bidding is not available at this time for you.')
            return redirect(url_for('game_home'))
        except BadGameStateError:
            flash('An error occurred while trying to pace your bid. Please try again.')
            return redirect(url_for('game_home'))
        else:
            flash(f'Your bid of {bid} has been placed.')
            return redirect(url_for('game_home'))


@app.route('/game/play_card', methods=['POST'])
@login_required
def play_card():
    """
    Endpoint for playing a card
    """
    game = current_user.get_active_game()
    card = request.form.get('card', '')

    if game is None:
        flash('If you want to join a game, click the Join button.')
        return redirect(url_for('home'))
    else:
        # Validate card
        if not isinstance(card, str):
            # Invalid input for card, but no need to alert user
            return redirect(url_for('game_home'))
        card = card.strip()
        if not CARD_REGEX.match(card):
            flash('Invalid card format.')
            return redirect(url_for('game_home'))

        hand = game.get_latest_hand()
        trick = hand.get_latest_trick(with_for_update=True)
        # Attempt to play the card
        try:
            trick.play_card(current_user.user_id, card, game, hand)
        except CardNotInHandError:
            flash('The card \'{0}\' is not in your hand or has already been played.'
                  ' Please play a card from your hand.'.format(card))
            return redirect(url_for('game_home'))
        except SpadesNotBrokenError:
            flash('Spades have not yet been broken. Please choose a different suit.')
            return redirect(url_for('game_home'))
        except NotFollowingLeadSuitError:
            flash('You must follow the lead suit whenever possible. Please choose a card with the lead suit.')
            return redirect(url_for('game_home'))
        except BadGameStateError:
            flash('An error occurred while trying to play your card. Please try again.')
            return redirect(url_for('game_home'))
        else:
            flash(f'You played {card} successfully.')
            if trick.winner is not None:
                flash(f'{trick.winner.value} won the trick.')
                if trick.trick_number == 13 and game.state == GameStateEnum.IN_PROGRESS:
                    flash('A new hand has been dealt.')
                    return redirect(url_for('game_home'))
                elif game.state == GameStateEnum.COMPLETED:
                    if game.ns_win:
                        flash('North/South team won the game.')
                    else:
                        flash('East/West team won the game.')
                    # Redirect to game summary screen
                    redirect(url_for('game_summary', game_id=game.game_id))
            return redirect(url_for('game_home'))


@app.route('/users', methods=['GET'])
@login_required
def user_list():
    users = User.query.all()
    return render_template('user_list.html', users=users)


@app.route('/game/list', methods=['GET'])
@login_required
def game_list():
    games = Game.get_viewable_games()
    users = {user.user_id: user.username for user in User.query.all()}
    return render_template('game_list.html', games=games, users=users)


@app.route('/game/summary/<game_id>', methods=['GET'])
@login_required
def game_summary(game_id):
    if not GAME_ID_REGEX.match(game_id):
        flash('Malformed game_id.')
        return redirect(url_for('game_list'))
    game_id = int(game_id)
    game = Game.get_game_by_id(game_id)
    if game is None:
        flash('No such game exists.')
        return redirect(url_for('game_list'))
    if game.state not in [GameStateEnum.ABANDONED, GameStateEnum.FORFEITED, GameStateEnum.COMPLETED]:
        flash('There is no viewable game with that id.')
        return redirect(url_for('game_list'))
    hands = game.get_all_hands_and_tricks()
    users = {user.user_id: user.username for user in User.query.all()}
    return render_template('game_summary.html', game=game, hands=hands, users=users)
