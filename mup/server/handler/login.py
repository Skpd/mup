import logging
from mup.common.password import check_password
from mup.error import NotFoundError
from mup.packet.client import CLoginRequest
from mup.packet.server import SLoginResult
from mup.server.protocol import BaseProtocol

logger = logging.getLogger(__name__)


def login_handler(msg: CLoginRequest, proto: BaseProtocol):
    logger.info('Login %s, version %s, serial %s', msg.login, msg.version, msg.serial)

    # todo check version / serial

    server = proto.server
    try:
        acc = server.accounts.load(msg.login)
    except NotFoundError:
        acc = None
        if server.config.auto_create_accounts and msg.login:
            # the client can't register, so the first login creates the account
            acc = server.accounts.create(msg.login, msg.passw, server.config.personal_code)
            logger.info('Created account %s', acc.name)

    if acc is None:
        res = SLoginResult.NO_ACCOUNT
    elif not check_password(msg.passw, acc.password_hash):
        res = SLoginResult.BAD_PASSWORD
    elif not acc.active:
        res = SLoginResult.ACCOUNT_BANNED
    elif server.account_online(acc.id):
        res = SLoginResult.IN_USE
    else:
        proto.joined = True
        proto.acc = acc
        res = SLoginResult.SUCCESS

    if res != SLoginResult.SUCCESS:
        logger.info('Login %s refused: result %s', msg.login, res)
    proto.write(SLoginResult(result=res))
