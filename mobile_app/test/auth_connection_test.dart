import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:mobile_app/services/api_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('Đăng ký gửi JSON, bỏ cảnh báo Ngrok và lưu phiên hợp lệ', () async {
    final api = ApiService(
      client: MockClient((request) async {
        expect(request.url.path, '/api/auth/register');
        expect(request.headers['ngrok-skip-browser-warning'], 'true');
        expect(jsonDecode(request.body), {
          'username': 'tester',
          'password': 'abcdefgh',
          'genres': ['Action'],
        });
        return http.Response(
          jsonEncode({
            'user_id': 200001,
            'username': 'tester',
            'access_token': 'test-token',
            'expires_at': '2099-01-01T00:00:00Z',
          }),
          201,
        );
      }),
    );
    expect(
      (await api.register('tester', 'abcdefgh', ['Action'])).isSuccess,
      isTrue,
    );
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('accessToken'), 'test-token');
  });

  test('Ngrok trả HTML báo lỗi đường hầm thay vì lỗi mật khẩu', () async {
    final api = ApiService(
      client: MockClient(
        (_) async => http.Response('<html>ERR_NGROK_3200</html>', 404),
      ),
    );
    final result = await api.login('tester', 'abcdefgh');
    expect(result.isSuccess, isFalse);
    expect(result.error, contains('HTTP 404'));
    expect(result.error, contains('Ngrok'));
  });

  test('Đăng ký 422 giải thích giới hạn tài khoản bằng tiếng Việt', () async {
    final api = ApiService(
      client: MockClient(
        (_) async => http.Response(
          jsonEncode({
            'detail': [
              {
                'loc': ['body', 'username'],
              },
            ],
          }),
          422,
        ),
      ),
    );
    final result = await api.register('x', 'abcdefgh', ['Action']);
    expect(result.error, contains('3 đến 50'));
  });

  test('Sai mật khẩu giữ nguyên thông báo xác thực từ máy chủ', () async {
    const message = 'Tên đăng nhập hoặc mật khẩu không đúng';
    final api = ApiService(
      client: MockClient(
        (_) async => http.Response.bytes(
          utf8.encode(jsonEncode({'detail': message})),
          401,
        ),
      ),
    );
    expect((await api.login('tester', 'wrong')).error, message);
  });

  test(
    'Phản hồi xác thực sai cấu trúc không lưu token hoặc ném lỗi ép kiểu',
    () async {
      for (final payload in [
        <String, dynamic>{
          'access_token': 'bad-token',
          'expires_at': '2099-01-01T00:00:00Z',
        },
        <String, dynamic>{
          'user_id': 200001,
          'username': 'tester',
          'access_token': 'bad-token',
          'expires_at': 'invalid',
        },
        [],
      ]) {
        final api = ApiService(
          client: MockClient(
            (_) async => http.Response(jsonEncode(payload), 200),
          ),
        );
        expect((await api.login('tester', 'abcdefgh')).isSuccess, isFalse);
        expect(
          (await SharedPreferences.getInstance()).getString('accessToken'),
          isNull,
        );
      }
    },
  );
}
