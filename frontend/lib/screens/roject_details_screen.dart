import 'package:flutter/material.dart';
import '../services/api_service.dart';

class ProjectDetailsScreen extends StatefulWidget {
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
  State<ProjectDetailsScreen> createState() => _ProjectDetailsScreenState();
}

class _ProjectDetailsScreenState extends State<ProjectDetailsScreen> {
  List<dynamic> files = [];
  List<dynamic> requirements = [];
  List<dynamic> checklist = [];

  bool isLoading = true;
  String? errorMessage;

  @override
  void initState() {
    super.initState();
    loadProjectData();
  }

  Future<void> loadProjectData() async {
    setState(() {
      isLoading = true;
      errorMessage = null;
    });

    try {
      final results = await Future.wait([
        ApiService.getProjectFiles(widget.token, widget.projectId),
        ApiService.getRequirements(widget.token, widget.projectId),
        ApiService.getChecklist(widget.token, widget.projectId),
      ]);

      if (!mounted) return;

      setState(() {
        files = results[0];
        requirements = results[1];
        checklist = results[2];
        isLoading = false;
      });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        isLoading = false;
        errorMessage = e.toString();
      });
    }
  }

  Future<void> generateChecklist() async {
    try {
      await ApiService.generateChecklist(widget.token, widget.projectId);

      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Checklist generated successfully!')),
      );

      await loadProjectData();
    } catch (e) {
      if (!mounted) return;

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Error: $e')));
    }
  }

  Widget buildSectionTitle(String title, IconData icon) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Row(
        children: [
          Icon(icon, color: const Color(0xFF6750A4)),
          const SizedBox(width: 10),
          Text(
            title,
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
          ),
        ],
      ),
    );
  }

  Widget buildFileSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildSectionTitle('Assignment Files', Icons.picture_as_pdf),
        if (files.isEmpty)
          const Text('No files uploaded yet.')
        else
          ...files.map((file) {
            final name =
                file['filename'] ??
                file['original_filename'] ??
                'Assignment file';

            return Card(
              child: ListTile(
                leading: const Icon(Icons.picture_as_pdf, color: Colors.red),
                title: Text(name.toString()),
                subtitle: Text('File ID: ${file['id']}'),
                trailing: IconButton(
                  tooltip: 'Analyze with AI',
                  icon: const Icon(Icons.auto_awesome),
                  onPressed: () async {
                    try {
                      await ApiService.analyzeFile(
                        widget.token,
                        widget.projectId,
                        (file['id'] as num).toInt(),
                      );

                      if (!mounted) return;

                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('AI analysis completed!')),
                      );

                      await loadProjectData();
                    } catch (e) {
                      if (!mounted) return;

                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(content: Text('Analysis failed: $e')),
                      );
                    }
                  },
                ),
              ),
            );
          }),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: null,
          icon: const Icon(Icons.upload_file),
          label: const Text('Upload PDF - Coming Next'),
        ),
      ],
    );
  }

  Widget buildRequirementsSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildSectionTitle('Requirements', Icons.fact_check_outlined),
        if (requirements.isEmpty)
          const Text('No requirements extracted yet.')
        else
          ...requirements.map((requirement) {
            final content =
                requirement['text'] ??
                requirement['description'] ??
                requirement['title'] ??
                requirement.toString();

            return Card(
              child: ListTile(
                leading: const Icon(Icons.check_circle_outline),
                title: Text(content.toString()),
              ),
            );
          }),
      ],
    );
  }

  Widget buildChecklistSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        buildSectionTitle('Checklist', Icons.checklist),
        if (checklist.isEmpty)
          const Text('No checklist items yet.')
        else
          ...checklist.map((item) {
            final content =
                item['text'] ??
                item['title'] ??
                item['description'] ??
                item.toString();

            return Card(
              child: ListTile(
                leading: const Icon(Icons.task_alt),
                title: Text(content.toString()),
              ),
            );
          }),
        const SizedBox(height: 12),
        ElevatedButton.icon(
          onPressed: generateChecklist,
          icon: const Icon(Icons.auto_awesome),
          label: const Text('Generate Checklist'),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF7F7FB),
      appBar: AppBar(
        title: Text(widget.projectTitle),
        backgroundColor: const Color(0xFF6750A4),
        foregroundColor: Colors.white,
      ),
      body: isLoading
          ? const Center(child: CircularProgressIndicator())
          : errorMessage != null
          ? Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text('Error: $errorMessage'),
                  const SizedBox(height: 12),
                  ElevatedButton(
                    onPressed: loadProjectData,
                    child: const Text('Retry'),
                  ),
                ],
              ),
            )
          : RefreshIndicator(
              onRefresh: loadProjectData,
              child: ListView(
                padding: const EdgeInsets.all(24),
                children: [
                  Text(
                    widget.projectTitle,
                    style: const TextStyle(
                      fontSize: 28,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Text('Manage assignment files and requirements.'),
                  const SizedBox(height: 24),
                  buildFileSection(),
                  const Divider(height: 40),
                  buildRequirementsSection(),
                  const Divider(height: 40),
                  buildChecklistSection(),
                ],
              ),
            ),
    );
  }
}
