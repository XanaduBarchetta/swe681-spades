import secrets


# The full deck encodes the 52 available cards as three-character strings.
# The first two characters represent the face value of the card. The third character is the suit.
# Special values: Jack = 11, Queen = 12, King = 13, Ace = 14 (since Aces beat Kings)
FULL_DECK = [
    '02S',
    '03S',
    '04S',
    '05S',
    '06S',
    '07S',
    '08S',
    '09S',
    '10S',
    '11S',
    '12S',
    '13S',
    '14S',
    '02H',
    '03H',
    '04H',
    '05H',
    '06H',
    '07H',
    '08H',
    '09H',
    '10H',
    '11H',
    '12H',
    '13H',
    '14H',
    '02C',
    '03C',
    '04C',
    '05C',
    '06C',
    '07C',
    '08C',
    '09C',
    '10C',
    '11C',
    '12C',
    '13C',
    '14C',
    '02D',
    '03D',
    '04D',
    '05D',
    '06D',
    '07D',
    '08D',
    '09D',
    '10D',
    '11D',
    '12D',
    '13D',
    '14D'
]


def get_shuffled_deck():
    """
    Uses cryptographically secure random generator to return a shuffled deck
    :return: Copy of FULL_DECK shuffled
    """
    old_deck = FULL_DECK.copy()
    new_deck = []
    for i in range(51, 1, -1):
        new_deck.append(old_deck.pop(secrets.randbelow(i)))
    new_deck.append(old_deck.pop(0))
    return new_deck
