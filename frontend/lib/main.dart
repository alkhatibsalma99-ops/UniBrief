import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'screens/login_screen.dart';

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
  String _language = 'en';

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
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
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

      home: LoginScreen(
        selectedLanguage: _language,
        onLanguageChanged: _changeLanguage,
      ),
    );
  }
}
