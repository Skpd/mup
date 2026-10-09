from mup.packet.client import CQuestStates, CQuestProceed
from mup.server import quest
from mup.server.session import Session


def quest_states_handler(msg: CQuestStates, proto: Session):
    if proto.player is None:
        return
    quest.send_states(proto)


def quest_proceed_handler(msg: CQuestProceed, proto: Session):
    if proto.player is None:
        return
    quest.proceed(proto.server, proto, msg.quest)
