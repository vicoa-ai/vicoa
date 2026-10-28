import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vicoa/auth/base_auth_user_provider.dart';
import 'package:vicoa/custom_code/actions/api_add_email.dart';
import 'package:vicoa/flutter_flow/nav/nav.dart';
import 'package:vicoa/onboarding/add_email/add_email_model.dart';

class _FakeUser extends BaseAuthUser {
  _FakeUser({this.signedIn = true, this.address});

  final bool signedIn;
  final String? address;

  @override
  bool get loggedIn => signedIn;

  @override
  bool get emailVerified => false;

  @override
  AuthUserInfo get authUserInfo => AuthUserInfo(uid: signedIn ? 'u1' : null, email: address);

  @override
  Future? delete() => null;

  @override
  Future? updateEmail(String email) => null;

  @override
  Future? updatePassword(String newPassword) => null;

  @override
  Future? sendEmailVerification() => null;
}

void main() {
  group('addEmailFailureOutcome', () {
    // These detail strings are the backend's contract (POST /auth/email).
    test('an address another account holds is taken', () {
      expect(addEmailFailureOutcome(409, {'detail': 'email_taken'}), AddEmailOutcome.taken);
    });

    test('an account that already has an email carries on', () {
      // An earlier attempt saved it but its session refresh failed.
      expect(addEmailFailureOutcome(409, {'detail': 'account_has_email'}), isNull);
    });

    test('a malformed address is invalid', () {
      expect(addEmailFailureOutcome(422, {'detail': []}), AddEmailOutcome.invalid);
    });

    test('anything else is a failure to retry', () {
      expect(addEmailFailureOutcome(502, {'detail': 'auth_provider_unavailable'}), AddEmailOutcome.failed);
      expect(addEmailFailureOutcome(409, 'not json'), AddEmailOutcome.failed);
    });
  });

  group('AddEmailModel.submit', () {
    test('rejects a malformed address without calling the backend', () async {
      final model = AddEmailModel()..emailController = TextEditingController(text: 'not-an-email');
      var notified = 0;
      model.setNotify(() => notified++);

      expect(await model.submit(), isFalse);
      expect(model.outcome, AddEmailOutcome.invalid);
      expect(model.isSaving, isFalse);
      expect(notified, 1);
    });
  });

  group('AppStateNotifier.needsEmail', () {
    final notifier = AppStateNotifier.instance;

    test('a signed-in account with no email needs one', () {
      notifier.update(_FakeUser(address: ''));
      expect(notifier.needsEmail, isTrue);
      notifier.update(_FakeUser(address: null));
      expect(notifier.needsEmail, isTrue);
    });

    test('an account with an email does not', () {
      notifier.update(_FakeUser(address: 'a@example.com'));
      expect(notifier.needsEmail, isFalse);
    });

    test('a signed-out session does not', () {
      notifier.update(_FakeUser(signedIn: false));
      expect(notifier.needsEmail, isFalse);
    });
  });
}
