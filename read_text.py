import sys

k = [0xFC, 0xCF, 0xAB]
lines = []
contents = ''

with open(sys.argv[1], 'rb') as f:
    for i, x in enumerate(f.read()):
        contents += chr(x ^ k[i % 3])

for i in range(0, len(contents), 300):
    line = contents[i:i+300].strip('\0')
    lines.append(line)

print(lines)
