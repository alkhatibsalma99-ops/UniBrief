import 'dart:async';
import 'dart:convert';

import 'package:file_picker/file_picker.dart' as picker;
import 'package:http/http.dart' as http;
import 'error_handler.dart';

import 'auth_storage.dart';

class ApiService {
  // =====================================
  // CONFIGURATION
  // =====================================

  static const String baseUrl = 'https://unibrief-1.onrender.com';

  static const Duration defaultTimeout = Duration(seconds: 45);

  static const Duration aiTimeout = Duration(minutes: 3);

  static const Duration uploadTimeout = Duration(minutes: 3);

  static Future<String?>? _refreshInProgress;

  // =====================================
  // HEADERS
  // =====================================

  static Map<String, String> _headers(String token) {
    return {
      'Authorization': 'Bearer $token',
      'Content-Type': 'application/json',
    };
  }

  static Future<void> deletePdf(String token, int projectId, int fileId) async {
    final response = await _authorizedRequest(
      token,
      (activeToken) => http
          .delete(
            Uri.parse('$baseUrl/projects/$projectId/files/$fileId'),
            headers: _headers(activeToken),
          )
          .timeout(uploadTimeout),
    );

    _decode(response);
  }

  static List<dynamic> _asList(dynamic data) {
    if (data is List) {
      return List<dynamic>.from(data);
    }

    if (data is Map) {
      for (final key in [
        'items',
        'results',
        'files',
        'projects',
        'requirements',
        'checklist',
        'submission_results',
        'details',
      ]) {
        if (data[key] is List) {
          return List<dynamic>.from(data[key]);
        }
      }
    }

    if (data == null) return [];

    throw Exception('Expected a list from server');
  }

  // =====================================
  // RESPONSE HELPERS
  // =====================================

  static dynamic _decode(http.Response response) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ApiException(response.statusCode);
    }

    if (response.bodyBytes.isEmpty) {
      return null;
    }

    final body = utf8.decode(response.bodyBytes);

    try {
      return jsonDecode(body);
    } on FormatException {
      return body;
    }
  }

  // =====================================
  // TOKEN STORAGE
  // =====================================

  static Future<void> saveLoginTokens(dynamic response) async {
    if (response is! Map) {
      throw Exception('Invalid login response');
    }

    final accessToken = response['access_token'];
    final refreshToken = response['refresh_token'];

    if (accessToken is! String || accessToken.isEmpty) {
      throw Exception('Access token is missing');
    }

    if (refreshToken is String && refreshToken.isNotEmpty) {
      await AuthStorage.saveTokens(
        accessToken: accessToken,
        refreshToken: refreshToken,
      );
    } else {
      await AuthStorage.clearTokens();
      await AuthStorage.saveToken(accessToken);
    }
  }

  // =====================================
  // REFRESH TOKEN
  // =====================================

  static Future<String?> refreshAccessToken() async {
    final existing = _refreshInProgress;

    if (existing != null) {
      return existing;
    }

    final operation = _performTokenRefresh();
    _refreshInProgress = operation;

    try {
      return await operation;
    } finally {
      if (identical(_refreshInProgress, operation)) {
        _refreshInProgress = null;
      }
    }
  }

  static Future<String?> _performTokenRefresh() async {
    final refreshToken = await AuthStorage.getRefreshToken();

    if (refreshToken == null || refreshToken.isEmpty) {
      return null;
    }

    final response = await http
        .post(
          Uri.parse('$baseUrl/refresh'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'refresh_token': refreshToken}),
        )
        .timeout(defaultTimeout);

    if (response.statusCode == 401) {
      await AuthStorage.clearTokens();
      return null;
    }

    final data = _decode(response);

    if (data is! Map) {
      throw Exception('Invalid refresh response');
    }

    final accessToken = data['access_token'];
    final newRefreshToken = data['refresh_token'];

    if (accessToken is! String || accessToken.isEmpty) {
      throw Exception('Invalid access token');
    }

    if (newRefreshToken is String && newRefreshToken.isNotEmpty) {
      await AuthStorage.saveTokens(
        accessToken: accessToken,
        refreshToken: newRefreshToken,
      );
    } else {
      await AuthStorage.saveToken(accessToken);
    }

    return accessToken;
  }

  // =====================================
  // AUTHORIZED REQUESTS
  // =====================================

  static Future<http.Response> _authorizedRequest(
    String token,
    Future<http.Response> Function(String) send,
  ) async {
    final storedToken = await AuthStorage.getToken();

    var activeToken = storedToken ?? token;

    if (activeToken.isEmpty) {
      final refreshed = await refreshAccessToken();

      if (refreshed == null) {
        throw const SessionExpiredException();
      }

      activeToken = refreshed;
    }

    var response = await send(activeToken);

    if (response.statusCode != 401) {
      return response;
    }

    final latestToken = await AuthStorage.getToken();

    if (latestToken != null &&
        latestToken.isNotEmpty &&
        latestToken != activeToken) {
      response = await send(latestToken);

      if (response.statusCode != 401) {
        return response;
      }
    }

    final refreshed = await refreshAccessToken();

    if (refreshed == null) {
      throw const SessionExpiredException();
    }

    return send(refreshed);
  }

  // =====================================
  // HTTP METHODS
  // =====================================

  static Future<http.Response> _get(
    String path,
    String token, {
    Duration timeout = defaultTimeout,
  }) {
    return _authorizedRequest(
      token,
      (activeToken) => http
          .get(Uri.parse('$baseUrl$path'), headers: _headers(activeToken))
          .timeout(timeout),
    );
  }

  static Future<http.Response> _post(
    String path,
    String token, {
    Object? body,
    Duration timeout = defaultTimeout,
  }) {
    return _authorizedRequest(
      token,
      (activeToken) => http
          .post(
            Uri.parse('$baseUrl$path'),
            headers: _headers(activeToken),
            body: body == null ? null : jsonEncode(body),
          )
          .timeout(timeout),
    );
  }

  static Future<http.Response> _patch(
    String path,
    String token, {
    Object? body,
  }) {
    return _authorizedRequest(
      token,
      (activeToken) => http
          .patch(
            Uri.parse('$baseUrl$path'),
            headers: _headers(activeToken),
            body: jsonEncode(body ?? {}),
          )
          .timeout(defaultTimeout),
    );
  }

  static Future<http.Response> _delete(String path, String token) {
    return _authorizedRequest(
      token,
      (activeToken) => http
          .delete(Uri.parse('$baseUrl$path'), headers: _headers(activeToken))
          .timeout(defaultTimeout),
    );
  }

  static Future<List<dynamic>> _getList(
    String path,
    String token, {
    bool forceRefresh = false,
  }) async {
    final response = await _get(path, token);
    return _asList(_decode(response));
  }

  static void clearCache() {
    // No local response cache.
  }

  static List<dynamic>? getCachedProjects(String token) {
    return null;
  }

  // =====================================
  // REGISTER
  // =====================================

  static Future<dynamic> register({
    required String name,
    required String email,
    required String password,
  }) async {
    final response = await http
        .post(
          Uri.parse('$baseUrl/register'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'name': name,
            'email': email,
            'password': password,
          }),
        )
        .timeout(defaultTimeout);

    return _decode(response);
  }

  // =====================================
  // LOGIN
  // Returns Map with access_token
  // =====================================

  static Future<dynamic> login(String email, String password) async {
    final response = await http
        .post(
          Uri.parse('$baseUrl/login'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'email': email, 'password': password}),
        )
        .timeout(defaultTimeout);

    final data = _decode(response);

    await saveLoginTokens(data);

    return data;
  }

  // =====================================
  // CURRENT USER
  // =====================================

  static Future<dynamic> getMe(String token) async {
    final response = await _get('/me', token);
    return _decode(response);
  }
  // =====================================
  // RESTORE SAVED SESSION
  // =====================================

  static Future<String?> restoreSession() async {
    var accessToken = await AuthStorage.getToken();

    final refreshToken = await AuthStorage.getRefreshToken();

    if ((accessToken == null || accessToken.isEmpty) &&
        (refreshToken == null || refreshToken.isEmpty)) {
      return null;
    }

    Future<http.Response> validateToken(String token) {
      return http
          .get(Uri.parse('$baseUrl/me'), headers: _headers(token))
          .timeout(defaultTimeout);
    }

    if (accessToken != null && accessToken.isNotEmpty) {
      final response = await validateToken(accessToken);

      if (response.statusCode != 401) {
        _decode(response);
        return accessToken;
      }
    }

    accessToken = await refreshAccessToken();

    if (accessToken == null || accessToken.isEmpty) {
      await AuthStorage.clearTokens();
      return null;
    }

    final response = await validateToken(accessToken);

    if (response.statusCode == 401) {
      await AuthStorage.clearTokens();
      return null;
    }

    _decode(response);

    return accessToken;
  }

  // =====================================
  // DELETE ACCOUNT
  // =====================================

  static Future<void> deleteAccount(String token) async {
    final response = await _authorizedRequest(
      token,
      (activeToken) => http
          .delete(Uri.parse('$baseUrl/me'), headers: _headers(activeToken))
          .timeout(uploadTimeout),
    );

    _decode(response);

    try {
      await _refreshInProgress;
    } catch (_) {
      // Continue local cleanup after successful deletion.
    }

    await AuthStorage.clearTokens();
    clearCache();
  }

  // =====================================
  // LOGOUT
  // =====================================

  static Future<void> logout() async {
    try {
      await _refreshInProgress;
    } catch (_) {
      // Continue logout even if refresh failed.
    }

    final refreshToken = await AuthStorage.getRefreshToken();

    try {
      if (refreshToken != null && refreshToken.isNotEmpty) {
        await http
            .post(
              Uri.parse('$baseUrl/logout'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({'refresh_token': refreshToken}),
            )
            .timeout(defaultTimeout);
      }
    } finally {
      await AuthStorage.clearTokens();
      clearCache();
    }
  }

  // =====================================
  // PROJECTS
  // =====================================

  static Future<List<dynamic>> getProjects(
    String token, {
    bool forceRefresh = false,
  }) {
    return _getList('/projects', token, forceRefresh: forceRefresh);
  }

  static Future<dynamic> createProject(
    String token,
    String title, [
    String description = '',
  ]) async {
    final response = await _post(
      '/projects',
      token,
      body: {'title': title, 'description': description},
    );

    return _decode(response);
  }

  static Future<dynamic> updateProject(
    String token,
    int projectId,
    String title,
    String description,
  ) async {
    final response = await _patch(
      '/projects/$projectId',
      token,
      body: {'title': title, 'description': description},
    );

    return _decode(response);
  }

  static Future<dynamic> deleteProject(String token, int projectId) async {
    final response = await _delete('/projects/$projectId', token);

    return _decode(response);
  }

  // =====================================
  // PROJECT FILES
  // =====================================

  static Future<List<dynamic>> getProjectFiles(
    String token,
    int projectId, {
    bool forceRefresh = false,
  }) {
    return _getList(
      '/projects/$projectId/files',
      token,
      forceRefresh: forceRefresh,
    );
  }

  // =====================================
  // UPLOAD PDF
  // =====================================

  static Future<dynamic> uploadPdf(
    String token,
    int projectId,
    picker.PlatformFile file,
  ) async {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      throw Exception('Please select a PDF file');
    }

    final bytes = await file.readAsBytes();

    Future<http.Response> sendUpload(String activeToken) async {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/projects/$projectId/files'),
      );

      request.headers['Authorization'] = 'Bearer $activeToken';

      request.files.add(
        http.MultipartFile.fromBytes('file', bytes, filename: file.name),
      );

      final streamedResponse = await http.Client()
          .send(request)
          .timeout(uploadTimeout);

      return http.Response.fromStream(streamedResponse).timeout(uploadTimeout);
    }

    final response = await _authorizedRequest(token, sendUpload);

    return _decode(response);
  }

  // =====================================
  // FILE TEXT
  // =====================================

  static Future<dynamic> getFileText(
    String token,
    int projectId,
    int fileId,
  ) async {
    final response = await _get(
      '/projects/$projectId/files/$fileId/text',
      token,
    );

    return _decode(response);
  }

  // =====================================
  // EXTRACT REQUIREMENTS
  // =====================================

  static Future<dynamic> extractRequirements(
    String token,
    int projectId,
    int fileId,
  ) async {
    final response = await _get(
      '/projects/$projectId/files/$fileId/requirements',
      token,
      timeout: aiTimeout,
    );

    return _decode(response);
  }

  // =====================================
  // ANALYZE FILE WITH AI
  // =====================================

  static Future<dynamic> analyzeFile(
    String token,
    int projectId,
    int fileId,
  ) async {
    final response = await _post(
      '/projects/$projectId/files/$fileId/analyze',
      token,
      timeout: aiTimeout,
    );

    return _decode(response);
  }

  // =====================================
  // GET REQUIREMENTS
  // =====================================

  static Future<List<dynamic>> getRequirements(
    String token,
    int projectId, {
    bool forceRefresh = false,
  }) {
    return _getList(
      '/projects/$projectId/requirements',
      token,
      forceRefresh: forceRefresh,
    );
  }

  // =====================================
  // GENERATE CHECKLIST
  // =====================================

  static Future<List<dynamic>> generateChecklist(
    String token,
    int projectId,
  ) async {
    final response = await _post(
      '/projects/$projectId/checklist/generate',
      token,
      timeout: aiTimeout,
    );

    return _asList(_decode(response));
  }

  // =====================================
  // GET CHECKLIST
  // =====================================

  static Future<List<dynamic>> getChecklist(
    String token,
    int projectId, {
    bool forceRefresh = false,
  }) {
    return _getList(
      '/projects/$projectId/checklist',
      token,
      forceRefresh: forceRefresh,
    );
  }

  // =====================================
  // UPDATE CHECKLIST ITEM
  // =====================================

  static Future<dynamic> updateChecklistItem(
    String token,
    int itemId,
    bool completed,
  ) async {
    final response = await _patch(
      '/checklist/$itemId',
      token,
      body: {'completed': completed},
    );

    return _decode(response);
  }

  // =====================================
  // CHECK SUBMISSION
  // =====================================

  static Future<dynamic> checkSubmission(
    String token,
    int projectId,
    int fileId,
  ) async {
    final response = await _post(
      '/projects/$projectId/submission/$fileId/check',
      token,
      timeout: aiTimeout,
    );

    return _decode(response);
  }

  // =====================================
  // SUBMISSION RESULTS
  // =====================================

  static Future<List<dynamic>> getSubmissionResults(
    String token,
    int projectId, {
    bool forceRefresh = false,
  }) {
    return _getList(
      '/projects/$projectId/submission-results',
      token,
      forceRefresh: forceRefresh,
    );
  }

  // =====================================
  // FINAL REPORT
  // =====================================

  static Future<dynamic> getSubmissionReport(
    String token,
    int projectId,
    int fileId,
  ) async {
    final response = await _get(
      '/projects/$projectId/submission/$fileId/report',
      token,
      timeout: aiTimeout,
    );

    return _decode(response);
  }

  // =====================================
  // AI TRANSLATION
  // =====================================

  static Future<List<String>> translateContent({
    required String token,
    required int projectId,
    required String language,
    required List<String> texts,
  }) async {
    if (!['en', 'de', 'ar'].contains(language)) {
      throw ArgumentError('Unsupported language: $language');
    }

    if (texts.isEmpty) {
      return [];
    }

    final translations = <String>[];
    var start = 0;

    while (start < texts.length) {
      final batch = <String>[];
      var characters = 0;

      while (start < texts.length && batch.length < 30) {
        final value = texts[start];

        if (value.length > 4000) {
          throw ArgumentError('Text exceeds 4000 characters');
        }

        if (batch.isNotEmpty && characters + value.length > 30000) {
          break;
        }

        batch.add(value);
        characters += value.length;
        start++;
      }

      final response = await _post(
        '/projects/$projectId/translate',
        token,
        body: {'target_language': language, 'texts': batch},
        timeout: aiTimeout,
      );

      final data = _decode(response);

      if (data is! Map) {
        throw Exception('Invalid translation response');
      }

      final rawTranslations = data['translations'];

      if (rawTranslations is! List) {
        throw Exception('Translations list is missing');
      }

      final translatedBatch = rawTranslations
          .map((value) => value.toString())
          .toList();

      if (translatedBatch.length != batch.length) {
        throw Exception('Translation count mismatch');
      }

      translations.addAll(translatedBatch);
    }

    return translations;
  }
}
