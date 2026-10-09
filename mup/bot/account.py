"""Making and removing bots: an account without password named after the bot, its character and its bots row."""
import os
import random
from mup.error import NotFoundError
from mup.model.bot import Personality
from mup.model.player import Player
from mup.repository.account import AccountRepository
from mup.repository.bot import BotRepository
from mup.repository.character import CharacterRepository
from mup.server import character, gate
from mup.server.game import GATE_PATH, TERRAIN_PATH
from mup.server.terrain import Terrain


def start_spot(class_type):
    """Map and a random walkable tile of the class's start gate, where the game puts a new character."""
    g = gate.load(GATE_PATH)[character.start_gate(class_type)]
    terrain = Terrain.load(os.path.join(TERRAIN_PATH, 'Terrain{}.att'.format(g.map_id + 1)))
    x, y = terrain.random_spot(g.xs, g.ys)
    return g.map_id, x, y


def create(db, name, class_type, at, seed, personality=None):
    """
    A level 1 bot of class_type at (map, x, y), its personality drawn from seed when not given. Its account takes
    its name and has no password, nobody logs in to it. Raises ValueError for a name that is invalid or taken.
    """
    if not character.valid_name(name):
        raise ValueError('{}: 3..10 letters and digits'.format(name))
    accounts = AccountRepository(db)
    characters = CharacterRepository(db, {})
    try:
        accounts.load(name)
        raise ValueError('an account {} exists'.format(name))
    except NotFoundError:
        pass
    if characters.exists(name):
        raise ValueError('a character {} exists'.format(name))
    account = accounts.create(name, None)
    map_id, x, y = at
    p = character.new_character(account.id, 0, name, class_type, map_id, x, y)
    characters.create(p)
    return BotRepository(db).create(p.id, seed, personality or Personality.roll(random.Random(seed)))


def delete(db, bot):
    """The bot's character with its row, items and skills, then its account."""
    CharacterRepository(db, {}).delete(Player(id=bot.character_id, name=bot.name))
    accounts = AccountRepository(db)
    accounts.delete(accounts.load_id(bot.account_id))

