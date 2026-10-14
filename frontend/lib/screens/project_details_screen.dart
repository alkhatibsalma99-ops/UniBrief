import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';

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
  bool isUploading = false;
  bool isAnalyzing = false;
  bool isLoadingRequirements = false;
  bool isGeneratingChecklist = false;
  bool isLoadingChecklist = false;

  String? errorMessage;
  String? requirementsError;
  String? checklistError;

  int? selectedFileId;

  @override
  void initState() {
    super.initState();
    loadFiles();
    loadRequirements();
    loadChecklist();
  }

  // =========================
  // SHOW MESSAGE
  // =========================
  void showMessage(String message, {bool isError = false}) {
    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: isError ? Colors.red : Colors.green,
      ),
    );
  }

  // =========================
  // LOAD PROJECT FILES
  // =========================
  Future<void> loadFiles() async {
    setState(() {
      isLoading = true;
      errorMessage = null;
    });

    try {
      final result = await ApiService.getProjectFiles(
        widget.token,
        widget.projectId,
      );

      if (!mounted) return;

      setState(() {
        files = result;

        final availableIds = files
            .whereType<Map>()
            .map((file) => file['id'])
            .whereType<int>()
            .toList();

        if (!availableIds.contains(selectedFileId)) {
          selectedFileId = null;
        }
      });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        errorMessage = e.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          isLoading = false;
        });
      }
    }
  }

  // =========================
  // LOAD REQUIREMENTS
  // =========================
  Future<void> loadRequirements() async {
    setState(() {
      isLoadingRequirements = true;
      requirementsError = null;
    });

    try {
      final result = await ApiService.getRequirements(
        widget.token,
        widget.projectId,
      );

      if (!mounted) return;

      setState(() {
        requirements = result;
      });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        requirementsError = e.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          isLoadingRequirements = false;
        });
      }
    }
  }

  // =========================
  // LOAD CHECKLIST
  // =========================
  Future<void> loadChecklist() async {
    setState(() {
      isLoadingChecklist = true;
      checklistError = null;
    });

    try {
      final result = await ApiService.getChecklist(
        widget.token,
        widget.projectId,
      );

      if (!mounted) return;

      setState(() {
        checklist = result;
      });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        checklistError = e.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          isLoadingChecklist = false;
        });
      }
    }
  }

  // =========================
  // UPLOAD PDF
  // =========================
  Future<void> uploadPdf() async {
    if (isUploading || isAnalyzing) return;

    try {
      final List<PlatformFile> selectedFiles = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['pdf'],
      );

      if (selectedFiles.isEmpty) {
        return;
      }

      final selectedFile = selectedFiles.first;

      if (!selectedFile.name.toLowerCase().endsWith('.pdf')) {
        showMessage('Please select a PDF file.', isError: true);
        return;
      }

      if (!mounted) return;

      setState(() {
        isUploading = true;
      });

      final uploadedFile = await ApiService.uploadPdf(
        widget.token,
        widget.projectId,
        selectedFile,
      );

      if (!mounted) return;

      await loadFiles();

      if (!mounted) return;

      final uploadedId = uploadedFile['id'];

      if (uploadedId is int) {
        setState(() {
          selectedFileId = uploadedId;
        });
      }

      showMessage('PDF uploaded successfully!');
    } catch (e) {
      if (!mounted) return;

      showMessage('Upload failed: $e', isError: true);
    } finally {
      if (mounted) {
        setState(() {
          isUploading = false;
        });
      }
    }
  }

  // =========================
  // EXTRACT REQUIREMENTS WITH AI
  // =========================
  Future<void> extractRequirements(int fileId) async {
    if (isAnalyzing || isUploading) return;

    setState(() {
      isAnalyzing = true;
    });

    try {
      await ApiService.analyzeFile(widget.token, widget.projectId, fileId);

      if (!mounted) return;

      await loadRequirements();

      if (!mounted) return;

      if (requirementsError != null) {
        showMessage(
          'Analysis completed, but loading results failed.',
          isError: true,
        );
      } else {
        showMessage('Requirements extracted successfully!');
      }
    } catch (e) {
      if (!mounted) return;

      showMessage('AI analysis failed: $e', isError: true);
    } finally {
      if (mounted) {
        setState(() {
          isAnalyzing = false;
        });
      }
    }
  }

  // =========================
  // GENERATE CHECKLIST
  // =========================
  Future<void> createChecklist() async {
    if (isGeneratingChecklist || isAnalyzing || isUploading) {
      return;
    }

    setState(() {
      isGeneratingChecklist = true;
    });

    try {
      await ApiService.generateChecklist(widget.token, widget.projectId);

      if (!mounted) return;

      await loadChecklist();

      if (!mounted) return;

      if (checklistError != null) {
        showMessage('Checklist generated, but loading failed.', isError: true);
      } else {
        showMessage('Checklist generated successfully!');
      }
    } catch (e) {
      if (!mounted) return;

      showMessage('Checklist generation failed: $e', isError: true);
    } finally {
      if (mounted) {
        setState(() {
          isGeneratingChecklist = false;
        });
      }
    }
  }

  // =========================
  // GET FILE NAME
  // =========================
  String getFileName(dynamic file) {
    if (file is Map) {
      final name =
          file['original_filename'] ?? file['filename'] ?? file['name'];

      if (name != null) {
        return name.toString();
      }
    }

    return 'Uploaded PDF';
  }

  // =========================
  // GET REQUIREMENT TEXT
  // =========================
  String getRequirementText(dynamic requirement) {
    if (requirement is Map) {
      final value =
          requirement['text'] ??
          requirement['description'] ??
          requirement['requirement_text'] ??
          requirement['content'] ??
          requirement['title'];

      if (value != null) {
        return value.toString();
      }
    }

    return requirement.toString();
  }

  // =========================
  // GET CHECKLIST TITLE
  // =========================
  String getChecklistTitle(dynamic item) {
    if (item is Map) {
      final value =
          item['text'] ??
          item['title'] ??
          item['description'] ??
          item['content'];

      if (value != null) {
        return value.toString();
      }
    }

    return item.toString();
  }

  // =========================
  // ACTION CARD
  // =========================
  Widget buildActionCard({
    required IconData icon,
    required String title,
    required String subtitle,
    required VoidCallback? onTap,
  }) {
    return Card(
      margin: const EdgeInsets.only(bottom: 14),
      elevation: 2,
      child: ListTile(
        contentPadding: const EdgeInsets.all(16),
        leading: Icon(icon, color: Colors.deepPurple, size: 32),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
        subtitle: Text(subtitle),
        trailing: const Icon(Icons.arrow_forward_ios, size: 18),
        onTap: onTap,
      ),
    );
  }

  // =========================
  // BUILD SCREEN
  // =========================
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.projectTitle),
        backgroundColor: Colors.deepPurple,
        foregroundColor: Colors.white,
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          await loadFiles();
          await loadRequirements();
          await loadChecklist();
        },
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            // =========================
            // PROJECT INFORMATION
            // =========================
            Text(
              widget.projectTitle,
              style: const TextStyle(fontSize: 26, fontWeight: FontWeight.bold),
            ),

            const SizedBox(height: 6),

            Text(
              'Project ID: ${widget.projectId}',
              style: const TextStyle(color: Colors.grey),
            ),

            const SizedBox(height: 24),

            // =========================
            // UPLOAD ASSIGNMENT
            // =========================
            buildActionCard(
              icon: Icons.upload_file,
              title: 'Upload Assignment',
              subtitle: isUploading
                  ? 'Uploading your PDF...'
                  : 'Select and upload a PDF file',
              onTap: isUploading || isAnalyzing ? null : uploadPdf,
            ),

            if (isUploading) ...[
              const LinearProgressIndicator(),
              const SizedBox(height: 16),
            ],

            // =========================
            // EXTRACT REQUIREMENTS
            // =========================
            buildActionCard(
              icon: Icons.auto_awesome,
              title: 'Extract Requirements',
              subtitle: isAnalyzing
                  ? 'AI is analyzing your PDF...'
                  : selectedFileId == null
                  ? 'Select a PDF below first'
                  : 'Analyze selected PDF with AI',
              onTap: isAnalyzing || isUploading || selectedFileId == null
                  ? null
                  : () => extractRequirements(selectedFileId!),
            ),

            if (isAnalyzing) ...[
              const LinearProgressIndicator(),
              const SizedBox(height: 16),
              const Text('AI is extracting requirements...'),
            ],

            // =========================
            // GENERATE CHECKLIST
            // =========================
            buildActionCard(
              icon: Icons.checklist,
              title: 'Generate Checklist',
              subtitle: isGeneratingChecklist
                  ? 'Generating checklist...'
                  : 'Convert requirements into tasks',
              onTap:
                  isGeneratingChecklist ||
                      isAnalyzing ||
                      isUploading ||
                      requirements.isEmpty
                  ? null
                  : createChecklist,
            ),

            if (isGeneratingChecklist) ...[
              const LinearProgressIndicator(),
              const SizedBox(height: 16),
            ],

            const SizedBox(height: 24),

            // =========================
            // UPLOADED FILES
            // =========================
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Expanded(
                  child: Text(
                    'Uploaded Files',
                    style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                  ),
                ),
                IconButton(
                  onPressed: isLoading ? null : loadFiles,
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),

            const SizedBox(height: 12),

            if (isLoading)
              const Center(
                child: Padding(
                  padding: EdgeInsets.all(20),
                  child: CircularProgressIndicator(),
                ),
              )
            else if (errorMessage != null)
              Text(
                'Could not load files: $errorMessage',
                style: const TextStyle(color: Colors.red),
              )
            else if (files.isEmpty)
              const Card(
                child: Padding(
                  padding: EdgeInsets.all(20),
                  child: Text(
                    'No files uploaded yet.',
                    textAlign: TextAlign.center,
                  ),
                ),
              )
            else
              RadioGroup<int>(
                groupValue: selectedFileId,
                onChanged: (value) {
                  setState(() {
                    selectedFileId = value;
                  });
                },
                child: Column(
                  children: files.map((file) {
                    final dynamic rawId = file is Map ? file['id'] : null;

                    final int? fileId = rawId is int ? rawId : null;

                    return Card(
                      child: RadioListTile<int>(
                        value: fileId ?? -1,
                        enabled: fileId != null && !isAnalyzing && !isUploading,
                        secondary: const Icon(
                          Icons.picture_as_pdf,
                          color: Colors.red,
                        ),
                        title: Text(getFileName(file)),
                        subtitle: const Text('Select for AI analysis'),
                        activeColor: Colors.deepPurple,
                      ),
                    );
                  }).toList(),
                ),
              ),

            const SizedBox(height: 28),

            // =========================
            // EXTRACTED REQUIREMENTS
            // =========================
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Expanded(
                  child: Text(
                    'Extracted Requirements',
                    style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                  ),
                ),
                IconButton(
                  onPressed: isLoadingRequirements ? null : loadRequirements,
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),

            const SizedBox(height: 12),

            if (isLoadingRequirements)
              const Center(
                child: Padding(
                  padding: EdgeInsets.all(20),
                  child: CircularProgressIndicator(),
                ),
              )
            else if (requirementsError != null)
              Text(
                'Could not load requirements: '
                '$requirementsError',
                style: const TextStyle(color: Colors.red),
              )
            else if (requirements.isEmpty)
              const Card(
                child: Padding(
                  padding: EdgeInsets.all(20),
                  child: Text(
                    'No requirements extracted yet.',
                    textAlign: TextAlign.center,
                  ),
                ),
              )
            else
              ...requirements.map((requirement) {
                return Card(
                  child: ListTile(
                    leading: const Icon(
                      Icons.check_circle_outline,
                      color: Colors.deepPurple,
                    ),
                    title: Text(getRequirementText(requirement)),
                  ),
                );
              }),

            const SizedBox(height: 28),

            // =========================
            // ASSIGNMENT CHECKLIST
            // =========================
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Expanded(
                  child: Text(
                    'Assignment Checklist',
                    style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                  ),
                ),
                IconButton(
                  onPressed: isLoadingChecklist ? null : loadChecklist,
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),

            const SizedBox(height: 12),

            if (isLoadingChecklist)
              const Center(
                child: Padding(
                  padding: EdgeInsets.all(20),
                  child: CircularProgressIndicator(),
                ),
              )
            else if (checklistError != null)
              Text(
                'Could not load checklist: $checklistError',
                style: const TextStyle(color: Colors.red),
              )
            else if (checklist.isEmpty)
              const Card(
                child: Padding(
                  padding: EdgeInsets.all(20),
                  child: Text(
                    'No checklist generated yet.',
                    textAlign: TextAlign.center,
                  ),
                ),
              )
            else
              ...checklist.map((item) {
                return Card(
                  child: ListTile(
                    leading: const Icon(
                      Icons.check_box_outline_blank,
                      color: Colors.deepPurple,
                    ),
                    title: Text(getChecklistTitle(item)),
                  ),
                );
              }),
          ],
        ),
      ),
    );
  }
}
