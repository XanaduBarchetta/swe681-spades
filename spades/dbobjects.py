import bcrypt
import enum
import logging

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound

from . import app


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

    @classmethod
    def get_user(cls, username: str, password: str):
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

    @classmethod
    def create_user(cls, username: str, password: str):
        hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        new_user = User(
            username=username,
            password=hashed_pw
        )
        # TODO: try/except block for user already exists
        db.session.add(new_user)
        db.session.commit()
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
    create_date = db.Column(db.DateTime)
    state = db.Column(db.Enum(GameStateEnum), default='FILLING')
    ns_win = db.Column(db.Boolean)


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
    last_play = db.Column(db.DateTime)

    __table_args__ = (
        # Enforce composite Foreign Key
        db.ForeignKeyConstraint([game_id, hand_number],
                                [Hand.game_id, Hand.hand_number]),
    )
