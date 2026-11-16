import 'package:flutter/material.dart';

import 'api_service.dart';

class ContentTranslation {
  static final Map<String, String> _cache = {};

  static String _key(int projectId, String language, String text) {
    return '$projectId|$language|$text';
  }

  static String getText(dynamic item) {
    if (item is Map) {
      return (item['text'] ??
              item['requirement_text'] ??
              item['description'] ??
              item['title'] ??
              item['content'] ??
              item['task'] ??
              '')
          .toString();
    }

    return item?.toString() ?? '';
  }

  static String cachedText({
    required int projectId,
    required String language,
    required String text,
  }) {
    return _cache[_key(projectId, language, text)] ?? text;
  }

  static Future<void> translate({
    required String token,
    required int projectId,
    required String language,
    required List<String> texts,
  }) async {
    if (!['ar', 'de', 'en'].contains(language)) {
      return;
    }

    final missing = texts
        .where((text) => text.trim().isNotEmpty)
        .where((text) => !_cache.containsKey(_key(projectId, language, text)))
        .toSet()
        .toList();

    if (missing.isEmpty) return;

    final translated = await ApiService.translateContent(
      token: token,
      projectId: projectId,
      language: language,
      texts: missing,
    );

    if (translated.length != missing.length) {
      throw Exception('Translation response count mismatch');
    }

    for (var i = 0; i < missing.length; i++) {
      _cache[_key(projectId, language, missing[i])] = translated[i];
    }
  }
}

class TranslatedContent extends StatefulWidget {
  final String token;
  final int projectId;
  final String language;
  final String text;
  final TextStyle? style;
  final TextAlign? textAlign;

  const TranslatedContent({
    super.key,
    required this.token,
    required this.projectId,
    required this.language,
    required this.text,
    this.style,
    this.textAlign,
  });

  @override
  State<TranslatedContent> createState() => _TranslatedContentState();
}

class _TranslatedContentState extends State<TranslatedContent> {
  String? _translated;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(covariant TranslatedContent oldWidget) {
    super.didUpdateWidget(oldWidget);

    if (oldWidget.language != widget.language ||
        oldWidget.text != widget.text ||
        oldWidget.projectId != widget.projectId) {
      _translated = null;
      _load();
    }
  }

  Future<void> _load() async {
    final language = widget.language;
    final text = widget.text;
    final projectId = widget.projectId;

    final cached = ContentTranslation.cachedText(
      projectId: projectId,
      language: language,
      text: text,
    );

    if (cached != text || text.trim().isEmpty) {
      setState(() {
        _translated = cached;
        _loading = false;
      });
      return;
    }

    setState(() {
      _loading = true;
    });

    try {
      await ContentTranslation.translate(
        token: widget.token,
        projectId: projectId,
        language: language,
        texts: [text],
      );

      if (!mounted ||
          widget.language != language ||
          widget.text != text ||
          widget.projectId != projectId) {
        return;
      }

      setState(() {
        _translated = ContentTranslation.cachedText(
          projectId: projectId,
          language: language,
          text: text,
        );
      });
    } catch (e) {
      debugPrint('Translation failed: $e');
    } finally {
      if (mounted &&
          widget.language == language &&
          widget.text == text &&
          widget.projectId == projectId) {
        setState(() {
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Flexible(
          child: Text(
            _translated ?? widget.text,
            style: widget.style,
            textAlign: widget.textAlign,
            textDirection: widget.language == 'ar'
                ? TextDirection.rtl
                : TextDirection.ltr,
          ),
        ),
        if (_loading) ...[
          const SizedBox(width: 6),
          const SizedBox(
            width: 12,
            height: 12,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ],
      ],
    );
  }
}
