from mup.packet.client import CMoveGate
from mup.server import casting, gate
from mup.server.protocol import BaseProtocol


def move_gate_handler(msg: CMoveGate, proto: BaseProtocol):
    p = proto.player
    if p is None or p.dead:
        return
    if msg.gate == 0:
        # the teleport skill: gate 0 and the target tile
        casting.teleport(proto.server, proto, msg.x, msg.y)
    else:
        gate.enter(proto.server, proto, msg.gate)
