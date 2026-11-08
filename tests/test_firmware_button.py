"""Host checks of the actual input headers; not an Arduino board/library build."""
import importlib.util
import shutil
import subprocess
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, call, patch


BASE = Path(__file__).resolve().parents[1]
HEADERS = (
    BASE / 'hardware/uno_q_rfid/sketch/mirror_inputs.h',
    BASE / 'hardware/uno_r3_mirror/mirror_inputs.h',
)

DHT_STUB = r'''
#pragma once
#include <cstdint>
using byte = uint8_t;
constexpr int LOW = 0, HIGH = 1, INPUT_PULLUP = 2, INPUT = 0, DHT11 = 11;
extern int pins[32];
extern uint32_t clockNow;
inline int digitalRead(byte pin) { return pins[pin]; }
inline void pinMode(byte, int) {}
inline unsigned long millis() { return clockNow; }
class DHT {
 public:
  DHT(byte, int) {}
  void begin() {}
  float readTemperature() { return 23.5f; }
  float readHumidity() { return 46.0f; }
};
'''

HARNESS = r'''
#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>
#include "mirror_inputs.h"

int pins[32] = {};
uint32_t clockNow = 0;
std::vector<std::string> events;
void emitEncoder(int delta) { events.push_back("delta:" + std::to_string(delta)); }
void emitAnalyze() { events.push_back("analyze"); }
void emitPress() { events.push_back("press"); }
void emitSensors(float, float, bool) {}
static_assert(ENCODER_CLK == 2 && ENCODER_DT == 3 && ENCODER_SW == 4,
              "Existing encoder wiring must be preserved");
static_assert(DHT_PIN == 7 && PIR_PIN == 6 && !REVERSE_ENCODER,
              "Existing sensor wiring and direction must be preserved");

void expect(std::initializer_list<std::string> expected) {
  if (events == std::vector<std::string>(expected)) return;
  std::cerr << "Unexpected events:";
  for (const auto &event : events) std::cerr << ' ' << event;
  std::cerr << "; expected:";
  for (const auto &event : expected) std::cerr << ' ' << event;
  std::cerr << std::endl;
  std::exit(1);
}
void boot(uint32_t at = 0, bool held = false) {
  std::fill(pins, pins + 32, HIGH);
  pins[ENCODER_SW] = held ? LOW : HIGH;
  clockNow = at;
  setupMirrorInputs();
  sensorsAt = at;
}
void tick(uint32_t at, bool raw) {
  clockNow = at;
  pins[ENCODER_SW] = raw;
  pollMirrorInputs();
}
void turn(int state) {
  pins[ENCODER_CLK] = (state >> 1) & 1;
  pins[ENCODER_DT] = state & 1;
  tick(clockNow + 10, HIGH);
}

int main(int argc, char **argv) {
  if (argc != 2) return 2;
  const std::string name = argv[1];
  if (name == "short") {
    boot();
    tick(100, LOW); tick(139, LOW); expect({});
    tick(140, LOW); expect({});
    tick(200, HIGH); tick(239, HIGH); expect({});
    tick(240, HIGH); expect({"analyze"});
    tick(1000, HIGH); expect({"analyze"});
  } else if (name == "long") {
    boot();
    tick(100, LOW); tick(140, LOW); tick(1099, LOW); expect({});
    tick(1100, LOW); expect({"press"});
    tick(1500, LOW); tick(2000, LOW); expect({"press"});
    tick(2050, HIGH); tick(2090, HIGH); expect({"press"});
    tick(3000, LOW); tick(3040, LOW); tick(3100, HIGH); tick(3140, HIGH);
    expect({"press", "analyze"});
  } else if (name == "noise") {
    boot();
    tick(100, LOW); tick(139, HIGH); tick(179, HIGH); expect({});
    tick(200, LOW); tick(210, HIGH); tick(220, LOW); tick(225, HIGH);
    tick(230, LOW); tick(269, LOW); expect({});
    tick(270, LOW); tick(300, HIGH); tick(310, LOW); tick(320, HIGH);
    tick(359, HIGH); expect({});
    tick(360, HIGH); expect({"analyze"});
  } else if (name == "release_bounce") {
    boot();
    tick(100, LOW); tick(140, LOW);
    tick(1090, HIGH); tick(1095, LOW); tick(1105, HIGH); expect({});
    tick(1144, HIGH); expect({});
    tick(1145, HIGH); expect({"analyze"});
  } else if (name == "release_glitch") {
    boot();
    tick(100, LOW); tick(140, LOW);
    tick(600, HIGH); tick(610, LOW); tick(649, LOW); tick(650, LOW);
    tick(1099, LOW); expect({});
    tick(1100, LOW); expect({"press"});
    tick(1200, HIGH); tick(1240, HIGH); expect({"press"});
  } else if (name == "release_boundary") {
    boot();
    tick(100, LOW); tick(140, LOW); tick(1099, HIGH); tick(1139, HIGH);
    expect({"analyze"});
    tick(2000, LOW); tick(2040, LOW); tick(3000, HIGH); tick(3040, HIGH);
    expect({"analyze", "press"});
    tick(4000, LOW); tick(4040, LOW); tick(5500, HIGH); tick(5540, HIGH);
    expect({"analyze", "press", "press"});
  } else if (name == "boot_held") {
    boot(0, true);
    tick(40, LOW); tick(1000, LOW); tick(2000, LOW); expect({});
    tick(2100, HIGH); tick(2120, LOW); tick(2140, HIGH); tick(2180, HIGH);
    expect({});
    tick(2200, LOW); tick(2240, LOW); tick(2300, HIGH); tick(2340, HIGH);
    expect({"analyze"});
  } else if (name == "wrap_short") {
    const uint32_t start = UINT32_MAX - 80;
    boot(start);
    tick(start + 10, LOW); tick(start + 50, LOW); expect({});
    tick(start + 150, HIGH); tick(start + 189, HIGH); expect({});
    tick(start + 190, HIGH); expect({"analyze"});
  } else if (name == "wrap_long") {
    const uint32_t start = UINT32_MAX - 500;
    boot(start);
    tick(start + 10, LOW); tick(start + 50, LOW);
    tick(start + 1009, LOW); expect({});
    tick(start + 1010, LOW); expect({"press"});
    tick(start + 2000, HIGH); tick(start + 2040, HIGH); expect({"press"});
  } else if (name == "detents") {
    boot();
    turn(2); turn(0); turn(1); expect({});
    turn(3); expect({"delta:-1"});
    turn(1); turn(0); turn(2); expect({"delta:-1"});
    turn(3); expect({"delta:-1", "delta:1"});
    turn(0); turn(3); expect({"delta:-1", "delta:1"});  // Invalid two-bit jumps.
    turn(2); turn(3); turn(2); turn(0); turn(1); turn(3);  // Contact bounce.
    expect({"delta:-1", "delta:1", "delta:-1"});
  } else {
    return 2;
  }
  return 0;
}
'''


@unittest.skipUnless(shutil.which('g++'), 'g++ is required for the host firmware harness')
class FirmwareButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        root = Path(cls.folder.name)
        (root / 'DHT.h').write_text(DHT_STUB)
        (root / 'button.cpp').write_text(HARNESS)
        cls.binaries = []
        for number, header in enumerate(HEADERS):
            binary = root / f'button-{number}'
            compiled = subprocess.run([
                shutil.which('g++'), '-std=c++11', '-Wall', '-Wextra', '-Werror',
                '-I', str(root), '-I', str(header.parent), str(root / 'button.cpp'), '-o', str(binary)
            ], capture_output=True, text=True, timeout=30)
            if compiled.returncode:
                raise AssertionError(f'{header}: {compiled.stdout}{compiled.stderr}')
            cls.binaries.append((header, binary))

    def assert_scenario(self, name):
        for header, binary in self.binaries:
            with self.subTest(header=header.relative_to(BASE), scenario=name):
                result = subprocess.run([str(binary), name], capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_short_press_waits_for_debounced_release(self):
        self.assert_scenario('short')

    def test_hold_fires_once_while_down_and_suppresses_its_short_press(self):
        self.assert_scenario('long')

    def test_sub_40ms_noise_and_contact_bounce_do_not_duplicate_actions(self):
        self.assert_scenario('noise')

    def test_release_bounce_cannot_upgrade_a_quick_press_to_a_hold(self):
        self.assert_scenario('release_bounce')

    def test_brief_release_glitch_does_not_cancel_a_real_hold(self):
        self.assert_scenario('release_glitch')

    def test_999ms_release_is_short_and_1000ms_release_or_poll_gap_is_long(self):
        self.assert_scenario('release_boundary')

    def test_held_at_startup_waits_for_release_before_accepting_actions(self):
        self.assert_scenario('boot_held')

    def test_short_press_crosses_32bit_millis_wrap(self):
        self.assert_scenario('wrap_short')

    def test_hold_crosses_32bit_millis_wrap(self):
        self.assert_scenario('wrap_long')

    def test_detents_direction_and_bounce_recovery_are_preserved(self):
        self.assert_scenario('detents')


class FirmwareProtocolTests(unittest.TestCase):
    def test_both_boards_use_identical_input_headers(self):
        self.assertEqual(HEADERS[0].read_bytes(), HEADERS[1].read_bytes())

    def test_uno_q_callbacks_publish_distinct_short_and_legacy_hold_events(self):
        callbacks = {}
        utilities = types.ModuleType('arduino.app_utils')
        utilities.Bridge = types.SimpleNamespace(provide=lambda name, callback: callbacks.update({name: callback}))
        utilities.App = types.SimpleNamespace(run=Mock())
        bridge = types.ModuleType('rfid_bridge')
        publisher = Mock()
        bridge.ScanPublisher = Mock(return_value=publisher)
        spec = importlib.util.spec_from_file_location('firmware_button_app', BASE / 'hardware/uno_q_rfid/python/main.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'arduino': types.ModuleType('arduino'),
                                     'arduino.app_utils': utilities, 'rfid_bridge': bridge}), patch('builtins.print'):
            spec.loader.exec_module(module)
        callbacks['on_mirror_analyze']()
        callbacks['on_mirror_press']()
        self.assertEqual(publisher.publish_event.call_args_list, [
            call({'type': 'encoder', 'action': 'analyze'}),
            call({'type': 'encoder', 'action': 'press'}),
        ])


if __name__ == '__main__':
    unittest.main()
