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
from .exceptions import UserAlreadyExistsException, InvalidDirectionError, UserCanNotBidError, BadGameStateError
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
            logger.error("Database in unexpected state. User [%s] in two active games at once.", self.username)
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
            logger.error("Database in unexpected state. Two results found for username [%s]", username)
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

    @staticmethod
    def get_username_by_id(user_id: int):
        """
        :param user_id: The user_id on which to search
        :return: The username of the matching user, or None if no users match
        """
        if user_id is None:
            return None
        return db.session.query(User.username).filter(
            User.user_id == user_id
        ).scalar()


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

    def player_is_direction(self, user_id: int, direction: 'DirectionsEnum'):
        """
        :param user_id: The user_id to check
        :param direction: The direction to check
        :return: True if the provided user_id matched the provided direction, False otherwise
        """
        if direction == DirectionsEnum.NORTH and self.player_north == user_id:
            return True
        if direction == DirectionsEnum.SOUTH and self.player_south == user_id:
            return True
        if direction == DirectionsEnum.EAST and self.player_east == user_id:
            return True
        if direction == DirectionsEnum.WEST and self.player_west == user_id:
            return True
        return False

    def get_latest_hand(self):
        """
        :return: The most recent Hand for this game, or None if this game has no hands yet
        """
        hand_number = db.session.query(
            func.max(Hand.hand_number)
        ).filter(
            Hand.game_id == self.game_id
        ).scalar()
        if hand_number is None:
            return None
        else:
            return db.session.query(Hand).filter(
                Hand.game_id == self.game_id,
                Hand.hand_number == hand_number
            ).one()

    def can_user_place_bid(self, user_id: int, hand: 'Hand'):
        next_dir = hand.get_next_required_bid_direction()
        if next_dir is None:
            return False
        if self.player_is_direction(user_id, next_dir):
            return True
        return False

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

    @classmethod
    def get_next_clockwise(cls, direction: 'DirectionsEnum'):
        if direction == cls.NORTH:
            return cls.EAST
        if direction == cls.EAST:
            return cls.SOUTH
        if direction == cls.SOUTH:
            return cls.WEST
        if direction == cls.WEST:
            return cls.NORTH
        raise InvalidDirectionError(f'Received invalid direction [{direction}]')

    @classmethod
    def get_partner_direction(cls, direction: 'DirectionsEnum'):
        if direction == cls.NORTH:
            return cls.SOUTH
        if direction == cls.SOUTH:
            return cls.NORTH
        if direction == cls.EAST:
            return cls.WEST
        if direction == cls.WEST:
            return cls.EAST
        raise InvalidDirectionError(f'Received invalid direction [{direction}]')


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

    def get_latest_trick(self):
        """
        :return: The most recent Trick for this Hand, or None if this Hand has no Tricks yet
        """
        trick_number = db.session.query(
            func.max(Trick.trick_number)
        ).filter(
            Trick.game_id == self.game_id,
            Trick.hand_number == self.hand_number
        ).scalar()
        if trick_number is None:
            return None
        else:
            return db.session.query(Trick).filter(
                Trick.game_id == self.game_id,
                Trick.hand_number == self.hand_number,
                Trick.trick_number == trick_number
            ).one()

    def get_playable_cards_for_user(self, user_id: int):
        return db.session.query(HandCard).filter(
            HandCard.game_id == self.game_id,
            HandCard.hand_number == self.hand_number,
            HandCard.user_id == user_id,
            HandCard.played.is_(False)
        ).all()

    def get_next_required_bid_direction(self):
        """
        :return: The direction of the next required bidder, or None if all bids have been placed for this hand
        """
        if self.north_bid is not None and self.east_bid is None:
            return DirectionsEnum.EAST
        if self.east_bid is not None and self.south_bid is None:
            return DirectionsEnum.SOUTH
        if self.south_bid is not None and self.west_bid is None:
            return DirectionsEnum.WEST
        if self.west_bid is not None and self.north_bid is None:
            return DirectionsEnum.NORTH
        # If we made it this far, either all bids have been placed or no bids have been placed
        if self.north_bid is None:
            # No bids have been made yet
            return DirectionsEnum.get_next_clockwise(self.dealer)
        # All bids have been made
        return None

    def place_bid(self, user_id: int, bid: int, game: Game):
        """
        Pace a bid for a given user
        :param user_id: The user attempting to bid
        :param bid: The bid the user is attempting to make
        :param game: The Game object (for convenience)
        :return: None
        :raise: UserCanNotBidError if it is not the user's turn to bid for the specified game
        :raise: BadGameStateError if the user is expected to be able to bid but no bid directions are acceptable
        """
        if not game.can_user_place_bid(user_id, self):
            raise UserCanNotBidError()
        bid_direction = self.get_next_required_bid_direction()
        # Locking objects for updating at the sqlalchemy layer is tricky here,
        # so check the value of self.{direction}_bid even in the if statements
        if bid_direction == DirectionsEnum.NORTH and self.north_bid is None:
            self.north_bid = bid
        elif bid_direction == DirectionsEnum.EAST and self.east_bid is None:
            self.east_bid = bid
        elif bid_direction == DirectionsEnum.SOUTH and self.south_bid is None:
            self.south_bid = bid
        elif bid_direction == DirectionsEnum.WEST and self.west_bid is None:
            self.west_bid = bid
        else:
            # Shouldn't arrive at this state, log error and raise exception
            # NOTE: possible to arrive at this state if two competing bids from same player are placed
            #       extremely close together.
            logger.error('Bad game state found while user [%s] bid on game [%s].', user_id, game.game_id)
            raise BadGameStateError()
        game.last_activity = datetime.utcnow()
        db.session.commit()

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
        db.session.add(Trick(
            game_id=game.game_id,
            hand_number=self.hand_number,
            trick_number=1,
            lead_player=DirectionsEnum.get_next_clockwise(self.dealer),
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
