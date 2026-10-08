"""
Accounts in the game server database (db_path in the config), the server can keep running.
Changes apply on the account's next login.

usage: ./venv/bin/python bin/account.py list
       ./venv/bin/python bin/account.py create NAME PASSWORD [PERSONAL_CODE]
       ./venv/bin/python bin/account.py password NAME PASSWORD
       ./venv/bin/python bin/account.py code NAME PERSONAL_CODE
       ./venv/bin/python bin/account.py ban NAME | unban NAME
       ./venv/bin/python bin/account.py gm NAME | ungm NAME    GM commands in chat (mup/server/command.py)
"""
import argparse
import sys

from mup import config
from mup.common.password import hash_password
from mup.error import NotFoundError
from mup.model.account import GM
from mup.repository import database
from mup.repository.account import AccountRepository


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
    args = parser.parse_args(argv)
    # the client sends account, password and personal code in 10 byte fields
    for field in ('name', 'password', 'personal_code'):
        if len(getattr(args, field, None) or '') > 10:
            parser.error('{} is longer than 10 characters'.format(field))

    cfg = config.load()
    accounts = AccountRepository(database.connect(cfg.db_path))

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


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
