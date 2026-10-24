import 'movie.dart';

/// Thông tin nguồn gợi ý giúp diễn đạt đúng trạng thái cá nhân hóa.
class RecommendationResult {
  final List<Movie> movies;
  final String strategy;
  final String stage;
  final int historyCount;
  final int candidateCount;

  const RecommendationResult({
    required this.movies,
    required this.strategy,
    required this.stage,
    required this.historyCount,
    required this.candidateCount,
  });

  factory RecommendationResult.fromJson(Map<String, dynamic> json) =>
      RecommendationResult(
        movies: (json['recommendations'] as List)
            .map((v) => Movie.fromJson(v))
            .toList(),
        strategy: json['strategy'] as String? ?? 'popularity',
        stage: json['stage'] as String? ?? 'cold_start',
        historyCount: (json['history_count'] as num?)?.toInt() ?? 0,
        candidateCount: (json['candidate_count'] as num?)?.toInt() ?? 0,
      );

  String get explanation {
    if (strategy == 'catalog_fallback') {
      return 'Đang khám phá danh mục. Chưa có mô hình để cá nhân hóa.';
    }
    if (strategy == 'hybrid_svd') {
      return 'Gợi ý kết hợp SVD với lịch sử tương tác và sở thích thể loại. '
          'Điểm dự đoán không phải xác suất bạn sẽ thích phim.';
    }
    if (strategy == 'genre_popularity') {
      return 'Gợi ý theo thể loại bạn quan tâm và điểm cộng đồng. '
          'Đánh giá vài phim để hệ thống hiểu sở thích rõ hơn.';
    }
    return 'Bạn đang bắt đầu với các phim được cộng đồng đánh giá cao. '
        'Chọn thể loại trong Hồ sơ hoặc đánh giá phim để cá nhân hóa.';
  }
}
