#include <Wire.h>
#include <Adafruit_AS7341.h>

Adafruit_AS7341 as7341;

bool initAS7341(void) {
  if (!as7341.begin()){
    Serial.println("Could not find AS7341");
    while (1) { delay(10); }
  } else {
    Serial.println("AS7341 Found!");
    as7341.setATIME(100);
    as7341.setASTEP(999);
    as7341.setGain(AS7341_GAIN_4X);
  }
  return true;
}


uint8_t as7341_setAtIME(uint8_t atime_value) {
  return as7341.setATIME(atime_value);
}

uint8_t as7341_getAtIME() {
  return as7341.getATIME();
}

uint16_t as7341_setAStep(uint16_t astep_value) {
  return as7341.setASTEP(astep_value);
}

uint16_t as7341_getAStep() {
  return as7341.getASTEP();
}


bool as7341_setGain(as7341_gain_t gain) {
  if (!as7341.setGain(gain)) {
    Serial.println("AS7341: setGain failed");
    return false;
  }

  if (as7341.getGain() != gain) {
    Serial.println("AS7341: gain readback mismatch");
    return false;
  }

  return true;
}


bool as7341_setLEDCurrent(uint16_t led_current_ma) {
  bool enable_led = false;
  uint8_t requested_current = led_current_ma;

  if (led_current_ma > 20) {
    Serial.println("AS7341: LED current must be <= 20 mA");
    led_current_ma = 20; // Cap to max 
  } else if (led_current_ma == 0) {
    enable_led = false; // if 0 mA requested, disable LED
  } else {
    enable_led = true; // Enable LED for any non-zero current
  }
  
  if (!as7341.setLEDCurrent(led_current_ma)) {
    Serial.println("AS7341: setLEDCurrent failed");
    return false;
  } 

  // Normalize requested current to the value actually representable by the device
  // Adafruit AS7341 uses 4mA minimum and 2mA quantization steps.
  uint16_t normalized_current_ma = led_current_ma;
  if (normalized_current_ma < 4) {
    normalized_current_ma = 4;
  }
  normalized_current_ma = 4 + (((normalized_current_ma - 4) / 2) * 2);
 
  if (as7341.getLEDCurrent() != normalized_current_ma) {
    Serial.println("AS7341: LED current readback mismatch");
    if (requested_current != led_current_ma) {
      Serial.print("AS7341: requested current: ");
      Serial.print(requested_current);
      Serial.print("mA, normalized request: ");
      Serial.print(normalized_current_ma);
      Serial.print("mA, readback: ");
      Serial.print(as7341.getLEDCurrent());
      Serial.println("mA");
    }
    return false;
  }
  
  as7341.enableLED(enable_led); // switch LED on

  return true;
}

bool as7341_readAll(uint16_t readings[12]) {
    // Read all channels and print them in a JSON-like format
  if (!as7341.readAllChannels(readings)) {
    Serial.println("Error reading all channels!");
    return false;
  }

  Serial.print("{\"415nm\":");
  Serial.print(readings[0]);
  Serial.print(",\"445nm\":");
  Serial.print(readings[1]);
  Serial.print(",\"480nm\":");
  Serial.print(readings[2]);
  Serial.print(",\"515nm\":");
  Serial.print(readings[3]);
  Serial.print(",\"555nm\":");
  Serial.print(readings[6]);
  Serial.print(",\"590nm\":");
  Serial.print(readings[7]);
  Serial.print(",\"630nm\":");
  Serial.print(readings[8]);
  Serial.print(",\"680nm\":");
  Serial.print(readings[9]);
  Serial.print(",\"Clear\":");
  Serial.print(readings[10]);
  Serial.print(",\"NIR\":");
  Serial.print(readings[11]);
  Serial.print("}");
  Serial.println();

  return true;
}



void cmd_as7341_read(){
    Serial.print(F("\"as7341\":")); 
    uint16_t reads[12];
    as7341_readAll(reads);
}

void cmd_read_as7341_flash(int arg){
    // print the AS7341 read with LED off and on, and the difference.
    int ledCurrent = 10; // default LED current in mA
    if (arg >= 0) {
      ledCurrent = arg;
    }

    Serial.print(F("\"as7341_dark\":")); 
    uint16_t drk[12];
    uint16_t lit[12];
    uint16_t dif[12] = {0};
    as7341_readAll(drk);
    as7341_setLEDCurrent(ledCurrent); 
    Serial.print(F(",\"as7341_lit\":")); 
    as7341_readAll(lit);
    as7341_setLEDCurrent(0); 
    Serial.print(F(",\"as7341_dif\":")); 
  
    for (int i = 0; i < 12; i++) {
      dif[i] = lit[i] > drk[i] ? lit[i] - drk[i] : 0;
    }
    
    Serial.print("{\"415nm\":");
    Serial.print(dif[0]);
    Serial.print(",\"445nm\":");
    Serial.print(dif[1]);
    Serial.print(",\"480nm\":");
    Serial.print(dif[2]);
    Serial.print(",\"515nm\":");
    Serial.print(dif[3]);
    Serial.print(",\"555nm\":");
    Serial.print(dif[6]);
    Serial.print(",\"590nm\":");
    Serial.print(dif[7]);
    Serial.print(",\"630nm\":");
    Serial.print(dif[8]);
    Serial.print(",\"680nm\":");
    Serial.print(dif[9]);
    Serial.print(",\"Clear\":");
    Serial.print(dif[10]);
    Serial.print(",\"NIR\":");
    Serial.print(dif[11]);
    Serial.println("}");
    

}