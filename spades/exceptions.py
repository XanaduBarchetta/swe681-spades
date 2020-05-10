class UserAlreadyExistsException(Exception):
    pass


class InvalidDirectionError(Exception):
    """
    Raised when an invalid Direction is referenced
    """
    pass


class UserCanNotBidError(Exception):
    """
    Raised when attempting to place a bid for a user who is ineligible for bidding
    """
    pass


class BadGameStateError(Exception):
    pass
