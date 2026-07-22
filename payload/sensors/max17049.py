from smbus2 import SMBus


class MAX17049:
    ADDRESS = 0x36
    VCELL_REGISTER = 0x02
    SOC_REGISTER = 0x04
    VERSION_REGISTER = 0x08

    def __init__(self, bus_number: int = 1) -> None:
        self.bus = SMBus(bus_number)

    def _read_word(self, register: int) -> int:
        msb, lsb = self.bus.read_i2c_block_data(
            self.ADDRESS, register, 2
        )
        return (msb << 8) | lsb

    def read_voltage(self) -> float:
        return self._read_word(self.VCELL_REGISTER) * 78.125e-6

    def read_soc(self) -> float:
        return self._read_word(self.SOC_REGISTER) / 256.0

    def read_version(self) -> int:
        return self._read_word(self.VERSION_REGISTER)

    def close(self) -> None:
        self.bus.close()

    def __enter__(self) -> "MAX17049":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
