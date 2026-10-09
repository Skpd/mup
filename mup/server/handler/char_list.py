from mup.packet.client import CCharList
from mup.packet.server import SCharList
from mup.server.session import Session


def char_list_handler(msg: CCharList, proto: Session):
    if proto.acc is None:
        return

    chars = proto.server.characters.by_account(proto.acc.id)
    proto.write(SCharList.of(chars))
