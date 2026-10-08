"""
Server settings, read from config.ini in the working directory or the file named by MU_CONFIG.
Every setting has a default, a missing file or key keeps it.
"""
import configparser
import logging
import os
import sys
from dataclasses import dataclass, fields

PACKET_LOGGER = 'mup.packet'


@dataclass
class Config:
    cs_port: int = 44405
    gs_port: int = 55901
    gs_host: str = '127.0.0.1'  # game server address the connect server hands to clients
    exp_rate: float = 1.0
    drop_rate: float = 1.0
    db_path: str = 'mu.db'  # SQLite file, created on the first start
    autosave_interval: float = 300.0  # seconds between saves of the characters in game
    monster_info: str = 'data/Monster.txt'  # monster types, server file of a later version
    monster_spawns: str = 'data/MonsterSetBase.txt'  # where they appear, only maps 0..10 are used
    item_info: str = 'data/Item.txt'  # which items drop, have a skill or options, server file of a later version
    item_drops: str = ''  # fixed drops per monster type on top of the random ones, none when empty
    skill_info: str = 'data/Skill.txt'  # area radius, effect and classes of the skills, server file of a later version
    shops: str = 'data/shop'  # ShopManager.txt and the shops' items, server files of a later version
    mixes: str = 'data/ChaosMix.txt'  # rates and zen of the chaos machine's mixes
    auto_create_accounts: bool = True  # the first login with an unknown account name creates it
    personal_code: str = '1111111'  # personal code of auto created accounts, deleting a character asks for it
    log_level: str = 'INFO'
    log_packets: bool = False  # every packet in and out, at DEBUG


def load(path=None):
    """Settings from path, MU_CONFIG or config.ini. Only a missing config.ini falls back to the defaults."""
    path = path or os.environ.get('MU_CONFIG')
    parser = configparser.ConfigParser()
    if path is None:
        path = 'config.ini'
        parser.read(path)
    elif not parser.read(path):
        raise FileNotFoundError(path)

    config = Config()
    known = {f.name: f.type for f in fields(Config)}
    for section in parser.sections():
        for key in parser[section]:
            if key not in known:
                raise ValueError('{}: unknown setting {} in [{}]'.format(path, key, section))
            if known[key] is bool:
                value = parser[section].getboolean(key)
            else:
                value = known[key](parser[section][key])
            setattr(config, key, value)
    return config


def setup_logging(config: Config):
    handler = logging.StreamHandler(sys.stdout)
    # \r: the client shares the terminal (run-gs.sh) and wine leaves it without carriage returns
    handler.setFormatter(logging.Formatter('\r%(asctime)s %(levelname)s: %(message)s\r'))
    logging.basicConfig(level=config.log_level.upper(), handlers=[handler], force=True)
    logging.getLogger(PACKET_LOGGER).setLevel(logging.DEBUG if config.log_packets else logging.INFO)
