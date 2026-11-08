#include <Arduino_RouterBridge.h>
#include <DHT.h>

constexpr uint8_t DHT_PIN = 7;
constexpr unsigned long READ_INTERVAL_MS = 2500;
DHT sensor(DHT_PIN, DHT11);
unsigned long lastReadAt = 0;
int sequence = 0;

void setup() {
  Bridge.begin();
  Monitor.begin();
  sensor.begin();
  lastReadAt = millis();
  Monitor.println("DHT11_Test: data=D7. Reading temperature and humidity every 2.5 seconds.");
}

void loop() {
  const unsigned long now = millis();
  if (now - lastReadAt < READ_INTERVAL_MS) {
    delay(10);
    return;
  }
  lastReadAt = now;
  ++sequence;
  const float humidity = sensor.readHumidity();
  const float temperature = sensor.readTemperature();
  const bool valid = !isnan(humidity) && !isnan(temperature);
  if (valid) {
    Monitor.print("DHT11 reading | temperature_c=");
    Monitor.print(temperature);
    Monitor.print(" | humidity_pct=");
    Monitor.println(humidity);
  } else {
    Monitor.println("DHT11 read failed. No temperature or humidity value is assumed.");
  }
  // Fixed-point integers keep the MCU-to-Python message explicit and never send NaN.
  Bridge.notify("on_dht11_test", valid ? 1 : 0,
                valid ? static_cast<int>(round(temperature * 10)) : 0,
                valid ? static_cast<int>(round(humidity * 10)) : 0, sequence);
}
