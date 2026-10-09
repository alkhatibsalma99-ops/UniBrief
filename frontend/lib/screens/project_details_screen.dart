import 'package:flutter/material.dart';

class ProjectDetailsScreen extends StatelessWidget {
  final String token;
  final int projectId;
  final String projectTitle;

  const ProjectDetailsScreen({
    super.key,
    required this.token,
    required this.projectId,
    required this.projectTitle,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF7F7FB),
      appBar: AppBar(
        title: Text(projectTitle),
        backgroundColor: const Color(0xFF6750A4),
        foregroundColor: Colors.white,
      ),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              projectTitle,
              style: const TextStyle(fontSize: 26, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 12),
            Text('Project ID: $projectId'),
            const SizedBox(height: 30),
            const Card(
              child: ListTile(
                leading: Icon(Icons.upload_file),
                title: Text('Upload Assignment'),
                subtitle: Text('PDF upload coming next'),
              ),
            ),
            const Card(
              child: ListTile(
                leading: Icon(Icons.auto_awesome),
                title: Text('Extract Requirements'),
                subtitle: Text('AI analysis coming next'),
              ),
            ),
            const Card(
              child: ListTile(
                leading: Icon(Icons.checklist),
                title: Text('Checklist'),
                subtitle: Text('Track your project requirements'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
