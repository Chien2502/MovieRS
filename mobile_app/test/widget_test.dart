import 'package:flutter_test/flutter_test.dart';
import 'package:mobile_app/main.dart';
import 'package:mobile_app/screens/login_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('MovieRS App smoke test', (WidgetTester tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(const MovieRSApp());
    expect(find.byType(MovieRSApp), findsOneWidget);

    // Chờ SplashScreen hoàn tất timer 3s và chuyển màn hình
    await tester.pump(const Duration(seconds: 4));
    await tester.pump(const Duration(milliseconds: 500));

    // Chưa đăng nhập -> phải tới màn Đăng nhập
    expect(find.byType(LoginScreen), findsOneWidget);
  });
}
