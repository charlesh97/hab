#include <Arduino.h>
#include <Wire.h>

#define SDA 6
#define SCL 7

void setup() {
    Serial.begin(115200); delay(1000);
    Wire.begin(SDA, SCL);
    Wire.setClock(100000);
    Serial.println("Sweeping I2C 0x00-0x7F...\n");
}

void loop() {
    static unsigned long last = 0;
    if (millis() - last < 3000) return;
    last = millis();
    
    int n = 0;
    Serial.print("[");
    for (uint8_t a = 0; a < 0x80; a++) {
        Wire.beginTransmission(a);
        if (Wire.endTransmission() == 0) {
            if (a < 0x10) Serial.print("0");
            Serial.print(a, HEX);
            Serial.print(" ");
            n++;
        }
    }
    if (!n) Serial.print("none");
    Serial.printf("] %d device(s)\n", n);
}
