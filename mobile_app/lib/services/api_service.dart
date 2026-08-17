import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../models/movie.dart';
import '../models/watch_progress.dart';
import '../config/app_config.dart';

/// Kết quả đăng ký / đăng nhập: thành công có [userId]/[username], thất bại có [error].
class AuthResult {
  final int? userId;
  final String? username;
  final String? error;

  const AuthResult({this.userId, this.username, this.error});

  bool get isSuccess => userId != null;
}

class ApiService {
  static String get baseUrl => AppConfig.baseUrl;

  /// Đăng ký tài khoản mới (kèm thể loại yêu thích cho Cold-Start)
  Future<AuthResult> register(String username, String password, List<String> genres) async {
    final url = Uri.parse('$baseUrl/auth/register');
    try {
      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: json.encode({
          'username': username,
          'password': password,
          'genres': genres,
        }),
      );
      if (response.statusCode == 201) {
        final data = json.decode(response.body) as Map<String, dynamic>;
        return AuthResult(userId: data['user_id'], username: data['username']);
      }
      return AuthResult(error: _detailFrom(response));
    } catch (e) {
      debugPrint('Error registering: $e');
      return const AuthResult(error: 'Không kết nối được máy chủ');
    }
  }

  /// Đăng nhập bằng tên đăng nhập + mật khẩu
  Future<AuthResult> login(String username, String password) async {
    final url = Uri.parse('$baseUrl/auth/login');
    try {
      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'username': username, 'password': password}),
      );
      if (response.statusCode == 200) {
        final data = json.decode(response.body) as Map<String, dynamic>;
        return AuthResult(userId: data['user_id'], username: data['username']);
      }
      return AuthResult(error: _detailFrom(response));
    } catch (e) {
      debugPrint('Error logging in: $e');
      return const AuthResult(error: 'Không kết nối được máy chủ');
    }
  }

  /// Lấy hồ sơ người dùng (username, genres, số lượng tương tác)
  Future<Map<String, dynamic>?> getProfile(int userId) async {
    final url = Uri.parse('$baseUrl/users/$userId/profile');
    try {
      final response = await http.get(url);
      if (response.statusCode == 200) {
        return json.decode(response.body) as Map<String, dynamic>;
      }
    } catch (e) {
      debugPrint('Error fetching profile: $e');
    }
    return null;
  }

  /// Danh sách phim yêu thích từ server
  Future<List<Movie>> getFavorites(int userId) async {
    final url = Uri.parse('$baseUrl/users/$userId/favorites');
    try {
      final response = await http.get(url);
      if (response.statusCode == 200) {
        final List<dynamic> list = json.decode(response.body);
        return list.map((json) => Movie.fromJson(json)).toList();
      }
    } catch (e) {
      debugPrint('Error fetching favorites: $e');
    }
    return [];
  }

  /// Thêm/bỏ phim yêu thích trên server
  Future<bool> setFavorite(int userId, int movieId, bool isFavorite) async {
    final url = Uri.parse('$baseUrl/users/$userId/favorites');
    try {
      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'movieId': movieId, 'isFavorite': isFavorite}),
      );
      return response.statusCode == 200;
    } catch (e) {
      debugPrint('Error setting favorite: $e');
      return false;
    }
  }

  /// Lịch sử đánh giá của user từ server (interactions_log)
  Future<List<Map<String, dynamic>>> getRatingsHistory(int userId) async {
    final url = Uri.parse('$baseUrl/users/$userId/ratings');
    try {
      final response = await http.get(url);
      if (response.statusCode == 200) {
        return (json.decode(response.body) as List<dynamic>)
            .cast<Map<String, dynamic>>();
      }
    } catch (e) {
      debugPrint('Error fetching ratings history: $e');
    }
    return [];
  }

  /// Cập nhật thể loại yêu thích (dùng cho Cold-Start theo genres)
  Future<bool> savePreferences(int userId, List<String> genres) async {
    final url = Uri.parse('$baseUrl/users/$userId/preferences');
    try {
      final response = await http.put(
        url,
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'genres': genres}),
      );
      return response.statusCode == 200;
    } catch (e) {
      debugPrint('Error saving preferences: $e');
      return false;
    }
  }

  /// Lấy chuỗi detail lỗi từ FastAPI response
  String _detailFrom(http.Response response) {
    try {
      final data = json.decode(response.body);
      if (data is Map && data['detail'] != null) {
        return data['detail'].toString();
      }
    } catch (_) {}
    return 'Lỗi máy chủ (${response.statusCode})';
  }

  /// Lấy danh sách phim gợi ý cá nhân hóa cho user
  Future<List<Movie>> getRecommendations(int userId, {int limit = 10}) async {
    final url = Uri.parse('$baseUrl/recommendations/$userId?limit=$limit');
    try {
      final response = await http.get(url);
      if (response.statusCode == 200) {
        final Map<String, dynamic> data = json.decode(response.body);
        final List<dynamic> list = data['recommendations'];
        return list.map((json) => Movie.fromJson(json)).toList();
      } else {
        throw Exception('Failed to load recommendations');
      }
    } catch (e) {
      debugPrint('Error fetching recommendations: $e');
      return [];
    }
  }

  /// Lấy danh sách phim phổ biến nhất (Popularity Recommender)
  Future<List<Movie>> getPopularMovies({int limit = 10}) async {
    final url = Uri.parse('$baseUrl/movies?limit=$limit');
    try {
      final response = await http.get(url);
      if (response.statusCode == 200) {
        final Map<String, dynamic> data = json.decode(response.body);
        final List<dynamic> list = data['results'];
        return list.map((json) => Movie.fromJson(json)).toList();
      } else {
        throw Exception('Failed to load popular movies');
      }
    } catch (e) {
      debugPrint('Error fetching popular movies: $e');
      return [];
    }
  }

  /// Tìm kiếm phim theo tiêu đề hoặc thể loại
  Future<List<Movie>> searchMovies(String query) async {
    final url = Uri.parse('$baseUrl/movies/search?q=${Uri.encodeComponent(query)}');
    try {
      final response = await http.get(url);
      if (response.statusCode == 200) {
        final List<dynamic> list = json.decode(response.body);
        return list.map((json) => Movie.fromJson(json)).toList();
      } else {
        throw Exception('Failed to search movies');
      }
    } catch (e) {
      debugPrint('Error searching movies: $e');
      return [];
    }
  }

  /// Gửi đánh giá sao (Explicit Feedback)
  Future<bool> sendRating(int userId, int movieId, double rating) async {
    final url = Uri.parse('$baseUrl/interactions/rating');
    try {
      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: json.encode({
          'userId': userId,
          'movieId': movieId,
          'rating': rating,
        }),
      );
      return response.statusCode == 200;
    } catch (e) {
      debugPrint('Error sending rating: $e');
      return false;
    }
  }

  /// Gửi tương tác yêu thích (Implicit Feedback)
  Future<bool> sendFavorite(int userId, int movieId, bool isFavorite) async {
    final url = Uri.parse('$baseUrl/interactions/favorite');
    try {
      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: json.encode({
          'userId': userId,
          'movieId': movieId,
          'isFavorite': isFavorite,
        }),
      );
      return response.statusCode == 200;
    } catch (e) {
      debugPrint('Error sending favorite: $e');
      return false;
    }
  }

  /// Gửi lịch sử xem phim (Implicit Feedback)
  Future<bool> sendWatchHistory(int userId, int movieId, int watchDuration, int totalDuration) async {
    final url = Uri.parse('$baseUrl/interactions/watch');
    try {
      final response = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: json.encode({
          'userId': userId,
          'movieId': movieId,
          'watchDurationSeconds': watchDuration,
          'totalDurationSeconds': totalDuration,
        }),
      );
      return response.statusCode == 200;
    } catch (e) {
      debugPrint('Error sending watch history: $e');
      return false;
    }
  }

  /// Gửi heartbeat tiến độ xem (player gọi mỗi ~5 giây) — upsert trên server.
  Future<bool> sendWatchProgress(int userId, int movieId, int positionSeconds, int durationSeconds) async {
    final url = Uri.parse('$baseUrl/watch/progress');
    try {
      final response = await http.put(
        url,
        headers: {'Content-Type': 'application/json'},
        body: json.encode({
          'userId': userId,
          'movieId': movieId,
          'positionSeconds': positionSeconds,
          'durationSeconds': durationSeconds,
        }),
      );
      return response.statusCode == 200;
    } catch (e) {
      debugPrint('Error sending watch progress: $e');
      return false;
    }
  }

  /// Danh sách phim đang xem dở (hàng "Tiếp tục xem" trên Home).
  Future<List<WatchProgress>> getContinueWatching(int userId) async {
    final url = Uri.parse('$baseUrl/watch/progress/$userId');
    try {
      final response = await http.get(url);
      if (response.statusCode == 200) {
        final List<dynamic> list = json.decode(response.body);
        return list.map((json) => WatchProgress.fromJson(json)).toList();
      }
    } catch (e) {
      debugPrint('Error fetching continue watching: $e');
    }
    return [];
  }

  /// Tiến độ xem của 1 phim (để player seek đúng vị trí khi mở lại).
  /// Trả về null nếu phim chưa từng xem.
  Future<Map<String, dynamic>?> getWatchProgress(int userId, int movieId) async {
    final url = Uri.parse('$baseUrl/watch/progress/$userId/$movieId');
    try {
      final response = await http.get(url);
      if (response.statusCode == 200) {
        return json.decode(response.body) as Map<String, dynamic>;
      }
    } catch (e) {
      debugPrint('Error fetching watch progress: $e');
    }
    return null;
  }

  /// Xoá phim khỏi hàng "Tiếp tục xem".
  Future<bool> removeContinueWatching(int userId, int movieId) async {
    final url = Uri.parse('$baseUrl/watch/progress/$userId/$movieId');
    try {
      final response = await http.delete(url);
      return response.statusCode == 200;
    } catch (e) {
      debugPrint('Error removing continue watching: $e');
      return false;
    }
  }
}
