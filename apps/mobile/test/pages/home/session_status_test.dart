// The status sets behind the home filters must match the web sidebar's
// `CLOSED_STATUSES` / in-progress definition in `session-grouping.ts`.

import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/pages/home/session_status.dart';

void main() {
  test('closed = the terminal statuses, exactly as on the web', () {
    expect(kClosedStatuses, {'COMPLETED', 'FAILED', 'KILLED', 'DELETED', 'DISCONNECTED'});
    for (final live in ['STARTING', 'ACTIVE', 'AWAITING_INPUT', 'PAUSED', 'STALE', 'REVIEWED']) {
      expect(isClosedStatus(live), isFalse, reason: live);
    }
    expect(isClosedStatus(null), isFalse);
  });

  test('in progress = ACTIVE or STALE', () {
    expect(isInProgressStatus('ACTIVE'), isTrue);
    expect(isInProgressStatus('STALE'), isTrue);
    expect(isInProgressStatus('AWAITING_INPUT'), isFalse);
    expect(isInProgressStatus('REVIEWED'), isFalse);
    expect(isInProgressStatus(null), isFalse);
  });
}
