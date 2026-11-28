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
  String checklistFilter = 'all';
  List<dynamic> submissionResults = [];

  dynamic submissionReport;
  Map<String, dynamic>? analysisSummary;
  int? analyzedFileId;

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
            'priority',
            'source_filename',
            'source_page',
            'source_evidence',
            'evidence_verified',
            'pipeline_version',
            'pipeline_versions',
            'submission_filename',
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
    if (fileActionsBusy || checklistBusy) return;
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
        if (analyzedFileId == fileId) {
          analysisSummary = null;
          analyzedFileId = null;
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

    setState(() {
      isAnalyzing = true;
      analysisSummary = null;
      analyzedFileId = null;
    });

    try {
      final result = await ApiService.analyzeFile(
        widget.token,
        widget.projectId,
        fileId,
      );

      if (!mounted) return;

      final rawAnalysis = result is Map ? result['analysis'] : null;

      final summary = rawAnalysis is Map
          ? Map<String, dynamic>.from(rawAnalysis)
          : null;

      setState(() {
        analysisSummary = summary;
        analyzedFileId = fileId;
      });

      await loadRequirements();

      if (!mounted) return;

      if (requirementsError != null) {
        showMessage(
          t(
            'Analysis finished, but saved requirements could not be loaded.',
            'Analyse beendet, aber gespeicherte Anforderungen konnten nicht geladen werden.',
            'انتهى التحليل، لكن تعذر تحميل المتطلبات المحفوظة.',
          ),
          error: true,
        );
        return;
      }

      final status = summary?['status'];

      if (status == 'failed') {
        showMessage(
          t(
            'No valid requirements found. Review the analysis.',
            'Keine gültigen Anforderungen gefunden. Prüfe die Analyse.',
            'لم يتم العثور على متطلبات صالحة. راجعي نتائج التحليل.',
          ),
          error: true,
        );
      } else if (status == 'empty') {
        showMessage(
          t(
            'No requirements were extracted.',
            'Es wurden keine Anforderungen extrahiert.',
            'لم يتم استخراج أي متطلبات.',
          ),
        );
      } else if (summary?['review_required'] == true) {
        showMessage(
          t(
            'Analysis finished. Manual review recommended.',
            'Analyse beendet. Manuelle Prüfung empfohlen.',
            'انتهى التحليل. يُنصح بالمراجعة اليدوية.',
          ),
        );
      } else {
        showMessage(
          t(
            'AI analysis completed',
            'KI-Analyse abgeschlossen',
            'اكتمل تحليل الملف بالذكاء الاصطناعي',
          ),
        );
      }
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
    if (checklistBusy ||
        fileActionsBusy ||
        isLoadingRequirements ||
        requirementsError != null ||
        requirements.isEmpty) {
      return;
    }

    setState(() => isGeneratingChecklist = true);

    try {
      final result = await ApiService.generateChecklist(
        widget.token,
        widget.projectId,
      );

      if (!mounted) return;

      setState(() {
        checklist = result;
        checklistError = null;
      });
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

    if (id == null || checklistBusy || fileActionsBusy) {
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
  // ANALYSIS STATISTICS
  // ==========================================

  Widget analysisMetric({
    required String label,
    required String value,
    required IconData icon,
    required Color color,
  }) {
    return Container(
      width: 150,
      constraints: const BoxConstraints(minHeight: 110),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.20)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color, size: 22),
          const SizedBox(height: 8),
          Text(
            value,
            style: TextStyle(
              fontSize: 23,
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
          const SizedBox(height: 4),
          Text(label, style: const TextStyle(fontSize: 12)),
        ],
      ),
    );
  }

  Widget buildAnalysisSummary() {
    final summary = analysisSummary;

    if (summary == null ||
        analyzedFileId != selectedFileId ||
        !hasFileRole(analyzedFileId, ApiService.requirementsRole)) {
      return const SizedBox.shrink();
    }

    final rawStatistics = summary['statistics'];

    final statistics = rawStatistics is Map
        ? rawStatistics
        : <String, dynamic>{};

    final rawPriorities = summary['priority_counts'];

    final priorities = rawPriorities is Map
        ? rawPriorities
        : <String, dynamic>{};

    final rawPersistence = summary['persistence'];

    final persistence = rawPersistence is Map
        ? rawPersistence
        : <String, dynamic>{};

    final originalCount = statistics['original_count'] ?? 0;

    final validCount = statistics['valid_count'] ?? 0;

    final invalidCount = statistics['invalid_count'] ?? 0;

    final exactDuplicates = statistics['exact_duplicates_count'] ?? 0;

    final possibleDuplicates = statistics['possible_duplicates_count'] ?? 0;

    final validationRate = statistics['validation_rate'];

    final validationText = validationRate is num
        ? '${validationRate.toStringAsFixed(1)}%'
        : '—';

    final high = priorities['high'] ?? 0;
    final medium = priorities['medium'] ?? 0;
    final low = priorities['low'] ?? 0;

    final reviewRequired = summary['review_required'] == true;

    final status = summary['status'];

    final pipelineVersion = summary['pipeline_version'] ?? '—';

    String statusLabel;
    Color statusColor;
    IconData statusIcon;

    if (status == 'failed') {
      statusLabel = t(
        'No valid requirements',
        'Keine gültigen Anforderungen',
        'لا توجد متطلبات صالحة',
      );
      statusColor = Colors.red.shade700;
      statusIcon = Icons.error_outline;
    } else if (status == 'empty') {
      statusLabel = t(
        'No requirements extracted',
        'Keine Anforderungen extrahiert',
        'لم يتم استخراج متطلبات',
      );
      statusColor = Colors.grey.shade700;
      statusIcon = Icons.info_outline;
    } else if (reviewRequired) {
      statusLabel = t(
        'Manual review recommended',
        'Manuelle Prüfung empfohlen',
        'يُنصح بالمراجعة اليدوية',
      );
      statusColor = Colors.orange.shade800;
      statusIcon = Icons.warning_amber_rounded;
    } else if (status == 'completed') {
      statusLabel = t(
        'Validation completed',
        'Validierung abgeschlossen',
        'اكتمل التحقق',
      );
      statusColor = Colors.green.shade700;
      statusIcon = Icons.check_circle_outline;
    } else {
      statusLabel = t(
        'Unknown analysis status',
        'Unbekannter Analysestatus',
        'حالة التحليل غير معروفة',
      );
      statusColor = Colors.grey.shade700;
      statusIcon = Icons.info_outline;
    }

    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: Colors.deepPurple.withValues(alpha: 0.20)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.analytics_outlined, color: Colors.deepPurple),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    t(
                      'Analysis overview',
                      'Analyseübersicht',
                      'نظرة عامة على التحليل',
                    ),
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ],
            ),

            const SizedBox(height: 8),

            Text(
              t(
                'Results of the last analysis of the selected PDF.',
                'Ergebnisse der letzten Analyse der ausgewählten PDF.',
                'نتائج آخر تحليل لملف PDF المحدد.',
              ),
              style: const TextStyle(fontSize: 13, color: Colors.grey),
            ),

            const SizedBox(height: 16),

            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                analysisMetric(
                  label: t('Extracted', 'Extrahiert', 'المتطلبات المستخرجة'),
                  value: '$originalCount',
                  icon: Icons.description_outlined,
                  color: Colors.deepPurple,
                ),

                analysisMetric(
                  label: t(
                    'Valid requirements',
                    'Gültige Anforderungen',
                    'المتطلبات الصالحة',
                  ),
                  value: '$validCount',
                  icon: Icons.verified_outlined,
                  color: Colors.green.shade700,
                ),

                analysisMetric(
                  label: t(
                    'Invalid requirements',
                    'Ungültige Anforderungen',
                    'المتطلبات غير الصالحة',
                  ),
                  value: '$invalidCount',
                  icon: Icons.error_outline,
                  color: invalidCount == 0
                      ? Colors.blueGrey
                      : Colors.red.shade700,
                ),

                analysisMetric(
                  label: t(
                    'Possible duplicate pairs',
                    'Mögliche Duplikatpaare',
                    'أزواج المتطلبات المتشابهة',
                  ),
                  value: '$possibleDuplicates',
                  icon: Icons.compare_arrows,
                  color: Colors.orange.shade800,
                ),

                analysisMetric(
                  label: t(
                    'Exact duplicates',
                    'Exakte Duplikate',
                    'المتطلبات المتطابقة',
                  ),
                  value: '$exactDuplicates',
                  icon: Icons.copy_outlined,
                  color: Colors.blueGrey,
                ),

                analysisMetric(
                  label: t(
                    'Validation rate',
                    'Validierungsrate',
                    'نسبة اجتياز التحقق',
                  ),
                  value: validationText,
                  icon: Icons.fact_check_outlined,
                  color: Colors.teal,
                ),
              ],
            ),

            const SizedBox(height: 16),

            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(statusIcon, color: statusColor),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    statusLabel,
                    style: TextStyle(
                      color: statusColor,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),

            const SizedBox(height: 12),

            Text(
              t(
                'Validation checks text evidence and data structure, not semantic accuracy.',
                'Die Validierung prüft Textbelege und Datenstruktur, nicht die semantische Richtigkeit.',
                'يتحقق النظام من الأدلة النصية وبنية البيانات، وليس من الدقة الدلالية للمتطلبات.',
              ),
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),

            const Divider(height: 28),

            Text(
              t(
                'Priority distribution (unique requirements)',
                'Prioritätsverteilung (eindeutige Anforderungen)',
                'توزيع أولويات المتطلبات الفريدة',
              ),
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),

            const SizedBox(height: 12),

            Wrap(
              spacing: 16,
              runSpacing: 8,
              children: [
                Text(
                  '${t("High", "Hoch", "عالية")}: $high',
                  style: TextStyle(
                    color: Colors.red.shade700,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                Text(
                  '${t("Medium", "Mittel", "متوسطة")}: $medium',
                  style: TextStyle(
                    color: Colors.orange.shade800,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                Text(
                  '${t("Low", "Niedrig", "منخفضة")}: $low',
                  style: const TextStyle(
                    color: Colors.blueGrey,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),

            const Divider(height: 28),

            Text(
              '${t("Newly saved", "Neu gespeichert", "المتطلبات المحفوظة حديثاً")}: '
              '${persistence["inserted_count"] ?? 0}',
            ),

            const SizedBox(height: 6),

            Text(
              '${t("Reused requirements", "Wiederverwendete Anforderungen", "المتطلبات المعاد استخدامها")}: '
              '${persistence["reused_count"] ?? 0}',
            ),

            const SizedBox(height: 6),

            Text(
              '${t("Additional sources preserved", "Zusätzliche Quellen erhalten", "المصادر الإضافية المحفوظة")}: '
              '${persistence["preserved_source_count"] ?? 0}',
            ),

            const SizedBox(height: 12),

            Text(
              '${t("Pipeline version", "Pipeline-Version", "إصدار المعالجة")}: '
              '$pipelineVersion',
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }

  // ==========================================
  // SMART CHECKLIST V2
  // ==========================================

  int checklistPriority(dynamic item) {
    if (item is! Map) return 3;

    switch ((item['priority'] ?? '').toString().toLowerCase()) {
      case 'high':
        return 0;
      case 'medium':
        return 1;
      case 'low':
        return 2;
      default:
        return 3;
    }
  }

  List<dynamic> get filteredChecklist {
    final result = checklist.where((item) {
      switch (checklistFilter) {
        case 'completed':
          return isCompleted(item);

        case 'pending':
          return !isCompleted(item);

        default:
          return true;
      }
    }).toList();

    result.sort((a, b) {
      final priorityComparison = checklistPriority(
        a,
      ).compareTo(checklistPriority(b));

      if (priorityComparison != 0) {
        return priorityComparison;
      }

      return (itemId(a) ?? 0).compareTo(itemId(b) ?? 0);
    });

    return result;
  }

  bool get checklistBusy =>
      isLoadingChecklist || isGeneratingChecklist || updatingItemIds.isNotEmpty;

  Widget checklistFilterChip(String value, String label, int count) {
    return ChoiceChip(
      label: Text('$label ($count)'),
      selected: checklistFilter == value,
      selectedColor: Colors.deepPurple.shade100,
      onSelected: (_) {
        setState(() {
          checklistFilter = value;
        });
      },
    );
  }

  Widget checklistCounter(String label, int count, Color color, IconData icon) {
    return Container(
      constraints: const BoxConstraints(minWidth: 95),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.18)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: color, size: 22),
          const SizedBox(height: 6),
          Text(
            '$count',
            style: TextStyle(
              fontSize: 23,
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            label,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 12),
          ),
        ],
      ),
    );
  }

  Widget buildChecklistProgress(int completed, double progress) {
    final total = checklist.length;
    final pending = total - completed;

    final percentage = (progress * 100).round();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.deepPurple.shade50,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.deepPurple.shade100),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  t(
                    'Checklist progress',
                    'Checklistenfortschritt',
                    'تقدم قائمة المهام',
                  ),
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              Text(
                '$percentage%',
                style: TextStyle(
                  fontSize: 25,
                  fontWeight: FontWeight.bold,
                  color: progress == 1.0
                      ? Colors.green.shade700
                      : Colors.deepPurple,
                ),
              ),
            ],
          ),

          const SizedBox(height: 12),

          LinearProgressIndicator(
            value: progress,
            minHeight: 12,
            borderRadius: BorderRadius.circular(12),
            backgroundColor: Colors.deepPurple.shade100,
            color: progress == 1.0 ? Colors.green : Colors.deepPurple,
          ),

          const SizedBox(height: 12),

          Text(
            t(
              '$completed of $total tasks completed',
              '$completed von $total Aufgaben erledigt',
              'تم إنجاز $completed من أصل $total مهمة',
            ),
          ),

          const SizedBox(height: 16),

          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              checklistCounter(
                t('Total', 'Gesamt', 'الإجمالي'),
                total,
                Colors.deepPurple,
                Icons.list_alt,
              ),
              checklistCounter(
                t('Completed', 'Erledigt', 'مكتملة'),
                completed,
                Colors.green.shade700,
                Icons.check_circle_outline,
              ),
              checklistCounter(
                t('Pending', 'Offen', 'متبقية'),
                pending,
                Colors.orange.shade800,
                Icons.pending_actions,
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget buildChecklistItem(dynamic item) {
    final id = itemId(item);
    final completed = isCompleted(item);

    final description = item is Map
        ? (item['description'] ?? '').toString()
        : '';

    final updating = id != null && updatingItemIds.contains(id);

    return Card(
      key: id == null ? null : ValueKey(id),
      elevation: 0,
      color: completed ? Colors.green.shade50 : Colors.white,
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(
          color: completed ? Colors.green.shade200 : Colors.grey.shade300,
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Checkbox(
                  value: completed,
                  activeColor: Colors.green,
                  onChanged: id == null || checklistBusy || fileActionsBusy
                      ? null
                      : (value) {
                          toggleChecklist(item, value ?? false);
                        },
                ),

                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.only(top: 10),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        contentText(getChecklistTitle(item)),

                        if (description.trim().isNotEmpty) ...[
                          const SizedBox(height: 8),
                          contentText(description),
                        ],

                        const SizedBox(height: 10),

                        Row(
                          children: [
                            Icon(
                              completed ? Icons.check_circle : Icons.schedule,
                              size: 17,
                              color: completed ? Colors.green : Colors.orange,
                            ),
                            const SizedBox(width: 6),
                            Expanded(
                              child: Text(
                                completed
                                    ? t(
                                        'Marked complete',
                                        'Als erledigt markiert',
                                        'مكتملة يدوياً',
                                      )
                                    : t('Pending', 'Offen', 'قيد الإنجاز'),
                                style: TextStyle(
                                  fontSize: 12,
                                  color: completed
                                      ? Colors.green.shade700
                                      : Colors.orange.shade800,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),

                if (updating)
                  const Padding(
                    padding: EdgeInsets.all(8),
                    child: SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  ),
              ],
            ),

            const SizedBox(height: 8),

            requirementEvidence(item),
          ],
        ),
      ),
    );
  }

  // ==========================================
  // REQUIREMENT EVIDENCE DISPLAY
  // ==========================================

  Widget requirementEvidence(dynamic item) {
    if (item is! Map) {
      return const SizedBox.shrink();
    }

    final sourcePage = item['source_page'];
    final sourceEvidence = (item['source_evidence'] ?? '').toString();

    final verified = item['evidence_verified'];

    final hasEvidence =
        sourcePage is int && sourcePage > 0 && sourceEvidence.trim().isNotEmpty;

    final priority = (item['priority'] ?? '').toString().toLowerCase();

    String priorityLabel = '';
    Color priorityColor = Colors.grey;

    switch (priority) {
      case 'high':
        priorityLabel = t('High priority', 'Hohe Priorität', 'أولوية عالية');
        priorityColor = Colors.red.shade700;
        break;

      case 'medium':
        priorityLabel = t(
          'Medium priority',
          'Mittlere Priorität',
          'أولوية متوسطة',
        );
        priorityColor = Colors.orange.shade800;
        break;

      case 'low':
        priorityLabel = t(
          'Low priority',
          'Niedrige Priorität',
          'أولوية منخفضة',
        );
        priorityColor = Colors.blueGrey;
        break;
    }

    final isVerified = verified == true && hasEvidence;

    final isLegacy =
        verified == null && sourcePage == null && sourceEvidence.trim().isEmpty;

    final Color evidenceColor = isVerified
        ? Colors.green.shade700
        : isLegacy
        ? Colors.grey.shade700
        : Colors.orange.shade800;

    final String evidenceLabel = isVerified
        ? t(
            'Evidence matched',
            'Textbeleg bestätigt',
            'تمت مطابقة الدليل النصي',
          )
        : isLegacy
        ? t(
            'Legacy requirement — no evidence available',
            'Bestehende Anforderung ohne Textbeleg',
            'متطلب قديم — لا يتوفر دليل نصي',
          )
        : t(
            'Evidence not verified',
            'Textbeleg nicht bestätigt',
            'الدليل غير متحقق منه',
          );

    final IconData evidenceIcon = isVerified
        ? Icons.check_circle_outline
        : isLegacy
        ? Icons.info_outline
        : Icons.warning_amber_rounded;

    final fileId = item['file_id'];

    String? sourceFileName;

    for (final file in files) {
      if (fileId != null && itemId(file) == fileId) {
        sourceFileName = fileName(file);
        break;
      }
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (priorityLabel.isNotEmpty) ...[
          const SizedBox(height: 10),

          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
            decoration: BoxDecoration(
              color: priorityColor.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              priorityLabel,
              style: TextStyle(
                color: priorityColor,
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],

        const SizedBox(height: 10),
        const Divider(),

        if (sourceFileName != null) ...[
          Row(
            children: [
              const Icon(
                Icons.picture_as_pdf_outlined,
                size: 18,
                color: Colors.deepPurple,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  sourceFileName,
                  style: const TextStyle(fontSize: 13),
                ),
              ),
            ],
          ),

          const SizedBox(height: 8),
        ],

        if (sourcePage is int && sourcePage > 0) ...[
          Row(
            children: [
              const Icon(
                Icons.description_outlined,
                size: 18,
                color: Colors.deepPurple,
              ),
              const SizedBox(width: 8),
              Text(
                '${t("Page", "Seite", "الصفحة")} $sourcePage',
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),

          const SizedBox(height: 8),
        ],

        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(evidenceIcon, color: evidenceColor, size: 18),

            const SizedBox(width: 8),

            Expanded(
              child: Text(
                evidenceLabel,
                style: TextStyle(
                  color: evidenceColor,
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          ],
        ),

        if (sourceEvidence.trim().isNotEmpty) ...[
          const SizedBox(height: 8),

          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: const EdgeInsets.only(bottom: 8),
            leading: const Icon(
              Icons.menu_book_outlined,
              color: Colors.deepPurple,
              size: 20,
            ),
            title: Text(
              t(
                'Show original evidence',
                'Originalbeleg anzeigen',
                'عرض الدليل الأصلي',
              ),
              style: const TextStyle(fontSize: 14),
            ),
            children: [
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.deepPurple.withValues(alpha: 0.05),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      t(
                        'Original PDF text',
                        'Originaler PDF-Text',
                        'النص الأصلي من PDF',
                      ),
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        color: Colors.deepPurple,
                      ),
                    ),

                    const SizedBox(height: 8),

                    SelectionArea(
                      child: Text(
                        sourceEvidence.toString(),
                        style: const TextStyle(
                          fontSize: 14.0,
                          height: 1.5,
                          color: Colors.black87,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ],
    );
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
                        analysisSummary = null;
                        analyzedFileId = null;
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

                  if (isAnalyzing) ...[
                    const LinearProgressIndicator(),
                    const SizedBox(height: 16),
                  ],

                  buildAnalysisSummary(),

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
                                margin: const EdgeInsets.only(bottom: 12),
                                child: Padding(
                                  padding: const EdgeInsets.all(14),
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                          CircleAvatar(
                                            backgroundColor: Colors.deepPurple,
                                            foregroundColor: Colors.white,
                                            child: Text('${entry.key + 1}'),
                                          ),

                                          const SizedBox(width: 12),

                                          Expanded(
                                            child: Column(
                                              crossAxisAlignment:
                                                  CrossAxisAlignment.start,
                                              children: [
                                                contentText(
                                                  title,
                                                  style: const TextStyle(
                                                    fontWeight: FontWeight.w600,
                                                    fontSize: 16,
                                                  ),
                                                ),

                                                if (description.isNotEmpty) ...[
                                                  const SizedBox(height: 6),
                                                  contentText(description),
                                                ],
                                              ],
                                            ),
                                          ),
                                        ],
                                      ),

                                      requirementEvidence(item),
                                    ],
                                  ),
                                ),
                              );
                            }).toList(),
                          ),
                  ),
                ],
              ),
            ),

            // ==================================
            // SMART CHECKLIST V2
            // ==================================
            section(
              title: t(
                'Smart Checklist',
                'Intelligente Checkliste',
                'قائمة المهام الذكية',
              ),
              icon: Icons.checklist,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    t(
                      'Organize your requirements and track your progress.',
                      'Organisiere deine Anforderungen und verfolge deinen Fortschritt.',
                      'نظّم متطلبات مشروعك وتابع تقدمك في إنجاز المهام.',
                    ),
                  ),

                  const SizedBox(height: 12),

                  ElevatedButton.icon(
                    onPressed:
                        checklistBusy ||
                            fileActionsBusy ||
                            isLoadingRequirements ||
                            requirementsError != null ||
                            requirements.isEmpty
                        ? null
                        : generateChecklist,

                    icon: isGeneratingChecklist
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.playlist_add),

                    label: Text(
                      isGeneratingChecklist
                          ? t(
                              'Generating...',
                              'Wird erstellt...',
                              'جارٍ الإنشاء...',
                            )
                          : checklist.isEmpty
                          ? t(
                              'Generate Checklist',
                              'Checkliste erstellen',
                              'إنشاء قائمة المهام',
                            )
                          : t(
                              'Update Checklist',
                              'Checkliste aktualisieren',
                              'تحديث قائمة المهام',
                            ),
                    ),
                  ),

                  const SizedBox(height: 16),

                  if (checklist.isNotEmpty && checklistError == null) ...[
                    buildChecklistProgress(completed, progress),

                    const SizedBox(height: 16),

                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.blue.shade50,
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(
                            Icons.info_outline,
                            color: Colors.blue,
                            size: 20,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              t(
                                'Manual completion is not an AI verification of your submission.',
                                'Die manuelle Erledigung ist keine KI-Prüfung deiner Abgabe.',
                                'تحديد المهمة كمكتملة يدوياً لا يعني أن الذكاء الاصطناعي تحقق من تنفيذها.',
                              ),
                              style: const TextStyle(fontSize: 12),
                            ),
                          ),
                        ],
                      ),
                    ),

                    const SizedBox(height: 16),

                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        checklistFilterChip(
                          'all',
                          t('All', 'Alle', 'الكل'),
                          checklist.length,
                        ),
                        checklistFilterChip(
                          'pending',
                          t('Pending', 'Offen', 'المتبقية'),
                          checklist.length - completed,
                        ),
                        checklistFilterChip(
                          'completed',
                          t('Completed', 'Erledigt', 'المكتملة'),
                          completed,
                        ),
                      ],
                    ),

                    const SizedBox(height: 16),

                    Row(
                      children: [
                        const Icon(
                          Icons.sort,
                          size: 18,
                          color: Colors.deepPurple,
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            t(
                              'Sorted by priority',
                              'Nach Priorität sortiert',
                              'مرتبة حسب الأولوية',
                            ),
                            style: const TextStyle(
                              fontSize: 12,
                              color: Colors.deepPurple,
                            ),
                          ),
                        ),
                      ],
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
                        : filteredChecklist.isEmpty
                        ? Padding(
                            padding: const EdgeInsets.all(16),
                            child: Center(
                              child: Text(
                                t(
                                  'No matching tasks.',
                                  'Keine passenden Aufgaben.',
                                  'لا توجد مهام مطابقة للفلتر.',
                                ),
                              ),
                            ),
                          )
                        : Column(
                            children: filteredChecklist
                                .map(buildChecklistItem)
                                .toList(),
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

  String _submissionReportFilter = 'all';

  // ==========================================
  // SMART REPORT HELPERS
  // ==========================================

  Map<String, dynamic> reportMap(dynamic value) {
    if (value is Map) {
      return Map<String, dynamic>.from(value);
    }

    return <String, dynamic>{};
  }

  int reportInt(dynamic value) {
    if (value is num) {
      return value.toInt();
    }

    return int.tryParse(value?.toString() ?? '') ?? 0;
  }

  double reportDouble(dynamic value) {
    final number = value is num
        ? value.toDouble()
        : double.tryParse(value?.toString() ?? '') ?? 0.0;

    if (!number.isFinite) return 0.0;

    return number.clamp(0.0, 100.0).toDouble();
  }

  String reportStatusLabel(String status) {
    switch (status) {
      case 'fulfilled':
        return t('Fulfilled', 'Erfüllt', 'مكتمل');

      case 'partially_fulfilled':
        return t('Partially fulfilled', 'Teilweise erfüllt', 'مكتمل جزئياً');

      case 'missing':
        return t('Missing', 'Fehlend', 'ناقص');

      case 'unclear':
        return t('Unclear', 'Unklar', 'غير واضح');

      default:
        return t('Unknown', 'Unbekannt', 'غير معروف');
    }
  }

  Color reportStatusColor(String status) {
    switch (status) {
      case 'fulfilled':
        return Colors.green.shade700;

      case 'partially_fulfilled':
        return Colors.orange.shade800;

      case 'missing':
        return Colors.red.shade700;

      default:
        return Colors.blueGrey;
    }
  }

  IconData reportStatusIcon(String status) {
    switch (status) {
      case 'fulfilled':
        return Icons.check_circle_outline;

      case 'partially_fulfilled':
        return Icons.timelapse;

      case 'missing':
        return Icons.cancel_outlined;

      default:
        return Icons.help_outline;
    }
  }

  // ==========================================
  // REPORT PROGRESS
  // ==========================================

  Widget reportProgress({
    required String title,
    required double percentage,
    required String description,
    required Color color,
  }) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            SizedBox(
              width: 100,
              height: 100,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  SizedBox(
                    width: 100,
                    height: 100,
                    child: CircularProgressIndicator(
                      value: percentage / 100.0,
                      strokeWidth: 9.0,
                      color: color,
                      backgroundColor: color.withValues(alpha: 0.12),
                    ),
                  ),
                  Text(
                    '${percentage.toStringAsFixed(1)}%',
                    style: TextStyle(
                      fontSize: 22.0,
                      fontWeight: FontWeight.bold,
                      color: color,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontWeight: FontWeight.bold,
                fontSize: 15.0,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              description,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 12.0),
            ),
          ],
        ),
      ),
    );
  }

  // ==========================================
  // REPORT STATUS CARD
  // ==========================================

  Widget reportStatusCard(String status, int count) {
    final color = reportStatusColor(status);

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(reportStatusIcon(status), color: color),
          const SizedBox(height: 8),
          Text(
            count.toString(),
            style: TextStyle(
              color: color,
              fontSize: 25.0,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            reportStatusLabel(status),
            style: const TextStyle(fontWeight: FontWeight.w500),
          ),
        ],
      ),
    );
  }

  // ==========================================
  // REPORT NOTICE
  // ==========================================

  Widget reportNotice(String message, {bool warning = true}) {
    final color = warning ? Colors.orange.shade800 : Colors.blue.shade700;

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            warning ? Icons.warning_amber_rounded : Icons.info_outline,
            color: color,
          ),
          const SizedBox(width: 10),
          Expanded(child: Text(message)),
        ],
      ),
    );
  }

  // ==========================================
  // SUBMISSION EVIDENCE
  // ==========================================

  Widget reportEvidence(Map<String, dynamic> result) {
    final page = reportInt(result['source_page']);

    final evidence = result['source_evidence']?.toString() ?? '';

    final verified = result['evidence_verified'];

    if (evidence.trim().isEmpty || page <= 0) {
      return reportNotice(
        t(
          'No source quotation available.',
          'Kein Quellenzitat verfügbar.',
          'لا يوجد اقتباس متاح من الملف.',
        ),
        warning: false,
      );
    }

    final color = verified == true
        ? Colors.green.shade700
        : Colors.orange.shade800;

    final verificationLabel = verified == true
        ? t(
            'Quotation verified in source text',
            'Zitat im Quelltext bestätigt',
            'تم التحقق من وجود الاقتباس في النص',
          )
        : verified == false
        ? t(
            'Unverified quotation',
            'Nicht bestätigtes Zitat',
            'اقتباس غير متحقق منه',
          )
        : t(
            'Verification unavailable',
            'Überprüfung nicht verfügbar',
            'التحقق غير متاح',
          );

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                verified == true ? Icons.verified_outlined : Icons.info_outline,
                color: color,
                size: 20,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  verificationLabel,
                  style: TextStyle(color: color, fontWeight: FontWeight.bold),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '${t('Page', 'Seite', 'الصفحة')} $page',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),

          // Preserve the original source quotation.
          SelectableText(
            evidence,
            style: const TextStyle(fontSize: 14.0, height: 1.5),
          ),
        ],
      ),
    );
  }

  // ==========================================
  // INDIVIDUAL REQUIREMENT RESULT
  // ==========================================

  Widget reportResultCard(Map<String, dynamic> result) {
    final status = result['status']?.toString() ?? 'unknown';

    final requirementId = result['requirement_id']?.toString() ?? '?';

    final feedback = result['feedback']?.toString() ?? '';

    final improvement = result['suggested_improvement']?.toString() ?? '';

    final version = result['pipeline_version']?.toString() ?? '';

    final color = reportStatusColor(status);

    return Card(
      key: ValueKey('report-${result['file_id']}-${result['id']}'),
      margin: const EdgeInsets.only(bottom: 10),
      child: ExpansionTile(
        leading: Icon(reportStatusIcon(status), color: color),
        title: Text(
          '${t('Requirement', 'Anforderung', 'المتطلب')} #$requirementId',
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
        subtitle: Text(
          reportStatusLabel(status),
          style: TextStyle(color: color),
        ),
        childrenPadding: const EdgeInsets.all(16),
        expandedCrossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            t('AI Feedback', 'KI-Feedback', 'ملاحظات الذكاء الاصطناعي'),
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15.0),
          ),
          const SizedBox(height: 8),

          if (feedback.trim().isNotEmpty) contentText(feedback),

          const SizedBox(height: 16),

          Text(
            t('Source Evidence', 'Quellennachweis', 'الدليل من الملف'),
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15.0),
          ),
          const SizedBox(height: 8),

          reportEvidence(result),

          if (improvement.trim().isNotEmpty) ...[
            const SizedBox(height: 16),
            Row(
              children: [
                const Icon(Icons.lightbulb_outline, color: Colors.orange),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    t(
                      'Suggested improvement',
                      'Verbesserungsvorschlag',
                      'اقتراح التحسين',
                    ),
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            contentText(improvement),
          ],

          if (version.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(
              '${t('Pipeline version', 'Pipeline-Version', 'إصدار التقييم')}: $version',
              style: const TextStyle(fontSize: 12.0),
            ),
          ],
        ],
      ),
    );
  }

  // ==========================================
  // SMART SUBMISSION REPORT
  // ==========================================

  Widget buildReport(dynamic report) {
    if (report is! Map) {
      return buildReportValue(report);
    }

    final data = reportMap(report);

    final summary = reportMap(data['summary']);

    final evidenceSummary = reportMap(data['evidence_summary']);

    final evaluation = reportMap(data['evaluation']);

    if (summary.isEmpty) {
      return buildReportValue(report);
    }

    final total = reportInt(summary['total_requirements']);

    final fulfilled = reportInt(summary['fulfilled']);

    final partial = reportInt(summary['partially_fulfilled']);

    final missing = reportInt(summary['missing']);

    final unclear = reportInt(summary['unclear']);

    final unknown = reportInt(summary['unknown_status_count']);

    final completion = reportDouble(summary['completion_percentage']);

    final coverage = reportDouble(
      evidenceSummary['evidence_coverage_percentage'],
    );

    final verifiedCount = reportInt(evidenceSummary['verified_evidence']);

    final unverifiedCount = reportInt(evidenceSummary['unverified_evidence']);

    final unavailableCount = reportInt(
      evidenceSummary['evidence_not_available'],
    );

    final missingEvidence = reportInt(
      evidenceSummary['missing_required_evidence'],
    );

    final legacyCount = reportInt(evaluation['legacy_results']);

    final isLegacy =
        evaluation['is_legacy_report'] == true || evidenceSummary.isEmpty;

    final reviewRequired =
        evaluation['review_required'] == true ||
        isLegacy ||
        unclear > 0 ||
        unknown > 0 ||
        missingEvidence > 0 ||
        unverifiedCount > 0 ||
        legacyCount > 0;

    final rawVersions = evaluation['pipeline_versions'];

    final versions = rawVersions is List
        ? rawVersions.map((item) => item.toString()).join(', ')
        : '';

    final rawDetails = data['details'];

    final details = rawDetails is List
        ? rawDetails.whereType<Map>().map((item) => reportMap(item)).toList()
        : <Map<String, dynamic>>[];

    final knownStatuses = [
      'fulfilled',
      'partially_fulfilled',
      'missing',
      'unclear',
    ];

    final filteredDetails = details.where((item) {
      if (_submissionReportFilter == 'all') {
        return true;
      }

      final status = item['status']?.toString();

      if (_submissionReportFilter == 'unknown') {
        return !knownStatuses.contains(status);
      }

      return status == _submissionReportFilter;
    }).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          t(
            'Smart Submission Report',
            'Intelligenter Abschlussbericht',
            'تقرير التسليم الذكي',
          ),
          style: const TextStyle(fontSize: 21.0, fontWeight: FontWeight.bold),
        ),

        const SizedBox(height: 8),

        Text(data['submission_filename']?.toString() ?? ''),

        const SizedBox(height: 16),

        // RESPONSIVE PROGRESS CARDS
        LayoutBuilder(
          builder: (context, constraints) {
            final completionCard = reportProgress(
              title: t(
                'Full completion',
                'Vollständig erfüllt',
                'الإنجاز الكامل',
              ),
              percentage: completion,
              description: t(
                '$fulfilled of $total requirements',
                '$fulfilled von $total Anforderungen',
                '$fulfilled من أصل $total متطلبات',
              ),
              color: Colors.green.shade700,
            );

            final evidenceCard = reportProgress(
              title: t(
                'Evidence coverage',
                'Nachweisabdeckung',
                'تغطية الأدلة',
              ),
              percentage: coverage,
              description: t(
                '$verifiedCount of $total results with verified quotations',
                '$verifiedCount von $total Ergebnissen mit bestätigten Zitaten',
                '$verifiedCount من أصل $total نتائج باقتباسات متحقق منها',
              ),
              color: Colors.blue.shade700,
            );

            final cards = [
              completionCard,
              if (!isLegacy || evidenceSummary.isNotEmpty) evidenceCard,
            ];

            if (constraints.maxWidth < 420) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: cards,
              );
            }

            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: cards.map((card) {
                return Expanded(child: card);
              }).toList(),
            );
          },
        ),

        const SizedBox(height: 16),

        // STATUS STATISTICS
        Row(
          children: [
            Expanded(child: reportStatusCard('fulfilled', fulfilled)),
            const SizedBox(width: 10),
            Expanded(child: reportStatusCard('partially_fulfilled', partial)),
          ],
        ),

        const SizedBox(height: 10),

        Row(
          children: [
            Expanded(child: reportStatusCard('missing', missing)),
            const SizedBox(width: 10),
            Expanded(child: reportStatusCard('unclear', unclear)),
          ],
        ),

        if (unknown > 0) ...[
          const SizedBox(height: 10),
          reportStatusCard('unknown', unknown),
        ],

        const SizedBox(height: 16),

        // REVIEW AND LEGACY NOTICES
        if (reviewRequired)
          reportNotice(
            t(
              'Human review required. Some results need additional verification.',
              'Menschliche Überprüfung erforderlich. Einige Ergebnisse müssen zusätzlich geprüft werden.',
              'المراجعة البشرية مطلوبة. بعض النتائج تحتاج إلى تحقق إضافي.',
            ),
          ),

        if (isLegacy)
          reportNotice(
            t(
              'Historical report. Evidence verification was not available when this report was generated.',
              'Historischer Bericht. Bei seiner Erstellung war keine Nachweisprüfung verfügbar.',
              'تقرير قديم. لم يكن التحقق من الأدلة متاحاً عند إنشائه.',
            ),
            warning: false,
          ),

        if (missingEvidence > 0)
          reportNotice(
            t(
              '$missingEvidence results lack required verified evidence.',
              '$missingEvidence Ergebnissen fehlen erforderliche bestätigte Nachweise.',
              '$missingEvidence نتائج تفتقر إلى الأدلة المطلوبة المتحقق منها.',
            ),
          ),

        if (unverifiedCount > 0)
          reportNotice(
            t(
              '$unverifiedCount results contain unverified evidence.',
              '$unverifiedCount Ergebnisse enthalten unbestätigte Nachweise.',
              '$unverifiedCount نتائج تحتوي على أدلة غير متحقق منها.',
            ),
          ),

        if (unavailableCount > 0 && !isLegacy)
          reportNotice(
            t(
              '$unavailableCount results have no available evidence verification.',
              'Für $unavailableCount Ergebnisse ist keine Nachweisprüfung verfügbar.',
              '$unavailableCount نتائج لا يتوفر لها تحقق من الأدلة.',
            ),
            warning: false,
          ),

        reportNotice(
          t(
            'AI-assisted evaluation. Verified quotations confirm text presence, not the correctness of the entire assessment.',
            'KI-gestützte Bewertung. Bestätigte Zitate belegen das Vorhandensein im Text, nicht die Richtigkeit der gesamten Bewertung.',
            'تقييم بمساعدة الذكاء الاصطناعي. التحقق من الاقتباسات يؤكد وجودها في النص، وليس صحة التقييم بالكامل.',
          ),
          warning: false,
        ),

        const SizedBox(height: 16),

        // FILTER
        Text(
          t('Detailed results', 'Detaillierte Ergebnisse', 'النتائج التفصيلية'),
          style: const TextStyle(fontSize: 18.0, fontWeight: FontWeight.bold),
        ),

        const SizedBox(height: 12),

        DropdownButtonFormField<String>(
          initialValue: _submissionReportFilter,
          isExpanded: true,
          decoration: InputDecoration(
            labelText: t(
              'Filter by status',
              'Nach Status filtern',
              'التصفية حسب الحالة',
            ),
            border: const OutlineInputBorder(),
          ),
          items: [
            DropdownMenuItem(
              value: 'all',
              child: Text(t('All', 'Alle', 'الكل')),
            ),
            ...[
              'fulfilled',
              'partially_fulfilled',
              'missing',
              'unclear',
              'unknown',
            ].map((status) {
              return DropdownMenuItem(
                value: status,
                child: Text(reportStatusLabel(status)),
              );
            }),
          ],
          onChanged: (value) {
            if (value == null) return;

            setState(() {
              _submissionReportFilter = value;
            });
          },
        ),

        const SizedBox(height: 12),

        Text(
          t(
            '${filteredDetails.length} of ${details.length} results',
            '${filteredDetails.length} von ${details.length} Ergebnissen',
            '${filteredDetails.length} من أصل ${details.length} نتائج',
          ),
        ),

        const SizedBox(height: 12),

        if (filteredDetails.isEmpty)
          Padding(
            padding: const EdgeInsets.all(16),
            child: Text(
              t(
                'No matching results.',
                'Keine passenden Ergebnisse.',
                'لا توجد نتائج مطابقة.',
              ),
            ),
          ),

        ...filteredDetails.map(reportResultCard),

        if (versions.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text(
            '${t('Pipeline versions', 'Pipeline-Versionen', 'إصدارات التقييم')}: $versions',
            style: const TextStyle(fontSize: 12.0),
          ),
        ],
      ],
    );
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
