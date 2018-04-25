#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import io
import os
import sys


class BinStream:
    def __init__(self):
        self.fd = None

        self.size = 0
        self.pos = 0
        self.name = ""

        self.data_byteorder = sys.byteorder

    def open(self, filename):
        self.name = filename
        self.fd = io.open(filename, 'rb')
        self.size = os.stat(filename).st_size

    def close(self):
        self.fd.close()
        self.size = 0
        self.pos = 0

    def eof(self):
        return self.pos >= self.size

    def check_data_available(self, size=1):
        return self.pos + size <= self.size

    def read_bytes(self, size=1):
        if not self.check_data_available(size):
            raise IOError("Unexpected EOF while trying to read {0} bytes"
                          .format(size))

        data = self.fd.read(size)
        self.pos += size

        return data

    def read_byte(self):
        if not self.check_data_available(1):
            raise IOError("Unexpected EOF while trying to read 1 byte")

        data = self.fd.read(1)
        self.pos += 1

        return int.from_bytes(data,
                              byteorder=sys.byteorder,
                              signed=False)

    def read_zstring(self):
        string = b''

        while not self.eof():
            byte = self.read_bytes(1)

            if byte == b'\x00':
                return string
            else:
                string += byte

        return string

    def read_uleb128(self):
        value = self.read_byte()

        if value >= 0x80:
            bitshift = 0
            value &= 0x7f

            while True:
                byte = self.read_byte()

                bitshift += 7
                value |= (byte & 0x7f) << bitshift

                if byte < 0x80:
                    break

        return value

    def read_uleb128_str(self, length=1):
        string = ""
        i = 0

        while length > i:
            string += chr(self.read_uleb128())
            i = i + 1

        return string

    @staticmethod
    def decode_uleb128(buff, buff_len):
        string = ""
        i = 0

        while buff_len > i:
            value = buff[i]
            i = i + 1

            print(str(value))
            print(chr(value))
            print(value >= 0x80)

            if value >= 0x80 and buff_len > i:
                bitshift = 0
                value &= 0x7f

                print(str(value))
                print(chr(value))

                while buff_len > i:
                    byte = buff[i]
                    i = i + 1

                    bitshift += 7
                    value |= (byte & 0x7f) << bitshift

                    if byte < 0x80:
                        break

            print(str(value))
            print(chr(value))

            if value == 0 or value == 128:
                string += "\\" + str(value)
            else:
                string += chr(value)

        return string

    def read_uleb128_from33bit(self):
        first_byte = self.read_byte()

        is_number_bit = first_byte & 0x1
        value = first_byte >> 1

        if value >= 0x40:
            bitshift = -1
            value &= 0x3f

            while True:
                byte = self.read_byte()

                bitshift += 7
                value |= (byte & 0x7f) << bitshift

                if byte < 0x80:
                    break

        return is_number_bit, value

    def read_uint(self, size=4):
        value = self.read_bytes(size)

        return int.from_bytes(value, byteorder=self.data_byteorder,
                              signed=False)
