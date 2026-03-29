#pragma once
#include <Adafruit_AS7341.h>

extern bool as7341_available;

bool initAS7341();
uint8_t as7341_setAtIME(uint8_t atime_value);
uint8_t as7341_getAtIME();
uint16_t as7341_setAStep(uint16_t astep_value);
uint16_t as7341_getAStep();
bool as7341_setGain(as7341_gain_t gain);
bool as7341_setLEDCurrent(uint16_t led_current_ma);
bool as7341_readAll(uint16_t readings[12]);
void cmd_as7341_read();
void cmd_read_as7341_flash(int led_current_ma);

