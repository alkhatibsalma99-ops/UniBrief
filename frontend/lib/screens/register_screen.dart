import 'package:flutter/material.dart';

import '../services/api_service.dart';

class RegisterScreen extends StatefulWidget {
  final String selectedLanguage;
  final ValueChanged<String> onLanguageChanged;

  const RegisterScreen({
    super.key,
    required this.selectedLanguage,
    required this.onLanguageChanged,
  });

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();

  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();

  bool _isLoading = false;
  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;

  static const primaryColor = Color(0xFF6750A4);

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
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  Future<void> _register() async {
    if (_isLoading) return;

    if (!_formKey.currentState!.validate()) return;

    FocusScope.of(context).unfocus();

    setState(() => _isLoading = true);

    try {
      await ApiService.register(
        name: _nameController.text.trim(),
        email: _emailController.text.trim(),
        password: _passwordController.text,
      );

      if (!mounted) return;

      final message = t(
        'Account created successfully! Please log in.',
        'Konto erfolgreich erstellt! Bitte melde dich an.',
        'تم إنشاء الحساب بنجاح! سجّل الدخول الآن.',
      );

      final messenger = ScaffoldMessenger.of(context);

      Navigator.of(context).pop(_emailController.text.trim());

      messenger.showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: Colors.green,
          duration: const Duration(seconds: 5),
        ),
      );
    } catch (error) {
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            '${t('Registration failed', 'Registrierung fehlgeschlagen', 'فشل إنشاء الحساب')}: $error',
          ),
          backgroundColor: Colors.red,
          duration: const Duration(seconds: 5),
        ),
      );
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  InputDecoration fieldDecoration({
    required String label,
    required IconData icon,
    Widget? suffixIcon,
  }) {
    return InputDecoration(
      labelText: label,
      prefixIcon: Icon(icon),
      suffixIcon: suffixIcon,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF7F7FB),
      body: SafeArea(
        child: Center(
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
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            IconButton(
                              onPressed: _isLoading
                                  ? null
                                  : () => Navigator.pop(context),
                              icon: const Icon(Icons.arrow_back),
                            ),
                            PopupMenuButton<String>(
                              icon: const Icon(Icons.language),
                              tooltip: t('Language', 'Sprache', 'اللغة'),
                              onSelected: widget.onLanguageChanged,
                              itemBuilder: (_) => const [
                                PopupMenuItem(
                                  value: 'en',
                                  child: Text('English'),
                                ),
                                PopupMenuItem(
                                  value: 'de',
                                  child: Text('Deutsch'),
                                ),
                                PopupMenuItem(
                                  value: 'ar',
                                  child: Text('العربية'),
                                ),
                              ],
                            ),
                          ],
                        ),

                        const Icon(Icons.school, size: 65, color: primaryColor),

                        const SizedBox(height: 15),

                        const Text(
                          'UniBrief',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 30,
                            fontWeight: FontWeight.bold,
                            color: primaryColor,
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

                        const SizedBox(height: 30),

                        Text(
                          t(
                            'Create Account',
                            'Konto erstellen',
                            'إنشاء حساب جديد',
                          ),
                          style: const TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.bold,
                          ),
                        ),

                        const SizedBox(height: 8),

                        Text(
                          t(
                            'Start your journey with UniBrief',
                            'Starte deine Reise mit UniBrief',
                            'ابدأ رحلتك مع UniBrief',
                          ),
                          style: const TextStyle(color: Colors.grey),
                        ),

                        const SizedBox(height: 25),

                        // NAME
                        TextFormField(
                          controller: _nameController,
                          enabled: !_isLoading,
                          textCapitalization: TextCapitalization.words,
                          textInputAction: TextInputAction.next,
                          autofillHints: const [AutofillHints.name],
                          decoration: fieldDecoration(
                            label: t(
                              'Full Name',
                              'Vollständiger Name',
                              'الاسم الكامل',
                            ),
                            icon: Icons.person_outline,
                          ),
                          validator: (value) {
                            if (value == null || value.trim().isEmpty) {
                              return t(
                                'Please enter your name',
                                'Bitte Namen eingeben',
                                'يرجى إدخال الاسم',
                              );
                            }

                            if (value.trim().length > 100) {
                              return t(
                                'Name is too long',
                                'Name ist zu lang',
                                'الاسم طويل جداً',
                              );
                            }

                            return null;
                          },
                        ),

                        const SizedBox(height: 20),

                        // EMAIL
                        TextFormField(
                          controller: _emailController,
                          enabled: !_isLoading,
                          keyboardType: TextInputType.emailAddress,
                          textInputAction: TextInputAction.next,
                          autofillHints: const [AutofillHints.email],
                          decoration: fieldDecoration(
                            label: t('Email', 'E-Mail', 'البريد الإلكتروني'),
                            icon: Icons.email_outlined,
                          ),
                          validator: (value) {
                            if (value == null || value.trim().isEmpty) {
                              return t(
                                'Please enter your email',
                                'Bitte E-Mail eingeben',
                                'يرجى إدخال البريد الإلكتروني',
                              );
                            }

                            final emailPattern = RegExp(
                              r'^[^@\s]+@[^@\s]+\.[^@\s]+$',
                            );

                            if (!emailPattern.hasMatch(value.trim()) ||
                                value.trim().length > 255) {
                              return t(
                                'Please enter a valid email',
                                'Bitte gültige E-Mail eingeben',
                                'يرجى إدخال بريد إلكتروني صحيح',
                              );
                            }

                            return null;
                          },
                        ),

                        const SizedBox(height: 20),

                        // PASSWORD
                        TextFormField(
                          controller: _passwordController,
                          enabled: !_isLoading,
                          obscureText: _obscurePassword,
                          textInputAction: TextInputAction.next,
                          autofillHints: const [AutofillHints.newPassword],
                          decoration: fieldDecoration(
                            label: t('Password', 'Passwort', 'كلمة المرور'),
                            icon: Icons.lock_outline,
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
                          ),
                          validator: (value) {
                            if (value == null || value.isEmpty) {
                              return t(
                                'Please enter a password',
                                'Bitte Passwort eingeben',
                                'يرجى إدخال كلمة المرور',
                              );
                            }

                            if (value.length < 8) {
                              return t(
                                'Use at least 8 characters',
                                'Mindestens 8 Zeichen verwenden',
                                'استخدم 8 أحرف على الأقل',
                              );
                            }

                            return null;
                          },
                        ),

                        const SizedBox(height: 20),

                        // CONFIRM PASSWORD
                        TextFormField(
                          controller: _confirmPasswordController,
                          enabled: !_isLoading,
                          obscureText: _obscureConfirmPassword,
                          textInputAction: TextInputAction.done,
                          decoration: fieldDecoration(
                            label: t(
                              'Confirm Password',
                              'Passwort bestätigen',
                              'تأكيد كلمة المرور',
                            ),
                            icon: Icons.lock_outline,
                            suffixIcon: IconButton(
                              icon: Icon(
                                _obscureConfirmPassword
                                    ? Icons.visibility_off
                                    : Icons.visibility,
                              ),
                              onPressed: () {
                                setState(() {
                                  _obscureConfirmPassword =
                                      !_obscureConfirmPassword;
                                });
                              },
                            ),
                          ),
                          validator: (value) {
                            if (value == null || value.isEmpty) {
                              return t(
                                'Please confirm your password',
                                'Bitte Passwort bestätigen',
                                'يرجى تأكيد كلمة المرور',
                              );
                            }

                            if (value != _passwordController.text) {
                              return t(
                                'Passwords do not match',
                                'Passwörter stimmen nicht überein',
                                'كلمتا المرور غير متطابقتين',
                              );
                            }

                            return null;
                          },
                          onFieldSubmitted: (_) => _register(),
                        ),

                        const SizedBox(height: 30),

                        // REGISTER BUTTON
                        SizedBox(
                          height: 50,
                          child: ElevatedButton(
                            onPressed: _isLoading ? null : _register,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: primaryColor,
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
                                    t(
                                      'Create Account',
                                      'Konto erstellen',
                                      'إنشاء حساب',
                                    ),
                                    style: const TextStyle(
                                      fontSize: 17,
                                      fontWeight: FontWeight.bold,
                                    ),
                                  ),
                          ),
                        ),

                        const SizedBox(height: 20),

                        Text(
                          t(
                            'Already have an account?',
                            'Du hast bereits ein Konto?',
                            'لديك حساب بالفعل؟',
                          ),
                          textAlign: TextAlign.center,
                        ),

                        TextButton(
                          onPressed: _isLoading
                              ? null
                              : () => Navigator.pop(context),
                          child: Text(
                            t('Login', 'Anmelden', 'تسجيل الدخول'),
                            style: const TextStyle(
                              color: primaryColor,
                              fontWeight: FontWeight.bold,
                            ),
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
      ),
    );
  }
}
