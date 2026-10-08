"""Character creation rules."""
import random
import re
from mup.model.player import Player, CharacterClass, DEFAULT_SKILLS

MAX_CHARACTERS = 5  # the client has 5 character slots
NAME = re.compile('[A-Za-z0-9]{3,10}')
BASE_CLASSES = {CharacterClass.DARK_WIZARD, CharacterClass.DARK_KNIGHT, CharacterClass.ELF,
                CharacterClass.MAGIC_GLADIATOR}

# where new characters start: map and the area of a gate in Move/Gate.txt, 17 in Lorencia, 27 in Noria for elves
START = (0, range(133, 152), range(118, 136))
START_BY_CLASS = {CharacterClass.ELF: (3, range(171, 178), range(108, 118))}


def valid_name(name):
    # the client doesn't show players whose name contains "webzen"
    return NAME.fullmatch(name) is not None and 'webzen' not in name.lower()


def creatable_class(value):
    """CharacterClass for the class a create request asks for, None if it isn't a first class."""
    try:
        class_type = CharacterClass(value)
    except ValueError:
        return None
    return class_type if class_type in BASE_CLASSES else None


def new_character(account_id, slot, name, class_type: CharacterClass):
    """A level 1 character at a random spot of its start area."""
    map_id, xs, ys = START_BY_CLASS.get(class_type, START)
    # todo the area has walls and a fountain, pick a walkable spot once the terrain is loaded (roadmap M2)
    return Player.new(class_type, account_id=account_id, index=slot, name=name, map_id=map_id,
                      x=random.choice(xs), y=random.choice(ys), skills=list(DEFAULT_SKILLS.get(class_type, [])))
