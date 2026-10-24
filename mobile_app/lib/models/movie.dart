class Movie {
  final int movieId;
  final String title;
  final String genres;
  final String posterPath;
  final String overview;
  final double voteAverage;
  final int runtimeMinutes;
  final String reason;
  final double? predictedRating;

  Movie({
    required this.movieId,
    required this.title,
    required this.genres,
    required this.posterPath,
    required this.overview,
    required this.voteAverage,
    this.runtimeMinutes = 100,
    this.reason = '',
    this.predictedRating,
  });

  factory Movie.fromJson(Map<String, dynamic> json) {
    double number(dynamic value, double fallback) {
      final parsed = value is num
          ? value.toDouble()
          : double.tryParse('$value');
      return parsed != null && parsed.isFinite ? parsed : fallback;
    }

    final runtime = number(json['runtime_minutes'], 100).toInt();
    return Movie(
      movieId: number(json['movieId'], 0).toInt(),
      title: json['title'] ?? 'Chưa có tên phim',
      genres: json['genres'] ?? '',
      posterPath: json['poster_path'] ?? json['posterPath'] ?? '',
      overview: json['overview'] ?? 'Không có tóm tắt.',
      voteAverage: number(json['vote_average'] ?? json['voteAverage'], 0),
      runtimeMinutes: runtime > 0 ? runtime : 100,
      reason: json['reason'] as String? ?? '',
      predictedRating: (json['predicted_rating'] as num?)?.toDouble(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'movieId': movieId,
      'title': title,
      'genres': genres,
      'poster_path': posterPath,
      'overview': overview,
      'vote_average': voteAverage,
      'runtime_minutes': runtimeMinutes,
      'reason': reason,
      'predicted_rating': predictedRating,
    };
  }
}
