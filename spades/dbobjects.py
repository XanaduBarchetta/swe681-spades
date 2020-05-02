import enum
import logging

from flask_sqlalchemy import SQLAlchemy

from . import app


logger = logging.getLogger('spades_db')
hdlr = logging.FileHandler('../spades_db.log')
logger.addHandler(hdlr)

# database engine
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://{user}:{password}@{host}:{port}/{dbname}'.format(
    user=app.config['DB_USERNAME'],
    password=app.config['DB_PASSWORD'],
    host=app.config['DB_HOST'],
    port=app.config['DB_PORT'],
    dbname=app.config['DB_PORT']
)
db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = 'User'

    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String)
    password = db.Column(db.String)
    wins = db.Column(db.Integer)
    losses = db.Column(db.Integer)


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
    state = db.Column(db.Enum(GameStateEnum))
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
    spades_broken = db.Column(db.Boolean)
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
    played = db.Column(db.Boolean)

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
