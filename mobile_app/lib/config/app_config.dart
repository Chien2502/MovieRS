import 'package:flutter/foundation.dart';

/// Cấu hình độc lập với .env backend; có thể truyền --dart-define=API_URL=...
class AppConfig {
  static const String ngrokUrl = '';
  static const String _overrideUrl = String.fromEnvironment('API_URL');

  static String get _localUrl =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android
      ? 'http://10.0.2.2:8000'
      : 'http://127.0.0.1:8000';

  static String get serverUrl {
    final value = _overrideUrl.isNotEmpty
        ? _overrideUrl
        : (ngrokUrl.isNotEmpty ? ngrokUrl : _localUrl);
    return value
        .replaceFirst(RegExp(r'/+$'), '')
        .replaceFirst(RegExp(r'/api$'), '');
  }

  static String get baseUrl => '$serverUrl/api';
  static bool get isUsingNgrok => serverUrl.contains('.ngrok');
}
