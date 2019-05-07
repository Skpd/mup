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

    def add_connection(self, c):
        self.connections[c] = c

    def disconnect(self, c):
        del self.connections[c]

