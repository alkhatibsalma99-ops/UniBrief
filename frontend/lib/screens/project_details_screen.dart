import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart' as picker;

import '../services/api_service.dart';
import '../services/error_handler.dart';

class ProjectDetailsScreen extends StatefulWidget {
  final String token;
  final int projectId;
  final String projectTitle;
  final String selectedLanguage;
  final ValueChanged<String> onLanguageChanged;

  const ProjectDetailsScreen({
    super.key,
    required this.token,
    required this.projectId,
    required this.projectTitle,
    required this.selectedLanguage,
    required this.onLanguageChanged,
  });

  @override
  State<ProjectDetailsScreen> createState() => _ProjectDetailsScreenState();
}

class _ProjectDetailsScreenState extends State<ProjectDetailsScreen> {
  List<dynamic> files = [];
  List<dynamic> requirements = [];
  List<dynamic> checklist = [];
  List<dynamic> submissionResults = [];

  dynamic submissionReport;

  int? selectedFileId;
  int? selectedSubmissionFileId;
  int? selectedReportFileId;

  bool hasReportFile(int? id) {
    return hasFileRole(id, ApiService.submissionRole) ||
        hasFileRole(id, ApiService.unclassifiedRole);
  }

  bool isLoadingFiles = false;
  bool isUploading = false;
  bool isAssigningRole = false;
  bool isDeletingFile = false;

  bool get fileActionsBusy =>
      isUploading ||
      isAssigningRole ||
      isDeletingFile ||
      isLoadingFiles ||
      isAnalyzing ||
      isCheckingSubmission ||
      isLoadingReport;

  List<dynamic> filesByRole(String role) {
    return files.where((file) {
      return itemId(file) != null && ApiService.getFileRole(file) == role;
    }).toList();
  }

  bool hasFileRole(int? id, String role) {
    if (id == null) return false;

    return filesByRole(role).any((file) => itemId(file) == id);
  }

  String fileName(dynamic file) {
    if (file is Map) {
      return (file['filename'] ?? file['name'] ?? 'PDF').toString();
    }

    return 'PDF';
  }

  bool isAnalyzing = false;
  bool isLoadingRequirements = false;
  bool isGeneratingChecklist = false;
  bool isLoadingChecklist = false;
  bool isCheckingSubmission = false;
  bool isLoadingSubmissionResults = false;
  bool isLoadingReport = false;
  bool isTranslating = false;

  String? filesError;
  String? requirementsError;
  String? checklistError;
  String? submissionError;
  String? reportError;
  String friendlyError(Object error) {
    return ErrorHandler.message(
      error,
      Localizations.localeOf(context).languageCode,
    );
  }

  final Set<int> updatingItemIds = {};

  final Map<String, String> _translationCache = {};
  final Set<String> _failedTranslations = {};

  String _currentLanguage = 'en';
  bool _translationRunning = false;
  bool _translationPending = false;

  String get language => _currentLanguage;

  String t(String en, String de, String ar) {
    switch (_currentLanguage) {
      case 'de':
        return de;
      case 'ar':
        return ar;
      default:
        return en;
    }
  }

  @override
  void initState() {
    super.initState();
    _currentLanguage = widget.selectedLanguage;
    refreshAll();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();

    final newLanguage = Localizations.localeOf(context).languageCode;

    if (_currentLanguage != newLanguage) {
      _currentLanguage = newLanguage;

      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          _scheduleTranslation();
        }
      });
    }
  }

  void showMessage(String message, {bool error = false}) {
    if (!mounted) return;

    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: error ? Colors.red : Colors.green,
        ),
      );
  }

  int? itemId(dynamic item) {
    if (item is! Map) return null;

    final value = item['id'];

    if (value is int) return value;
    return int.tryParse('$value');
  }

  String getText(dynamic item) {
    if (item == null) return '';

    if (item is Map) {
      final value =
          item['text'] ??
          item['requirement_text'] ??
          item['description'] ??
          item['title'] ??
          item['content'] ??
          item['task'] ??
          item['feedback'];

      return value?.toString() ?? '';
    }

    return item.toString();
  }

  String getChecklistTitle(dynamic item) {
    if (item is Map) {
      return (item['title'] ??
              item['text'] ??
              item['task'] ??
              item['description'] ??
              item['content'] ??
              '')
          .toString();
    }

    return getText(item);
  }

  bool isCompleted(dynamic item) {
    if (item is! Map) return false;

    final value = item['completed'] ?? item['is_completed'] ?? item['done'];

    return value == true || value == 1 || value == 'true';
  }

  String getResultFeedback(dynamic item) {
    if (item is Map) {
      return (item['feedback'] ??
              item['message'] ??
              item['description'] ??
              item['details'] ??
              '')
          .toString();
    }

    return getText(item);
  }

  String getResultStatus(dynamic item) {
    if (item is Map) {
      return (item['status'] ?? item['result'] ?? '').toString();
    }

    return '';
  }

  // ==========================================
  // CONTENT TRANSLATION
  // ==========================================

  String _translationKey(String lang, String text) {
    return '$lang\u0000$text';
  }

  String displayText(String original) {
    if (original.trim().isEmpty) return original;

    if (_currentLanguage == 'en') {
      return original;
    }

    return _translationCache[_translationKey(_currentLanguage, original)] ??
        original;
  }

  Widget contentText(String original, {TextStyle? style}) {
    return Text(displayText(original), style: style);
  }

  void _scheduleTranslation() {
    if (!mounted) return;

    if (_currentLanguage == 'en') {
      if (isTranslating) {
        setState(() => isTranslating = false);
      }
      return;
    }

    _translationPending = true;

    if (!_translationRunning) {
      _processTranslations();
    }
  }

  List<String> _collectTexts() {
    final texts = <String>{};

    void add(dynamic value) {
      if (value is String && value.trim().isNotEmpty) {
        texts.add(value);
      }
    }

    void collect(dynamic value) {
      if (value is String) {
        add(value);
      } else if (value is List) {
        for (final item in value) {
          collect(item);
        }
      } else if (value is Map) {
        for (final entry in value.entries) {
          final key = entry.key.toString();

          if ([
            'id',
            'project_id',
            'file_id',
            'requirement_id',
            'checklist_item_id',
            'created_at',
            'updated_at',
            'filename',
            'stored_path',
            'path',
            'url',
            'status',
            'result',
            'completed',
            'is_completed',
            'done',
            'score',
            'percentage',
          ].contains(key)) {
            continue;
          }

          collect(entry.value);
        }
      }
    }

    for (final item in requirements) {
      collect(item);
    }

    for (final item in checklist) {
      collect(item);
    }

    for (final item in submissionResults) {
      collect(item);
    }

    if (submissionReport != null) {
      collect(submissionReport);
    }

    return texts.toList();
  }

  Future<void> _processTranslations() async {
    if (_translationRunning || !mounted) return;

    _translationRunning = true;

    try {
      while (_translationPending && mounted) {
        _translationPending = false;

        final requestedLanguage = _currentLanguage;

        if (requestedLanguage == 'en') {
          continue;
        }

        final missing = _collectTexts().where((text) {
          final key = _translationKey(requestedLanguage, text);

          return !_translationCache.containsKey(key) &&
              !_failedTranslations.contains(key);
        }).toList();

        if (missing.isEmpty) continue;

        setState(() => isTranslating = true);

        try {
          final translated = await ApiService.translateContent(
            token: widget.token,
            projectId: widget.projectId,
            language: requestedLanguage,
            texts: missing,
          );

          if (!mounted) return;

          if (translated.length != missing.length) {
            throw Exception('Translation count mismatch');
          }

          setState(() {
            for (var i = 0; i < missing.length; i++) {
              _translationCache[_translationKey(
                    requestedLanguage,
                    missing[i],
                  )] =
                  translated[i];
            }
          });
        } catch (e) {
          debugPrint('Translation error: ${e.runtimeType}');
          for (final text in missing) {
            _failedTranslations.add(_translationKey(requestedLanguage, text));
          }

          if (mounted) {
            showMessage(
              t(
                'Translation unavailable. Showing original text.',
                'Übersetzung nicht verfügbar. Originaltext wird angezeigt.',
                'الترجمة غير متاحة، سيتم عرض النص الأصلي.',
              ),
              error: true,
            );
          }
        }
      }
    } finally {
      _translationRunning = false;

      if (mounted) {
        setState(() => isTranslating = false);
      }
    }
  }

  // ==========================================
  // LOAD DATA
  // ==========================================

  Future<void> refreshAll() async {
    if (fileActionsBusy) return;

    await Future.wait([
      loadFiles(),
      loadRequirements(),
      loadChecklist(),
      loadSubmissionResults(),
    ]);
  }

  Future<void> loadFiles() async {
    if (!mounted) return;

    setState(() {
      isLoadingFiles = true;
      filesError = null;
    });

    try {
      final result = await ApiService.getProjectFiles(
        widget.token,
        widget.projectId,
      );

      if (!mounted) return;

      setState(() {
        files = result;

        if (!hasFileRole(selectedFileId, ApiService.requirementsRole)) {
          selectedFileId = null;
        }

        if (!hasFileRole(selectedSubmissionFileId, ApiService.submissionRole)) {
          selectedSubmissionFileId = null;
        }

        if (!hasReportFile(selectedReportFileId)) {
          selectedReportFileId = null;
          submissionReport = null;
          reportError = null;
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => filesError = friendlyError(e));
    } finally {
      if (mounted) {
        setState(() => isLoadingFiles = false);
      }
    }
  }

  Future<void> loadRequirements() async {
    if (!mounted) return;

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

      setState(() => requirements = result);
      _scheduleTranslation();
    } catch (e) {
      if (!mounted) return;
      setState(() => requirementsError = friendlyError(e));
    } finally {
      if (mounted) {
        setState(() => isLoadingRequirements = false);
      }
    }
  }

  Future<void> loadChecklist() async {
    if (!mounted) return;

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

      setState(() => checklist = result);
      _scheduleTranslation();
    } catch (e) {
      if (!mounted) return;
      setState(() => checklistError = friendlyError(e));
    } finally {
      if (mounted) {
        setState(() => isLoadingChecklist = false);
      }
    }
  }

  Future<void> loadSubmissionResults() async {
    if (!mounted) return;

    setState(() {
      isLoadingSubmissionResults = true;
      submissionError = null;
    });

    try {
      final result = await ApiService.getSubmissionResults(
        widget.token,
        widget.projectId,
      );

      if (!mounted) return;

      setState(() => submissionResults = result);
      _scheduleTranslation();
    } catch (e) {
      if (!mounted) return;
      setState(() => submissionError = friendlyError(e));
    } finally {
      if (mounted) {
        setState(() => isLoadingSubmissionResults = false);
      }
    }
  }

  // ==========================================
  // PDF UPLOAD
  // ==========================================

  Future<void> uploadPdf(String role) async {
    if (fileActionsBusy) return;

    if (!ApiService.assignableFileRoles.contains(role)) {
      return;
    }

    setState(() => isUploading = true);

    try {
      final selectedFiles = await picker.FilePicker.pickFiles(
        type: picker.FileType.custom,
        allowedExtensions: ['pdf'],
      );

      if (!mounted || selectedFiles.isEmpty) {
        return;
      }

      setState(() => filesError = null);

      await ApiService.uploadPdf(
        widget.token,
        widget.projectId,
        selectedFiles.first,
        fileRole: role,
      );

      if (!mounted) return;

      await loadFiles();

      if (!mounted) return;

      showMessage(
        t(
          'PDF uploaded successfully',
          'PDF erfolgreich hochgeladen',
          'تم رفع ملف PDF بنجاح',
        ),
      );
    } catch (e) {
      if (!mounted) return;

      showMessage(friendlyError(e), error: true);
    } finally {
      if (mounted) {
        setState(() => isUploading = false);
      }
    }
  }

  Future<void> assignFileRole(int fileId, String role) async {
    if (fileActionsBusy || filesError != null) return;

    if (!ApiService.assignableFileRoles.contains(role)) {
      return;
    }

    if (!hasFileRole(fileId, ApiService.unclassifiedRole)) {
      return;
    }

    setState(() => isAssigningRole = true);

    try {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text(
            t('Assign file role?', 'Dateityp zuweisen?', 'تحديد نوع الملف؟'),
          ),
          content: Text(
            t(
              'The assigned role cannot be changed later. '
                  'Please select the correct file type.',
              'Der zugewiesene Dateityp kann später '
                  'nicht geändert werden.',
              'لا يمكن تغيير نوع الملف بعد تصنيفه. '
                  'يرجى التأكد من اختيار النوع الصحيح.',
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: Text(t('Cancel', 'Abbrechen', 'إلغاء')),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: Text(
                role == ApiService.requirementsRole
                    ? t('Requirements', 'Anforderungen', 'المتطلبات')
                    : t('Submission', 'Abgabe', 'التسليم'),
              ),
            ),
          ],
        ),
      );

      if (!mounted || confirmed != true) return;

      await ApiService.updateFileRole(
        widget.token,
        widget.projectId,
        fileId,
        role,
      );

      if (!mounted) return;

      await loadFiles();

      if (!mounted) return;

      showMessage(
        t(
          'File role assigned successfully',
          'Dateityp erfolgreich zugewiesen',
          'تم تصنيف الملف بنجاح',
        ),
      );
    } catch (e) {
      if (!mounted) return;

      if (e is ApiException && e.statusCode == 409) {
        showMessage(
          t(
            'This file cannot be assigned to the selected '
                'role because of its existing data or role.',
            'Diese Datei kann aufgrund vorhandener Daten '
                'oder ihres Dateityps nicht zugeordnet werden.',
            'لا يمكن تصنيف الملف بهذا النوع بسبب '
                'البيانات المرتبطة به أو تصنيفه الحالي.',
          ),
          error: true,
        );
      } else {
        showMessage(friendlyError(e), error: true);
      }
    } finally {
      if (mounted) {
        setState(() => isAssigningRole = false);
      }
    }
  }

  Future<void> deletePdfFile(int fileId, String fileName) async {
    if (fileActionsBusy || filesError != null) return;

    setState(() => isDeletingFile = true);

    try {
      await _deletePdfFile(fileId, fileName);
    } finally {
      if (mounted) {
        setState(() => isDeletingFile = false);
      }
    }
  }

  Future<void> _deletePdfFile(int fileId, String fileName) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(t('Delete PDF?', 'PDF löschen?', 'حذف ملف PDF؟')),
        content: Text(
          t(
            'Are you sure you want to delete "$fileName"? '
                'Related requirements, checklist items and '
                'submission results may also be deleted.',
            'Möchtest du "$fileName" wirklich löschen? '
                'Zugehörige Anforderungen, Checklistenpunkte '
                'und Prüfergebnisse können ebenfalls gelöscht werden.',
            'هل أنتِ متأكدة من حذف "$fileName"؟ '
                'قد تُحذف أيضاً المتطلبات والمهام ونتائج الفحص المرتبطة به.',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: Text(t('Cancel', 'Abbrechen', 'إلغاء')),
          ),
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: Text(
              t('Delete', 'Löschen', 'حذف'),
              style: const TextStyle(color: Colors.red),
            ),
          ),
        ],
      ),
    );

    if (confirmed != true || !mounted) return;

    try {
      await ApiService.deletePdf(widget.token, widget.projectId, fileId);

      if (!mounted) return;

      setState(() {
        if (selectedSubmissionFileId == fileId) {
          selectedSubmissionFileId = null;
        }

        if (selectedReportFileId == fileId) {
          selectedReportFileId = null;
        }

        submissionReport = null;
        reportError = null;
        submissionResults = [];
      });

      await loadFiles();
      if (!mounted) return;

      await loadRequirements();
      if (!mounted) return;

      await loadChecklist();
      if (!mounted) return;

      await loadSubmissionResults();
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            t(
              'PDF deleted successfully!',
              'PDF erfolgreich gelöscht!',
              'تم حذف ملف PDF بنجاح!',
            ),
          ),
          backgroundColor: Colors.green,
        ),
      );
    } catch (e) {
      if (!mounted) return;

      showMessage(friendlyError(e), error: true);
    }
  }

  // ==========================================
  // AI ANALYSIS
  // ==========================================

  Future<void> analyzePdf() async {
    final fileId = selectedFileId;

    if (fileId == null ||
        fileActionsBusy ||
        filesError != null ||
        !hasFileRole(fileId, ApiService.requirementsRole)) {
      return;
    }

    setState(() => isAnalyzing = true);

    try {
      await ApiService.analyzeFile(widget.token, widget.projectId, fileId);

      if (!mounted) return;

      await loadRequirements();

      if (!mounted) return;

      showMessage(
        t(
          'AI analysis completed',
          'KI-Analyse abgeschlossen',
          'اكتمل تحليل الملف بالذكاء الاصطناعي',
        ),
      );
    } catch (e) {
      if (!mounted) return;
      showMessage(friendlyError(e), error: true);
    } finally {
      if (mounted) {
        setState(() => isAnalyzing = false);
      }
    }
  }

  // ==========================================
  // CHECKLIST
  // ==========================================

  Future<void> generateChecklist() async {
    if (isGeneratingChecklist || requirements.isEmpty) {
      return;
    }

    setState(() => isGeneratingChecklist = true);

    try {
      final result = await ApiService.generateChecklist(
        widget.token,
        widget.projectId,
      );

      if (!mounted) return;

      setState(() => checklist = result);
      _scheduleTranslation();

      showMessage(
        t(
          'Checklist generated',
          'Checkliste erstellt',
          'تم إنشاء قائمة المهام',
        ),
      );
    } catch (e) {
      if (!mounted) return;
      showMessage(friendlyError(e), error: true);
    } finally {
      if (mounted) {
        setState(() => isGeneratingChecklist = false);
      }
    }
  }

  Future<void> toggleChecklist(dynamic item, bool completed) async {
    final id = itemId(item);

    if (id == null || updatingItemIds.contains(id)) {
      return;
    }

    setState(() => updatingItemIds.add(id));

    try {
      await ApiService.updateChecklistItem(widget.token, id, completed);

      if (!mounted) return;

      await loadChecklist();
    } catch (e) {
      if (!mounted) return;
      showMessage(friendlyError(e), error: true);
    } finally {
      if (mounted) {
        setState(() => updatingItemIds.remove(id));
      }
    }
  }

  // ==========================================
  // SUBMISSION CHECK
  // ==========================================

  Future<void> checkSubmission() async {
    final fileId = selectedSubmissionFileId;

    if (fileId == null ||
        fileActionsBusy ||
        filesError != null ||
        !hasFileRole(fileId, ApiService.submissionRole)) {
      return;
    }

    setState(() {
      isCheckingSubmission = true;
      selectedReportFileId = fileId;
      submissionReport = null;
      reportError = null;
    });

    try {
      await ApiService.checkSubmission(widget.token, widget.projectId, fileId);

      if (!mounted) return;

      await loadSubmissionResults();

      if (!mounted) return;

      showMessage(t('Submission checked', 'Abgabe geprüft', 'تم فحص التسليم'));
    } catch (e) {
      if (!mounted) return;
      showMessage(friendlyError(e), error: true);
    } finally {
      if (mounted) {
        setState(() => isCheckingSubmission = false);
      }
    }
  }

  Future<void> loadReport() async {
    final fileId = selectedReportFileId;

    if (fileId == null ||
        fileActionsBusy ||
        filesError != null ||
        !hasReportFile(fileId)) {
      return;
    }

    setState(() {
      isLoadingReport = true;
      submissionReport = null;
      reportError = null;
    });

    try {
      final result = await ApiService.getSubmissionReport(
        widget.token,
        widget.projectId,
        fileId,
      );

      if (!mounted) return;

      setState(() => submissionReport = result);
      _scheduleTranslation();
    } catch (e) {
      if (!mounted) return;
      setState(() => reportError = friendlyError(e));
    } finally {
      if (mounted) {
        setState(() => isLoadingReport = false);
      }
    }
  }

  // ==========================================
  // COLLAPSIBLE SECTIONS
  // ==========================================

  Widget section({
    required String title,
    required IconData icon,
    required Widget child,
  }) {
    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      elevation: 1,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: ExpansionTile(
        key: PageStorageKey<String>(title),
        initiallyExpanded: false,
        maintainState: true,
        leading: Icon(icon, color: Colors.deepPurple),
        title: Text(
          title,
          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
        ),
        childrenPadding: const EdgeInsets.all(16),
        expandedCrossAxisAlignment: CrossAxisAlignment.start,
        children: [const Divider(), const SizedBox(height: 8), child],
      ),
    );
  }

  Widget loadingOrError({
    required bool loading,
    required String? error,
    required Widget child,
  }) {
    if (loading) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(16),
          child: CircularProgressIndicator(),
        ),
      );
    }

    if (error != null) {
      return Text(error, style: const TextStyle(color: Colors.red));
    }

    return child;
  }

  Widget languageMenu() {
    return PopupMenuButton<String>(
      icon: const Icon(Icons.language),
      tooltip: t('Language', 'Sprache', 'اللغة'),
      onSelected: widget.onLanguageChanged,
      itemBuilder: (_) => const [
        PopupMenuItem(value: 'en', child: Text('English')),
        PopupMenuItem(value: 'de', child: Text('Deutsch')),
        PopupMenuItem(value: 'ar', child: Text('العربية')),
      ],
    );
  }

  Widget reportFileSelector() {
    final options = files.where((file) {
      return hasReportFile(itemId(file));
    }).toList();

    if (options.isEmpty) {
      return Text(
        t(
          'No files available for reports.',
          'Keine Dateien für Berichte verfügbar.',
          'لا توجد ملفات متاحة لعرض التقارير.',
        ),
        style: const TextStyle(color: Colors.grey),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          t('Saved Reports', 'Gespeicherte Berichte', 'التقارير المحفوظة'),
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
        ),

        const SizedBox(height: 8),

        Text(
          t(
            'View saved reports without running a new check.',
            'Gespeicherte Berichte ohne erneute Prüfung anzeigen.',
            'عرض التقارير المحفوظة دون إعادة الفحص.',
          ),
        ),

        const SizedBox(height: 12),

        DropdownButtonFormField<int>(
          key: ValueKey('report:$selectedReportFileId'),
          initialValue: hasReportFile(selectedReportFileId)
              ? selectedReportFileId
              : null,
          isExpanded: true,

          decoration: InputDecoration(
            labelText: t(
              'Select report file',
              'Berichtsdatei auswählen',
              'اختيار ملف التقرير',
            ),
            border: const OutlineInputBorder(),
          ),

          items: options.map((file) {
            final id = itemId(file)!;
            final legacy =
                ApiService.getFileRole(file) == ApiService.unclassifiedRole;

            final suffix = legacy
                ? t(' (Unclassified)', ' (Nicht zugeordnet)', ' (غير مصنف)')
                : '';

            return DropdownMenuItem<int>(
              value: id,
              child: Text(
                fileName(file) + suffix,
                overflow: TextOverflow.ellipsis,
              ),
            );
          }).toList(),

          onChanged: fileActionsBusy || filesError != null
              ? null
              : (id) {
                  setState(() {
                    selectedReportFileId = id;
                    submissionReport = null;
                    reportError = null;
                  });
                },
        ),
      ],
    );
  }

  Widget fileSelector({
    required String role,
    required int? value,
    required ValueChanged<int?> onChanged,
  }) {
    final options = filesByRole(role);

    if (options.isEmpty) {
      return Text(
        role == ApiService.requirementsRole
            ? t(
                'Upload or classify a requirements PDF first.',
                'Lade zuerst eine Anforderungs-PDF hoch '
                    'oder ordne eine Datei zu.',
                'ارفعي أو صنّفي ملف المتطلبات أولاً.',
              )
            : t(
                'Upload or classify a submission PDF first.',
                'Lade zuerst eine Abgabe-PDF hoch '
                    'oder ordne eine Datei zu.',
                'ارفعي أو صنّفي ملف التسليم أولاً.',
              ),
        style: const TextStyle(color: Colors.grey),
      );
    }

    final validIds = options.map(itemId).whereType<int>().toSet();

    return DropdownButtonFormField<int>(
      key: ValueKey('$role:$value'),
      initialValue: validIds.contains(value) ? value : null,
      isExpanded: true,
      decoration: InputDecoration(
        labelText: t(
          'Select PDF file',
          'PDF-Datei auswählen',
          'اختاري ملف PDF',
        ),
        border: const OutlineInputBorder(),
      ),
      items: options.map((file) {
        final id = itemId(file)!;

        final name = file is Map
            ? (file['filename'] ?? file['name'] ?? 'PDF $id').toString()
            : 'PDF $id';

        return DropdownMenuItem<int>(
          value: id,
          child: Text(name, overflow: TextOverflow.ellipsis),
        );
      }).toList(),
      onChanged: fileActionsBusy || filesError != null ? null : onChanged,
    );
  }

  // ==========================================
  // FILE ROLE GROUP
  // ==========================================

  Widget fileRoleGroup({
    required String role,
    required String title,
    required String description,
    required IconData icon,
    required Color color,
    String? uploadLabel,
  }) {
    final roleFiles = filesByRole(role);

    final isLegacy = role == ApiService.unclassifiedRole;

    return Card(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 16),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: color.withValues(alpha: 0.25)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: color),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    title,
                    style: TextStyle(
                      color: color,
                      fontSize: 17,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(description),

            if (uploadLabel != null) ...[
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: fileActionsBusy ? null : () => uploadPdf(role),
                  icon: const Icon(Icons.upload_file),
                  label: Text(uploadLabel),
                ),
              ),
            ],

            const SizedBox(height: 12),

            if (roleFiles.isEmpty)
              Text(
                t(
                  'No files in this category.',
                  'Keine Dateien in dieser Kategorie.',
                  'لا توجد ملفات في هذا القسم.',
                ),
              ),

            ...roleFiles.map((file) {
              final id = itemId(file);
              final name = fileName(file);

              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Divider(),

                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(Icons.picture_as_pdf, color: color),
                    title: Text(name),
                    subtitle: Text('ID: ${id ?? "-"}'),
                    trailing: IconButton(
                      tooltip: t('Delete PDF', 'PDF löschen', 'حذف ملف PDF'),
                      icon: const Icon(Icons.delete_outline, color: Colors.red),
                      onPressed: id == null || fileActionsBusy
                          ? null
                          : () => deletePdfFile(id, name),
                    ),
                  ),

                  if (isLegacy && id != null)
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        OutlinedButton(
                          onPressed: fileActionsBusy
                              ? null
                              : () => assignFileRole(
                                  id,
                                  ApiService.requirementsRole,
                                ),
                          child: Text(
                            t(
                              'As requirements',
                              'Als Anforderungen',
                              'ملف متطلبات',
                            ),
                          ),
                        ),
                        OutlinedButton(
                          onPressed: fileActionsBusy
                              ? null
                              : () => assignFileRole(
                                  id,
                                  ApiService.submissionRole,
                                ),
                          child: Text(
                            t('As submission', 'Als Abgabe', 'ملف تسليم'),
                          ),
                        ),
                      ],
                    ),
                ],
              );
            }),
          ],
        ),
      ),
    );
  }

  // ==========================================
  // MAIN SCREEN
  // ==========================================

  @override
  Widget build(BuildContext context) {
    final completed = checklist.where(isCompleted).length;

    final progress = checklist.isEmpty ? 0.0 : completed / checklist.length;

    return Scaffold(
      backgroundColor: const Color(0xFFF7F7FB),
      appBar: AppBar(
        title: Text(widget.projectTitle),
        backgroundColor: Colors.deepPurple,
        foregroundColor: Colors.white,
        actions: [
          languageMenu(),
          IconButton(
            tooltip: t('Refresh', 'Aktualisieren', 'تحديث'),
            icon: const Icon(Icons.refresh),
            onPressed: refreshAll,
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: refreshAll,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              widget.projectTitle,
              style: const TextStyle(fontSize: 25, fontWeight: FontWeight.bold),
            ),

            const SizedBox(height: 8),

            Text(
              t(
                'Manage files, AI requirements and submissions.',
                'Dateien, KI-Anforderungen und Abgaben verwalten.',
                'إدارة الملفات والمتطلبات والتسليمات.',
              ),
            ),

            if (isTranslating && _currentLanguage != 'en') ...[
              const SizedBox(height: 12),
              const LinearProgressIndicator(),
              const SizedBox(height: 5),
              Text(
                t(
                  'Translating content...',
                  'Inhalte werden übersetzt...',
                  'جارٍ ترجمة المحتوى...',
                ),
              ),
            ],

            const SizedBox(height: 20),

            // ==================================
            // PROJECT FILES
            // ==================================
            section(
              title: t('Project Files', 'Projektdateien', 'ملفات المشروع'),
              icon: Icons.folder_outlined,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (isUploading || isAssigningRole || isDeletingFile) ...[
                    const LinearProgressIndicator(),
                    const SizedBox(height: 12),
                  ],

                  loadingOrError(
                    loading: isLoadingFiles,
                    error: filesError,
                    child: Column(
                      children: [
                        fileRoleGroup(
                          role: ApiService.requirementsRole,
                          title: t(
                            'Requirements Documents',
                            'Anforderungsdokumente',
                            'ملفات المتطلبات',
                          ),
                          description: t(
                            'Upload assignment instructions '
                                'and requirements for AI analysis.',
                            'Lade Aufgabenstellungen und '
                                'Anforderungen zur KI-Analyse hoch.',
                            'ارفعي تعليمات الأستاذ والمتطلبات '
                                'لتحليلها بالذكاء الاصطناعي.',
                          ),
                          icon: Icons.description_outlined,
                          color: Colors.deepPurple,
                          uploadLabel: t(
                            'Upload Requirements PDF',
                            'Anforderungs-PDF hochladen',
                            'رفع ملف المتطلبات PDF',
                          ),
                        ),

                        fileRoleGroup(
                          role: ApiService.submissionRole,
                          title: t(
                            'Submission Documents',
                            'Abgabedokumente',
                            'ملفات الحل والتسليم',
                          ),
                          description: t(
                            'Upload your solution to check '
                                'it against the requirements.',
                            'Lade deine Lösung hoch, um sie '
                                'mit den Anforderungen abzugleichen.',
                            'ارفعي الحل الخاص بك لفحصه '
                                'ومقارنته بالمتطلبات.',
                          ),
                          icon: Icons.fact_check_outlined,
                          color: Colors.teal,
                          uploadLabel: t(
                            'Upload Submission PDF',
                            'Abgabe-PDF hochladen',
                            'رفع ملف التسليم PDF',
                          ),
                        ),

                        if (filesByRole(ApiService.unclassifiedRole).isNotEmpty)
                          fileRoleGroup(
                            role: ApiService.unclassifiedRole,
                            title: t(
                              'Unclassified Files',
                              'Nicht zugeordnete Dateien',
                              'الملفات غير المصنفة',
                            ),
                            description: t(
                              'Assign a role to your existing '
                                  'PDF files before using them.',
                              'Ordne vorhandene PDF-Dateien '
                                  'einem Dateityp zu.',
                              'حددي نوع الملفات القديمة '
                                  'قبل استخدامها.',
                            ),
                            icon: Icons.folder_outlined,
                            color: Colors.orange.shade800,
                          ),
                      ],
                    ),
                  ),

                  if (filesError != null)
                    TextButton.icon(
                      onPressed: fileActionsBusy ? null : loadFiles,
                      icon: const Icon(Icons.refresh),
                      label: Text(
                        t('Retry', 'Erneut versuchen', 'إعادة المحاولة'),
                      ),
                    ),
                ],
              ),
            ),

            // ==================================
            // AI REQUIREMENTS
            // ==================================
            section(
              title: t(
                'AI Requirements',
                'KI-Anforderungen',
                'المتطلبات بالذكاء الاصطناعي',
              ),
              icon: Icons.auto_awesome,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  fileSelector(
                    role: ApiService.requirementsRole,
                    value: selectedFileId,
                    onChanged: (id) {
                      setState(() {
                        selectedFileId = id;
                      });
                    },
                  ),

                  const SizedBox(height: 12),

                  ElevatedButton.icon(
                    onPressed:
                        fileActionsBusy ||
                            filesError != null ||
                            !hasFileRole(
                              selectedFileId,
                              ApiService.requirementsRole,
                            )
                        ? null
                        : analyzePdf,
                    icon: const Icon(Icons.auto_awesome),
                    label: Text(
                      isAnalyzing
                          ? t(
                              'Analyzing...',
                              'Analyse läuft...',
                              'جارٍ التحليل...',
                            )
                          : t(
                              'Analyze PDF with AI',
                              'PDF mit KI analysieren',
                              'تحليل PDF بالذكاء الاصطناعي',
                            ),
                    ),
                  ),

                  const SizedBox(height: 16),

                  loadingOrError(
                    loading: isLoadingRequirements,
                    error: requirementsError,
                    child: requirements.isEmpty
                        ? Text(
                            t(
                              'No requirements extracted yet.',
                              'Noch keine Anforderungen extrahiert.',
                              'لم يتم استخراج متطلبات بعد.',
                            ),
                          )
                        : Column(
                            children: requirements.asMap().entries.map((entry) {
                              final item = entry.value;

                              final title = item is Map
                                  ? (item['title'] ??
                                            item['text'] ??
                                            item['requirement_text'] ??
                                            '')
                                        .toString()
                                  : getText(item);

                              final description = item is Map
                                  ? (item['description'] ?? '').toString()
                                  : '';

                              return Card(
                                child: ListTile(
                                  leading: CircleAvatar(
                                    child: Text('${entry.key + 1}'),
                                  ),
                                  title: contentText(
                                    title,
                                    style: const TextStyle(
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  subtitle: description.isEmpty
                                      ? null
                                      : contentText(description),
                                ),
                              );
                            }).toList(),
                          ),
                  ),
                ],
              ),
            ),

            // ==================================
            // CHECKLIST
            // ==================================
            section(
              title: t('Checklist', 'Checkliste', 'قائمة المهام'),
              icon: Icons.checklist,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  ElevatedButton.icon(
                    onPressed: isGeneratingChecklist || requirements.isEmpty
                        ? null
                        : generateChecklist,
                    icon: const Icon(Icons.playlist_add),
                    label: Text(
                      isGeneratingChecklist
                          ? t(
                              'Generating...',
                              'Wird erstellt...',
                              'جارٍ الإنشاء...',
                            )
                          : t(
                              'Generate Checklist',
                              'Checkliste erstellen',
                              'إنشاء قائمة المهام',
                            ),
                    ),
                  ),

                  const SizedBox(height: 16),

                  if (checklist.isNotEmpty) ...[
                    Text(
                      '$completed / ${checklist.length} '
                      '${t("completed", "erledigt", "مكتمل")}',
                    ),
                    const SizedBox(height: 8),
                    LinearProgressIndicator(
                      value: progress,
                      minHeight: 8,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    const SizedBox(height: 12),
                  ],

                  loadingOrError(
                    loading: isLoadingChecklist,
                    error: checklistError,
                    child: checklist.isEmpty
                        ? Text(
                            t(
                              'No checklist generated yet.',
                              'Noch keine Checkliste erstellt.',
                              'لم يتم إنشاء قائمة المهام بعد.',
                            ),
                          )
                        : Column(
                            children: checklist.map((item) {
                              final id = itemId(item);

                              return CheckboxListTile(
                                value: isCompleted(item),
                                controlAffinity:
                                    ListTileControlAffinity.leading,
                                title: contentText(getChecklistTitle(item)),
                                onChanged:
                                    id == null || updatingItemIds.contains(id)
                                    ? null
                                    : (value) {
                                        toggleChecklist(item, value ?? false);
                                      },
                              );
                            }).toList(),
                          ),
                  ),
                ],
              ),
            ),

            // ==================================
            // SUBMISSION CHECK
            // ==================================
            section(
              title: t('Submission Check', 'Abgabeprüfung', 'فحص التسليم'),
              icon: Icons.fact_check_outlined,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    t(
                      'Select your final submission PDF.',
                      'Wähle deine finale Abgabe-PDF.',
                      'اختاري ملف PDF النهائي للتسليم.',
                    ),
                  ),

                  const SizedBox(height: 12),

                  OutlinedButton.icon(
                    onPressed: fileActionsBusy
                        ? null
                        : () => uploadPdf(ApiService.submissionRole),
                    icon: const Icon(Icons.upload_file),
                    label: Text(
                      isUploading
                          ? t(
                              'Uploading...',
                              'Wird hochgeladen...',
                              'جارٍ رفع الملف...',
                            )
                          : t(
                              'Upload submission PDF',
                              'Abgabe-PDF hochladen',
                              'رفع ملف التسليم PDF',
                            ),
                    ),
                  ),

                  const SizedBox(height: 12),

                  fileSelector(
                    role: ApiService.submissionRole,
                    value: selectedSubmissionFileId,
                    onChanged: (id) {
                      setState(() {
                        selectedSubmissionFileId = id;
                        selectedReportFileId = id;
                        submissionReport = null;
                        reportError = null;
                      });
                    },
                  ),
                  const SizedBox(height: 12),

                  OutlinedButton.icon(
                    onPressed:
                        fileActionsBusy ||
                            filesError != null ||
                            !hasFileRole(
                              selectedSubmissionFileId,
                              ApiService.submissionRole,
                            )
                        ? null
                        : () async {
                            final fileId = selectedSubmissionFileId;

                            if (fileId == null) return;

                            for (final file in files) {
                              if (itemId(file) == fileId) {
                                final fileName = file is Map
                                    ? (file['filename'] ??
                                              file['name'] ??
                                              'PDF $fileId')
                                          .toString()
                                    : 'PDF $fileId';

                                await deletePdfFile(fileId, fileName);
                                return;
                              }
                            }
                          },
                    icon: const Icon(Icons.delete_outline),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.red,
                    ),
                    label: Text(
                      t(
                        'Delete selected PDF',
                        'Ausgewählte PDF löschen',
                        'حذف ملف PDF المحدد',
                      ),
                    ),
                  ),

                  const SizedBox(height: 12),

                  ElevatedButton.icon(
                    onPressed:
                        fileActionsBusy ||
                            filesError != null ||
                            !hasFileRole(
                              selectedSubmissionFileId,
                              ApiService.submissionRole,
                            )
                        ? null
                        : checkSubmission,
                    icon: const Icon(Icons.verified),
                    label: Text(
                      isCheckingSubmission
                          ? t('Checking...', 'Wird geprüft...', 'جارٍ الفحص...')
                          : t(
                              'Check Submission',
                              'Abgabe prüfen',
                              'فحص التسليم',
                            ),
                    ),
                  ),

                  const SizedBox(height: 16),

                  loadingOrError(
                    loading: isLoadingSubmissionResults,
                    error: submissionError,
                    child: submissionResults.isEmpty
                        ? Text(
                            t(
                              'No submission results yet.',
                              'Noch keine Prüfergebnisse.',
                              'لا توجد نتائج فحص بعد.',
                            ),
                          )
                        : Column(
                            children: submissionResults.map((item) {
                              final status = getResultStatus(item);

                              final feedback = getResultFeedback(item);

                              return Card(
                                child: ListTile(
                                  leading: const Icon(
                                    Icons.assignment_turned_in,
                                    color: Colors.deepPurple,
                                  ),
                                  title: Text(displayText(status)),
                                  subtitle: contentText(feedback),
                                ),
                              );
                            }).toList(),
                          ),
                  ),
                ],
              ),
            ),

            // ==================================
            // FINAL REPORT
            // ==================================
            section(
              title: t('Final Report', 'Abschlussbericht', 'التقرير النهائي'),
              icon: Icons.description_outlined,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  reportFileSelector(),

                  const SizedBox(height: 12),

                  ElevatedButton.icon(
                    onPressed:
                        fileActionsBusy ||
                            filesError != null ||
                            !hasReportFile(selectedReportFileId)
                        ? null
                        : loadReport,
                    icon: const Icon(Icons.summarize_outlined),
                    label: Text(
                      isLoadingReport
                          ? t(
                              'Loading report...',
                              'Bericht wird geladen...',
                              'جارٍ تحميل التقرير...',
                            )
                          : t(
                              'View Final Report',
                              'Abschlussbericht anzeigen',
                              'عرض التقرير النهائي',
                            ),
                    ),
                  ),

                  const SizedBox(height: 16),

                  if (reportError != null)
                    Text(
                      reportError!,
                      style: const TextStyle(color: Colors.red),
                    ),

                  if (submissionReport != null) buildReport(submissionReport),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ==========================================
  // FINAL REPORT DISPLAY
  // ==========================================

  Widget buildReport(dynamic report) {
    return buildReportValue(report);
  }

  Widget buildReportValue(dynamic value) {
    if (value is String) {
      return contentText(value);
    }

    if (value is List) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: value.map((item) {
          return Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: buildReportValue(item),
          );
        }).toList(),
      );
    }

    if (value is Map) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: value.entries.map((entry) {
          return Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  entry.key.toString(),
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 5),
                buildReportValue(entry.value),
              ],
            ),
          );
        }).toList(),
      );
    }

    return Text(value?.toString() ?? '');
  }
}
