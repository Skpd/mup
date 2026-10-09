"""
Accounts in the game server database (db_path in the config), the server can keep running.
Changes apply on the account's next login.

usage: ./venv/bin/python bin/account.py list
       ./venv/bin/python bin/account.py create NAME PASSWORD [PERSONAL_CODE]
       ./venv/bin/python bin/account.py password NAME PASSWORD
       ./venv/bin/python bin/account.py code NAME PERSONAL_CODE
       ./venv/bin/python bin/account.py ban NAME | unban NAME
       ./venv/bin/python bin/account.py gm NAME | ungm NAME    GM commands in chat (mup/server/command.py)
       ./venv/bin/python bin/account.py bot create NAME CLASS [--seed N]    CLASS: dw, dk, elf, mg
       ./venv/bin/python bin/account.py bots
       ./venv/bin/python bin/account.py bot delete NAME
Bots (docs/bots.md) are characters the server plays, on accounts named after them without a password. They play
while the game server runs with bots_enabled, the ones made while it runs from its next start.
"""
import argparse
import random
import sys

from mup import config
from mup.bot import CLASSES, account as bot_account
from mup.common.password import hash_password
from mup.error import NotFoundError
from mup.model.account import GM
from mup.repository import database
from mup.repository.account import AccountRepository
from mup.repository.bot import BotRepository
from mup.repository.character import CharacterRepository


def main(argv):
    parser = argparse.ArgumentParser(description='Manage accounts')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list')
    create = commands.add_parser('create')
    create.add_argument('name')
    create.add_argument('password')
    create.add_argument('personal_code', nargs='?')
    password = commands.add_parser('password')
    password.add_argument('name')
    password.add_argument('password')
    code = commands.add_parser('code')
    code.add_argument('name')
    code.add_argument('personal_code')
    for command in ('ban', 'unban', 'gm', 'ungm'):
        commands.add_parser(command).add_argument('name')
    commands.add_parser('bots')
    bot = commands.add_parser('bot').add_subparsers(dest='bot_command', required=True)
    bot_create = bot.add_parser('create')
    bot_create.add_argument('name')
    bot_create.add_argument('class_name', choices=sorted(CLASSES))
    bot_create.add_argument('--seed', type=int, help='of its own draws, random when not given')
    bot.add_parser('delete').add_argument('name')
    args = parser.parse_args(argv)
    # the client sends account, password and personal code in 10 byte fields
    for field in ('name', 'password', 'personal_code'):
        if len(getattr(args, field, None) or '') > 10:
            parser.error('{} is longer than 10 characters'.format(field))

    cfg = config.load()
    db = database.connect(cfg.db_path)
    accounts = AccountRepository(db)

    if args.command == 'bots':
        characters = CharacterRepository(db, {})
        for b in BotRepository(db).all():
            p = characters.load(b.name)
            print('{:<10} {:<15} level {:>3} map {:>2} {:>3},{:<3} seed {}'.format(
                b.name, p.class_type.name, p.level, p.map_id, p.x, p.y, b.seed))
        return 0
    if args.command == 'bot':
        return bot_command(args, db)

    if args.command == 'list':
        for a in accounts.all():
            print('{:<10} code {:<10} {}{}'.format(a.name, a.personal_code, 'active' if a.active else 'banned',
                                              ' GM' if a.ctl_code & GM else ''))
        return 0

    if args.command == 'create':
        code = cfg.personal_code if args.personal_code is None else args.personal_code
        accounts.create(args.name, args.password, code)
        print('created', args.name)
        return 0

    try:
        a = accounts.load(args.name)
    except NotFoundError:
        print('no account', args.name)
        return 1
    if args.command == 'password':
        a.password_hash = hash_password(args.password)
    elif args.command == 'code':
        a.personal_code = args.personal_code
    elif args.command in ('gm', 'ungm'):
        a.ctl_code = a.ctl_code | GM if args.command == 'gm' else a.ctl_code & ~GM
    else:
        a.active = args.command == 'unban'
    accounts.save(a)
    print(args.command, a.name)
    return 0


def bot_command(args, db):
    if args.bot_command == 'create':
        class_type = CLASSES[args.class_name]
        seed = args.seed if args.seed is not None else random.randrange(1 << 31)
        try:
            b = bot_account.create(db, args.name, class_type, bot_account.start_spot(class_type), seed)
        except ValueError as e:
            print(e)
            return 1
        print('created bot {} ({}, seed {})'.format(b.name, class_type.name, b.seed))
        return 0
    try:
        b = BotRepository(db).load(args.name)
    except NotFoundError:
        print('no bot', args.name)
        return 1
    bot_account.delete(db, b)
    print('deleted bot', b.name)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
