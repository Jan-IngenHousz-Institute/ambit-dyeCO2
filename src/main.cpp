#include <Arduino.h>
#include <Wire.h>
#include "app/commands.h"
#include "app/bme68x_api.h"
#include "app/as7341_api.h"

bool bme_available = false;
bool as7341_available = false;

String line;
enum class RxMode { UNKNOWN, LINE, JSON };
String rx;
RxMode mode = RxMode::UNKNOWN;
int braceDepth = 0;   // {}
int bracketDepth = 0; // []
bool inString = false;
char prev = 0;

void resetRx() {
  rx = "";
  mode = RxMode::UNKNOWN;
  braceDepth = 0;
  bracketDepth = 0;
  inString = false;
  prev = 0;
}

void setup() {
  
  Serial.begin(115200);

  Wire.begin(3, 4);

  // BME68x initialization
  bme_available = initBME();
  if (!bme_available) {
    Serial.println("BME68x initialization failed. Check connections and I2C address.");
  } else {
    Serial.println("BME68x initialized successfully.");
  }

  // AS7341 initialization
  as7341_available = initAS7341();
  if (!as7341_available) {
    Serial.println("AS7341 initialization failed. Check connections and I2C address.");
  } else {
    Serial.println("AS7341 initialized successfully.");
  }

  

}
 


void loop() {
while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r')
      continue;

    rx += c;

    // Decide mode once we see the first non-whitespace char
    if (mode == RxMode::UNKNOWN) {
      // find first non-space char in the current buffer
      int i = 0;
      while (i < (int)rx.length() && isspace((unsigned char)rx[i]))
        i++;
      if (i < (int)rx.length()) {
        char first = rx[i];
        if (first == '{' || first == '[') {
          mode = RxMode::JSON; // start JSON mode (typically openJII app series of commands)
        } else {
          mode = RxMode::LINE; // start LINE mode (simple single-line commands)
        }
      }
    }

    // LINE mode: only process on newline
    if (mode == RxMode::LINE) {
      if (c == '\n') {
        rx.trim();
        if (rx.length() > 0)
          handleCommandText(rx);
        resetRx();
      }
      continue;
    }

    // JSON mode: track braces/brackets until outermost closes
    if (mode == RxMode::JSON) {
      if (c == '"' && prev != '\\')
        inString = !inString;

      if (!inString) {
        if (c == '{')
          braceDepth++;
        else if (c == '}')
          braceDepth--;
        else if (c == '[')
          bracketDepth++;
        else if (c == ']')
          bracketDepth--;
      }

      prev = c;

      // Only declare "complete" after the top-level JSON object/array closes.
      if (!inString && braceDepth == 0 && bracketDepth == 0) {
        rx.trim();
        // bool ok = HandleCommandJson(rx);
        bool ok = false; // TODO: implement JSON commands and set this accordingly
        if (!ok)
          Serial.println("json_error");
        resetRx();
      }
      continue;
    }

    // Safety: prevent runaway buffer
    if (rx.length() > 2048) {
      Serial.println("rx_overflow");
      resetRx();
    }
  }
}







