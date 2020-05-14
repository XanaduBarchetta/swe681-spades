class UserAlreadyExistsException(Exception):
    """
    Raised when attempting to add a user with a username already in the database
    """


class InvalidDirectionError(Exception):
    """
    Raised when an invalid Direction is referenced
    """


class InvalidSuitError(Exception):
    """
    Raised when an invalid Suit is referenced
    """


class NotPlayersTurnError(Exception):
    """
    Raise when a user attempts to play a card, but it is not their turn to do so
    """


class UserCanNotBidError(Exception):
    """
    Raised when attempting to place a bid for a user who is ineligible for bidding
    """


class CardNotInHandError(Exception):
    """
    Raised when attempting to play a card that is either not in a user's hand or has already been played
    """


class SpadesNotBrokenError(Exception):
    """
    Raised when attempting to lead with a spade when spades have not yet been broken
    and other suits are available in the player's hand
    """


class NotFollowingLeadSuitError(Exception):
    """
    Raised when attempting to not follow the lead suit but cards in that suit are available to play
    """


class BadGameStateError(Exception):
    """
    Raised when data in the database is found to be in a state supposedly impossible for a game
    """
