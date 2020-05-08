import bcrypt
import enum
import logging
from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound

from . import app
from .exceptions import UserAlreadyExistsException
from .utils import get_shuffled_deck

logger = logging.getLogger('spades_db')
hdlr = logging.FileHandler('../spades_db.log')
logger.addHandler(hdlr)

# database engine
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqldb://{user}:{password}@{host}:{port}/{dbname}'.format(
    user=app.config['DB_USERNAME'],
    password=app.config['DB_PASSWORD'],
    host=app.config['DB_HOST'],
    port=app.config['DB_PORT'],
    dbname=app.config['DB_NAME']
)
db = SQLAlchemy(app)


class User(db.Model, UserMixin):
    __tablename__ = 'User'

    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String)
    password = db.Column(db.Binary)
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)

    def get_id(self):
        """
        Required for flask_login
        :return: The user_id of the User
        """
        return self.user_id

    def get_active_game(self):
        """
        Gets the active game for this user
        :return: game_id of active game for this user, or None if user is not in an active game
        """
        try:
            game = db.session.query(Game).filter(
                Game.state.in_([GameStateEnum.FILLING, GameStateEnum.IN_PROGRESS]),
                or_(
                    Game.player_north == self.user_id,
                    Game.player_south == self.user_id,
                    Game.player_east == self.user_id,
                    Game.player_west == self.user_id
                )
            ).one()
        except NoResultFound:
            return None
        except MultipleResultsFound:
            # This should be impossible, since user can only be in one game at a time, but catching just in case
            logger.error("Database in unexpected state. User [{}] in two active games at once.".format(self.username))
            return None
        else:
            return game

    @staticmethod
    def get_user(username: str, password: str):
        """
        :param username: User-provided username
        :param password: User-provided password (not hashed or salted)
        :return: User object matching supplied credentials, otherwise None
        """
        try:
            user = db.session.query(User).filter(
                User.username == username
            ).one()
        except NoResultFound:
            return None
        except MultipleResultsFound:
            # This should be impossible, since `username` column has Unique Index, but catching just in case
            logger.error("Database in unexpected state. Two results found for username [{}]".format(username))
            return None
        else:
            # Check password
            if bcrypt.checkpw(password.encode('utf-8'), user.password):
                return user
            else:
                # Failed login attempt
                # TODO: Handle retries here
                return None

    @staticmethod
    def create_user(username: str, password: str):
        hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        new_user = User(
            username=username,
            password=hashed_pw
        )
        try:
            db.session.add(new_user)
            db.session.commit()
        except IntegrityError:
            raise UserAlreadyExistsException()
        else:
            return new_user


class GameStateEnum(enum.Enum):
    FILLING = 'FILLING'
    IN_PROGRESS = 'IN_PROGRESS'
    ABANDONED = 'ABANDONED'
    FORFEITED = 'FORFEITED'
    COMPLETED = 'COMPLETED'


class Game(db.Model):
    __tablename__ = 'Game'

    game_id = db.Column(db.Integer, primary_key=True)
    player_north = db.Column(db.Integer, db.ForeignKey('User.user_id'))
    player_south = db.Column(db.Integer, db.ForeignKey('User.user_id'))
    player_east = db.Column(db.Integer, db.ForeignKey('User.user_id'))
    player_west = db.Column(db.Integer, db.ForeignKey('User.user_id'))
    last_activity = db.Column(db.DateTime)
    state = db.Column(db.Enum(GameStateEnum), default='FILLING')
    ns_win = db.Column(db.Boolean)

    @staticmethod
    def join_game(user_id: int):
        """
        Joins a user to an existing game or creates a new one.
        Positions are filled starting with North and then clockwise.
        If the West position is filled, then the game is initialized.
        :param user_id: The user_id of the User joining a game
        """
        game = db.session.query(Game).filter(
            Game.state == GameStateEnum.FILLING
        ).with_for_update().first()
        if game is None:
            # Create a new game
            game = Game(
                player_north=user_id,
                last_activity=datetime.utcnow()
            )
            db.session.add(game)
            db.session.commit()
        else:
            # Join the user to the existing game
            if game.player_south is None:
                game.player_south = user_id
                game.last_activity = datetime.utcnow()
                db.session.commit()
            elif game.player_east is None:
                game.player_east = user_id
                game.last_activity = datetime.utcnow()
                db.session.commit()
            elif game.player_west is None:
                game.player_west = user_id

                # Start the game
                game.state = GameStateEnum.IN_PROGRESS

                # Create the first hand
                hand = Hand(
                    game_id=game.game_id,
                    hand_number=1,
                    dealer=DirectionsEnum.NORTH
                )
                db.session.add(hand)
                db.session.flush()  # Required so that HardCard inserts can reference the hand_number

                hand.deal_cards(game)
                game.last_activity = datetime.utcnow()
                db.session.commit()


class DirectionsEnum(enum.Enum):
    NORTH = 'NORTH'
    SOUTH = 'SOUTH'
    EAST = 'EAST'
    WEST = 'WEST'


class Hand(db.Model):
    __tablename__ = 'Hand'

    game_id = db.Column(db.Integer, db.ForeignKey('Game.game_id'), primary_key=True)
    hand_number = db.Column(db.Integer, primary_key=True)
    dealer = db.Column(db.Enum(DirectionsEnum))
    north_bid = db.Column(db.Integer)
    south_bid = db.Column(db.Integer)
    east_bid = db.Column(db.Integer)
    west_bid = db.Column(db.Integer)
    spades_broken = db.Column(db.Boolean, default=False)
    ns_bags_at_end = db.Column(db.Integer)
    ew_bags_at_end = db.Column(db.Integer)
    ns_score_after_bags = db.Column(db.Integer)
    ew_score_after_bags = db.Column(db.Integer)

    def deal_cards(self, game: Game):
        """
        Shuffle a deck and deal cards by populating the HandCards table.
        Initializes the first trick of a Hand.

        NOTE: DOES NOT COMMIT CHANGES. MAKE SURE PARENT FUNCTION COMMITS CHANGES.

        :param game: the Game object for this hand.
        """
        deck = get_shuffled_deck()
        for card in deck[:13]:
            db.session.add(HandCard(
                game_id=game.game_id,
                hand_number=self.hand_number,
                user_id=game.player_north,
                card=card
            ))
        for card in deck[13:26]:
            db.session.add(HandCard(
                game_id=game.game_id,
                hand_number=self.hand_number,
                user_id=game.player_south,
                card=card
            ))
        for card in deck[26:39]:
            db.session.add(HandCard(
                game_id=game.game_id,
                hand_number=self.hand_number,
                user_id=game.player_east,
                card=card
            ))
        for card in deck[39:52]:
            db.session.add(HandCard(
                game_id=game.game_id,
                hand_number=self.hand_number,
                user_id=game.player_west,
                card=card
            ))

        # Initialize first Trick
        lead_player = DirectionsEnum.NORTH
        if self.dealer == DirectionsEnum.NORTH:
            lead_player = DirectionsEnum.EAST
        elif self.dealer == DirectionsEnum.EAST:
            lead_player = DirectionsEnum.SOUTH
        elif self.dealer == DirectionsEnum.SOUTH:
            lead_player = DirectionsEnum.WEST
        db.session.add(Trick(
            game_id=game.game_id,
            hand_number=self.hand_number,
            trick_number=1,
            lead_player=lead_player,
        ))


class HandCard(db.Model):
    __tablename__ = 'HandCard'

    game_id = db.Column(db.Integer, primary_key=True)
    hand_number = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('User.user_id'), primary_key=True)
    card = db.Column(db.String, primary_key=True)
    played = db.Column(db.Boolean, default=False)

    __table_args__ = (
        # Enforce composite Foreign Key
        db.ForeignKeyConstraint([game_id, hand_number],
                                [Hand.game_id, Hand.hand_number]),
    )


class Trick(db.Model):
    __tablename__ = 'Trick'

    game_id = db.Column(db.Integer, primary_key=True)
    hand_number = db.Column(db.Integer, primary_key=True)
    trick_number = db.Column(db.Integer, primary_key=True)
    lead_player = db.Column(db.Enum(DirectionsEnum))
    north_play = db.Column(db.String)
    south_play = db.Column(db.String)
    east_play = db.Column(db.String)
    west_play = db.Column(db.String)
    winner = db.Column(db.Enum(DirectionsEnum))

    __table_args__ = (
        # Enforce composite Foreign Key
        db.ForeignKeyConstraint([game_id, hand_number],
                                [Hand.game_id, Hand.hand_number]),
    )
