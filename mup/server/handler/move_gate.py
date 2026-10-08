from mup.packet.client import CMoveGate
from mup.server import gate
from mup.server.protocol import BaseProtocol


def move_gate_handler(msg: CMoveGate, proto: BaseProtocol):
    p = proto.player
    if p is None or p.dead:
        return
    gate.enter(proto.server, proto, msg.gate)
