import sys
from mup.common.crypt import decrypt, load_keys

if __name__ == '__main__':
    raw_data = sys.argv[1].replace(' ', '')
    data = bytearray()
    for i in range(0, len(raw_data), 2):
        data.append(int(raw_data[i] + raw_data[i+1], 16))
    load_keys(sys.path[0] + '/../data/Dec1.dat', use_global=True, decode_keys=True)
    res = decrypt(data)
    print(res.length, len(res.hex()) / 2, res.hex())

