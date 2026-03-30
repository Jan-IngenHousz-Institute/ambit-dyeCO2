#pragma once

#include <Arduino.h>
#include <stdint.h>

enum class SpectrometerModel : uint8_t {
  None,
  AS7341,
  AS7343,
  ProbePendingAt0x39,
  UnknownAt0x39,
};

extern bool spectrometer_available;
extern SpectrometerModel spectrometer_model;

const char *spectrometerModelName(SpectrometerModel model);
bool initSpectrometer();
bool spectrometerPrepareLegacyCommand();
bool spectrometer_read();
bool spectrometer_set_led_current(uint16_t led_current_ma);
bool spectrometer_read_flash(uint16_t led_current_ma);
void spectrometerPrintNotAvailableError();
void spectrometerPrintUnsupportedDeviceError();
