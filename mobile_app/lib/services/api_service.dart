import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter/foundation.dart';
import '../config/app_config.dart';
import '../models/movie.dart';
import '../models/recommendation_result.dart';
import '../models/watch_progress.dart';

class ApiException implements Exception {
  final String message;
  const ApiException(this.message);
  @override
  String toString() => message;
}

class AuthResult {
  final int? userId;
  final String? username;
  final String? error;
  const AuthResult({this.userId, this.username, this.error});
  bool get isSuccess => userId != null;
}

class ApiService {
  static final ValueNotifier<int> sessionExpired = ValueNotifier<int>(0);
  static final Map<int, int> _dataVersions = {};
  static int dataVersion(int userId) => _dataVersions[userId] ?? 0;
  static String get baseUrl => AppConfig.baseUrl;
  static final http.Client _defaultClient = http.Client();
  final http.Client _client;
  ApiService({http.Client? client}) : _client = client ?? _defaultClient;

  Future<bool> hasValidSession() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('accessToken');
    final expiry = DateTime.tryParse(prefs.getString('sessionExpiresAt') ?? '');
    if (token == null || expiry == null || !expiry.isAfter(DateTime.now())) {
      return false;
    }
    try {
      await _request('GET', '/auth/me');
      return true;
    } on ApiException {
      return false;
    }
  }

  Future<void> logout() async {
    try {
      await _request('POST', '/auth/logout', {});
    } on ApiException {
      // Máy chủ tự hết hạn phiên; xóa bản local kể cả khi mất mạng.
    }
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('accessToken');
    await prefs.remove('sessionExpiresAt');
    await prefs.remove('userId');
    await prefs.remove('username');
  }

  Future<dynamic> _request(
    String method,
    String path, [
    Map<String, dynamic>? body,
    String? idempotencyKey,
  ]) async {
    final uri = Uri.parse('$baseUrl$path');
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('accessToken');
    final headers = {
      'Content-Type': 'application/json',
      'ngrok-skip-browser-warning': 'true',
      if (token != null) 'Authorization': 'Bearer $token',
      if (idempotencyKey != null) 'Idempotency-Key': idempotencyKey,
    };
    try {
      final pending = switch (method) {
        'POST' => _client.post(uri, headers: headers, body: json.encode(body)),
        'PUT' => _client.put(uri, headers: headers, body: json.encode(body)),
        'DELETE' => _client.delete(uri, headers: headers),
        _ => _client.get(uri, headers: headers),
      };
      final response = await pending.timeout(const Duration(seconds: 20));
      dynamic data;
      try {
        data = json.decode(utf8.decode(response.bodyBytes));
      } on FormatException {
        throw ApiException(
          'Địa chỉ ${uri.host} không trả về API MovieRS '
          '(HTTP ${response.statusCode}). Kiểm tra máy chủ và đường hầm Ngrok.',
        );
      }
      if (response.statusCode < 200 || response.statusCode >= 300) {
        if (response.statusCode == 401 && !path.startsWith('/auth/login')) {
          await prefs.remove('accessToken');
          await prefs.remove('sessionExpiresAt');
          if (token != null) sessionExpired.value++;
        }
        if (response.statusCode == 422 && path == '/auth/register') {
          throw const ApiException(
            'Tên đăng nhập cần từ 3 đến 50 ký tự; mật khẩu cần từ 8 đến 100 ký tự.',
          );
        }
        throw ApiException(
          data is Map && data['detail'] is String
              ? data['detail'] as String
              : 'Máy chủ từ chối yêu cầu (${response.statusCode})',
        );
      }
      return data;
    } on ApiException {
      rethrow;
    } on TimeoutException {
      throw const ApiException('Máy chủ phản hồi quá lâu. Vui lòng thử lại.');
    } on FormatException {
      throw const ApiException(
        'Phản hồi máy chủ không hợp lệ. Kiểm tra địa chỉ API.',
      );
    } catch (_) {
      throw ApiException(
        'Không kết nối được ${uri.host}. Kiểm tra mạng và địa chỉ API; '
        'điện thoại thật cần URL Ngrok hoặc địa chỉ LAN của máy chủ.',
      );
    }
  }

  Future<bool> _write(
    String method,
    String path, [
    Map<String, dynamic>? body,
    int? userId,
  ]) async {
    try {
      final key =
          '${DateTime.now().microsecondsSinceEpoch}-${Random.secure().nextInt(1 << 32)}';
      await _request(method, path, body, key);
      if (userId != null) {
        _dataVersions[userId] = dataVersion(userId) + 1;
      }
      return true;
    } on ApiException {
      return false;
    }
  }

  Future<AuthResult> _auth(String path, Map<String, dynamic> body) async {
    try {
      final data = await _request('POST', path, body);
      if (data is! Map<String, dynamic> ||
          data['user_id'] is! int ||
          data['username'] is! String ||
          data['access_token'] is! String ||
          (data['access_token'] as String).isEmpty ||
          data['expires_at'] is! String ||
          !(DateTime.tryParse(
                data['expires_at'] as String,
              )?.isAfter(DateTime.now()) ??
              false)) {
        throw const ApiException(
          'Máy chủ chưa cung cấp phiên đăng nhập hợp lệ.',
        );
      }
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('accessToken', data['access_token'] as String);
      await prefs.setString('sessionExpiresAt', data['expires_at'] as String);
      return AuthResult(
        userId: (data['user_id'] as num).toInt(),
        username: data['username'],
      );
    } on ApiException catch (e) {
      return AuthResult(error: e.message);
    }
  }

  Future<AuthResult> register(
    String username,
    String password,
    List<String> genres,
  ) => _auth('/auth/register', {
    'username': username,
    'password': password,
    'genres': genres,
  });
  Future<AuthResult> login(String username, String password) =>
      _auth('/auth/login', {'username': username, 'password': password});

  Future<Map<String, dynamic>?> getProfile(int userId) async =>
      await _request('GET', '/users/$userId/profile') as Map<String, dynamic>;

  Future<List<Movie>> getFavorites(int userId) async =>
      (await _request('GET', '/users/$userId/favorites') as List)
          .map((v) => Movie.fromJson(v))
          .toList();
  Future<bool> setFavorite(int userId, int movieId, bool isFavorite) => _write(
    'POST',
    '/users/$userId/favorites',
    {'movieId': movieId, 'isFavorite': isFavorite},
    userId,
  );
  Future<List<Map<String, dynamic>>> getRatingsHistory(int userId) async =>
      (await _request('GET', '/users/$userId/ratings') as List)
          .cast<Map<String, dynamic>>();
  Future<bool> savePreferences(int userId, List<String> genres) =>
      _write('PUT', '/users/$userId/preferences', {'genres': genres}, userId);

  Future<RecommendationResult> getRecommendationResult(
    int userId, {
    int limit = 10,
    bool explore = false,
  }) async => RecommendationResult.fromJson(
    await _request(
      'GET',
      '/recommendations/$userId?limit=$limit&explore=$explore',
    ),
  );
  Future<List<Movie>> getRecommendations(int userId, {int limit = 10}) async =>
      (await getRecommendationResult(userId, limit: limit)).movies;
  Future<List<Movie>> getPopularMovies({int limit = 10}) async {
    final data = await _request('GET', '/movies/popular?limit=$limit');
    return (data['results'] as List).map((v) => Movie.fromJson(v)).toList();
  }

  Future<Movie> getMovie(int movieId) async =>
      Movie.fromJson(await _request('GET', '/movies/$movieId'));
  Future<List<Movie>> searchMovies(String query) async =>
      (await _request('GET', '/movies/search?q=${Uri.encodeComponent(query)}')
              as List)
          .map((v) => Movie.fromJson(v))
          .toList();

  Future<bool> sendRating(int userId, int movieId, double rating) => _write(
    'POST',
    '/interactions/rating',
    {'userId': userId, 'movieId': movieId, 'rating': rating},
    userId,
  );
  Future<bool> sendFavorite(int userId, int movieId, bool isFavorite) =>
      setFavorite(userId, movieId, isFavorite);
  Future<bool> sendWatchHistory(
    int userId,
    int movieId,
    int position,
    int duration,
  ) => _write('POST', '/interactions/watch', {
    'userId': userId,
    'movieId': movieId,
    'watchDurationSeconds': position,
    'totalDurationSeconds': duration,
  }, userId);
  Future<bool> sendWatchProgress(
    int userId,
    int movieId,
    int position,
    int duration,
  ) => _write('PUT', '/watch/progress', {
    'userId': userId,
    'movieId': movieId,
    'positionSeconds': position,
    'durationSeconds': duration,
  }, userId);
  Future<List<WatchProgress>> getContinueWatching(int userId) async =>
      (await _request('GET', '/watch/progress/$userId') as List)
          .map((v) => WatchProgress.fromJson(v))
          .toList();
  Future<Map<String, dynamic>?> getWatchProgress(
    int userId,
    int movieId,
  ) async =>
      await _request('GET', '/watch/progress/$userId/$movieId')
          as Map<String, dynamic>;
  Future<bool> removeContinueWatching(int userId, int movieId) =>
      _write('DELETE', '/watch/progress/$userId/$movieId', null, userId);
}
