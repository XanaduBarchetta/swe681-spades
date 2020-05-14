import enum
import logging
from datetime import datetime
from typing import Union, List

import bcrypt

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound

from spades import app
from spades.exceptions import UserAlreadyExistsException, InvalidDirectionError, UserCanNotBidError, \
    BadGameStateError, CardNotInHandError, SpadesNotBrokenError, NotFollowingLeadSuitError, InvalidSuitError, \
    NotPlayersTurnError
from spades.utils import get_shuffled_deck

logger = logging.getLogger('spades_db')
hdlr = logging.FileHandler(app.config['LOGFILE'])
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
        :return: Game of active game for this user, or None if user is not in an active game
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

    def get_last_ended_game(self):
        """
        Gets the last ended game for this user
        :return: Game of last ended game for this user, or None if user has no prior games
        """
        return db.session.query(Game).filter(
            Game.state.notin_([GameStateEnum.FILLING, GameStateEnum.IN_PROGRESS]),
            or_(
                Game.player_north == self.user_id,
                Game.player_south == self.user_id,
                Game.player_east == self.user_id,
                Game.player_west == self.user_id
            )
        ).order_by(Game.last_activity.desc()).first()

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

    def get_all_hands_and_tricks(self):
        hands = db.session.query(Hand).filter(
            Hand.game_id == self.game_id
        ).order_by(
            Hand.hand_number
        ).all()
        tricks = db.session.query(Trick).filter(
            Trick.game_id == self.game_id
        ).order_by(
            Trick.hand_number,
            Trick.trick_number
        ).all()
        return [
            {
                'hand': hand,
                'tricks': [trick for trick in tricks if trick.hand_number == hand.hand_number]
            } for hand in hands
        ]

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
    def get_game_by_id(game_id: int) -> Union['Game', None]:
        """
        Get a game by its id
        :param game_id: The game_id for which to search
        :return: the matching Game, or None if no results are found
        """
        try:
            return db.session.query(Game).filter(
                Game.game_id == game_id
            ).one()
        except (NoResultFound, MultipleResultsFound):
            return None

    @staticmethod
    def get_viewable_games() -> List['Game']:
        return db.session.query(Game).filter(
            Game.state.in_([
                GameStateEnum.COMPLETED,
                GameStateEnum.FORFEITED,
                GameStateEnum.ABANDONED
            ])
        ).order_by(
            Game.last_activity.desc()
        ).all()

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

    def get_latest_trick(self, with_for_update=False) -> Union['Trick', None]:
        """
        :param with_for_update: Indicates whether or not a lock should be held on the returned Trick
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
            query = db.session.query(Trick).filter(
                Trick.game_id == self.game_id,
                Trick.hand_number == self.hand_number,
                Trick.trick_number == trick_number
            )
            if with_for_update:
                query = query.with_for_update()
            return query.one()

    def get_playable_cards_for_user(self, user_id: int):
        return db.session.query(HandCard).filter(
            HandCard.game_id == self.game_id,
            HandCard.hand_number == self.hand_number,
            HandCard.user_id == user_id,
            HandCard.played.is_(False)
        ).all()

    def get_total_tricks_taken(self):
        tricks_summary = db.session.query(
            Trick.winner.label('direction'),
            func.count(Trick.winner).label('tricks_won')
        ).filter(
            Trick.game_id == self.game_id,
            Trick.hand_number == self.hand_number
        ).group_by(
            Trick.winner
        )
        tricks_taken = {
            DirectionsEnum.NORTH: 0,
            DirectionsEnum.SOUTH: 0,
            DirectionsEnum.EAST: 0,
            DirectionsEnum.WEST: 0,
        }
        for trick in tricks_summary:
            if trick[0] is not None:
                tricks_taken[trick[0]] = trick[1]
        return tricks_taken

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
        :raise UserCanNotBidError if it is not the user's turn to bid for the specified game
        :raise BadGameStateError if the user is expected to be able to bid but no bid directions are acceptable
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

    def get_score_from_previous_hand(self):
        if self.hand_number == 1:
            return 0, 0
        else:
            try:
                return db.session.query(
                    Hand.ns_score_after_bags,
                    Hand.ew_score_after_bags
                ).filter(
                    Hand.game_id == self.game_id,
                    Hand.hand_number == self.hand_number - 1
                ).one()
            except (NoResultFound, MultipleResultsFound):
                # Shouldn't arrive at this state
                logger.fatal(
                    'Missing hand with game [%s] hand_number [%s]',
                    self.game_id,
                    self.hand_number - 1
                )
                db.session.rollback()
                raise BadGameStateError()


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


class SuitEnum(enum.Enum):
    S = 'S'  # Spades
    H = 'H'  # Hearts
    C = 'C'  # Clubs
    D = 'D'  # Diamonds

    @classmethod
    def get_suit_word(cls, suit: 'SuitEnum'):
        if suit == SuitEnum.S:
            return 'spades'
        if suit == SuitEnum.H:
            return 'hearts'
        if suit == SuitEnum.C:
            return 'clubs'
        if suit == SuitEnum.D:
            return 'diamonds'
        raise InvalidSuitError(f'Received invalid suit [{suit}]')


class Trick(db.Model):
    __tablename__ = 'Trick'

    game_id = db.Column(db.Integer, primary_key=True)
    hand_number = db.Column(db.Integer, primary_key=True)
    trick_number = db.Column(db.Integer, primary_key=True)
    lead_player = db.Column(db.Enum(DirectionsEnum))
    lead_suit = db.Column(db.Enum(SuitEnum))
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

    def direction_has_played(self, direction: DirectionsEnum):
        """
        :param direction: The direction player to check
        :return: True if the player with the provided direction has played a card for this trick, False otherwise
        """
        if direction == DirectionsEnum.NORTH:
            return self.north_play is not None
        if direction == DirectionsEnum.EAST:
            return self.east_play is not None
        if direction == DirectionsEnum.SOUTH:
            return self.south_play is not None
        if direction == DirectionsEnum.WEST:
            return self.west_play is not None
        return False

    def get_next_play_direction(self):
        """
        Get the Direction of the next required play
        :return: DirectionsEnum member of the direction for next play, or None if the trick is over
        """
        if not self.direction_has_played(self.lead_player):
            return self.lead_player
        next_direction = DirectionsEnum.get_next_clockwise(self.lead_player)
        if not self.direction_has_played(next_direction):
            return next_direction
        next_direction = DirectionsEnum.get_next_clockwise(next_direction)
        if not self.direction_has_played(next_direction):
            return next_direction
        next_direction = DirectionsEnum.get_next_clockwise(next_direction)
        if not self.direction_has_played(next_direction):
            return next_direction
        # At this point, we've exhausted all four directions. The trick must be over.
        return None

    def play_card(self, user_id: int, card: str, game: Game, hand: Hand):
        """
        Plays a card for a given user

        NOTE: Make sure to rollback any session in the event of a raised exception, since we should be acting on a
              Trick object which has a lock.

        :param user_id: The user attempting to play the card
        :param card: The card the user is attempting to play
        :param game: The Game object for this Trick (for convenience)
        :param hand: The Hand object for this Trick (for convenience)
        :return: None
        :raise NotPlayersTurnError: if the user attempts to play when it is not their turn
        :raise CardNotInHandError: if the user tries to play a card not in their hand
        :raise SpadesNotBrokenError: if the user has cards other than spades to play and spades have not yet been broken
        :raise BadGameStateError: if duplicate cards found
        :raise BadGameStateError: if user is expected ot be able to play but play has already been made
        """
        if not game.player_is_direction(user_id, self.get_next_play_direction()):
            raise NotPlayersTurnError()
        try:
            # Acquire a lock on the card
            hand_card = db.session.query(HandCard).filter(
                HandCard.game_id == self.game_id,
                HandCard.hand_number == self.hand_number,
                HandCard.user_id == user_id,
                HandCard.card == card,
                HandCard.played.is_(False)
            ).with_for_update().one()
        except NoResultFound:
            db.session.rollback()  # Release the lock
            raise CardNotInHandError()
        except MultipleResultsFound:
            # This should be VERY impossible, log a critical error
            logger.critical(
                'Duplicate cards found in HandCard table for: game [%s] hand [%s] user [%s] card [%s]',
                self.game_id,
                self.hand_number,
                user_id,
                card
            )
            db.session.rollback()  # Release the lock
            raise BadGameStateError()
        else:
            # Check if this card is a legal move
            if game.player_is_direction(user_id, self.lead_player):
                # Can lead with any suit except spades, unless spades is broken
                if not hand.spades_broken and card.endswith('S'):
                    # Check to see if user only has spades in hand
                    if db.session.query(func.count(HandCard.card)).filter(
                            HandCard.game_id == self.game_id,
                            HandCard.hand_number == self.hand_number,
                            HandCard.user_id == user_id,
                            HandCard.card.notlike('%S'),
                            HandCard.played.is_(False)
                    ).scalar() != 0:
                        db.session.rollback()  # Release the lock
                        raise SpadesNotBrokenError()
            elif card[-1] != self.lead_suit.value:
                # Must follow the lead suit if possible
                if db.session.query(func.count(HandCard.card)).filter(
                        HandCard.game_id == self.game_id,
                        HandCard.hand_number == self.hand_number,
                        HandCard.user_id == user_id,
                        HandCard.card.like('%{0}'.format(self.lead_suit.value)),
                        HandCard.played.is_(False)
                ).scalar() != 0:
                    db.session.rollback()  # Release the lock
                    raise NotFollowingLeadSuitError()

            hand_card.played = True
            if game.player_is_direction(user_id, DirectionsEnum.NORTH) and self.north_play is None:
                self.north_play = card
            elif game.player_is_direction(user_id, DirectionsEnum.EAST) and self.east_play is None:
                self.east_play = card
            elif game.player_is_direction(user_id, DirectionsEnum.SOUTH) and self.south_play is None:
                self.south_play = card
            elif game.player_is_direction(user_id, DirectionsEnum.WEST) and self.west_play is None:
                self.west_play = card
            else:
                # Shouldn't arrive at this state, log error and raise exception
                # NOTE: might be possible to arrive at this state if two competing plays from same player are made
                #       extremely close together.
                logger.error(
                    'Bad game state found while user [%s] played card in game [%s] hand [%s] trick [%s]',
                    user_id,
                    self.game_id,
                    self.hand_number,
                    self.trick_number
                )
                db.session.rollback()  # Release the lock
                raise BadGameStateError()

            if not hand.spades_broken and card.endswith('S'):
                hand.spades_broken = True

            # Update the last_activity for the game so that it doesn't accidentally time out before following
            # calculations are made
            game.last_activity = datetime.utcnow()

            if game.player_is_direction(user_id, self.lead_player):
                self.lead_suit = card[-1]

            db.session.flush()
            trick_cards = [
                (DirectionsEnum.NORTH, self.north_play),
                (DirectionsEnum.EAST, self.east_play),
                (DirectionsEnum.SOUTH, self.south_play),
                (DirectionsEnum.WEST, self.west_play)
            ]
            if None not in [x[1] for x in trick_cards]:
                # The Trick has completed
                # Determine winner
                trick_cards.sort(key=lambda x: x[1])
                spade_cards = [(direction, card) for direction, card in trick_cards if card.endswith('S')]
                if spade_cards:
                    self.winner = spade_cards[-1][0]
                else:
                    # Get the winner from the lead suit
                    self.winner = [
                        (direction, card) for direction, card in trick_cards if card.endswith(self.lead_suit.value)
                    ][-1][0]

                if self.trick_number == 13:
                    # Resolve the hand
                    ns_score = 0
                    ew_score = 0
                    ns_bags = 0
                    ew_bags = 0
                    if self.hand_number != 1:
                        # Update scores and bags from last hand
                        try:
                            previous_hand = db.session.query(Hand).filter(
                                Hand.game_id == self.game_id,
                                Hand.hand_number == self.hand_number-1
                            ).one()
                        except (NoResultFound, MultipleResultsFound):
                            # Shouldn't arrive at this state
                            logger.fatal(
                                'Missing hand with game [%s] hand_number [%s]',
                                self.game_id,
                                self.hand_number-1
                            )
                            db.session.rollback()
                            raise BadGameStateError()
                        else:
                            ns_score = previous_hand.ns_score_after_bags
                            ew_score = previous_hand.ew_score_after_bags
                            ns_bags = previous_hand.ns_bags_at_end
                            ew_bags = previous_hand.ew_bags_at_end

                    tricks_taken = hand.get_total_tricks_taken()
                    # Handle nil bids
                    if hand.north_bid == 0:
                        if tricks_taken[DirectionsEnum.NORTH] == 0:
                            ns_score = ns_score + 100
                        else:
                            ns_score = ns_score - 100
                    if hand.south_bid == 0:
                        if tricks_taken[DirectionsEnum.SOUTH] == 0:
                            ns_score = ns_score + 100
                        else:
                            ns_score = ns_score - 100
                    if hand.east_bid == 0:
                        if tricks_taken[DirectionsEnum.EAST] == 0:
                            ew_score = ew_score + 100
                        else:
                            ew_score = ew_score - 100
                    if hand.west_bid == 0:
                        if tricks_taken[DirectionsEnum.WEST] == 0:
                            ew_score = ew_score + 100
                        else:
                            ew_score = ew_score - 100

                    # Handle non-nil bids
                    ns_bid = hand.north_bid + hand.south_bid
                    ns_tricks = tricks_taken[DirectionsEnum.NORTH] + tricks_taken[DirectionsEnum.SOUTH]
                    ns_new_bags = ns_tricks - ns_bid
                    if ns_tricks >= ns_bid:
                        if ns_bid > 0:
                            # North/South at least met their bid
                            ns_score = ns_score + (ns_bid * 10)
                        # Handle bags
                        ns_score = ns_score + ns_new_bags
                        ns_bags = ns_bags + ns_new_bags
                        while ns_bags >= 10:
                            ns_score = ns_score - 100
                            ns_bags = ns_bags - 10
                        hand.ns_bags_at_end = ns_bags
                    elif ns_tricks < ns_bid:
                        # North/South did not meet their bid
                        ns_score = ns_score - (ns_bid * 10)
                        hand.ns_bags_at_end = ns_bags
                    hand.ns_score_after_bags = ns_score

                    ew_bid = hand.east_bid + hand.west_bid
                    ew_tricks = tricks_taken[DirectionsEnum.EAST] + tricks_taken[DirectionsEnum.WEST]
                    ew_new_bags = ew_tricks - ew_bid
                    if ew_tricks >= ew_bid:
                        if ew_bid > 0:
                            # East/West at least met their bid
                            ew_score = ew_score + (ew_bid * 10)
                        # Handle bags
                        ew_score = ew_score + ew_new_bags
                        ew_bags = ew_bags + ew_new_bags
                        while ew_bags >= 10:
                            ew_score = ew_score - 100
                            ew_bags = ew_bags - 10
                        hand.ew_bags_at_end = ew_bags
                    elif ew_tricks < ew_bid:
                        # East/West did not meet their bid
                        ew_score = ew_score - (ew_bid * 10)
                        hand.ew_bags_at_end = ew_bags
                    hand.ew_score_after_bags = ew_score

                    if 500 <= hand.ew_score_after_bags == hand.ns_score_after_bags \
                            or hand.ew_score_after_bags < 500 and hand.ns_score_after_bags < 500:
                        # Keep playing
                        next_hand = Hand(
                            game_id=self.game_id,
                            hand_number=self.hand_number + 1,
                            dealer=DirectionsEnum.get_next_clockwise(hand.dealer)
                        )
                        db.session.add(next_hand)
                        db.session.flush()
                        next_hand.deal_cards(game)
                    elif hand.ns_score_after_bags >= 500 and hand.ns_score_after_bags > hand.ew_score_after_bags:
                        game.state = GameStateEnum.COMPLETED
                        # North/South team wins
                        game.ns_win = True
                        for user in db.session.query(User).filter(
                            User.user_id.in_([
                                game.player_north,
                                game.player_south
                            ])
                        ):
                            user.wins = user.wins + 1
                        for user in db.session.query(User).filter(
                            User.user_id.in_([
                                game.player_east,
                                game.player_west
                            ])
                        ):
                            user.losses = user.losses + 1
                    elif hand.ew_score_after_bags >= 500 and hand.ew_score_after_bags > hand.ns_score_after_bags:
                        game.state = GameStateEnum.COMPLETED
                        # East/West team wins
                        game.ns_win = False
                        for user in db.session.query(User).filter(
                            User.user_id.in_([
                                game.player_north,
                                game.player_south
                            ])
                        ):
                            user.losses = user.losses + 1
                        for user in db.session.query(User).filter(
                            User.user_id.in_([
                                game.player_east,
                                game.player_west
                            ])
                        ):
                            user.wins = user.wins + 1

                    game.last_activity = datetime.utcnow()
                    db.session.commit()
                else:
                    # Create the next trick
                    db.session.add(Trick(
                        game_id=self.game_id,
                        hand_number=self.hand_number,
                        trick_number=self.trick_number + 1,
                        lead_player=self.winner
                    ))
                    game.last_activity = datetime.utcnow()
                    db.session.commit()
            else:
                db.session.commit()
