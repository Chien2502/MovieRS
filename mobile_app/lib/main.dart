import 'package:flutter/material.dart';
import 'constants/app_colors.dart';
import 'screens/splash_screen.dart';
import 'screens/login_screen.dart';
import 'services/api_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const MovieRSApp());
}

class MovieRSApp extends StatefulWidget {
  const MovieRSApp({super.key});

  @override
  State<MovieRSApp> createState() => _MovieRSAppState();
}

class _MovieRSAppState extends State<MovieRSApp> {
  final _navigatorKey = GlobalKey<NavigatorState>();

  @override
  void initState() {
    super.initState();
    ApiService.sessionExpired.addListener(_returnToLogin);
  }

  void _returnToLogin() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _navigatorKey.currentState?.pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const LoginScreen()),
        (_) => false,
      );
    });
  }

  @override
  void dispose() {
    ApiService.sessionExpired.removeListener(_returnToLogin);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: _navigatorKey,
      title: 'MovieRS Client',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.light,
        primarySwatch: Colors.grey,
        scaffoldBackgroundColor: AppColors.background,
        appBarTheme: const AppBarTheme(
          backgroundColor: AppColors.appBarBackground,
          elevation: 0,
        ),
      ),
      home: const SplashScreen(),
    );
  }
}
