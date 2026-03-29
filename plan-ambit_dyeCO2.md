# Fix Plan: firmware-ambit_dyeCO2

Revise the existing fix plan so the firmware can work with either an AS7341 or an AS7343 spectrometer on the same I2C address (`0x39`), while still addressing the previously identified robustness and command-path issues.

The current codebase is AS7341-only:
- `src/app/as7341_api.cpp` instantiates `Adafruit_AS7341` directly.
- `initAS7341()` assumes the device is an AS7341.
- command output is hard-coded to the AS7341 12-value layout.

That is not sufficient for AS7343 support because:
- both sensors use I2C address `0x39`;
- AS7341 and AS7343 use different identification registers and different register maps;
- the bundled Adafruit AS7341 driver validates the AS7341 chip ID and will reject AS7343;
- AS7343 exposes a different channel set and supports automatic 12-channel / 18-channel readout.

## Datasheet Constraints That Must Drive the Design

### Shared bus address, different identification
- **AS7341:** I2C address `0x39`; part identification is read via register `0x92`
- **AS7343:** I2C address `0x39`; part identification is read via register `0x5A` and the datasheet lists value `0x81`
- Consequence: `i2c_scan` can only prove that *something* exists at `0x39`; firmware must probe ID registers to know which spectrometer is populated

### Different register maps
- **AS7341:** LED register at `0x74`; ASTEP at `0xCA/0xCB`
- **AS7343:** LED register at `0xCD`; ASTEP at `0xD4/0xD5`
- Consequence: AS7343 cannot be supported by extending the AS7341 register code in-place without a device-specific backend

### Different spectral result shapes
- **AS7341:** 8 VIS bands plus Clear and NIR, acquired via SMUX sequencing
- **AS7343:** 11 VIS bands plus Clear and NIR; the datasheet recommends automatic 12-channel or 18-channel processing, with measurements stored in 18 data registers
- Consequence: the current fixed `uint16_t[12]` printing path is too narrow for AS7343

### LED driver capability versus board policy
- Both datasheets describe a programmable LED driver with 4 mA minimum and 2 mA steps up to 258 mA
- This board has a real hardware limit of **20 mA maximum**
- Consequence: firmware must enforce `20 mA` as a **hard board-level safety limit** on both AS7341 and AS7343, even though the sensor LED drivers support more

### Compatibility contract
- **Command-name compatibility only**
- Legacy command names such as `as7341_read`, `as7341_read_flash`, and `set_led` must continue to dispatch
- Response payload compatibility is **not** required
- Consequence: legacy command aliases may return the new generic `"spectrometer"` payload rather than old `"as7341"` keys
- Spectrometer errors should use the same structured JSON-fragment shape in both line mode and JSON/openJII mode so the error contract is not mode-dependent

### Spectral output contract
- Expose a **normalized semantic channel set only**
- Do **not** expose raw AS7343 auto-read slots such as `DATA_0..DATA_17`, `2xVIS`, `FD`, or ADC channel numbers in the public API
- Consequence: the facade must convert backend-specific raw reads into stable, named spectral channels before command output

---

## Phase 0: Spectrometer Detection And Abstraction

### Step 0.1 - Introduce a generic spectrometer facade
- **Add files:** `include/app/spectrometer_api.h`, `src/app/spectrometer_api.cpp`
- **Keep existing file:** `src/app/as7341_api.cpp` as the AS7341-specific backend
- **Add files:** `include/app/as7343_api.h`, `src/app/as7343_api.cpp` for the AS7343-specific backend
- Define:
  - `enum class SpectrometerModel { None, AS7341, AS7343, ProbePendingAt0x39, UnknownAt0x39 };`
  - `extern bool spectrometer_available;`
  - `extern SpectrometerModel spectrometer_model;`
  - generic entry points such as:
    - `bool initSpectrometer();`
    - `bool spectrometer_read(...);`
    - `bool spectrometer_set_led_current(uint16_t ma);`
    - `bool spectrometer_read_flash(...);`
- **Phase sequencing rule:** introduce the generic facade first, but keep the existing AS7341 symbols and command flow temporarily until Phase 3 moves the command layer over
- Move `main.cpp` init onto the generic facade in Phase 0; move command handling in Phase 3

### Step 0.2 - Detect the populated spectrometer before backend init
- **Files:** `src/app/spectrometer_api.cpp`, `src/main.cpp`
- After `Wire.begin(3, 4)`, run the full detect-and-identify sequence inside a bounded startup retry window rather than doing a single immediate probe
- Retry policy:
  - retry for up to `5 ms`
  - use a short retry interval in the `200 us` to `500 us` range
  - within each retry attempt:
    - check whether `0x39` ACKs
    - if it ACKs, try the AS7343 ID read
    - if that does not match, try the AS7341 ID read
  - only classify the device as `None` or `ProbePendingAt0x39` after the retry window expires
- If the retry window ends with successful AS7343 ID match, select `SpectrometerModel::AS7343`
- Otherwise, if the retry window ends with successful AS7341 masked WHOAMI match, select `SpectrometerModel::AS7341`
- Otherwise, if `0x39` ACKed during the retry window but no supported ID matched, set `SpectrometerModel::ProbePendingAt0x39`
- If `0x39` does not ACK, set `SpectrometerModel::None`
- Print a precise boot message:
  - `Spectrometer detected: AS7341`
  - `Spectrometer detected: AS7343`
  - `Unidentified spectrometer at 0x39, will retry on first command`
  - `No spectrometer detected at 0x39`
- Runtime command contract:
  - if `spectrometer_model == SpectrometerModel::None`, spectrometer commands return `"spectrometer":{"error":"not_available"}`
  - if `spectrometer_model == SpectrometerModel::ProbePendingAt0x39`, the first spectrometer command reruns the full detect-and-identify sequence before deciding availability
  - if that on-demand retry succeeds, proceed normally
  - if that on-demand retry still sees `0x39` with no supported ID match, set `spectrometer_model = SpectrometerModel::UnknownAt0x39` and return `"spectrometer":{"error":"unsupported_device_at_0x39"}`
  - if `spectrometer_model == SpectrometerModel::UnknownAt0x39`, subsequent spectrometer commands return `"spectrometer":{"error":"unsupported_device_at_0x39"}`
  - use the same structured JSON fragment shape in both line mode and JSON/openJII mode; do not emit free-text spectrometer errors

### Step 0.3 - Use separate backends, not a forced shared driver
- **AS7341 backend:** continue using `Adafruit_AS7341`
- **AS7343 backend:** implement a small raw-register backend from the datasheet
- Do **not** try to initialize AS7343 through `Adafruit_AS7341::begin()`; the library validates the AS7341 chip ID and will reject AS7343

### >>> HARDWARE TEST CHECKPOINT 0 <<<
- [ ] With AS7341 hardware fitted, boot detects `AS7341`
- [ ] With AS7343 hardware fitted, boot detects `AS7343`
- [ ] With no device at `0x39`, boot reports no spectrometer and does not hang
- [ ] With an unexpected or not-yet-identified device at `0x39`, boot leaves spectrometer unavailable, reports retry-on-first-command behavior, and does not hang
- [ ] Cold-power-up and rapid reboot both still detect AS7343 reliably, confirming the startup retry window works

---

## Phase 1: Safety-Critical And Bus-Level Fixes

### Step 1.1 - Keep spectrometer init non-blocking
- **Files:** `src/app/as7341_api.cpp`, `src/app/as7343_api.cpp`, `src/app/spectrometer_api.cpp`
- Every init path must return `false` on failure and must never stall in an infinite loop
- `setup()` already has the right pattern for graceful failure handling; keep that behavior

### Step 1.2 - Centralize I2C init and prevent bus reconfiguration
- **File:** `src/main.cpp` - keep a single `Wire.begin(3, 4);` in `setup()` after `Serial.begin(115200)` and before any sensor init
- **File:** `src/app/debug_api.cpp` - keep `i2c_scan()` as a pure scanner with no `Wire.begin(...)` or bus clock reset
- Ensure no spectrometer backend reinitializes `Wire`

### Step 1.3 - Add include guards to all API headers
- **Files:** `include/app/as7341_api.h`, `include/app/as7343_api.h`, `include/app/bme68x_api.h`, `include/app/spectrometer_api.h`
- Add `#pragma once`

### Step 1.4 - Replace AS7341-specific availability flags with generic spectrometer state
- **File:** `src/main.cpp`
  - keep `bme_available`
  - add `spectrometer_available`
  - add `spectrometer_model`
- **Transitional rule for compile-stable phases:** until Phase 3 removes the old AS7341-only command path, keep `as7341_available` as a derived compatibility shim:
  - `as7341_available = spectrometer_available && spectrometer_model == SpectrometerModel::AS7341`
- **Files:** `include/app/as7341_api.h`, `include/app/as7343_api.h`, `include/app/spectrometer_api.h`
  - expose only the state each layer truly needs
- Guard at the generic API layer, not at the command layer:
  - `spectrometer_read(...)`
  - `spectrometer_set_led_current(...)`
  - `spectrometer_read_flash(...)`
- Backends may assume the correct model has already been selected by the facade

### >>> HARDWARE TEST CHECKPOINT 1 <<<
- [ ] Device boots with BME68x plus AS7341
- [ ] Device boots with BME68x plus AS7343
- [ ] Device boots with spectrometer disconnected and prints a warning, not a hang
- [ ] `i2c_scan`, then a spectrometer read command, still works on the same bus

---

## Phase 2: Spectrometer Backend Implementation

### Step 2.1 - Stabilize the AS7341 backend
- **File:** `src/app/as7341_api.cpp`
- Keep the current Adafruit-based path, but limit it to AS7341-only responsibilities
- Fix the LED disable path:
  - `0 mA` means disable LED and return success without trying to write a 0 mA setpoint
- Fix current variable truncation:
  - change `requested_current` from `uint8_t` to `uint16_t`
- Remove JSON printing from the low-level backend read function; backend reads should populate a data structure, not print directly
- **Phase-stable compatibility rule:** when backend printing is removed in Phase 2, immediately replace it with facade-based payload emission for the still-existing legacy commands so Phase 2 does not break line-mode behavior while Phase 3 command migration is still pending

### Step 2.2 - Implement a minimal AS7343 backend from the datasheet
- **Files:** `include/app/as7343_api.h`, `src/app/as7343_api.cpp`
- Scope this backend to only what the firmware needs now:
  - init
  - configure gain / ATIME / ASTEP
  - read spectral data
  - switch LED on/off and set LED current
- Prefer the AS7343 automatic readout path instead of hand-recreating AS7341 SMUX logic:
  - after power-up, wait out the datasheet initialization window before assuming I2C access is valid
  - set `PON=1`
  - explicitly keep flicker detection disabled: set `FDEN=0` during init and verify it remains disabled for spectral reads
  - configure gain / `ATIME` / `ASTEP` / `auto_smux` **while `SP_EN=0`**
  - use `auto_smux = 3` for automatic 18-channel readout
  - start one measurement by setting `SP_EN=1`
  - poll `STATUS2.AVALID` (`0x90`) with a timeout derived from the configured integration time plus a conservative guard margin
  - read the latched ASTATUS plus spectral data block in one burst (`0x94` through `0xB8`) so all returned values are concurrent
  - return the device to idle by clearing `SP_EN` after the read sequence
  - if polling times out or any read fails, clear `SP_EN` before returning failure so the device does not remain stuck in `ACTIVE`
- Treat saturation/status bits as part of the backend read result so the facade can decide whether to expose, warn, or reject a sample
- LED control must use the AS7343 LED register at `0xCD`

### Step 2.3 - Define a generic spectrometer result model
- **Files:** `include/app/spectrometer_api.h`, `src/app/spectrometer_api.cpp`
- Replace the fixed `uint16_t[12]` contract with a model-aware structure, for example:
  - `model`
  - `channel_count`
  - `channels[]`
  - optional `channel_names[]` or symbolic identifiers
- Public output must be **semantic**, not raw-register-oriented
- Minimum required normalized output contract:
  - **AS7341:** `f1_415`, `f2_445`, `f3_480`, `f4_515`, `f5_555`, `f6_590`, `f7_630`, `f8_680`, `clear`, `nir`
  - **AS7343:** `f1_405`, `f2_425`, `fz_450`, `f3_475`, `f4_515`, `fy_555`, `f5_550`, `fxl_600`, `f6_640`, `f7_690`, `f8_745`, `clear`, `nir`
- AS7343 bring-up rule:
  - do **not** freeze a `DATA_0..DATA_17 -> semantic band` table purely from plan review
  - first implement a temporary bring-up path that can dump raw `DATA_0..DATA_17` for AS7343 while flicker is disabled and auto 18-channel mode is active
  - use that bring-up output on real hardware to confirm the band ordering under known illumination
  - only after that confirmation, encode the final fixed `DATA_0..DATA_17 -> semantic band` table in the backend and remove or disable the raw bring-up path
- Until the final table is frozen from bring-up evidence, AS7343 support is considered incomplete
- For AS7343, derive the public `clear` value from the automatic-readout `2xVIS` clear/VIS data using a fixed normalization rule:
  - collect all non-saturated, valid `2xVIS` values produced across the full automatic 18-channel sequence
  - compute the integer average of those valid `2xVIS` values
  - publish that average as the single semantic `clear` output
  - if every `2xVIS` sample in the sequence is invalid or saturated, fail the spectrometer sample rather than publishing a fabricated `clear`
- **Normalization note:** for AS7343, exported `clear` is a firmware-normalized broadband visible proxy derived from the default `2xVIS` readout. It is not asserted to be physically identical to AS7341 `clear`; it is provided to keep a stable cross-device semantic contract
- Do not expose `FD`, duplicated `2xVIS`, or `DATA_n` slots in the command payload
- Do not force AS7343 data into the AS7341 array indexing scheme

### Step 2.4 - Normalize output naming at the facade layer
- **Files:** `src/app/spectrometer_api.cpp`, `src/app/commands.cpp`
- The command layer should emit a generic payload:
  - `"spectrometer": { "model": "...", "channels": { ... } }`
- Move payload emission into Phase 2 together with the facade so output behavior stays valid before Phase 3 finishes the dispatch-table migration
- Keep legacy command names such as `as7341_read` only as compatibility aliases
- **Compatibility rule:** alias commands preserve command names only; they return the same generic payload as the new command names
- Do **not** keep the old `"as7341"` payload key, even when the hardware is AS7341

### Step 2.5 - Make LED current policy explicit
- **Files:** `src/app/spectrometer_api.cpp`, `src/app/as7341_api.cpp`, `src/app/as7343_api.cpp`
- Introduce a board-level constant such as `kSpectrometerLedBoardMaxMa`
- Set `kSpectrometerLedBoardMaxMa = 20`
- Enforce this limit unconditionally in the facade on both supported spectrometers
- Clamp silently or report via structured status; do **not** inject ad hoc free-text into JSON-formatted command output
- Preserve the sensor-level quantization behavior:
  - minimum 4 mA when enabling
  - 2 mA steps
  - `0 mA` means off

### Step 2.6 - Unify dark / lit / diff measurement flow
- **Files:** `src/app/spectrometer_api.cpp`, `src/app/commands.cpp`
- Replace `cmd_read_as7341_flash()` with a generic `spectrometer_read_flash(...)`
- Sequence:
  1. read dark
  2. enable LED at requested current
  3. read lit
  4. disable LED
  5. compute diff
- Output keys:
  - `"spectrometer_dark"`
  - `"spectrometer_lit"`
  - `"spectrometer_diff"`
- Keep `as7341_read_flash` as a compatibility alias only

### >>> HARDWARE TEST CHECKPOINT 2 <<<
- [ ] On AS7341 hardware, generic spectrometer read returns AS7341 model plus valid channels
- [ ] On AS7343 hardware, generic spectrometer read returns AS7343 model plus valid channels
- [ ] On both sensors, `set_led,0` disables the LED
- [ ] On both sensors, `set_led,25` clamps to the hard `20 mA` board limit and still turns the LED on
- [ ] On both sensors, non-zero LED current turns the LED on and readback is consistent with the hard board cap and device quantization
- [ ] Flash-read dark / lit / diff works on both sensor variants
- [ ] AS7343 timeout path clears `SP_EN` and the next measurement can still succeed
- [ ] AS7343 saturated or invalid `2xVIS` samples are excluded from `clear` averaging; if all are invalid, the sample fails cleanly

---

## Phase 3: Command Infrastructure And JSON Path

### Step 3.1 - Add generic command wrappers
- **File:** `src/app/commands.cpp`
- Create `CmdFn` wrappers for:
  - `cmd_bme_read`
  - `cmd_spectrometer_read`
  - `cmd_spectrometer_read_flash`
  - `cmd_spectrometer_set_led`
  - `i2c_scan`
  - `hello`
  - `battery`
- Keep aliases for backward compatibility:
  - `as7341_read` -> `cmd_spectrometer_read`
  - `as7341_read_flash` -> `cmd_spectrometer_read_flash`
  - `set_led` -> `cmd_spectrometer_set_led`
- Add canonical command names:
  - `spectrometer_read`
  - `spectrometer_read_flash`
  - `spectrometer_set_led`
- Parse LED current with `atoi()` and clamp negative values to `0`

### Step 3.2 - Populate the dispatch table
- **File:** `src/app/commands.cpp`
- Fill `kCmds[]` with both generic commands and compatibility aliases

### Step 3.3 - Migrate `handleCommandText()` to the dispatch table
- **File:** `src/app/commands.cpp`
- Replace the if-else chain with `dispatchCommand(...)`
- Change `handleCommandText()` return type from `void` to `bool`
- Update declaration in `include/app/commands.h`

### Step 3.4 - Fix and enable the JSON/openJII path
- **Files:** `src/main.cpp`, `src/app/commands.cpp`, `include/app/commands.h`
- Replace the JSON TODO in `main.cpp` with a real call to `HandleJson(...)`
- Remove `static` from `HandleJson(...)`
- Fix `serial_string_init()` so it emits valid JSON
- Fix `serial_string_end()` so the frame delimiter, if required, is emitted outside the JSON document
- Remove the redundant `commandExists()` pre-check; `dispatchCommand()` already determines success

### Step 3.5 - Make sensor output consistently JSON-shaped
- **Files:** `src/app/bme68x_api.cpp`, `src/app/commands.cpp`, `src/app/spectrometer_api.cpp`
- Ensure line-mode command handlers emit valid JSON fragments when they are supposed to
- Ensure the spectrometer payload always includes:
  - the detected model
  - the channel object
- Ensure both canonical and alias command names return the same normalized semantic spectrometer payload
- Ensure spectrometer errors in both line mode and JSON/openJII mode use the same JSON fragment contract:
  - `"spectrometer":{"error":"not_available"}`
  - `"spectrometer":{"error":"unsupported_device_at_0x39"}`
- Use the same payload shape in line mode and JSON mode

### Step 3.6 - Replace the `String` receive buffer with a fixed buffer
- **File:** `src/main.cpp`
- Replace `String rx` with `char rx[2048]` plus `size_t rxLen`
- Check bounds before appending
- Remove unused `String line`
- Change:
  - `HandleJson(const String &)` -> `HandleJson(const char *)`
  - `handleCommandText(const String &)` -> `handleCommandText(const char *)`

### >>> HARDWARE TEST CHECKPOINT 3 <<<
- [ ] Plain-text commands work on AS7341 hardware:
  - `spectrometer_read`
  - `spectrometer_read_flash,15`
  - `spectrometer_set_led,10`
  - `set_led,10`
  - compatibility aliases still dispatch
- [ ] Plain-text commands work on AS7343 hardware with the same command names
- [ ] JSON payload works and returns the detected model in the spectrometer object
- [ ] Alias commands such as `as7341_read` return the generic `"spectrometer"` payload, not legacy `"as7341"` keys
- [ ] In JSON/openJII mode, `None` and `UnknownAt0x39` produce distinct structured spectrometer error objects
- [ ] In LINE mode, spectrometer errors also use the same structured JSON fragment contract rather than free text
- [ ] Sending more than 2048 bytes of garbage returns `rx_overflow` and does not crash
- [ ] JSON/openJII output is valid JSON from `serial_string_init()` through `serial_string_end()`

---

## Phase 4: BME68x Robustness And Cleanup

### Step 4.1 - Fix `bme_read()` robustness
- **File:** `src/app/bme68x_api.cpp`
- Null-check `bme.getAllData()`
- Return `false` when `fetchData()` returns zero fields

### Step 4.2 - Make BME output consistently JSON-shaped
- **File:** `src/app/bme68x_api.cpp`
- Unify both `#ifdef BME68X_USE_FPU` branches to emit JSON format

### Step 4.3 - Remove invalid `platformio.ini` options
- **File:** `platformio.ini`
- Delete the `board_build.arduino.earlephilhower.*` lines; they are not relevant to ESP32 Arduino

### Step 4.4 - Pin library versions deliberately
- **File:** `platformio.ini`
- Replace bare Git URLs with explicit versions where possible
- Keep `Adafruit_AS7341` because it remains the AS7341 backend
- AS7343 support is implemented locally in the firmware; do not assume an external AS7343 Arduino library

---

## Files Affected

| File | Purpose |
|------|---------|
| `src/main.cpp` | Generic spectrometer init state, JSON path, fixed RX buffer |
| `src/app/commands.cpp` | Generic spectrometer commands, aliases, dispatch wiring |
| `include/app/commands.h` | Updated command signatures and JSON handler declaration |
| `src/app/as7341_api.cpp` | AS7341-only backend cleanup |
| `include/app/as7341_api.h` | AS7341 backend declarations only |
| `src/app/as7343_api.cpp` | New AS7343 backend |
| `include/app/as7343_api.h` | New AS7343 backend header |
| `src/app/spectrometer_api.cpp` | Generic spectrometer facade and shared policy |
| `include/app/spectrometer_api.h` | Generic spectrometer types and API |
| `src/app/bme68x_api.cpp` | BME robustness and JSON consistency |
| `include/app/bme68x_api.h` | Header cleanup |
| `src/app/debug_api.cpp` | Pure bus scan, no reinit |
| `platformio.ini` | Cleanup and dependency pinning |

## Final Verification Matrix

- [ ] `pio run` compiles cleanly after each phase
- [ ] AS7341 board variant:
  - boot detects `AS7341`
  - `spectrometer_read` returns model plus valid channels
  - LED control works
- [ ] AS7343 board variant:
  - boot detects `AS7343`
  - `spectrometer_read` returns model plus valid channels
  - LED control works
- [ ] No spectrometer fitted:
  - boot reports no spectrometer
  - spectrometer commands return a clear availability error
- [ ] Unknown device at `0x39`:
  - boot leaves spectrometer unavailable and indicates retry-on-first-command behavior
  - first spectrometer command retries detection
  - if still unsupported, spectrometer commands return a distinct unsupported-device error, not the no-device error
  - firmware remains responsive
- [ ] Backward-compatible aliases still work for hosts that still send `as7341_read` or `as7341_read_flash`
- [ ] Backward-compatible aliases are verified to preserve command names only, while returning the generic normalized spectrometer payload
- [ ] Long-running command loop for 10+ minutes shows no hangs and no obvious heap growth

## Reference Datasheets

- AS7341 datasheet: `AS7341-DS000504`
- AS7343 datasheet: `AS7343-14-Channel-Multi-Spectral-Sensor`, version dated 2023-06-07
