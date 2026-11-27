import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'screens/login_screen.dart';
import 'screens/dashboard_screen.dart';
import 'services/api_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const UniBriefApp());
}

class UniBriefApp extends StatefulWidget {
  const UniBriefApp({super.key});

  @override
  State<UniBriefApp> createState() => _UniBriefAppState();
}

class _UniBriefAppState extends State<UniBriefApp> {
  static const String _languageKey = 'unibrief_language';

  final SharedPreferencesAsync _preferences = SharedPreferencesAsync();

  final GlobalKey<ScaffoldMessengerState> _messengerKey =
      GlobalKey<ScaffoldMessengerState>();

  String _language = 'en';

  String? _sessionToken;

  bool _isInitializing = true;
  bool _initializationError = false;

  Future<void> _languageWrite = Future<void>.value();

  @override
  void initState() {
    super.initState();
    _initializeApp();
  }

  // =====================================
  // TRANSLATION HELPER
  // =====================================

  String t(String en, String de, String ar) {
    switch (_language) {
      case 'de':
        return de;
      case 'ar':
        return ar;
      default:
        return en;
    }
  }

  // =====================================
  // INITIALIZE APPLICATION
  // =====================================

  Future<void> _initializeApp() async {
    if (!mounted) return;

    setState(() {
      _isInitializing = true;
      _initializationError = false;
    });

    try {
      await _loadSavedLanguage();

      final token = await ApiService.restoreSession();

      if (!mounted) return;

      setState(() {
        _sessionToken = token;
        _isInitializing = false;
      });
    } catch (_) {
      if (!mounted) return;

      setState(() {
        _isInitializing = false;
        _initializationError = true;
      });
    }
  }

  // =====================================
  // LOAD SAVED LANGUAGE
  // =====================================

  Future<void> _loadSavedLanguage() async {
    final savedLanguage = await _preferences.getString(_languageKey);

    if (!mounted) return;

    if (savedLanguage != null && ['en', 'de', 'ar'].contains(savedLanguage)) {
      setState(() {
        _language = savedLanguage;
      });
    }
  }

  // =====================================
  // CHANGE AND SAVE LANGUAGE
  // =====================================

  void _changeLanguage(String language) {
    if (!['en', 'de', 'ar'].contains(language)) {
      return;
    }

    if (_language == language) {
      return;
    }

    setState(() {
      _language = language;
    });

    _languageWrite = _languageWrite.then((_) async {
      try {
        await _preferences.setString(_languageKey, language);
      } catch (_) {
        if (!mounted) return;

        _messengerKey.currentState?.showSnackBar(
          SnackBar(
            content: Text(
              t(
                'Could not save language preference.',
                'Spracheinstellung konnte nicht gespeichert werden.',
                'تعذر حفظ اللغة المختارة.',
              ),
            ),
          ),
        );
      }
    });
  }

  // =====================================
  // LOADING SCREEN
  // =====================================

  Widget _buildLoadingScreen() {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(
              Icons.school_rounded,
              size: 80,
              color: Color(0xFF6750A4),
            ),
            const SizedBox(height: 20),
            const Text(
              'UniBrief',
              style: TextStyle(
                fontSize: 30,
                fontWeight: FontWeight.bold,
                color: Color(0xFF6750A4),
              ),
            ),
            const SizedBox(height: 30),
            const CircularProgressIndicator(),
            const SizedBox(height: 20),
            Text(
              t(
                'Loading UniBrief...',
                'UniBrief wird geladen...',
                'جارٍ تحميل UniBrief...',
              ),
            ),
          ],
        ),
      ),
    );
  }

  // =====================================
  // STARTUP ERROR SCREEN
  // =====================================

  Widget _buildErrorScreen() {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(
                  Icons.sync_problem_rounded,
                  size: 70,
                  color: Color(0xFF6750A4),
                ),
                const SizedBox(height: 20),
                Text(
                  t(
                    'Could not start UniBrief',
                    'UniBrief konnte nicht gestartet werden',
                    'تعذر تشغيل UniBrief',
                  ),
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontSize: 23,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  t(
                    'Check your internet connection and try again.',
                    'Bitte überprüfe deine Internetverbindung und versuche es erneut.',
                    'تحقق من اتصال الإنترنت وحاول مرة أخرى.',
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 24),
                ElevatedButton.icon(
                  onPressed: _initializeApp,
                  icon: const Icon(Icons.refresh),
                  label: Text(
                    t('Try again', 'Erneut versuchen', 'إعادة المحاولة'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  // =====================================
  // SELECT START SCREEN
  // =====================================

  Widget _buildHome() {
    if (_isInitializing) {
      return _buildLoadingScreen();
    }

    if (_initializationError) {
      return _buildErrorScreen();
    }

    final token = _sessionToken;

    if (token != null && token.isNotEmpty) {
      return DashboardScreen(
        token: token,
        selectedLanguage: _language,
        onLanguageChanged: _changeLanguage,
      );
    }

    return LoginScreen(
      selectedLanguage: _language,
      onLanguageChanged: _changeLanguage,
    );
  }

  // =====================================
  // BUILD APPLICATION
  // =====================================

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      scaffoldMessengerKey: _messengerKey,

      debugShowCheckedModeBanner: false,

      title: 'UniBrief',

      locale: Locale(_language),

      supportedLocales: const [Locale('en'), Locale('de'), Locale('ar')],

      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],

      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF6750A4)),
        useMaterial3: true,
      ),

      home: _buildHome(),
    );
  }
}
