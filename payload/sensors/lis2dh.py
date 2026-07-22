from smbus2 import SMBus


class LIS2DH:
    ADDRESS = 0x19
    WHO_AM_I = 0x0F
    WHO_AM_I_VALUE = 0x33
    CTRL_REG1 = 0x20
    OUT_X_L = 0x28
    AUTO_INCREMENT = 0x80

    def __init__(self, bus_number):
        self.bus = SMBus(bus_number)
        try:
            device_id = self.bus.read_byte_data(self.ADDRESS, self.WHO_AM_I)
            if device_id != self.WHO_AM_I_VALUE:
                raise RuntimeError(
                    f"Unexpected LIS2DH WHO_AM_I value: 0x{device_id:02X}"
                )
            self.bus.write_byte_data(self.ADDRESS, self.CTRL_REG1, 0x47)
        except Exception:
            self.close()
            raise

    @staticmethod
    def _convert_axis(low, high):
        raw = (high << 8) | low
        if raw & 0x8000:
            raw -= 0x10000
        return float((raw >> 6) * 4)

    def read_accel(self):
        if self.bus is None:
            raise RuntimeError("LIS2DH bus is closed")

        data = self.bus.read_i2c_block_data(
            self.ADDRESS,
            self.OUT_X_L | self.AUTO_INCREMENT,
            6,
        )
        return (
            self._convert_axis(data[0], data[1]),
            self._convert_axis(data[2], data[3]),
            self._convert_axis(data[4], data[5]),
        )

    def close(self):
        if self.bus is not None:
            self.bus.close()
            self.bus = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
