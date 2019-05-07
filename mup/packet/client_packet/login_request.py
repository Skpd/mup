from mup.packet.base import Base


class LoginRequest(Base):
    login = None
    passw = None
    version = None
    serial = None

    def __init__(self, src):
        super().__init__(src)

        self.login = self[4:14].strip(b'\0').decode('ascii')
        self.passw = self[14:24].strip(b'\0').decode('ascii')
        self.version = self[28:32]
        self.serial = self[33:]


