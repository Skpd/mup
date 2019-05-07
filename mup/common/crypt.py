import struct
from mup.common.timer import Timer
from mup.packet.base import Base


class Crypt:
    encrypt_sequence = 0
    ext_keys = [0xE7, 0x6D, 0x3A, 0x89, 0xBC, 0xB2, 0x9F, 0x73, 0x23, 0xA8, 0xFE, 0xB6, 0x49, 0x5D, 0x39, 0x5D, 0x8A, 0xCB, 0x63, 0x8D, 0xEA, 0x7D, 0x2B, 0x5F, 0xC3, 0xB1, 0xE9, 0x83, 0x29, 0x51, 0xE8, 0x56]
    login_keys = [0xFC, 0xCF, 0xAB]
    encryption_modulus = encryption_keys = encryption_xor_keys = []
    decryption_modulus = decryption_keys = decryption_xor_keys = []
    do_extract = True

    def __init__(self, encode_keys=None, decode_keys=None):
        if encode_keys:
            self.encryption_modulus, self.encryption_keys, self.encryption_xor_keys = self.load_keys(encode_keys)
        if decode_keys:
            self.decryption_modulus, self.decryption_keys, self.decryption_xor_keys = self.load_keys(decode_keys)

    @staticmethod
    def load_keys(filename):
        with open(filename, 'rb') as fp:
            header = struct.unpack('h', fp.read(2))[0]
            size = struct.unpack('i', fp.read(4))[0]

            if header != 0x1112 or size != 54:
                raise RuntimeError('Invalid header {} or size {}.'.format(header, size))

            file_xor = [0x3F08A79B, 0xE25CC287, 0x93D27AB9, 0x20DEA7BF]

            key_size = 4

            modulus = []
            for i in range(0, key_size):
                modulus.append(file_xor[i] ^ struct.unpack('I', fp.read(4))[0])

            keys = []
            for i in range(0, key_size):
                keys.append(file_xor[i] ^ struct.unpack('I', fp.read(4))[0])

            xor_keys = []
            for i in range(0, key_size):
                xor_keys.append(file_xor[i] ^ struct.unpack('I', fp.read(4))[0])

        return modulus, keys, xor_keys

    def decrypt(self, src):
        is_double = src[0] in {0xC2, 0xC4}
        if is_double:
            res = Base([0, 0])
        else:
            res = Base([0])

        res[0] = src[0]

        dec_result = 2 if is_double else 1
        src_pos = 3 if is_double else 2

        while True:
            src_part = src[src_pos:]

            if not len(src_part):
                break

            block_result, dst_block = self.decrypt_block(src_part)
            res += dst_block

            if block_result < 0:
                raise RuntimeError('Unable to decrypt "{}"'.format(src))

            dec_result += block_result
            src_pos += 11

        res = Base(res[:dec_result])
        # print(res[1])
        res.length = dec_result

        if dec_result > 0:
            if res[0] in {0xC3, 0xC4}:
                if self.do_extract:
                    self.extract(res)
                res[0] = src[0] - 2

            if res.head == 0xF1 and res.sub in {1, 0}:
                self.decrypt_login(res, 4)
                self.decrypt_login(res, 14)

        return res

    def decrypt_block(self, src):
        dec_buff = [0, 0, 0, 0]
        bit_pos = 0
        buff = bytearray(8)

        for i in range(0, 4):
            r = self.add_bits(0, src, bit_pos, 16)
            dec_buff[i] = r[1] << 8 | r[0] & 0xFFFF
            bit_pos += 16

            r = self.add_bits(22, src, bit_pos, 2)
            dec_buff[i] |= r[0] << 16
            bit_pos += 2

        for i in range(2, -1, -1):
            dec_buff[i] = dec_buff[i] ^ self.decryption_xor_keys[i] ^ (dec_buff[i + 1] & 0xFFFF)

        prev_val = 0
        for i in range(0, 4):
            val = ((self.decryption_keys[i] * dec_buff[i]) % self.decryption_modulus[i]) ^ self.decryption_xor_keys[i] ^ prev_val
            buff[i*2] = (val & 0xff)
            buff[i*2+1] = (val >> 8 & 0xff)
            prev_val = dec_buff[i] & 0xFFFF

        src_checksum = self.add_bits(0, src, bit_pos, 16)
        src_checksum[0] = src_checksum[1] ^ src_checksum[0] ^ 0x3D
        length = src_checksum[0]
        src_checksum = src_checksum[1]

        checksum = 0xF8
        for i in range(0, 8):
            checksum ^= buff[i]

        if checksum == src_checksum:
            return length, buff
        else:
            return -1, buff

    def add_bits(self, add_pos, src, src_pos, size):
        src_bits = src_pos + size
        src_pos_byte = src_pos >> 3
        temp_buff_size = ((src_bits - 1) >> 3) + (1 - src_pos_byte)

        temp_buff = src[src_pos_byte:src_pos_byte + temp_buff_size]
        temp_buff.append(0)

        if src_bits % 8 != 0:
            temp_buff[temp_buff_size - 1] &= 0xFF << (8 - (src_bits % 8))

        shift_left = src_pos % 8
        shift_right = add_pos % 8
        self.shift(temp_buff, temp_buff_size, -shift_left)
        self.shift(temp_buff, temp_buff_size + 1, shift_right)

        new_temp_buff_size = (0 if shift_right <= shift_left else 1) + temp_buff_size

        return temp_buff[:new_temp_buff_size]

    @staticmethod
    def shift(buff, size, val):
        if val > 0:
            if size - 1 > 0:
                for i in range(size - 1, 0, -1):
                    buff[i] = ((buff[i-1] << (8 - val)) & 0xFF | (buff[i] >> val) & 0xff) & 0xff

            buff[0] = (buff[0] >> val) & 0xFF
        elif val < 0:
            val = -val

            if size - 1 > 0:
                for i in range(0, size - 1):
                    buff[i] = ((buff[i+1] >> (8 - val)) & 0xff | (buff[i] << val) & 0xff) & 0xff

            buff[size-1] = (buff[size-1] << val) & 0xff
        else:
            pass

    def extract(self, buff: Base, is_double=False):
        for i in range(len(buff) - 1, 3 if is_double else 2, -1):
            buff[i] ^= buff[i - 1] ^ self.ext_keys[i % 32]

    def pack(self, buff: Base, is_double=False):
        for i in range(4 if is_double else 3, len(buff)):
            buff[i] ^= buff[i - 1] ^ self.ext_keys[i % 32]

    def decrypt_login(self, buff: Base, start, length=10):
        for i in range(length):
            buff[start + i] ^= self.login_keys[i % 3]

    def encrypt_login(self, buff: Base, start, length=10):
        for i in range(length):
            buff[start + i] ^= self.login_keys[i % 3]

    def encrypt(self, p: Base):
        dec = Base(p.copy())

        if dec.head == 0xF1 and dec.sub in {0, 1}:
            self.encrypt_login(dec, 4)
            self.encrypt_login(dec, 14)

        # don't pack from server
        # pack(dec, dec.is_double())

        dec.length = self.encrypt_sequence
        self.encrypt_sequence += 1

        if dec.is_double():
            enc_result = [0xC4, 0x00, 0x00]
        else:
            enc_result = [0xC3, 0x00]
        enc_size = len(dec) - (2 if dec.is_double() else 1)
        start = 2 if dec.is_double() else 1
        # encrypt by block:
        for i in range(0, len(dec), 8):
            if not len(dec[start+i:]):
                continue
            enc_result += self.encrypt_block(dec[start+i:], enc_size)
            enc_size -= 8

        # enc_result[0] = enc_result[0] + 2
        enc_result = Base(enc_result)

        enc_result.length = len(enc_result)

        return enc_result

    def encrypt_block(self, src, size):
        dst = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        enc_buff = [0, 0, 0, 0]
        enc_value = 0

        for i in range(4):
            src_short = struct.unpack('H', struct.pack('2B', src[i*2] if i*2 < len(src) else 0, src[i*2+1] if i*2+1 < len(src) else 0))[0]
            enc_buff[i] = ((self.encryption_xor_keys[i] ^ src_short ^ enc_value) * self.encryption_keys[i]) % self.encryption_modulus[i]
            enc_value = enc_buff[i] & 0xFFFF

        for i in range(3):
            enc_buff[i] = enc_buff[i] ^ self.encryption_xor_keys[i] ^ (enc_buff[i+1] & 0xFFFF)

        bit_pos = 0

        for i in range(4):
            enc_buff_char = list(struct.unpack('4B', struct.pack('I', enc_buff[i])))
            r = self.add_bits(bit_pos, enc_buff_char, 0, 16)
            for k, v in enumerate(r):
                dst[k + (bit_pos >> 3)] |= v
            bit_pos += 16
            r = self.add_bits(bit_pos, enc_buff_char, 22, 2)
            for k, v in enumerate(r):
                dst[k + (bit_pos >> 3)] |= v
            bit_pos += 2

        checksum = 0xF8

        for i in range(8):
            checksum ^= src[i] if i < len(src) else 0

        enc_value_char = list(struct.unpack('2B', struct.pack('H', enc_value)))
        enc_value_char[1] = checksum
        enc_value_char[0] = checksum ^ min(8, size) ^ 0x3D

        r = self.add_bits(bit_pos, enc_value_char, 0, 16)
        for k, v in enumerate(r):
            dst[k + (bit_pos >> 3)] |= v

        return dst


if __name__ == '__main__':
    server = Crypt(decode_keys='/tmp/Dec1.dat')
    client = Crypt(decode_keys='/tmp/Dec2.dat')
    client.do_extract = False

    pa = [
        'c3:4f:f5:30:01:00:93:36:00:4e:2d:15:20:fb:eb:0e:ae:8a:3b:f3:85:42:d4:e1:9f:74:3c:c5:58:39:c2:53:f0:be:8b:8b:0c:22:1d:80:6b:75:90:6d:1a:2f:61:f8:2a:f7:dc:d3:55:d7:59:43:76:9d:e4:24:ba:0a:76:46:f2:40:8f:ba:13:02:0b:ff:1d:73:e4:2b:c5:6b:55',
        'c4:00:66:dd:ab:0b:4e:82:40:d6:52:49:d4:e1:3b:8a:1b:54:4c:5e:70:d8:1a:7d:48:d6:11:13:74:d9:bb:a3:49:a1:8b:be:cf:f6:1f:7c:0b:50:b1:b0:41:97:a2:16:f2:31:af:9b:7c:94:f1:b2:d5:e0:78:d9:27:46:8c:72:74:aa:25:45:70:9e:a3:3a:f4:9f:83:15:5a:a1:c5:f0:f7:14:19:f2:87:b6:11:90:02:04:31:0a:af:7d:af:9b:9a:47:30:ce:7c:44',
    ]

    for p in pa:
        raw = [int(x, 16) for x in p.split(':')]
        if raw[0] in {0xC3, 0xC4}:
            try:
                m = server.decrypt(bytearray(raw))
                print('from client ', end='')
            except RuntimeError:
                m = client.decrypt(bytearray(raw))
                print('from server ', end='')

            print(list(map(int, m)))
        else:
            print(raw)

    exit(0)
    c = Crypt(
        encode_keys='/home/skpd/projects/php/mu/data/Enc1.dat',
        # decode_keys='/home/skpd/projects/php/mu/data/Dec1.dat',
        decode_keys='/tmp/Dec2.dat',
        # decode_keys='/tmp/Dec1.dat',
        # decode_keys='/tmp/ImperialMu/Data/Dec2.dat'
    )

    if False:
        with open('/tmp/ImperialMu/dump2.hex') as f:
            
            lines = map(lambda x: x.strip(), f.readlines())
            contents = ''.join(lines)
            # print(contents)
            packets = []
            reading = False
            buff = ''
            for i in range(0, len(contents), 2):
                if reading and len(buff) < 0x0D*2:
                    buff += contents[i:i+2]
                elif len(buff) == 0x0D*2:
                    packets.append([int(buff[x:x+2], 16) for x in range(0, len(buff), 2)])
                    buff = ''
                    reading = False
                elif contents[i:i+4] == 'c30d':
                    buff = 'c3'
                    reading = True
                else:
                    continue
            for p in packets:
                m = c.decrypt(bytearray(p))
                if m[3] != 129:
                    continue
                print([x for x in m])
                # print(m[3], m[4] << 8 | m[5], m[7] << 8 | m[8])
            exit(0)

    pa = [
        # 'c3:0d:1b:4b:35:1b:59:40:e7:aa:04:de:e4',
        # 'c3:0d:dd:11:00:af:5c:78:f2:8c:28:ae:9b',
        # 'c3:0d:4b:1a:1d:89:00:4b:e7:45:12:c3:f9',
        #  4803
        # 'c3:0d:b4:3a:0a:cb:0b:40:c1:45:61:89:b1'

        # 'c3:0d:c8:d6:2b:ac:0b:14:a5:9a:14:7b:41',
        # 'c1:07:15:03:30:00:21',

        # 'c3:0d:57:6b:21:12:0d:8f:02:c3:d4:ba:82'
        #
        # 'c3:0d:c6:a0:08:ae:de:94:24:b6:1d:75:4f',
        # 'c1:05:17:03:30',
        # 'c3:0d:16:12:29:a8:12:93:21:31:00:63:56',
        #
        # 'c3:0d:1b:4b:01:d7:53:77:a2:6b:15:57:6d',
        # 'c3:0d:59:51:24:c9:8b:f4:d5:57:90:56:6c',
        # 'c3:0d:bd:70:29:55:8b:89:27:fd:36:54:6e',
        # 'c1:07:15:00:08:00:03',
        # 'c3:0d:8e:6c:24:c7:02:fb:35:2d:4d:51:6b',
        # 'c1:07:15:00:0f:00:06',
        #
        # 'c3:0d:75:2a:10:f8:57:6c:17:5c:60:5e:64',
        #
        # 'c3:0d:1b:4b:20:11:53:61:04:72:dc:4d:77',
        # 'c3:0d:1b:4b:3b:b2:95:45:60:41:f9:4c:76',

        'c3:0d:59:51:08:11:0d:de:d6:10:98:4b:71',
        'c3:0d:1b:4b:15:2d:53:67:e3:20:a6:4a:70',
        'c3:0d:59:51:28:53:03:05:e3:a2:75:55:6f',
        'c3:0d:1b:4b:2c:8e:d2:e4:d0:da:50:49:73',
        'c3:0d:59:51:31:f4:48:e4:10:c0:7d:56:6c',
        'c3:0d:1b:4b:0c:c8:9d:29:e5:2d:78:56:6c',
        'c3:0d:59:51:1f:56:8e:af:87:b8:b5:57:6d',
        'c3:0d:1b:4b:06:39:9a:6c:60:53:09:59:63',

        # 'c1:08:27:ff:00:c1:00:19'
        # 'c3:0d:3a:6f:23:ca:84:9c:c2:8d:c0:30:0a',
        # 'c3:0d:fa:c8:17:79:1c:76:76:22:3c:3c:06',
        # 'c3:0d:2c:51:12:07:47:bb:93:d8:da:31:0b',
        # 'c3:0d:10:4b:39:9d:c1:be:70:8b:fd:35:0f',
        # 'c3:0d:34:6e:17:16:18:f7:13:64:78:3b:01',
        # 'c3:0d:75:2a:2e:c1:d4:7b:30:7a:30:26:1c',
        # 'c3:0d:ce:a2:10:82:57:77:b3:f6:5c:32:08',
    ]
    # p = 'c30d215009ed0587619db16058'
    # p = 'c1:05:17:03:81'
    # p = 'c1:08:27:ff:00:c1:00:19'
    for p in pa:
        raw = [int(x, 16) for x in p.split(':')]
        if raw[0] == 0xC3:
            m = c.decrypt(bytearray(raw))
            print(list(map(int, m)))
        else:
            print(raw)
    exit(0)

    p = [
        # [0xc3, 0x0d, 0xa6, 0xf3, 0x14, 0xea, 0x0a, 0xbc, 0x62, 0xcc, 0xf5, 0x63, 0x56, ],
        # [0xc3, 0x0d, 0xb8, 0xf8, 0x26, 0x36, 0xd2, 0x89, 0x71, 0x51, 0x85, 0x08, 0x3d, ],
        # [0xc3, 0x0d, 0xff, 0x04, 0x34, 0x27, 0x0c, 0x9a, 0xb1, 0x4e, 0xf5, 0x8a, 0xbf, ],
        # [0xc3, 0x0d, 0x10, 0x94, 0x23, 0x3a, 0x98, 0x32, 0xb4, 0xee, 0x59, 0x64, 0x51, ],
        # [0xc3, 0x0d, 0x6e, 0x92, 0x2f, 0xfb, 0x9d, 0xb1, 0xb6, 0x46, 0x42, 0x67, 0x52, ],
        # [0xc3, 0x0d, 0x7c, 0x3d, 0x26, 0x24, 0x9a, 0xbd, 0xd5, 0x15, 0x5a, 0x66, 0x53, ],
        # [0xc3, 0x0d, 0x98, 0xeb, 0x1f, 0x1e, 0x4d, 0x5e, 0x60, 0x53, 0x39, 0x69, 0x5c, ],

        # [0xc3, 0x0d, 0xf7, 0x39, 0x1d, 0xc6, 0x4f, 0x76, 0x11, 0xd6, 0xb4, 0xcd, 0xf8, ],
        # [0xc3, 0x0d, 0x18, 0x3a, 0x1e, 0xc8, 0xd2, 0xbb, 0x21, 0xed, 0xb8, 0xb2, 0x87, ],
        # [0xc3, 0x0d, 0x64, 0xdb, 0x31, 0x07, 0x4e, 0x91, 0x03, 0xac, 0xbd, 0xbe, 0x8b, ],
        # [0xc3, 0x0d, 0x19, 0x44, 0x04, 0x68, 0x92, 0xbd, 0xa4, 0xc8, 0x4a, 0xbd, 0x88, ],
        # [0xc3, 0x0d, 0xa5, 0x65, 0x33, 0x76, 0x00, 0x5f, 0x63, 0xb4, 0xa4, 0x86, 0xb3, ],
        # [0xc3, 0x0d, 0x19, 0x28, 0x21, 0x22, 0xc4, 0x39, 0xc4, 0x1c, 0xae, 0xa3, 0x96, ],
        # [0xc3, 0x0d, 0xfc, 0x93, 0x32, 0x5e, 0x5e, 0xda, 0x66, 0x40, 0x15, 0xaf, 0x9a, ],
        # [0xc3, 0x0d, 0x18, 0x29, 0x36, 0x5b, 0x98, 0xf6, 0x33, 0xc5, 0x66, 0xac, 0x99, ],
        # [c30d ea6f 38e2 4bd3 13a6 d016],
        # [],
        # [],
        # [],
        # [],
        # [
        #     0xc3,0x18,0x75,0xe1,0x31,0x06,0x1c,0xd8,0xe1,0x49,0x00,0x8d,0xb8,0x58,0x39,0x0f,0xe5,0x51,0x2d,0x33,0x98,0x04,0x07,0x39,
        # ],
        # [
        #     0xc3,0x44,0xad,0xf8,0x00,0xfa,0x8e,0x3c,0x50,0x10,0xec,0xa7,0x92,0x83,0x3e,0x6f,0x51,0x5e,0x17,0x92,0xc6,0x14,0xdd,0xe8,0x21,0xbe,0x12,0xed,0x63,0x26,0xd1,0x84,0xb0,0x06,0x33,0x9e,0xc9,0x58,0xbd,0xc6,0xab,0x10,0x38,0x81,0x05,0x30,0xb6,0x57,0x39,0x92,0x18,0xf9,0x33,0x10,0x14,0xf4,0xc1,0x46,0xfa,0x65,0xb5,0x8e,0x05,0xa2,0xc1,0x08,0xcb,0xfe,
        # ]
        [0xc3, 0x0d, 0xb1, 0xaf, 0x16, 0x25, 0x4f, 0x99, 0x75, 0xa0, 0xd1, 0x99, 0xa3, ],
        [0xc3, 0x0d, 0x38, 0x87, 0x0b, 0x28, 0x1a, 0x5c, 0x24, 0x01, 0x30, 0x6d, 0x57, ],
    ]

    for x in p:
        m = c.decrypt(bytearray(x))
        # print(m, m[28:32], m[33:])
        print([x for x in m])
        print(m, m[1], m[3], m[4] << 8 | m[5], m[6] << 8 | m[7], m[8])
        # na = [x << i*8 for i, x in enumerate(m[3:][::-1])]
        # n = 0
        # for x in na:
        #     n |= x
        # print([x for x in m], bin(n), n.bit_length())
    c2 = bytearray([0xc2, 0x00, 0x1d, 0x13, 0x02, 0x02, 0x1a, 0x06, 0x00, 0x00, 0x00, 0x80, 0xbc, 0x81, 0xbd, 0x40, 0x00, 0x07, 0xfc, 0x0e, 0x00, 0x00, 0x00, 0x8b, 0xae, 0x8b, 0xae, 0x30, 0x00, ])
    print([x for x in c2], c2)
    exit(0)
    m2 = c.decrypt(bytearray([0xc3, 0x0d, 0xa6, 0xf3, 0x14, 0xea, 0x0a, 0xbc, 0x62, 0xcc, 0xf5, 0x63, 0x56, ]))
    print(m2, m2[1], m2[3], m2[4] << 8 | m2[5], m2[6] << 8 | m2[7], m2[8])
    print([x for x in m2])

    m3 = c.decrypt(bytearray([0xc3, 0x0d, 0xff, 0x04, 0x34, 0x27, 0x0c, 0x9a, 0xb1, 0x4e, 0xf5, 0x8a, 0xbf, ]))
    print(m3, m3[1], m3[3], m3[4] << 8 | m3[5], m3[6] << 8 | m3[7], m3[8])
    print([x for x in m3])

    exit(0)


    exit(0)

    t = Timer()
    incoming_packet = bytearray([0xC3, 0x44, 0xAD, 0xF8, 0x00, 0xFA, 0x8E, 0x3C, 0x50, 0x10, 0xEC, 0xA7, 0x92, 0x83, 0x3E, 0x49, 0xDE, 0x93, 0xC6, 0x13, 0xDA, 0x88, 0x83, 0xB6, 0x9B, 0x04, 0x3A, 0x4B, 0x96, 0x27, 0xF1, 0xA1, 0x04, 0x44, 0x71, 0xCE, 0x18, 0x16, 0x1A, 0xA8, 0x0D, 0x70, 0xF5, 0x55, 0xA9, 0x9C, 0x28, 0xF6, 0x71, 0x9D, 0xC4, 0x30, 0xC3, 0x66, 0xE8, 0xED, 0xD8, 0xD3, 0xE5, 0x0E, 0x43, 0xCE, 0x13, 0x90, 0x36, 0x15, 0xDD, 0xE8])

    t.start()
    decrypted = c.decrypt(incoming_packet)
    print('decoded in', t.end())

    assert decrypted[0] == 0xC1, 'invalid class code'
    assert decrypted.head == 0xF1, 'invalid head code'
    assert decrypted.sub == 0x01, 'invalid sub code'
    assert decrypted.length == 49, 'invalid length'
    assert decrypted[4:14].strip(b'\0') == b'skpd', 'invalid login'
    assert chr(decrypted[-1]) == 'R', decrypted[-1]

    encrypted = c.encrypt(decrypted)
    assert encrypted[0] == 0xC3, 'invalid class code'

    decrypted2 = c.decrypt(encrypted)
    assert decrypted2[0] == 0xC1, 'invalid class code'
    assert decrypted2.head == 0xF1, 'invalid head code'
    assert decrypted2.sub == 0x01, 'invalid sub code'
    assert decrypted2.length == 49, 'invalid length'
    assert decrypted2[4:14].strip(b'\0') == b'skpd', 'invalid login'
    assert chr(decrypted2[-1]) == 'R', decrypted2[-1]

