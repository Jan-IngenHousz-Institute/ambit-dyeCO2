# Fix Plan: firmware-ambit_dyeCO2-main

Fix all 16 issues from the critical review in 4 phases: safety-critical hardware bugs first, then sensor driver robustness, then command infrastructure wiring, then cleanup. Hardware tests are required after Phases 1, 2, and 3.

---

## Phase 1: Safety-Critical Fixes

### Step 1.1 — Fix `initAS7341()` infinite loop *(Issue #1)*
- **File:** `src/app/as7341_api.cpp`
- Remove `while (1) { delay(10); }` and replace with `return false;`
- `setup()` in `src/main.cpp` already handles the `false` return

### Step 1.2 — Centralize I2C init and fix pin conflict *(Issue #2)*
- **File:** `src/main.cpp` — add `Wire.begin(3, 4);` in `setup()` **after** `Serial.begin(115200)` and **before** any sensor init
- **File:** `src/app/bme68x_api.cpp` — remove `Wire.begin(I2C_SDA, I2C_SCL);` from `initBME()`
- **File:** `src/app/debug_api.cpp` — remove `Wire.begin(18, 19);` and `Wire.setClock(100000);` from `i2c_scan()`
- This eliminates the pin conflict and prevents any module from re-initializing the bus on wrong pins

### Step 1.3 — Add include guards *(Issue #3)*
- **Files:** `include/app/as7341_api.h`, `include/app/bme68x_api.h`
- Add `#pragma once` at the top of each file

### Step 1.4 — Add sensor availability flags *(new — graceful degradation)*
- **File:** `src/main.cpp` — store `initBME()` / `initAS7341()` results in global `bool bme_available` / `bool as7341_available`
- **Files:** `include/app/bme68x_api.h`, `include/app/as7341_api.h` — declare the flags as `extern bool`
- **Guard at the API layer, not the command layer:** add availability checks at the top of `as7341_readAll()`, `as7341_setLEDCurrent()`, `cmd_as7341_read()`, `cmd_read_as7341_flash()` in `src/app/as7341_api.cpp`, and `bme_read()`, `cmd_bme_read()` in `src/app/bme68x_api.cpp`. Each should print an error (e.g. `"as7341 not available"`) and return early. This way the guards survive regardless of whether the caller is the if-else chain, the dispatch table, or direct API use
- Note: `as7341_setGain()` is not called from anywhere in the codebase — no guard needed

### >>> HARDWARE TEST CHECKPOINT 1 <<<
- [ ] Device boots with both sensors connected
- [ ] Device boots with AS7341 **disconnected** — prints warning, does NOT hang
- [ ] With AS7341 disconnected, `as7341_read` prints `"as7341 not available"` instead of crashing
- [ ] Run `i2c_scan`, then `bme_read` — BME68x still responds after scan
- [ ] `as7341_read` returns valid spectral data (with sensor connected)

---

## Phase 2: Sensor Driver Robustness

### Step 2.1 — Fix `as7341_setLEDCurrent()` *(Issues #6, #7)*
- **File:** `src/app/as7341_api.cpp`
- Change `uint8_t requested_current` → `uint16_t` (fix truncation)
- Restructure enable logic: `enable_led = (led_current_ma > 0);` before the >20 cap
- When `led_current_ma == 0` (disable path): skip `setLEDCurrent` / readback entirely, just call `enableLED(false)` and return `true`. The current code tries to set 0 mA, then the normalization logic computes 4 mA, causing readback mismatch → the function returns `false` before ever disabling the LED

### Step 2.2 — Fix `bme_read()` robustness *(Issues #8, #9)*
- **File:** `src/app/bme68x_api.cpp`
- Null-check `bme.getAllData()` return
- Return `false` when `n == 0` (no data case)

### Step 2.3 — Extract duplicated JSON printing *(Issue #10)*
- **File:** `src/app/as7341_api.cpp`
- Extract a `static void printSpectralJson(const uint16_t data[12])` helper — must **not** include a trailing `println()`/newline; callers control line endings. The current `as7341_readAll()` appends `Serial.println()` after the JSON object, which breaks multi-key output composition in `cmd_read_as7341_flash()`
- Call it from both `as7341_readAll()` and `cmd_read_as7341_flash()`

### >>> HARDWARE TEST CHECKPOINT 2 <<<
- [ ] `set_led,0` disables LED; `set_led,10` enables at 10 mA; `set_led,25` caps to 20 mA **and LED turns on**
- [ ] `as7341_read_flash` produces correct dark/lit/diff readings
- [ ] `bme_read` returns valid data; with sensor disconnected returns error (no crash)

---

## Phase 3: Command Infrastructure & JSON Path

### Step 3.1 — Write `CmdFn`-compatible wrappers *(Issues #5, #14)*
- **File:** `src/app/commands.cpp`
- Create thin wrappers matching `bool (*)(int argc, const char *argv[])` for:
  - `cmd_bme_read`
  - `cmd_as7341_read`
  - `cmd_read_as7341_flash` — parse `argv[0]` as LED current via `atoi()`, clamp negative values to 0 *(Issue #11 validation moved here from old Step 2.3)*
  - `i2c_scan`
  - `as7341_setLEDCurrent` — parse `argv[0]` as LED current via `atoi()`, clamp negative values to 0 *(Issue #11)*
  - `hello` — prints `"Hello CO2 meter ready"`
  - `battery` — prints `"battery":0` placeholder

### Step 3.2 — Populate dispatch table
- **File:** `src/app/commands.cpp`
- Fill the empty `kCmds[]` array with entries mapping command names → wrappers

### Step 3.3 — Migrate `handleCommandText()` to use dispatch table
- **File:** `src/app/commands.cpp`
- Replace the if-else chain with `return dispatchCommand(cmd.c_str());` — signature stays `const String &` for now (changed to `const char *` in Step 3.6 when the rx buffer changes)
- `hello` and `battery` are in the dispatch table (added in Step 3.1/3.2) — no special cases needed
- Change `handleCommandText()` return type from `void` to `bool`. Update declaration in `include/app/commands.h` (signature remains `bool handleCommandText(const String &cmd)` at this stage)

### Step 3.4 — Wire up JSON path *(Issue #4)*
- **File:** `src/main.cpp`
- Replace `bool ok = false; // TODO` with a call to `HandleJson(rx)`
- Remove `static` from `HandleJson()` in `src/app/commands.cpp`
- Add declaration to `include/app/commands.h`
- Fix broken JSON in `serial_string_init()`: the two `Serial.print` calls produce `..."esp32-c3"",...` (double quote). Merge into a single correctly-escaped string or fix the boundary between the two prints
- Address `serial_string_end()`: it appends `7A1E3AA1` immediately after the closing `}`, producing invalid JSON. If this is an intentional openJII frame delimiter, separate it onto its own line (`Serial.println(); Serial.println("7A1E3AA1");`). If not, remove it. Document the decision
- Remove redundant `commandExists()` pre-check in `HandleJson()` — `dispatchCommand()` already returns `false` for unknown commands. The current pattern double-parses the command string

### Step 3.5 — Consistent JSON output *(Issue #15)*
- **File:** `src/app/bme68x_api.cpp`
- Unify both `#ifdef BME68X_USE_FPU` branches of `printBMEField()` to emit JSON format

### Step 3.6 — Replace `String` rx buffer with fixed `char[]` *(Issue #12)*
- **File:** `src/main.cpp`
- Replace `String rx` with `char rx[2048]` + `size_t rxLen`
- Check length **before** appending each character
- Remove unused `String line` global variable
- Replace all `String` method calls on `rx` in the loop body:
  - `rx += c` → `rx[rxLen++] = c; rx[rxLen] = '\0';`
  - `rx.trim()` → manual trim or just null-terminate at `rxLen` (we already skip `\r`, and `\n` triggers processing)
  - `rx.length()` → `rxLen`
  - `isspace((unsigned char)rx[i])` stays as-is (works on `char[]`)
- Update `resetRx()`: change `rx = "";` → `rxLen = 0; rx[0] = '\0';`
- **Cascading signature changes** (both must be `const char *` to avoid silent `String` temporaries):
  - `HandleJson()`: change from `const String &` to `const char *` — ArduinoJson's `deserializeJson` accepts `const char*` natively. Update declaration in `commands.h`
  - `handleCommandText()`: change from `const String &cmd` to `const char *cmd` — the body is just `return dispatchCommand(cmd);` after Step 3.3, so this is a trivial signature swap. Update declaration in `commands.h`

### >>> HARDWARE TEST CHECKPOINT 3 <<<
- [ ] All plain-text commands work: `hello`, `battery`, `bme_read`, `as7341_read`, `set_led,10`, `as7341_read_flash,15`, `i2c_scan`
- [ ] JSON payload works: `[{"_protocol_set_":[{"label":"bme_read","protocol_repeats":1},{"label":"as7341_read","protocol_repeats":1}]}]` → returns framed JSON with sensor data
- [ ] Send >2048 bytes of garbage → `rx_overflow`, no crash
- [ ] In **JSON/openJII mode**, the complete framed output (from `serial_string_init` to `serial_string_end`) parses as valid JSON
- [ ] In **LINE mode**, sensor outputs (`bme_read`, `as7341_read`, `as7341_read_flash`) emit valid JSON **fragments** (key:value pairs) — these are not standalone JSON by design. `hello` and `battery` emit plain text

---

## Phase 4: Cleanup (no hardware test needed)

### Step 4.1 — Remove invalid platformio.ini options *(Issue #13)*
- **File:** `platformio.ini`
- Delete the 4 `board_build.arduino.earlephilhower.*` lines (they do nothing on ESP32)

### Step 4.2 — Pin library versions *(Issue #16)*
- **File:** `platformio.ini`
- Replace bare `.git` URLs with versioned refs, e.g.:
  - `boschsensortec/Bosch-BME68x-Library@^1.1`
  - `adafruit/Adafruit_AS7341@^1.3`
  - `bblanchon/ArduinoJson@^7`

---

## Files Affected

| File | Phases |
|------|--------|
| `src/app/as7341_api.cpp` | 1, 2 |
| `src/app/bme68x_api.cpp` | 1, 2, 3 |
| `src/app/commands.cpp` | 3 |
| `src/app/debug_api.cpp` | 1 |
| `src/main.cpp` | 1, 3 |
| `include/app/as7341_api.h` | 1 |
| `include/app/bme68x_api.h` | 1 |
| `include/app/commands.h` | 3 |
| `platformio.ini` | 4 |

## Final Verification
- `pio run` compiles cleanly (zero warnings) after each phase
- Long-running stress test: send commands in a loop for 10+ minutes, monitor `ESP.getFreeHeap()` for leaks
