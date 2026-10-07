from mup.error import NotFoundError
from mup.model.account import Account
from mup.packet.client import CLoginRequest
from mup.packet.server import SLoginResult
from mup.server.protocol import BaseProtocol


def login_handler(msg: CLoginRequest, proto: BaseProtocol):
    print('Login: {}. Version: {}. Serial: {}'.format(msg.login, msg.version, msg.serial))

    # todo check version / serial

    accounts = proto.server.account_mapper
    try:
        acc = accounts.load(msg.login)
    except NotFoundError:
        # the client can't register, so the first login creates the account
        acc = Account(name=msg.login, password=msg.passw)
        accounts.store(acc)
        print('Created account {}'.format(acc.name))

    if acc.password != msg.passw:
        res = SLoginResult.BAD_PASSWORD
    elif not acc.active:
        res = SLoginResult.ACCOUNT_BANNED
    else:
        proto.joined = True
        proto.acc = acc
        res = SLoginResult.SUCCESS

    proto.write(SLoginResult(res))
