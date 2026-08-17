class Movie {
  final int movieId;
  final String title;
  final String genres;
  final String posterPath;
  final String overview;
  final double voteAverage;
  final int runtimeMinutes;

  Movie({
    required this.movieId,
    required this.title,
    required this.genres,
    required this.posterPath,
    required this.overview,
    required this.voteAverage,
    this.runtimeMinutes = 100,
  });

  factory Movie.fromJson(Map<String, dynamic> json) {
    return Movie(
      movieId: json['movieId'] ?? 0,
      title: json['title'] ?? 'Unknown Title',
      genres: json['genres'] ?? '',
      posterPath: json['poster_path'] ?? json['posterPath'] ?? '',
      overview: json['overview'] ?? 'Không có tóm tắt.',
      voteAverage: (json['vote_average'] ?? json['voteAverage'] ?? 0.0).toDouble(),
      runtimeMinutes: (json['runtime_minutes'] ?? 100) as int,
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
    };
  }
}
