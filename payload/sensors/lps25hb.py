from smbus2 import SMBus


class LPS25HB:
    ADDRESS = 0x5D
    WHO_AM_I = 0x0F
    WHO_AM_I_VALUE = 0xBD
    CTRL_REG1 = 0x20
    PRESS_OUT_XL = 0x28
    TEMP_OUT_L = 0x2B
    AUTO_INCREMENT = 0x80

    def __init__(self, bus_number: int):
        self._bus = SMBus(bus_number)

        try:
            device_id = self._bus.read_byte_data(self.ADDRESS, self.WHO_AM_I)
            if device_id != self.WHO_AM_I_VALUE:
                raise RuntimeError(
                    f"Unexpected LPS25HB WHO_AM_I value: 0x{device_id:02X}"
                )

            self._bus.write_byte_data(self.ADDRESS, self.CTRL_REG1, 0xC0)
        except Exception:
            self.close()
            raise

    def read_pressure(self) -> float:
        data = self._bus.read_i2c_block_data(
            self.ADDRESS,
            self.PRESS_OUT_XL | self.AUTO_INCREMENT,
            3,
        )
        raw = data[0] | (data[1] << 8) | (data[2] << 16)
        return raw / 4096.0

    def read_temperature(self) -> float:
        data = self._bus.read_i2c_block_data(
            self.ADDRESS,
            self.TEMP_OUT_L | self.AUTO_INCREMENT,
            2,
        )
        raw = int.from_bytes(bytes(data), byteorder="little", signed=True)
        return 42.5 + raw / 480.0

    def close(self) -> None:
        if self._bus is not None:
            self._bus.close()
            self._bus = None

    def __enter__(self) -> "LPS25HB":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
