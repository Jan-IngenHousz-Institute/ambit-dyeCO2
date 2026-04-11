#include <ArduinoJson.h>
#include <Wire.h>
#include "app/commands.h"
#include "app/bme68x_api.h"
#include "app/debug_api.h"
#include "app/spectrometer_api.h"


void handleCommandText(const String &cmd) {
  if (cmd == "hello") {
    Serial.println(F("Hello CO2 meter ready"));

  } else if (cmd == "env") {
    cmd_bme_read();

  } else if (cmd == "i2c_scan") {
    i2c_scan();

  } else if (cmd == "spec") {
    spectrometer_read();

  } else if (cmd.startsWith("set_led")) {
    int ledCurrent = 10;
    int comma = cmd.indexOf(',');
    if (comma > 0) {
      String arg = cmd.substring(comma + 1);
      arg.trim();
      ledCurrent = arg.toInt();
    }
    spectrometer_set_led_current(static_cast<uint16_t>(ledCurrent));

  } else if (cmd.startsWith("spec_flash")) {
    int ledCurrent = 10;
    int comma = cmd.indexOf(',');
    if (comma > 0) {
      String arg = cmd.substring(comma + 1);
      arg.trim();
      ledCurrent = arg.toInt();
    }
    spectrometer_read_flash(static_cast<uint16_t>(ledCurrent));

  } else if (cmd.startsWith("spec_set_atime")) {
    int comma = cmd.indexOf(',');
    const char *arg = (comma > 0) ? cmd.c_str() + comma + 1 : "";
    cmd_spectrometer_set_atime(comma > 0 ? 1 : 0, &arg);

  } else if (cmd.startsWith("spec_set_astep")) {
    int comma = cmd.indexOf(',');
    const char *arg = (comma > 0) ? cmd.c_str() + comma + 1 : "";
    cmd_spectrometer_set_astep(comma > 0 ? 1 : 0, &arg);

  } else if (cmd.startsWith("spec_set_gain")) {
    int comma = cmd.indexOf(',');
    const char *arg = (comma > 0) ? cmd.c_str() + comma + 1 : "";
    cmd_spectrometer_set_gain(comma > 0 ? 1 : 0, &arg);

  } else if (cmd == "spec_status") {
    cmd_spectrometer_status();

  } else if (cmd == "bme_status") {
    cmd_bme_status();

  } else if (cmd == "status") {
    // Single combined JSON line with both sub-objects, so the GUI sees one
    // message per "status" request.
    StaticJsonDocument<512> doc;
    JsonObject spec = doc["spectrometer_status"].to<JsonObject>();
    fill_spectrometer_status(spec);
    JsonObject bme = doc["bme_status"].to<JsonObject>();
    fill_bme_status(bme);
    serializeJson(doc, Serial);
    Serial.println();

  } else if (cmd == "reboot") {
    cmd_reboot();

  } else if (cmd.length() > 0) {
    Serial.println(F("unknown command"));
  }
}
