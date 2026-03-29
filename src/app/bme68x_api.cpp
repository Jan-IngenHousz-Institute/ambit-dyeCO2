#include <Wire.h>
#include <bme68xLibrary.h>
#include "app/bme68x_api.h"



static constexpr uint8_t BME68X_ADDR = 0x76; // common: 0x76 or 0x77
Bme68x bme;

static void printBMEField(const bme68xData &d)
{
#ifdef BME68X_USE_FPU
  Serial.print("{\"T\":");
  Serial.print(d.temperature, 2);
  Serial.print(",\"P\":");
  Serial.print(d.pressure / 100.0f, 2);
  Serial.print(",\"RH\":");
  Serial.print(d.humidity, 2);
  Serial.print(",\"Gas\":");
  Serial.print(d.gas_resistance, 0);
  Serial.println("}");
#else
  // Bosch fixed-point defaults:
  // temperature: °C * 100, humidity: %RH * 1000, pressure: Pa, gas_resistance: Ω
  Serial.print("T=");
  Serial.print(d.temperature / 100.0f, 2);
  Serial.print(" °C  P=");
  Serial.print(d.pressure / 100.0f, 2);
  Serial.print(" hPa  RH=");
  Serial.print(d.humidity / 1000.0f, 3);
  Serial.print(" %  Gas=");
  Serial.print(d.gas_resistance);
  Serial.println(" Ω");
#endif
}

bool initBME(void) {
  bme.begin(BME68X_ADDR, Wire);
  if (bme.checkStatus() != 0) {   
    Serial.print("BME68x init failed with status string: ");
    Serial.println(bme.statusString());
    return false;
  }
  // Configure BME68x Forced mode + filter
  bme.setTPH(BME68X_OS_2X, BME68X_OS_4X, BME68X_OS_2X);
  bme.setFilter(BME68X_FILTER_OFF);
  bme.setHeaterProf(320 /*°C*/, 150 /*ms*/);   // Gas heater for forced mode (example profile)
  bme.setOpMode(BME68X_FORCED_MODE); //  = one-shot measurement when you trigger it
  return true;
}


bool bme_read(void){
    if (!bme_available) {
      Serial.println("bme68x not available");
      return false;
    }
    bme.setOpMode(BME68X_FORCED_MODE);
    // Wait long enough for measurement + heater
    uint32_t dur_us = bme.getMeasDur(BME68X_FORCED_MODE);
    delayMicroseconds(dur_us + 150000); // + heater duration (150ms)
    // Fetch and print all returned fields
    uint8_t n = bme.fetchData();
    if (bme.checkStatus() != 0) {
    Serial.print("fetchData error: ");
    Serial.println(bme.statusString());
    return false;
    }
    if (n > 0) {
        bme68xData *all = bme.getAllData();
        for (uint8_t i = 0; i < n; i++) {
        printBMEField(all[i]);
        }
    }
    return true;
}

void cmd_bme_read(){
    if (!bme_available) {
      Serial.println("bme68x not available");
      return;
    }
    Serial.print(F("\"bme_read\":")); 
    bme_read();
}