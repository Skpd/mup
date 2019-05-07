from mup.error import NotFoundError
from mup.packet.client import CLoginRequest
from mup.packet.server import SLoginResult
from mup.server.protocol import BaseProtocol


def login_handler(msg: CLoginRequest, proto: BaseProtocol):
    print('Logged in: {}. Version: {}. Serial: {}'.format(msg.login, msg.version, msg.serial))

    # todo check passw
    # todo check version / serial

    try:
        acc = proto.server.account_mapper.load(msg.login)
        if acc.active:
            proto.joined = True
            proto.acc = acc
            res = SLoginResult.SUCCESS
        else:
            res = SLoginResult.ACCOUNT_BANNED
    except NotFoundError:
        res = SLoginResult.INVALID_ACCOUNT

    proto.write(SLoginResult(res))
