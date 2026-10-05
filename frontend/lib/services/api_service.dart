import 'dart:convert';

import 'package:http/http.dart' as http;

class ApiService {
  static const String baseUrl = 'http://127.0.0.1:8002';

  static Future<String> login({
    required String email,
    required String password,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);

      return data['access_token'];
    }

    String message = 'Login failed';

    try {
      final data = jsonDecode(response.body);

      if (data['detail'] != null) {
        message = data['detail'].toString();
      }
    } catch (_) {}

    throw Exception(message);
  }
}
