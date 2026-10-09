"""Character creation rules, start and respawn places."""
import re
from mup.model.player import Player, CharacterClass, DEFAULT_SKILLS

MAX_CHARACTERS = 5  # the client has 5 character slots
NAME = re.compile('[A-Za-z0-9]{3,10}')
BASE_CLASSES = {CharacterClass.DARK_WIZARD, CharacterClass.DARK_KNIGHT, CharacterClass.ELF,
                CharacterClass.MAGIC_GLADIATOR}

# town gates of the client's Gate.bmd: new characters start in Lorencia, elves in Noria
LORENCIA, DEVIAS, NORIA = 17, 22, 27
START_GATE = LORENCIA
START_GATE_BY_CLASS = {CharacterClass.ELF: NORIA}
# where the dead come back by the map they died on: Devias for Devias, Lost Tower and Icarus, Noria for Noria and
# Devil Square, Lorencia for the others. Usual rules, not from the client
RESPAWN_GATES = {2: DEVIAS, 3: NORIA, 4: DEVIAS, 9: NORIA, 10: DEVIAS}


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


def start_gate(class_type: CharacterClass):
    return START_GATE_BY_CLASS.get(class_type.base, START_GATE)


def respawn_gate(map_id):
    return RESPAWN_GATES.get(map_id, LORENCIA)


def new_character(account_id, slot, name, class_type: CharacterClass, map_id, x, y):
    """A level 1 character at map_id x, y."""
    return Player.new(class_type, account_id=account_id, index=slot, name=name, map_id=map_id, x=x, y=y,
                      skills=list(DEFAULT_SKILLS.get(class_type, [])))
