from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, ForeignKeyConstraint, Integer, String
from sqlalchemy.ext.declarative import declarative_base
import enum


Base = declarative_base()


class User(Base):
    __tablename__ = 'User'

    user_id = Column(Integer, primary_key=True)
    username = Column(String)
    password = Column(String)
    wins = Column(Integer)
    losses = Column(Integer)


class GameStateEnum(enum.Enum):
    FILLING = 'FILLING'
    IN_PROGRESS = 'IN_PROGRESS'
    ABANDONED = 'ABANDONED'
    FORFEITED = 'FORFEITED'
    COMPLETED = 'COMPLETED'


class Game(Base):
    __tablename__ = 'Game'

    game_id = Column(Integer, primary_key=True)
    player_north = Column(Integer, ForeignKey('User.user_id'))
    player_south = Column(Integer, ForeignKey('User.user_id'))
    player_east = Column(Integer, ForeignKey('User.user_id'))
    player_west = Column(Integer, ForeignKey('User.user_id'))
    create_date = Column(DateTime)
    state = Column(Enum(GameStateEnum))
    ns_win = Column(Boolean)


class DirectionsEnum(enum.Enum):
    NORTH = 'NORTH'
    SOUTH = 'SOUTH'
    EAST = 'EAST'
    WEST = 'WEST'


class Hand(Base):
    __tablename__ = 'Hand'

    game_id = Column(Integer, ForeignKey('Game.game_id'), primary_key=True)
    hand_number = Column(Integer, primary_key=True)
    dealer = Column(Enum(DirectionsEnum))
    north_bid = Column(Integer)
    south_bid = Column(Integer)
    east_bid = Column(Integer)
    west_bid = Column(Integer)
    spades_broken = Column(Boolean)
    ns_bags_at_end = Column(Integer)
    ew_bags_at_end = Column(Integer)
    ns_score_after_bags = Column(Integer)
    ew_score_after_bags = Column(Integer)


class HandCard(Base):
    __tablename__ = 'HandCard'

    game_id = Column(Integer, primary_key=True)
    hand_number = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('User.user_id'), primary_key=True)
    card = Column(String, primary_key=True)
    played = Column(Boolean)

    __table_args__ = (
        # Enforce composite Foreign Key
        ForeignKeyConstraint([game_id, hand_number],
                             [Hand.game_id, Hand.hand_number])
    )


class Trick(Base):
    __tablename__ = 'Trick'

    game_id = Column(Integer, primary_key=True)
    hand_number = Column(Integer, primary_key=True)
    trick_number = Column(Integer, primary_key=True)
    lead_player = Column(Enum(DirectionsEnum))
    north_play = Column(String)
    south_play = Column(String)
    east_play = Column(String)
    west_play = Column(String)
    winner = Column(Enum(DirectionsEnum))
    last_play = Column(DateTime)

    __table_args__ = (
        # Enforce composite Foreign Key
        ForeignKeyConstraint([game_id, hand_number],
                             [Hand.game_id, Hand.hand_number])
    )
