import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../models/movie.dart';
import '../models/recommendation_result.dart';
import '../models/watch_progress.dart';
import '../services/api_service.dart';
import '../constants/app_colors.dart';
import '../widgets/movie_card.dart';
import '../widgets/empty_state.dart';
import '../widgets/error_state.dart';
import 'detail_screen.dart';

class HomeScreen extends StatefulWidget {
  final int userId;
  final String username;
  final int refreshToken;
  final ApiService? apiService;
  const HomeScreen({
    super.key,
    required this.userId,
    required this.username,
    this.refreshToken = 0,
    this.apiService,
  });
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late final ApiService _apiService;
  RecommendationResult? _result;
  List<Movie> _popular = [];
  List<WatchProgress> _continuing = [];
  List<String> _genres = [];
  bool _loading = true;
  bool _refreshing = false;
  String? _error;
  int _requestId = 0;
  int? _loadedVersion;
  bool _explore = false;

  @override
  void initState() {
    super.initState();
    _apiService = widget.apiService ?? ApiService();
    _loadData();
  }

  @override
  void didUpdateWidget(covariant HomeScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.userId != oldWidget.userId) {
      _result = null;
      _loadedVersion = null;
      _loadData();
    } else if (widget.refreshToken != oldWidget.refreshToken &&
        _loadedVersion != ApiService.dataVersion(widget.userId)) {
      _loadData(refreshPopular: false);
    }
  }

  Future<void> _loadData({bool refreshPopular = true}) async {
    final requestId = ++_requestId;
    final version = ApiService.dataVersion(widget.userId);
    final hasContent = _result != null;
    setState(() {
      _loading = !hasContent;
      _refreshing = hasContent;
      _error = null;
    });
    try {
      final values = await Future.wait<dynamic>([
        _apiService.getRecommendationResult(widget.userId, explore: _explore),
        refreshPopular || !hasContent
            ? _apiService.getPopularMovies()
            : Future.value(_popular),
        _apiService.getContinueWatching(widget.userId),
        _apiService.getProfile(widget.userId),
      ]);
      if (!mounted || requestId != _requestId) return;
      setState(() {
        _result = values[0] as RecommendationResult;
        _popular = values[1] as List<Movie>;
        _continuing = values[2] as List<WatchProgress>;
        _genres = List<String>.from((values[3] as Map)['genres'] ?? []);
        _loading = false;
        _refreshing = false;
        _loadedVersion = version;
      });
    } catch (e) {
      if (!mounted || requestId != _requestId) return;
      setState(() {
        _error = e.toString();
        _loading = false;
        _refreshing = false;
      });
      if (hasContent) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Chưa cập nhật được trang chủ: $e')),
        );
      }
    }
  }

  Future<void> _openDetail(Movie movie) async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => DetailScreen(
          movie: movie,
          userId: widget.userId,
          apiService: _apiService,
        ),
      ),
    );
    if (mounted && _loadedVersion != ApiService.dataVersion(widget.userId)) {
      await _loadData(refreshPopular: false);
    }
  }

  Widget _heading(String text) => Padding(
    padding: const EdgeInsets.fromLTRB(16, 24, 16, 12),
    child: Text(
      text,
      style: const TextStyle(fontSize: 19, fontWeight: FontWeight.bold),
    ),
  );

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: AppColors.background,
    appBar: AppBar(
      title: Text('MovieRS · ${widget.username}'),
      actions: [
        IconButton(
          tooltip: 'Làm mới gợi ý',
          onPressed: _loading || _refreshing ? null : () => _loadData(),
          icon: _refreshing
              ? const SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.refresh),
        ),
      ],
    ),
    body: _loading
        ? const Center(child: CircularProgressIndicator())
        : _error != null && _result == null
        ? ErrorStateWidget(errorMessage: _error!, onRetry: _loadData)
        : RefreshIndicator(
            onRefresh: () => _loadData(),
            child: ListView(
              children: [
                Container(
                  margin: const EdgeInsets.all(16),
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    color: AppColors.cardBackground,
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Khám phá phim theo sở thích của bạn',
                        style: TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 21,
                        ),
                      ),
                      const SizedBox(height: 10),
                      Text(
                        _result!.explanation,
                        style: const TextStyle(
                          height: 1.5,
                          color: AppColors.textSecondary,
                        ),
                      ),
                      const SizedBox(height: 10),
                      Text(
                        '${_result!.historyCount} phim đã tương tác · ${_result!.candidateCount} ứng viên chưa tương tác',
                        style: const TextStyle(
                          fontSize: 12,
                          color: AppColors.textSecondary,
                        ),
                      ),
                      if (_genres.isNotEmpty) ...[
                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 6,
                          children: _genres
                              .map((g) => Chip(label: Text(g)))
                              .toList(),
                        ),
                      ],
                    ],
                  ),
                ),
                _heading('Dành cho bạn'),
                SwitchListTile(
                  title: const Text('Khám phá đa dạng'),
                  subtitle: const Text(
                    'Bật để giảm lặp thể loại. Thứ tự phim có thể thay đổi.',
                  ),
                  value: _explore,
                  onChanged: (value) {
                    _explore = value;
                    _loadData(refreshPopular: false);
                  },
                ),
                if (_result!.movies.isEmpty)
                  const EmptyStateWidget(
                    icon: Icons.movie_outlined,
                    title: 'Chưa có phim phù hợp',
                    subtitle:
                        'Thử thay đổi sở thích trong Hồ sơ hoặc khám phá danh sách bên dưới.',
                  )
                else
                  ..._result!.movies.asMap().entries.map(
                    (entry) => _recommendationTile(entry.value, entry.key + 1),
                  ),
                if (_continuing.isNotEmpty) ...[
                  _heading('Tiếp tục trải nghiệm'),
                  const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 16),
                    child: Text(
                      'Trình phát mô phỏng để minh họa phản hồi và tiếp tục xem.',
                      style: TextStyle(
                        fontSize: 12,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ),
                  ..._continuing.map(
                    (item) => ListTile(
                      leading: const Icon(Icons.play_circle_outline),
                      title: Text(
                        item.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      subtitle: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${item.positionLabel} · ${(item.ratio * 100).round()}%',
                          ),
                          LinearProgressIndicator(
                            value: item.ratio.clamp(0, 1),
                          ),
                        ],
                      ),
                      onTap: () async {
                        try {
                          final movie = await _apiService.getMovie(
                            item.movieId,
                          );
                          if (mounted) await _openDetail(movie);
                        } catch (e) {
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(content: Text(e.toString())),
                            );
                          }
                        }
                      },
                      trailing: IconButton(
                        icon: const Icon(Icons.close),
                        tooltip: 'Bỏ khỏi tiếp tục xem',
                        onPressed: () async {
                          final ok = await _apiService.removeContinueWatching(
                            widget.userId,
                            item.movieId,
                          );
                          if (!context.mounted) return;
                          if (ok) {
                            setState(
                              () => _continuing.removeWhere(
                                (v) => v.movieId == item.movieId,
                              ),
                            );
                          } else {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text(
                                  'Chưa xóa được tiến độ. Vui lòng thử lại.',
                                ),
                              ),
                            );
                          }
                        },
                      ),
                    ),
                  ),
                ],
                _heading('Được cộng đồng đánh giá cao'),
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 16),
                  child: Text(
                    'Xếp hạng từ dữ liệu huấn luyện, có điều chỉnh theo số lượt đánh giá.',
                    style: TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 12,
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  height: 250,
                  child: ListView.builder(
                    scrollDirection: Axis.horizontal,
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    itemCount: _popular.length,
                    itemBuilder: (_, i) => MovieCard(
                      movie: _popular[i],
                      onTap: () => _openDetail(_popular[i]),
                    ),
                  ),
                ),
                const SizedBox(height: 24),
              ],
            ),
          ),
  );

  Widget _recommendationTile(Movie movie, int rank) => Card(
    margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
    color: AppColors.cardBackground,
    child: InkWell(
      onTap: () => _openDetail(movie),
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Text(
              '$rank',
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(width: 12),
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: CachedNetworkImage(
                imageUrl: movie.posterPath,
                width: 60,
                height: 90,
                fit: BoxFit.cover,
                errorWidget: (_, url, error) => const SizedBox(
                  width: 60,
                  height: 90,
                  child: Icon(Icons.movie_outlined),
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    movie.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    movie.genres,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 12),
                  ),
                  if (movie.reason.isNotEmpty) ...[
                    const SizedBox(height: 6),
                    Text(
                      movie.reason,
                      style: const TextStyle(
                        fontSize: 12,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    ),
  );
}
