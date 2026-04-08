#include <Arduino.h>
#include <Wire.h>
#include "app/commands.h"
#include "app/bme68x_api.h"
#include "app/spectrometer_api.h"

bool bme_available = false;

static String rx;

void setup() {
  Serial.begin(115200);
  Wire.begin(3, 4);

  bme_available = initBME();
  #if DEBUG
  if (!bme_available)
    Serial.println(F("[init] BME68x not found"));
  else
    Serial.println(F("[init] BME68x OK"));
  #endif

  initSpectrometer();
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r')
      continue;
    if (c == '\n') {
      rx.trim();
      if (rx.length() > 0)
        handleCommandText(rx);
      rx = "";
      continue;
    }
    rx += c;
    if (rx.length() > 2048) {
      rx = "";
    }
  }
}





