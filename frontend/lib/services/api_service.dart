import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:http/http.dart' as http;

class ApiService {
  static const String baseUrl = 'http://127.0.0.1:8002';

  // =========================
  // REGISTER
  // =========================
  static Future<dynamic> register(String email, String password) async {
    final response = await http.post(
      Uri.parse('$baseUrl/register'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );

    if (response.statusCode == 200 || response.statusCode == 201) {
      return jsonDecode(response.body);
    }

    throw Exception('Registration failed: ${response.body}');
  }

  // =========================
  // LOGIN
  // =========================
  static Future<String> login(String email, String password) async {
    final response = await http.post(
      Uri.parse('$baseUrl/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      final token = data['access_token'];

      if (token is String && token.isNotEmpty) {
        return token;
      }

      throw Exception('No access token received');
    }

    throw Exception('Login failed: ${response.body}');
  }

  // =========================
  // GET CURRENT USER
  // =========================
  static Future<Map<String, dynamic>> getMe(String token) async {
    final response = await http.get(
      Uri.parse('$baseUrl/me'),
      headers: {'Authorization': 'Bearer $token'},
    );

    if (response.statusCode == 200) {
      return Map<String, dynamic>.from(jsonDecode(response.body));
    }

    throw Exception('Failed to load user: ${response.body}');
  }

  // =========================
  // GET PROJECTS
  // =========================
  static Future<List<dynamic>> getProjects(String token) async {
    final response = await http.get(
      Uri.parse('$baseUrl/projects'),
      headers: {'Authorization': 'Bearer $token'},
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);

      if (data is List) {
        return data;
      }

      throw Exception('Unexpected projects response');
    }

    throw Exception('Failed to load projects: ${response.body}');
  }

  // =========================
  // CREATE PROJECT
  // =========================
  static Future<Map<String, dynamic>> createProject(
    String token,
    String title, {
    String description = '',
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/projects'),
      headers: {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
      body: jsonEncode({'title': title, 'description': description}),
    );

    if (response.statusCode == 200 || response.statusCode == 201) {
      return Map<String, dynamic>.from(jsonDecode(response.body));
    }

    throw Exception('Failed to create project: ${response.body}');
  }

  // =========================
  // UPDATE PROJECT
  // =========================
  static Future<Map<String, dynamic>> updateProject(
    String token,
    int projectId, {
    String? title,
    String? description,
  }) async {
    final body = <String, dynamic>{};

    if (title != null) {
      body['title'] = title;
    }

    if (description != null) {
      body['description'] = description;
    }

    final response = await http.patch(
      Uri.parse('$baseUrl/projects/$projectId'),
      headers: {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      },
      body: jsonEncode(body),
    );

    if (response.statusCode == 200) {
      return Map<String, dynamic>.from(jsonDecode(response.body));
    }

    throw Exception('Failed to update project: ${response.body}');
  }

  // =========================
  // DELETE PROJECT
  // =========================
  static Future<void> deleteProject(String token, int projectId) async {
    final response = await http.delete(
      Uri.parse('$baseUrl/projects/$projectId'),
      headers: {'Authorization': 'Bearer $token'},
    );

    if (response.statusCode != 200 && response.statusCode != 204) {
      throw Exception('Failed to delete project: ${response.body}');
    }
  }

  // =========================
  // UPLOAD PDF
  // =========================
  static Future<Map<String, dynamic>> uploadPdf(
    String token,
    int projectId,
    PlatformFile file,
  ) async {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      throw Exception('Please select a PDF file');
    }

    // Read PDF using file_picker 13.1.0
    final bytes = await file.readAsBytes();

    final request = http.MultipartRequest(
      'POST',
      Uri.parse('$baseUrl/projects/$projectId/files'),
    );

    request.headers['Authorization'] = 'Bearer $token';

    request.files.add(
      http.MultipartFile.fromBytes('file', bytes, filename: file.name),
    );

    final streamedResponse = await request.send();

    final response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200 || response.statusCode == 201) {
      return Map<String, dynamic>.from(jsonDecode(response.body));
    }

    throw Exception('PDF upload failed: ${response.body}');
  }

  // =========================
  // GET PROJECT FILES
  // =========================
  static Future<List<dynamic>> getProjectFiles(
    String token,
    int projectId,
  ) async {
    final response = await http.get(
      Uri.parse('$baseUrl/projects/$projectId/files'),
      headers: {'Authorization': 'Bearer $token'},
    );

    if (response.statusCode == 200) {
      return List<dynamic>.from(jsonDecode(response.body));
    }

    throw Exception('Failed to load files: ${response.body}');
  }

  // =========================
  // GET REQUIREMENTS
  // =========================
  static Future<List<dynamic>> getRequirements(
    String token,
    int projectId,
  ) async {
    final response = await http.get(
      Uri.parse('$baseUrl/projects/$projectId/requirements'),
      headers: {'Authorization': 'Bearer $token'},
    );

    if (response.statusCode == 200) {
      return List<dynamic>.from(jsonDecode(response.body));
    }

    throw Exception('Failed to load requirements: ${response.body}');
  }

  // =========================
  // ANALYZE PDF WITH AI
  // =========================
  static Future<dynamic> analyzeFile(
    String token,
    int projectId,
    int fileId,
  ) async {
    final response = await http.post(
      Uri.parse('$baseUrl/projects/$projectId/files/$fileId/analyze'),
      headers: {'Authorization': 'Bearer $token'},
    );

    if (response.statusCode == 200 || response.statusCode == 201) {
      return jsonDecode(response.body);
    }

    throw Exception('AI analysis failed: ${response.body}');
  }

  // =========================
  // GENERATE CHECKLIST
  // =========================
  static Future<dynamic> generateChecklist(String token, int projectId) async {
    final response = await http.post(
      Uri.parse('$baseUrl/projects/$projectId/checklist/generate'),
      headers: {'Authorization': 'Bearer $token'},
    );

    if (response.statusCode == 200 || response.statusCode == 201) {
      return jsonDecode(response.body);
    }

    throw Exception('Failed to generate checklist: ${response.body}');
  }

  // =========================
  // GET CHECKLIST
  // =========================
  static Future<List<dynamic>> getChecklist(String token, int projectId) async {
    final response = await http.get(
      Uri.parse('$baseUrl/projects/$projectId/checklist'),
      headers: {'Authorization': 'Bearer $token'},
    );

    if (response.statusCode == 200) {
      return List<dynamic>.from(jsonDecode(response.body));
    }

    throw Exception('Failed to load checklist: ${response.body}');
  }
}
