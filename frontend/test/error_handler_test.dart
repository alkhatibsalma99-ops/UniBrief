import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:frontend/services/error_handler.dart';

void main() {
  group('ErrorHandler', () {
    test('Login error in English', () {
      final message = ErrorHandler.message(
        const ApiException(401),
        'en',
        isLogin: true,
      );

      expect(message, isNotEmpty);
      expect(message, isNot(contains('401')));
    });

    test('Login errors are translated', () {
      final messages = ['en', 'de', 'ar']
          .map(
            (language) => ErrorHandler.message(
              const ApiException(401),
              language,
              isLogin: true,
            ),
          )
          .toSet();

      expect(messages.length, 3);
    });

    test('Session expired error', () {
      final message = ErrorHandler.message(
        const SessionExpiredException(),
        'en',
      );

      expect(message.toLowerCase(), contains('session'));
    });

    test('Timeout error', () {
      final message = ErrorHandler.message(
        TimeoutException('Internal timeout details'),
        'en',
      );

      expect(message, isNotEmpty);
      expect(message, isNot(contains('Internal timeout details')));
    });

    test('Network error', () {
      final message = ErrorHandler.message(
        http.ClientException('Internal connection details'),
        'en',
      );

      expect(message, isNotEmpty);
      expect(message, isNot(contains('Internal connection details')));
    });

    test('API errors do not expose technical status codes', () {
      for (final code in [
        400,
        401,
        403,
        404,
        409,
        413,
        415,
        422,
        429,
        500,
        502,
        503,
        504,
      ]) {
        final message = ErrorHandler.message(ApiException(code), 'en');

        expect(message, isNotEmpty);
        expect(message, isNot(contains('API error')));
        expect(message, isNot(contains('$code')));
      }
    });

    test('Unknown errors do not expose sensitive details', () {
      final message = ErrorHandler.message(
        Exception('Sensitive internal information'),
        'en',
      );

      expect(message, isNotEmpty);
      expect(message, isNot(contains('Sensitive internal information')));
    });
  });
}
