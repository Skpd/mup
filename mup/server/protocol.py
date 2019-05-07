from asyncio import Protocol
from asyncio.transports import Transport
from mup.common.crypt import Crypt
from mup.model.account import Account
from mup.model.player import Player
from mup.packet.base import Base
from mup.packet.client import factory
from mup.server.game import GameServer


class BaseProtocol(Protocol):
    transport: Transport
    server: GameServer
    crypt: Crypt
    player: Player
    acc: Account

    cid = None
    connected = False
    joined = False
    playing = False
    server_tick = None
    client_tick = None

    def __init__(self, gs):
        self.crypt = Crypt(decode_keys='data/Dec1.dat', encode_keys='data/Enc2.dat')
        # self.crypt = Crypt(decode_keys='/tmp/server065/data/Dec1.dat', encode_keys='/tmp/server065/data/Enc2.dat')
        self.server = gs

    def disconnect(self):
        self.server.disconnect(self)
        self.transport.write(b'')
        self.transport.write_eof()
        self.transport.close()

    def connection_made(self, transport):
        self.transport = transport
        self.server.add_connection(self)
        self.connected = True

    def write(self, what, raw=False):
        if what[0] in {0xC3, 0xC4} and not raw:
            what = self.crypt.encrypt(what)
        print('Sending {}'.format(what))
        self.transport.write(what)

    def send_all(self, msg, except_self=True):
        for c in self.server.connections:
            if c.playing and (not except_self or c != self):
                c.write(msg)

    def send_same_map(self, msg, except_self=False):
        ...

    def send_near(self, msg, except_self=True):
        ...

    def data_received(self, data):
        message = Base(data)
        # print('Received {}'.format(message))

        if message[0] in {0xC3, 0xC4}:
            try:
                message = self.crypt.decrypt(message)
            except RuntimeError as e:
                print(e, message, len(message))
            # print('Decrypted {}'.format(message))
        elif message[0] in {0xC1, 0xC2} and self.joined:
            self.crypt.extract(message, message[0] == 0xC2)
            # print('Extracted {}'.format(message))

        packet = factory(message)
        # print('Incoming {}'.format(message))

        if packet and packet.key in self.server.handlers:
            callbacks = self.server.handlers[packet.key]
            if not len(callbacks):
                print('No handlers for {}'.format(packet.key))

            for c in callbacks:
                c(packet, self)
        else:
            print('No handlers for {}'.format(message))
