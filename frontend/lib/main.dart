import 'package:flutter/material.dart';
import 'screens/login_screen.dart';

void main() {
  runApp(const UniBriefApp());
}

class UniBriefApp extends StatelessWidget {
  const UniBriefApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'UniBrief',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF6750A4)),
        useMaterial3: true,
      ),
      home: const LoginScreen(),
    );
  }
}
