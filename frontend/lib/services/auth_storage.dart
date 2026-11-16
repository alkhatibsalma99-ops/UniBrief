import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class AuthStorage {
  static const FlutterSecureStorage _storage = FlutterSecureStorage();

  static const String _accessKey = 'unibrief_access_token';
  static const String _refreshKey = 'unibrief_refresh_token';

  static Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    await _storage.write(key: _accessKey, value: accessToken);

    await _storage.write(key: _refreshKey, value: refreshToken);
  }

  static Future<void> saveToken(String token) async {
    await _storage.write(key: _accessKey, value: token);
  }

  static Future<String?> getToken() async {
    return _storage.read(key: _accessKey);
  }

  static Future<String?> getRefreshToken() async {
    return _storage.read(key: _refreshKey);
  }

  static Future<void> clearTokens() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }

  static Future<void> clearToken() async {
    await clearTokens();
  }
}
