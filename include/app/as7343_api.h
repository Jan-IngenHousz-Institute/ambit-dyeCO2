#pragma once

#include <Arduino.h>

bool initAS7343();
bool as7343_readChipId(uint8_t *chip_id);
