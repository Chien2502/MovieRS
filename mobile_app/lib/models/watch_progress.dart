/// Tiến độ xem phim của user — dữ liệu hàng "Tiếp tục xem" (Continue Watching).
class WatchProgress {
  final int movieId;
  final String title;
  final String genres;
  final String posterPath;
  final int positionSeconds;
  final int durationSeconds;
  final double ratio;

  WatchProgress({
    required this.movieId,
    required this.title,
    required this.genres,
    required this.posterPath,
    required this.positionSeconds,
    required this.durationSeconds,
    required this.ratio,
  });

  factory WatchProgress.fromJson(Map<String, dynamic> json) {
    return WatchProgress(
      movieId: json['movieId'] ?? 0,
      title: json['title'] ?? 'Unknown Title',
      genres: json['genres'] ?? '',
      posterPath: json['poster_path'] ?? '',
      positionSeconds: (json['position_seconds'] ?? 0) as int,
      durationSeconds: (json['duration_seconds'] ?? 0) as int,
      ratio: (json['ratio'] ?? 0.0).toDouble(),
    );
  }

  /// Định dạng phút:giây (ví dụ 42:30) — hiển thị trên thẻ "Tiếp tục xem".
  String get positionLabel {
    final m = positionSeconds ~/ 60;
    final s = positionSeconds % 60;
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }
}
