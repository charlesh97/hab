"""TMP100 temperature sensor driver — I2C 0x48, 12-bit signed, MSB first."""

from smbus2 import SMBus


class TMP100:
    """TMP100 temperature sensor on I2C bus 0, address 0x48."""

    ADDRESS = 0x48
    TEMP_REG = 0x00

    def __init__(self, bus_number: int = 0) -> None:
        self.bus = SMBus(bus_number)

    def read_temperature(self) -> float:
        """Read temperature in degrees Celsius."""
        msb, lsb = self.bus.read_i2c_block_data(self.ADDRESS, self.TEMP_REG, 2)
        raw = ((msb << 8) | lsb) >> 4  # 12-bit, left-justified in 16 bits
        if raw & 0x800:  # sign extend
            raw -= 1 << 12
        return raw * 0.0625

    def close(self) -> None:
        self.bus.close()

    def __enter__(self) -> "TMP100":
        return self

    def __exit__(self, *args) -> None:
        self.close()
