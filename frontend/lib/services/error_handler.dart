import 'dart:async';

import 'package:http/http.dart' as http;

// =====================================
// API EXCEPTION
// =====================================

class ApiException implements Exception {
  final int statusCode;

  const ApiException(this.statusCode);

  @override
  String toString() => 'API error $statusCode';
}

// =====================================
// SESSION EXPIRED EXCEPTION
// =====================================

class SessionExpiredException implements Exception {
  const SessionExpiredException();
}

// =====================================
// CENTRAL ERROR HANDLER
// =====================================

class ErrorHandler {
  static String message(Object error, String language, {bool isLogin = false}) {
    String t(String en, String de, String ar) {
      switch (language) {
        case 'de':
          return de;
        case 'ar':
          return ar;
        default:
          return en;
      }
    }

    // SESSION EXPIRED

    if (error is SessionExpiredException) {
      return t(
        'Your session has expired. Please log in again.',
        'Deine Sitzung ist abgelaufen. Bitte melde dich erneut an.',
        'انتهت جلستك. يرجى تسجيل الدخول مجدداً.',
      );
    }

    // TIMEOUT

    if (error is TimeoutException) {
      return t(
        'The request took too long. Please try again.',
        'Die Anfrage hat zu lange gedauert. Bitte versuche es erneut.',
        'استغرق الطلب وقتاً طويلاً. يرجى المحاولة مجدداً.',
      );
    }

    // NETWORK ERROR

    if (error is http.ClientException) {
      return t(
        'Could not connect to the server. Please check your internet connection.',
        'Keine Verbindung zum Server. Bitte überprüfe deine Internetverbindung.',
        'تعذر الاتصال بالخادم. يرجى التحقق من اتصال الإنترنت.',
      );
    }

    // HTTP ERRORS

    if (error is ApiException) {
      switch (error.statusCode) {
        case 400:
          return t(
            'Invalid request. Please check your input.',
            'Ungültige Anfrage. Bitte überprüfe deine Eingaben.',
            'الطلب غير صالح. يرجى التحقق من البيانات المدخلة.',
          );

        case 401:
          if (isLogin) {
            return t(
              'Incorrect email or password.',
              'E-Mail-Adresse oder Passwort ist falsch.',
              'البريد الإلكتروني أو كلمة المرور غير صحيحة.',
            );
          }

          return t(
            'Your session has expired. Please log in again.',
            'Deine Sitzung ist abgelaufen. Bitte melde dich erneut an.',
            'انتهت جلستك. يرجى تسجيل الدخول مجدداً.',
          );

        case 403:
          return t(
            'You do not have permission to perform this action.',
            'Du hast keine Berechtigung für diese Aktion.',
            'ليس لديك صلاحية لتنفيذ هذا الإجراء.',
          );

        case 404:
          return t(
            'The requested item could not be found.',
            'Das gewünschte Element wurde nicht gefunden.',
            'لم يتم العثور على العنصر المطلوب.',
          );

        case 409:
          return t(
            'The action conflicts with the current state. Please check and try again.',
            'Die Aktion steht im Konflikt mit dem aktuellen Zustand. Bitte überprüfe deine Angaben.',
            'يتعارض الإجراء مع الحالة الحالية. يرجى التحقق والمحاولة مجدداً.',
          );

        case 413:
          return t(
            'The file exceeds the allowed size.',
            'Die Datei überschreitet die erlaubte Größe.',
            'حجم الملف يتجاوز الحد المسموح.',
          );

        case 415:
          return t(
            'This file format is not supported.',
            'Dieses Dateiformat wird nicht unterstützt.',
            'صيغة الملف غير مدعومة.',
          );

        case 422:
          return t(
            'Please check the entered information.',
            'Bitte überprüfe die eingegebenen Informationen.',
            'يرجى التحقق من البيانات المدخلة.',
          );

        case 429:
          return t(
            'The request limit has been reached. Please try again later.',
            'Das Anfragelimit wurde erreicht. Bitte versuche es später erneut.',
            'تم الوصول إلى الحد المسموح من الطلبات. يرجى المحاولة لاحقاً.',
          );

        case 408:
        case 504:
          return t(
            'The server took too long to respond. Please try again.',
            'Der Server hat zu lange für die Antwort benötigt.',
            'استغرق الخادم وقتاً طويلاً للاستجابة. يرجى المحاولة مجدداً.',
          );

        case 500:
        case 502:
        case 503:
          return t(
            'The service is temporarily unavailable. Please try again later.',
            'Der Dienst ist vorübergehend nicht verfügbar. Bitte versuche es später erneut.',
            'الخدمة غير متاحة مؤقتاً. يرجى المحاولة لاحقاً.',
          );
      }
    }

    // FALLBACK MESSAGE

    return t(
      'Something went wrong. Please try again.',
      'Etwas ist schiefgelaufen. Bitte versuche es erneut.',
      'حدث خطأ غير متوقع. يرجى المحاولة مجدداً.',
    );
  }
}
