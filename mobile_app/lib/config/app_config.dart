library;

/// app_config.dart — Cấu hình URL API cho ứng dụng MovieRS

class AppConfig {
  // ============================================================
  //  CẤU HÌNH CHÍNH — CHỈ CẦN THAY ĐỔI URL NGROK Ở ĐÂY
  // ============================================================

  /// URL Ngrok public (thay đổi mỗi phiên chạy ngrok).
  /// Để trống '' nếu muốn kết nối localhost (emulator).
  static const String ngrokUrl = 'https://arlette-irascible-containedly.ngrok-free.dev';

  // ============================================================
  //  LOGIC TỰ ĐỘNG — KHÔNG CẦN SỬA
  // ============================================================

  /// URL cho Android Emulator kết nối localhost
  static const String _emulatorUrl = 'http://10.0.2.2:8000';

  /// Base URL API — tự động chọn Ngrok nếu đã cấu hình, ngược lại dùng emulator localhost
  static String get baseUrl {
    if (ngrokUrl.isNotEmpty) {
      final url = ngrokUrl.endsWith('/')
          ? ngrokUrl.substring(0, ngrokUrl.length - 1)
          : ngrokUrl;
      return '$url/api';
    }
    return '$_emulatorUrl/api';
  }

  /// Base URL không có prefix /api (dùng cho health check)
  static String get serverUrl {
    if (ngrokUrl.isNotEmpty) {
      return ngrokUrl.endsWith('/')
          ? ngrokUrl.substring(0, ngrokUrl.length - 1)
          : ngrokUrl;
    }
    return _emulatorUrl;
  }

  static bool get isUsingNgrok => ngrokUrl.isNotEmpty;
}
