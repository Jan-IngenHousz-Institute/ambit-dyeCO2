#include <Arduino.h>
#include <Wire.h>

#include "app/as7343_api.h"

namespace {

constexpr uint8_t kAs7343I2cAddress = 0x39;
constexpr uint8_t kAs7343Cfg0Register = 0xBF;
constexpr uint8_t kAs7343RegBankBitMask = 0x10;
constexpr uint8_t kAs7343ChipIdRegister = 0x5A;
constexpr uint8_t kAs7343ChipId = 0x81;

bool writeRegister8(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(kAs7343I2cAddress);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool readRegister8(uint8_t reg, uint8_t *value) {
  if (value == nullptr) {
    return false;
  }

  Wire.beginTransmission(kAs7343I2cAddress);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  const uint8_t bytes_requested = 1;
  if (Wire.requestFrom(static_cast<int>(kAs7343I2cAddress),
                       static_cast<int>(bytes_requested)) != bytes_requested) {
    return false;
  }

  *value = Wire.read();
  return true;
}

bool setRegisterBank1(uint8_t *original_cfg0) {
  if (original_cfg0 == nullptr) {
    return false;
  }

  if (!readRegister8(kAs7343Cfg0Register, original_cfg0)) {
    return false;
  }

  const uint8_t bank1_cfg0 = *original_cfg0 | kAs7343RegBankBitMask;
  if (bank1_cfg0 == *original_cfg0) {
    return true;
  }

  return writeRegister8(kAs7343Cfg0Register, bank1_cfg0);
}

bool restoreRegisterBank(uint8_t original_cfg0) {
  return writeRegister8(kAs7343Cfg0Register, original_cfg0);
}

bool readBank1Register8(uint8_t reg, uint8_t *value) {
  uint8_t original_cfg0 = 0;
  if (!setRegisterBank1(&original_cfg0)) {
    return false;
  }

  const bool read_ok = readRegister8(reg, value);
  const bool restore_ok = restoreRegisterBank(original_cfg0);
  return read_ok && restore_ok;
}

} // namespace

bool as7343_readChipId(uint8_t *chip_id) {
  return readBank1Register8(kAs7343ChipIdRegister, chip_id);
}

bool initAS7343() {
  uint8_t chip_id = 0;
  if (!as7343_readChipId(&chip_id)) {
    return false;
  }

  return chip_id == kAs7343ChipId;
}
