import logging
from mup.packet.client import factory

logger = logging.getLogger(__name__)


class ServerBase:
    handlers = None
    available_servers = None

    def __init__(self):
        self.handlers = {}
        self.connections = {}

    def add_handler(self, head, sub, callback):
        key = (head, sub)
        if key not in self.handlers:
            self.handlers[key] = []
        self.handlers[key].append(callback)

    def dispatch(self, c, message):
        """A packet from connection c, decrypted and unchained, to its handlers. A failing handler is logged, the
        connection stays: one broken handler shouldn't kick the player."""
        try:
            packet = factory(message)
            if packet and packet.key in self.handlers:
                for handler in self.handlers[packet.key]:
                    handler(packet, c)
            else:
                logger.warning('Unhandled packet %s', message.hex(' '))
        except Exception:
            logger.exception('Failed to handle %s', message.hex(' '))

    def add_connection(self, c):
        self.connections[c] = c

    def disconnect(self, c):
        self.connections.pop(c, None)
