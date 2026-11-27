import 'package:flutter/material.dart';

import '../services/api_service.dart';
import 'dashboard_screen.dart';
import 'register_screen.dart';
import '../services/error_handler.dart';

class LoginScreen extends StatefulWidget {
  final String selectedLanguage;
  final ValueChanged<String> onLanguageChanged;

  const LoginScreen({
    super.key,
    required this.selectedLanguage,
    required this.onLanguageChanged,
  });

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();

  final TextEditingController _emailController = TextEditingController();

  final TextEditingController _passwordController = TextEditingController();

  bool _isLoading = false;
  bool _obscurePassword = true;

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

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    if (_isLoading) return;

    if (!_formKey.currentState!.validate()) {
      return;
    }

    setState(() {
      _isLoading = true;
    });

    try {
      final dynamic response = await ApiService.login(
        _emailController.text.trim(),
        _passwordController.text,
      );

      if (response is! Map) {
        throw Exception('Invalid login response');
      }

      final dynamic accessToken = response['access_token'];

      if (accessToken is! String || accessToken.trim().isEmpty) {
        throw Exception('Access token is missing or invalid');
      }

      if (!mounted) return;

      // Read the language before navigating.
      final currentLanguage = Localizations.localeOf(context).languageCode;

      Navigator.of(context).pushReplacement(
        MaterialPageRoute<void>(
          builder: (_) => DashboardScreen(
            token: accessToken,
            selectedLanguage: currentLanguage,
            onLanguageChanged: widget.onLanguageChanged,
          ),
        ),
      );
    } catch (error) {
      if (!mounted) return;

      final language = Localizations.localeOf(context).languageCode;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(ErrorHandler.message(error, language, isLogin: true)),
          backgroundColor: Colors.red,
          duration: const Duration(seconds: 5),
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF7F7FB),

      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),

          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),

            child: Card(
              elevation: 6,

              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(20),
              ),

              child: Padding(
                padding: const EdgeInsets.all(30),

                child: Form(
                  key: _formKey,

                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,

                    children: [
                      Align(
                        alignment: AlignmentDirectional.centerEnd,

                        child: PopupMenuButton<String>(
                          icon: const Icon(Icons.language),

                          tooltip: t('Language', 'Sprache', 'اللغة'),

                          onSelected: widget.onLanguageChanged,

                          itemBuilder: (_) => const [
                            PopupMenuItem(value: 'en', child: Text('English')),
                            PopupMenuItem(value: 'de', child: Text('Deutsch')),
                            PopupMenuItem(value: 'ar', child: Text('العربية')),
                          ],
                        ),
                      ),

                      const Icon(
                        Icons.school,
                        size: 65,
                        color: Color(0xFF6750A4),
                      ),

                      const SizedBox(height: 15),

                      const Text(
                        'UniBrief',
                        textAlign: TextAlign.center,

                        style: TextStyle(
                          fontSize: 30,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFF6750A4),
                        ),
                      ),

                      const SizedBox(height: 8),

                      Text(
                        t(
                          'Your AI-powered study assistant',
                          'Dein KI-Studienassistent',
                          'مساعدك الدراسي بالذكاء الاصطناعي',
                        ),
                        textAlign: TextAlign.center,

                        style: const TextStyle(
                          fontSize: 14,
                          color: Colors.grey,
                        ),
                      ),

                      const SizedBox(height: 35),

                      Text(
                        t(
                          'Welcome Back!',
                          'Willkommen zurück!',
                          'أهلاً بعودتك!',
                        ),

                        style: const TextStyle(
                          fontSize: 22,
                          fontWeight: FontWeight.bold,
                        ),
                      ),

                      const SizedBox(height: 8),

                      Text(
                        t(
                          'Sign in to continue',
                          'Melde dich an, um fortzufahren',
                          'سجّلي الدخول للمتابعة',
                        ),

                        style: const TextStyle(color: Colors.grey),
                      ),

                      const SizedBox(height: 25),

                      TextFormField(
                        controller: _emailController,

                        keyboardType: TextInputType.emailAddress,

                        textInputAction: TextInputAction.next,

                        decoration: InputDecoration(
                          labelText: t('Email', 'E-Mail', 'البريد الإلكتروني'),

                          prefixIcon: const Icon(Icons.email_outlined),

                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),

                        validator: (value) {
                          if (value == null || value.trim().isEmpty) {
                            return t(
                              'Please enter your email',
                              'Bitte E-Mail eingeben',
                              'أدخلي البريد الإلكتروني',
                            );
                          }

                          final emailPattern = RegExp(
                            r'^[^@\s]+@[^@\s]+\.[^@\s]+$',
                          );

                          if (!emailPattern.hasMatch(value.trim())) {
                            return t(
                              'Please enter a valid email',
                              'Bitte gültige E-Mail eingeben',
                              'أدخلي بريداً إلكترونياً صحيحاً',
                            );
                          }

                          return null;
                        },
                      ),

                      const SizedBox(height: 20),

                      TextFormField(
                        controller: _passwordController,
                        obscureText: _obscurePassword,

                        textInputAction: TextInputAction.done,

                        decoration: InputDecoration(
                          labelText: t('Password', 'Passwort', 'كلمة المرور'),

                          prefixIcon: const Icon(Icons.lock_outline),

                          suffixIcon: IconButton(
                            icon: Icon(
                              _obscurePassword
                                  ? Icons.visibility_off
                                  : Icons.visibility,
                            ),

                            onPressed: () {
                              setState(() {
                                _obscurePassword = !_obscurePassword;
                              });
                            },
                          ),

                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),

                        validator: (value) {
                          if (value == null || value.isEmpty) {
                            return t(
                              'Please enter your password',
                              'Bitte Passwort eingeben',
                              'أدخلي كلمة المرور',
                            );
                          }

                          return null;
                        },

                        onFieldSubmitted: (_) {
                          if (!_isLoading) {
                            _login();
                          }
                        },
                      ),

                      const SizedBox(height: 30),

                      SizedBox(
                        height: 50,

                        child: ElevatedButton(
                          onPressed: _isLoading ? null : _login,

                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFF6750A4),

                            foregroundColor: Colors.white,

                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                          ),

                          child: _isLoading
                              ? const SizedBox(
                                  width: 24,
                                  height: 24,

                                  child: CircularProgressIndicator(
                                    color: Colors.white,
                                    strokeWidth: 2,
                                  ),
                                )
                              : Text(
                                  t('Login', 'Anmelden', 'تسجيل الدخول'),

                                  style: const TextStyle(
                                    fontSize: 17,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                        ),
                      ),

                      const SizedBox(height: 20),
                      const Divider(),

                      const SizedBox(height: 12),

                      Text(
                        t(
                          "Don't have an account?",
                          'Du hast noch kein Konto?',
                          'ليس لديك حساب؟',
                        ),
                        textAlign: TextAlign.center,
                      ),

                      const SizedBox(height: 8),

                      OutlinedButton.icon(
                        onPressed: _isLoading
                            ? null
                            : () async {
                                final registeredEmail =
                                    await Navigator.of(context).push<String>(
                                      MaterialPageRoute<String>(
                                        builder: (_) => RegisterScreen(
                                          selectedLanguage:
                                              Localizations.localeOf(
                                                context,
                                              ).languageCode,
                                          onLanguageChanged:
                                              widget.onLanguageChanged,
                                        ),
                                      ),
                                    );

                                if (!mounted) return;

                                if (registeredEmail != null) {
                                  _emailController.text = registeredEmail;
                                  _passwordController.clear();
                                }
                              },
                        icon: const Icon(Icons.person_add_outlined),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: const Color(0xFF6750A4),
                          minimumSize: const Size(double.infinity, 50),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                        label: Text(
                          t(
                            'Create Account',
                            'Konto erstellen',
                            'إنشاء حساب جديد',
                          ),
                        ),
                      ),

                      const SizedBox(height: 20),

                      Text(
                        t(
                          'Organize your projects. Track your progress.',
                          'Organisiere Projekte und verfolge deinen Fortschritt.',
                          'نظّمي مشاريعك وتابعي تقدّمك.',
                        ),

                        textAlign: TextAlign.center,

                        style: const TextStyle(
                          fontSize: 12,
                          color: Colors.grey,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
