from mup.error import NotFoundError
from mup.packet.client import CLoginRequest
from mup.packet.server import SLoginResult
from mup.server.protocol import BaseProtocol


def login_handler(msg: CLoginRequest, proto: BaseProtocol):
    print('Logged in: {}. Version: {}. Serial: {}'.format(msg.login, msg.version, msg.serial))

    # todo check passw
    # todo check version / serial

    from mup.model.account import Account
    res = SLoginResult.SUCCESS
    proto.joined = True
    proto.acc = Account()
    proto.acc.name = "Skpd"
    proto.acc.id = 1

    # try:
    #     acc = proto.server.account_mapper.load(msg.login)
    #     print(acc)
    #     if acc.active:
    #         proto.joined = True
    #         proto.acc = acc
    #         res = SLoginResult.SUCCESS
    #     else:
    #         res = SLoginResult.ACCOUNT_BANNED
    # except NotFoundError:
    #     res = SLoginResult.INVALID_ACCOUNT

    proto.write(SLoginResult(res))
