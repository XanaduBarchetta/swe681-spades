class UserAlreadyExistsException(Exception):
    pass


class InvalidDirectionError(Exception):
    """
    Raised when an invalid Direction is referenced
    """
    pass


class InvalidSuitError(Exception):
    """
    Raised when an invalid Suit is referenced
    """
    pass


class UserCanNotBidError(Exception):
    """
    Raised when attempting to place a bid for a user who is ineligible for bidding
    """
    pass


class CardNotInHandError(Exception):
    """
    Raised when attempting to play a card that is either not in a user's hand or has already been played
    """
    pass


class SpadesNotBrokenError(Exception):
    """
    Raised when attempting to lead with a spade when spades have not yet been broken
    and other suits are available in the player's hand
    """
    pass


class NotFollowingLeadSuitError(Exception):
    """
    Raised when attempting to not follow the lead suit but cards in that suit are available to play
    """
    pass


class BadGameStateError(Exception):
    pass
