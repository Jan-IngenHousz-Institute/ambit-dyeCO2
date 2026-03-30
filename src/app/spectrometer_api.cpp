#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_AS7341.h>

#include "app/as7341_api.h"
#include "app/as7343_api.h"
#include "app/spectrometer_api.h"

bool spectrometer_available = false;
SpectrometerModel spectrometer_model = SpectrometerModel::None;
bool as7341_available = false;

namespace {

constexpr uint8_t kSpectrometerI2cAddress = 0x39;
constexpr uint32_t kProbeRetryWindowUs = 5000;
constexpr uint32_t kProbeRetryIntervalUs = 250;
constexpr bool kSpectrometerDetectionDebug = true;

struct DetectionResult {
  SpectrometerModel model = SpectrometerModel::None;
  bool saw_ack = false;
};

struct DetectionDebugInfo {
  uint32_t attempts = 0;
  bool saw_ack = false;
  bool as7343_id_read_ok = false;
  uint8_t as7343_chip_id = 0;
  bool as7341_id_read_ok = false;
  uint8_t as7341_chip_id = 0;
};

void syncLegacyAvailability() {
  as7341_available =
      spectrometer_available && spectrometer_model == SpectrometerModel::AS7341;
}

void setSpectrometerState(SpectrometerModel model, bool available) {
  spectrometer_model = model;
  spectrometer_available = available;
  syncLegacyAvailability();
}

bool spectrometerAddressAcks() {
  Wire.beginTransmission(kSpectrometerI2cAddress);
  return Wire.endTransmission() == 0;
}

bool readAs7341WhoAmI(uint8_t *chip_id) {
  if (chip_id == nullptr) {
    return false;
  }

  Wire.beginTransmission(kSpectrometerI2cAddress);
  Wire.write(AS7341_WHOAMI);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  const uint8_t bytes_requested = 1;
  if (Wire.requestFrom(static_cast<int>(kSpectrometerI2cAddress),
                       static_cast<int>(bytes_requested)) != bytes_requested) {
    return false;
  }

  *chip_id = Wire.read();
  return true;
}

void printHexByte(uint8_t value) {
  if (value < 0x10) {
    Serial.print('0');
  }
  Serial.print(value, HEX);
}

void printDetectionDebug(const char *reason, const DetectionDebugInfo &debug,
                         SpectrometerModel result_model,
                         bool initialized) {
  if (!kSpectrometerDetectionDebug) {
    return;
  }

  Serial.print(F("[spectrometer-debug] reason="));
  Serial.print(reason);
  Serial.print(F(" attempts="));
  Serial.print(debug.attempts);
  Serial.print(F(" ack="));
  Serial.print(debug.saw_ack ? F("1") : F("0"));
  Serial.print(F(" as7343_id_ok="));
  Serial.print(debug.as7343_id_read_ok ? F("1") : F("0"));
  Serial.print(F(" as7343_id=0x"));
  printHexByte(debug.as7343_chip_id);
  Serial.print(F(" as7341_id_ok="));
  Serial.print(debug.as7341_id_read_ok ? F("1") : F("0"));
  Serial.print(F(" as7341_id=0x"));
  printHexByte(debug.as7341_chip_id);
  Serial.print(F(" result="));
  Serial.print(spectrometerModelName(result_model));
  Serial.print(F(" init_ok="));
  Serial.println(initialized ? F("1") : F("0"));
}

DetectionResult detectSpectrometerWithinRetryWindow(DetectionDebugInfo *debug) {
  DetectionResult result;
  const uint32_t started_at = micros();

  while ((micros() - started_at) < kProbeRetryWindowUs) {
    if (debug != nullptr) {
      debug->attempts++;
    }

    if (spectrometerAddressAcks()) {
      result.saw_ack = true;
      if (debug != nullptr) {
        debug->saw_ack = true;
      }

      uint8_t as7343_chip_id = 0;
      const bool as7343_read_ok = as7343_readChipId(&as7343_chip_id);
      if (debug != nullptr) {
        debug->as7343_id_read_ok = as7343_read_ok;
        if (as7343_read_ok) {
          debug->as7343_chip_id = as7343_chip_id;
        }
      }
      if (as7343_read_ok && as7343_chip_id == 0x81) {
        result.model = SpectrometerModel::AS7343;
        return result;
      }

      uint8_t as7341_chip_id = 0;
      const bool as7341_read_ok = readAs7341WhoAmI(&as7341_chip_id);
      if (debug != nullptr) {
        debug->as7341_id_read_ok = as7341_read_ok;
        if (as7341_read_ok) {
          debug->as7341_chip_id = as7341_chip_id;
        }
      }
      if (as7341_read_ok &&
          ((as7341_chip_id & 0xFC) == (AS7341_CHIP_ID << 2))) {
        result.model = SpectrometerModel::AS7341;
        return result;
      }
    }

    delayMicroseconds(kProbeRetryIntervalUs);
  }

  result.model = result.saw_ack ? SpectrometerModel::ProbePendingAt0x39
                                : SpectrometerModel::None;
  return result;
}

bool initializeDetectedSpectrometer(SpectrometerModel model) {
  switch (model) {
  case SpectrometerModel::AS7341:
    return initAS7341();
  case SpectrometerModel::AS7343:
    return initAS7343();
  default:
    return false;
  }
}

bool detectAndInitialize(bool promote_pending_to_unknown, const char *reason) {
  DetectionDebugInfo debug;
  const DetectionResult detection = detectSpectrometerWithinRetryWindow(&debug);

  if (detection.model == SpectrometerModel::AS7341 ||
      detection.model == SpectrometerModel::AS7343) {
    const bool initialized = initializeDetectedSpectrometer(detection.model);
    setSpectrometerState(detection.model, initialized);
    printDetectionDebug(reason, debug, spectrometer_model, initialized);
    return initialized;
  }

  if (promote_pending_to_unknown &&
      detection.model == SpectrometerModel::ProbePendingAt0x39) {
    setSpectrometerState(SpectrometerModel::UnknownAt0x39, false);
    printDetectionDebug(reason, debug, spectrometer_model, false);
    return false;
  }

  setSpectrometerState(detection.model, false);
  printDetectionDebug(reason, debug, spectrometer_model, false);
  return false;
}

} // namespace

const char *spectrometerModelName(SpectrometerModel model) {
  switch (model) {
  case SpectrometerModel::AS7341:
    return "AS7341";
  case SpectrometerModel::AS7343:
    return "AS7343";
  case SpectrometerModel::ProbePendingAt0x39:
    return "ProbePendingAt0x39";
  case SpectrometerModel::UnknownAt0x39:
    return "UnknownAt0x39";
  case SpectrometerModel::None:
  default:
    return "None";
  }
}

bool initSpectrometer() {
  const bool initialized = detectAndInitialize(false, "boot");

  switch (spectrometer_model) {
  case SpectrometerModel::AS7341:
    Serial.println(F("Spectrometer detected: AS7341"));
    break;
  case SpectrometerModel::AS7343:
    Serial.println(F("Spectrometer detected: AS7343"));
    break;
  case SpectrometerModel::ProbePendingAt0x39:
    Serial.println(
        F("Unidentified spectrometer at 0x39, will retry on first command"));
    break;
  case SpectrometerModel::None:
    Serial.println(F("No spectrometer detected at 0x39"));
    break;
  case SpectrometerModel::UnknownAt0x39:
  default:
    Serial.println(F("No spectrometer detected at 0x39"));
    break;
  }

  return initialized;
}

void spectrometerPrintNotAvailableError() {
  Serial.println(F("\"spectrometer\":{\"error\":\"not_available\"}"));
}

void spectrometerPrintUnsupportedDeviceError() {
  Serial.println(F("\"spectrometer\":{\"error\":\"unsupported_device_at_0x39\"}"));
}

bool spectrometerPrepareLegacyCommand() {
  if (spectrometer_model == SpectrometerModel::ProbePendingAt0x39) {
    detectAndInitialize(true, "legacy_cmd_retry");
  }

  if (spectrometer_model == SpectrometerModel::UnknownAt0x39) {
    spectrometerPrintUnsupportedDeviceError();
    return false;
  }

  if (!spectrometer_available) {
    spectrometerPrintNotAvailableError();
    return false;
  }

  return true;
}

bool spectrometer_read() {
  if (!spectrometerPrepareLegacyCommand()) {
    return false;
  }

  if (!as7341_available) {
    spectrometerPrintNotAvailableError();
    return false;
  }

  cmd_as7341_read();
  return true;
}

bool spectrometer_set_led_current(uint16_t led_current_ma) {
  if (!spectrometerPrepareLegacyCommand()) {
    return false;
  }

  if (!as7341_available) {
    spectrometerPrintNotAvailableError();
    return false;
  }

  return as7341_setLEDCurrent(led_current_ma);
}

bool spectrometer_read_flash(uint16_t led_current_ma) {
  if (!spectrometerPrepareLegacyCommand()) {
    return false;
  }

  if (!as7341_available) {
    spectrometerPrintNotAvailableError();
    return false;
  }

  cmd_read_as7341_flash(static_cast<int>(led_current_ma));
  return true;
}
