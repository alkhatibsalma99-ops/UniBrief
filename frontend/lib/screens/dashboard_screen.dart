import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/auth_storage.dart';
import 'login_screen.dart';
import 'project_details_screen.dart';
import '../services/error_handler.dart';

class DashboardScreen extends StatefulWidget {
  final String token;
  final String selectedLanguage;
  final ValueChanged<String> onLanguageChanged;

  const DashboardScreen({
    super.key,
    required this.token,
    required this.selectedLanguage,
    required this.onLanguageChanged,
  });

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  List<dynamic> projects = [];

  bool isLoading = true;
  bool isCreating = false;
  bool isLoggingOut = false;
  bool isDeletingAccount = false;

  String t(String en, String de, String ar) {
    final language = Localizations.localeOf(context).languageCode;

    switch (language) {
      case 'de':
        return de;
      case 'ar':
        return ar;
      default:
        return en;
    }
  }

  String friendlyError(Object error) {
    return ErrorHandler.message(
      error,
      Localizations.localeOf(context).languageCode,
    );
  }

  @override
  void initState() {
    super.initState();
    loadProjects();
  }

  void message(String value, {bool error = false}) {
    if (!mounted) return;

    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(value),
          backgroundColor: error ? Colors.red : Colors.green,
        ),
      );
  }

  Future<void> loadProjects() async {
    if (isLoggingOut) return;

    setState(() {
      isLoading = true;
    });

    try {
      final result = await ApiService.getProjects(widget.token);

      if (!mounted) return;

      setState(() {
        projects = List<dynamic>.from(result);
      });
    } catch (e) {
      if (!mounted) return;

      message(friendlyError(e), error: true);
    } finally {
      if (mounted) {
        setState(() {
          isLoading = false;
        });
      }
    }
  }

  Future<void> createProject() async {
    if (isCreating) return;

    final controller = TextEditingController();

    final title = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(t('Create Project', 'Projekt erstellen', 'إنشاء مشروع')),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: InputDecoration(
            labelText: t('Project Title', 'Projekttitel', 'اسم المشروع'),
          ),
          onSubmitted: (value) {
            Navigator.of(dialogContext).pop(value.trim());
          },
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: Text(t('Cancel', 'Abbrechen', 'إلغاء')),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.of(dialogContext).pop(controller.text.trim());
            },
            child: Text(t('Create', 'Erstellen', 'إنشاء')),
          ),
        ],
      ),
    );

    await Future<void>.delayed(const Duration(milliseconds: 200));
    controller.dispose();

    if (!mounted || title == null || title.trim().isEmpty) {
      return;
    }

    setState(() {
      isCreating = true;
    });

    try {
      await ApiService.createProject(widget.token, title.trim());

      if (!mounted) return;

      await loadProjects();

      if (!mounted) return;

      message(t('Project created!', 'Projekt erstellt!', 'تم إنشاء المشروع!'));
    } catch (e) {
      if (!mounted) return;

      message(friendlyError(e), error: true);
    } finally {
      if (mounted) {
        setState(() {
          isCreating = false;
        });
      }
    }
  }

  Future<void> deleteProject(int id, String title) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(t('Delete Project', 'Projekt löschen', 'حذف المشروع')),
        content: Text(
          t(
            'Delete "$title" permanently?',
            '"$title" endgültig löschen?',
            'هل تريدين حذف "$title" نهائياً؟',
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

    if (!mounted || confirmed != true) return;

    try {
      await ApiService.deleteProject(widget.token, id);

      if (!mounted) return;

      await loadProjects();

      if (!mounted) return;

      message(t('Project deleted', 'Projekt gelöscht', 'تم حذف المشروع'));
    } catch (e) {
      if (!mounted) return;
      message(friendlyError(e), error: true);
    }
  }

  Future<void> editProject(
    int id,
    String oldTitle,
    String oldDescription,
  ) async {
    final titleController = TextEditingController(text: oldTitle);

    final descriptionController = TextEditingController(text: oldDescription);

    final result = await showDialog<Map<String, String>>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(t('Edit Project', 'Projekt bearbeiten', 'تعديل المشروع')),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: titleController,
              decoration: InputDecoration(
                labelText: t('Title', 'Titel', 'العنوان'),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: descriptionController,
              maxLines: 3,
              decoration: InputDecoration(
                labelText: t('Description', 'Beschreibung', 'الوصف'),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: Text(t('Cancel', 'Abbrechen', 'إلغاء')),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(dialogContext, {
                'title': titleController.text.trim(),
                'description': descriptionController.text.trim(),
              });
            },
            child: Text(t('Save', 'Speichern', 'حفظ')),
          ),
        ],
      ),
    );

    await Future<void>.delayed(const Duration(milliseconds: 200));

    titleController.dispose();
    descriptionController.dispose();

    if (!mounted || result == null) return;

    final newTitle = result['title'] ?? '';
    if (newTitle.isEmpty) return;

    try {
      await ApiService.updateProject(
        widget.token,
        id,
        newTitle,
        result['description'] ?? '',
      );

      if (!mounted) return;

      await loadProjects();

      if (!mounted) return;

      message(t('Project updated', 'Projekt aktualisiert', 'تم تحديث المشروع'));
    } catch (e) {
      if (!mounted) return;
      message(friendlyError(e), error: true);
    }
  }

  Future<void> deleteAccount() async {
    if (isDeletingAccount || isLoggingOut || isCreating || isLoading) return;

    final confirmed = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => AlertDialog(
        title: Text(t('Delete account', 'Konto löschen', 'حذف الحساب')),
        content: Text(
          t(
            'Your account, projects and PDF files will be permanently deleted. This cannot be undone.',
            'Dein Konto, deine Projekte und PDF-Dateien werden dauerhaft gelöscht. Dies kann nicht rückgängig gemacht werden.',
            'سيتم حذف حسابك ومشاريعك وملفات PDF نهائياً. لا يمكن التراجع عن هذه العملية.',
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
              t('Delete permanently', 'Endgültig löschen', 'حذف نهائي'),
              style: const TextStyle(color: Colors.red),
            ),
          ),
        ],
      ),
    );

    if (!mounted || confirmed != true || isDeletingAccount || isLoggingOut) {
      return;
    }
    setState(() => isDeletingAccount = true);

    try {
      await ApiService.deleteAccount(widget.token);
      if (!mounted) return;
      final currentLanguage = Localizations.localeOf(context).languageCode;
      final onLanguageChanged = widget.onLanguageChanged;
      message(t('Account deleted', 'Konto gelöscht', 'تم حذف الحساب'));
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute<void>(
          builder: (_) => LoginScreen(
            selectedLanguage: currentLanguage,
            onLanguageChanged: onLanguageChanged,
          ),
        ),
        (_) => false,
      );
    } catch (e) {
      if (!mounted) return;

      message(
        '${t('Account deletion could not be confirmed.', 'Kontolöschung konnte nicht bestätigt werden.', 'تعذر تأكيد حذف الحساب.')}\n${friendlyError(e)}',
        error: true,
      );
    } finally {
      if (mounted) setState(() => isDeletingAccount = false);
    }
  }

  Future<void> logout() async {
    if (isLoggingOut) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(t('Logout', 'Abmelden', 'تسجيل الخروج')),
        content: Text(
          t('Are you sure?', 'Bist du sicher?', 'هل تريدين تسجيل الخروج؟'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: Text(t('Cancel', 'Abbrechen', 'إلغاء')),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: Text(t('Logout', 'Abmelden', 'خروج')),
          ),
        ],
      ),
    );

    if (!mounted || confirmed != true) return;

    setState(() {
      isLoggingOut = true;
    });

    try {
      await ApiService.logout();
    } catch (e) {
      await AuthStorage.clearTokens();
    }

    if (!mounted) return;

    // Capture locale before removing this screen.
    final currentLanguage = Localizations.localeOf(context).languageCode;

    final onLanguageChanged = widget.onLanguageChanged;

    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute<void>(
        builder: (_) => LoginScreen(
          selectedLanguage: currentLanguage,
          onLanguageChanged: onLanguageChanged,
        ),
      ),
      (_) => false,
    );
  }

  Future<void> openProject(int id, String title) async {
    // Capture locale before navigating.
    final currentLanguage = Localizations.localeOf(context).languageCode;

    final token = widget.token;
    final onLanguageChanged = widget.onLanguageChanged;

    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => ProjectDetailsScreen(
          token: token,
          projectId: id,
          projectTitle: title,
          selectedLanguage: currentLanguage,
          onLanguageChanged: onLanguageChanged,
        ),
      ),
    );

    if (mounted) {
      await loadProjects();
    }
  }

  Widget languageButton() {
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

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !isDeletingAccount,
      child: Scaffold(
        backgroundColor: const Color(0xFFF7F7FB),

        appBar: AppBar(
          title: Text(
            t('UniBrief Dashboard', 'UniBrief Übersicht', 'لوحة تحكم UniBrief'),
          ),

          backgroundColor: Colors.deepPurple,
          foregroundColor: Colors.white,

          actions: [
            languageButton(),

            PopupMenuButton<String>(
              enabled:
                  !isDeletingAccount &&
                  !isLoggingOut &&
                  !isCreating &&
                  !isLoading,
              icon: const Icon(Icons.manage_accounts),
              tooltip: t('Account', 'Konto', 'الحساب'),
              onSelected: (value) {
                if (value == 'delete_account') deleteAccount();
              },
              itemBuilder: (_) => [
                PopupMenuItem(
                  value: 'delete_account',
                  child: Text(
                    t('Delete account', 'Konto löschen', 'حذف الحساب'),
                    style: const TextStyle(color: Colors.red),
                  ),
                ),
              ],
            ),

            IconButton(
              onPressed: isLoading || isDeletingAccount ? null : loadProjects,
              icon: const Icon(Icons.refresh),
            ),

            IconButton(
              onPressed: isLoggingOut || isDeletingAccount ? null : logout,
              icon: const Icon(Icons.logout),
            ),
          ],
        ),

        body: isDeletingAccount
            ? Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const CircularProgressIndicator(),
                    const SizedBox(height: 16),
                    Text(
                      t(
                        'Deleting account...',
                        'Konto wird gelöscht...',
                        'جارٍ حذف الحساب...',
                      ),
                    ),
                  ],
                ),
              )
            : Padding(
                padding: const EdgeInsets.all(20),

                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,

                  children: [
                    Text(
                      t(
                        'Welcome to UniBrief!',
                        'Willkommen bei UniBrief!',
                        'أهلاً بك في UniBrief!',
                      ),

                      style: const TextStyle(
                        fontSize: 25,
                        fontWeight: FontWeight.bold,
                      ),
                    ),

                    const SizedBox(height: 8),

                    Text(
                      t(
                        'Manage your university projects.',
                        'Verwalte deine Universitätsprojekte.',
                        'إدارة مشاريعك الجامعية بسهولة.',
                      ),
                    ),

                    const SizedBox(height: 24),

                    ElevatedButton.icon(
                      onPressed: isCreating ? null : createProject,

                      icon: isCreating
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.add),

                      label: Text(
                        t(
                          'Create New Project',
                          'Neues Projekt erstellen',
                          'إنشاء مشروع جديد',
                        ),
                      ),
                    ),

                    const SizedBox(height: 24),

                    Text(
                      t('My Projects', 'Meine Projekte', 'مشاريعي'),

                      style: const TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                      ),
                    ),

                    const SizedBox(height: 16),

                    Expanded(
                      child: isLoading
                          ? const Center(child: CircularProgressIndicator())
                          : projects.isEmpty
                          ? Center(
                              child: Text(
                                t(
                                  'No projects yet.',
                                  'Noch keine Projekte.',
                                  'لا توجد مشاريع بعد.',
                                ),
                              ),
                            )
                          : ListView.builder(
                              itemCount: projects.length,

                              itemBuilder: (context, index) {
                                final project = projects[index];

                                if (project is! Map) {
                                  return const SizedBox.shrink();
                                }

                                final rawId = project['id'];

                                final int? id = rawId is int
                                    ? rawId
                                    : int.tryParse('$rawId');

                                final title =
                                    project['title']?.toString() ?? '';

                                final description =
                                    project['description']?.toString() ?? '';

                                return Card(
                                  margin: const EdgeInsets.only(bottom: 12),

                                  child: ListTile(
                                    leading: const Icon(
                                      Icons.folder,
                                      color: Colors.deepPurple,
                                    ),

                                    title: Text(title),

                                    subtitle: Text(description),

                                    trailing: id == null
                                        ? null
                                        : PopupMenuButton<String>(
                                            onSelected: (action) {
                                              if (action == 'edit') {
                                                editProject(
                                                  id,
                                                  title,
                                                  description,
                                                );
                                              } else if (action == 'delete') {
                                                deleteProject(id, title);
                                              }
                                            },

                                            itemBuilder: (_) => [
                                              PopupMenuItem(
                                                value: 'edit',

                                                child: Text(
                                                  t(
                                                    'Edit',
                                                    'Bearbeiten',
                                                    'تعديل',
                                                  ),
                                                ),
                                              ),

                                              PopupMenuItem(
                                                value: 'delete',

                                                child: Text(
                                                  t('Delete', 'Löschen', 'حذف'),
                                                ),
                                              ),
                                            ],
                                          ),

                                    onTap: id == null
                                        ? null
                                        : () => openProject(id, title),
                                  ),
                                );
                              },
                            ),
                    ),
                  ],
                ),
              ),
      ),
    );
  }
}
