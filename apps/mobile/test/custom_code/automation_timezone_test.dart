// The zone an automation is saved with decides how the server turns its
// wall-clock times (daily time, "from 9:00 to 17:00" window) into fire times,
// so it has to be the device's real one — like the web dashboard's
// Intl.DateTimeFormat().resolvedOptions().timeZone.

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/custom_code/utils/automation_utils.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const channel = MethodChannel('flutter_timezone');
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  var calls = 0;

  void mockPlatformZone(Object? Function() reply) {
    calls = 0;
    messenger.setMockMethodCallHandler(channel, (call) async {
      calls++;
      return reply();
    });
  }

  setUp(resetDeviceIanaTimezoneCache);

  tearDown(() {
    messenger.setMockMethodCallHandler(channel, null);
    resetDeviceIanaTimezoneCache();
  });

  test('uses the IANA zone the platform reports', () async {
    mockPlatformZone(() => 'Asia/Shanghai');
    expect(await loadDeviceIanaTimezone(), 'Asia/Shanghai');
    // And a fresh draft carries it, since that is what reaches the API.
    expect(AutomationScheduleDraft().timezone, 'Asia/Shanghai');
  });

  test('caches the platform answer', () async {
    mockPlatformZone(() => 'Europe/Berlin');
    await loadDeviceIanaTimezone();
    await loadDeviceIanaTimezone();
    expect(calls, 1);
  });

  test('falls back to the offset scan for a bare GMT offset', () async {
    // Android reports this shape when the device has a manually-set offset;
    // the server can't resolve it and would silently schedule in UTC.
    mockPlatformZone(() => 'GMT+08:00');
    final zone = await loadDeviceIanaTimezone();
    expect(zone, isNot('GMT+08:00'));
    expect(zone == 'UTC' || zone.contains('/'), isTrue);
  });

  test('falls back to the offset scan when the platform channel is absent',
      () async {
    messenger.setMockMethodCallHandler(channel, null);
    final zone = await loadDeviceIanaTimezone();
    expect(zone, deviceIanaTimezone());
    expect(zone == 'UTC' || zone.contains('/'), isTrue);
  });
}
