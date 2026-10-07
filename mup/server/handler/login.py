import logging
from mup.error import NotFoundError
from mup.model.account import Account
from mup.packet.client import CLoginRequest
from mup.packet.server import SLoginResult
from mup.server.protocol import BaseProtocol

logger = logging.getLogger(__name__)


def login_handler(msg: CLoginRequest, proto: BaseProtocol):
    logger.info('Login %s, version %s, serial %s', msg.login, msg.version, msg.serial)

    # todo check version / serial

    accounts = proto.server.account_mapper
    try:
        acc = accounts.load(msg.login)
    except NotFoundError:
        # the client can't register, so the first login creates the account
        acc = Account(name=msg.login, password=msg.passw)
        accounts.store(acc)
        logger.info('Created account %s', acc.name)

    if acc.password != msg.passw:
        res = SLoginResult.BAD_PASSWORD
    elif not acc.active:
        res = SLoginResult.ACCOUNT_BANNED
    else:
        proto.joined = True
        proto.acc = acc
        res = SLoginResult.SUCCESS

    proto.write(SLoginResult(result=res))
