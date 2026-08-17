import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/movie.dart';
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

  const HomeScreen({super.key, required this.userId, required this.username});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final ApiService _apiService = ApiService();

  List<Movie> _recommendations = [];
  List<Movie> _popularMovies = [];
  List<WatchProgress> _continueWatching = [];
  List<String> _userGenres = [];
  bool _isLoading = true;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final prefs = await SharedPreferences.getInstance();
      final genres = prefs.getStringList('selected_genres') ?? [];

      // Chạy song song 3 luồng tải dữ liệu (mỗi future có kiểu riêng)
      final recsFuture = _apiService.getRecommendations(widget.userId);
      final popularFuture = _apiService.getPopularMovies(limit: 10);
      final continueFuture = _apiService.getContinueWatching(widget.userId);

      final recommendations = await recsFuture;
      final popularMovies = await popularFuture;
      final continueWatching = await continueFuture;

      setState(() {
        _recommendations = recommendations;
        _popularMovies = popularMovies;
        _continueWatching = continueWatching;
        _userGenres = genres;
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _errorMessage = e.toString();
        _isLoading = false;
      });
    }
  }

  /// Mở chi tiết phim; khi quay về thì refresh riêng hàng "Tiếp tục xem"
  /// (vì user có thể vừa xem xong một phim trong player).
  Future<void> _openDetail(Movie movie) async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => DetailScreen(movie: movie, userId: widget.userId),
      ),
    );
    if (!mounted) return;
    final updated = await _apiService.getContinueWatching(widget.userId);
    if (!mounted) return;
    setState(() => _continueWatching = updated);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.appBarBackground,
        elevation: 0,
        title: Row(
          children: [
            const Icon(Icons.movie_filter_rounded, color: AppColors.primary, size: 24),
            const SizedBox(width: 8),
            Text(
              'MovieRS (${widget.username})',
              style: const TextStyle(color: AppColors.textPrimary, fontWeight: FontWeight.bold, fontSize: 16),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: AppColors.primary),
            onPressed: _loadData,
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator(color: AppColors.primary))
          : _errorMessage != null
              ? ErrorStateWidget(errorMessage: _errorMessage!, onRetry: _loadData)
              : RefreshIndicator(
                  color: AppColors.primary,
                  backgroundColor: AppColors.cardBackground,
                  onRefresh: _loadData,
                  child: SingleChildScrollView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.symmetric(vertical: 16.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // SECTION 0: Tiếp Tục Xem (Continue Watching)
                        if (_continueWatching.isNotEmpty) ...[
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 16.0),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                const Text(
                                  '▶ Tiếp Tục Xem',
                                  style: TextStyle(
                                    fontSize: 18,
                                    fontWeight: FontWeight.bold,
                                    color: AppColors.textPrimary,
                                  ),
                                ),
                                const Flexible(
                                  child: Text(
                                    'Continue Watching',
                                    style: TextStyle(fontSize: 12, color: AppColors.primary),
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 12),
                          SizedBox(
                            height: 245,
                            child: ListView.builder(
                              padding: const EdgeInsets.only(left: 16),
                              scrollDirection: Axis.horizontal,
                              itemCount: _continueWatching.length,
                              itemBuilder: (context, index) {
                                final item = _continueWatching[index];
                                return _buildContinueCard(item);
                              },
                            ),
                          ),
                          const SizedBox(height: 20),
                        ],

                        // SECTION 1: Phim Phổ Biến (Popularity Recommender)
                        if (_popularMovies.isNotEmpty) ...[
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 16.0),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                const Text(
                                  '🔥 Phim Phổ Biến Nhất',
                                  style: TextStyle(
                                    fontSize: 18,
                                    fontWeight: FontWeight.bold,
                                    color: AppColors.textPrimary,
                                  ),
                                ),
                                const Flexible(
                                  child: Text(
                                    'Popularity',
                                    style: TextStyle(fontSize: 12, color: AppColors.primary),
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 12),
                          SizedBox(
                            height: 250,
                            child: ListView.builder(
                              padding: const EdgeInsets.only(left: 16),
                              scrollDirection: Axis.horizontal,
                              itemCount: _popularMovies.length,
                              itemBuilder: (context, index) {
                                final movie = _popularMovies[index];
                                return MovieCard(
                                  movie: movie,
                                  onTap: () => _openDetail(movie),
                                );
                              },
                            ),
                          ),
                          const SizedBox(height: 20),
                        ],

                        // SECTION 2: Thể loại yêu thích (Onboarding Chips)
                        if (_userGenres.isNotEmpty) ...[
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 16.0),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  '🎭 Thể loại bạn quan tâm',
                                  style: TextStyle(
                                    fontSize: 15,
                                    fontWeight: FontWeight.bold,
                                    color: AppColors.textPrimary,
                                  ),
                                ),
                                const SizedBox(height: 8),
                                SingleChildScrollView(
                                  scrollDirection: Axis.horizontal,
                                  child: Row(
                                    children: _userGenres.map((g) {
                                      return Container(
                                        margin: const EdgeInsets.only(right: 8),
                                        child: Chip(
                                          label: Text(g, style: const TextStyle(fontSize: 12, color: Colors.black)),
                                          backgroundColor: AppColors.primary,
                                        ),
                                      );
                                    }).toList(),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 24),
                        ],

                        // SECTION 3: Gợi ý Cá Nhân Hóa (AI SVD Model)
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 16.0),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              const Flexible(
                                child: Text(
                                  '🤖 Gợi Ý Cho Bạn (AI SVD)',
                                  style: TextStyle(
                                    fontSize: 18,
                                    fontWeight: FontWeight.bold,
                                    color: AppColors.primary,
                                  ),
                                ),
                              ),
                              IconButton(
                                icon: const Icon(Icons.info_outline, size: 20, color: AppColors.textSecondary),
                                onPressed: () {
                                  showDialog(
                                    context: context,
                                    builder: (context) => AlertDialog(
                                      backgroundColor: AppColors.cardBackground,
                                      title: const Text('Về Thuật Toán Gợi Ý', style: TextStyle(color: AppColors.primary)),
                                      content: const Text(
                                        'Danh sách phim này được tính toán bởi thuật toán SVD (Matrix Factorization) dựa trên tương tác của bạn và các người dùng tương tự.',
                                        style: TextStyle(color: AppColors.textSecondary),
                                      ),
                                      actions: [
                                        TextButton(
                                          onPressed: () => Navigator.pop(context),
                                          child: const Text('Đã hiểu', style: TextStyle(color: AppColors.primary)),
                                        ),
                                      ],
                                    ),
                                  );
                                },
                              ),
                            ],
                          ),
                        ),

                        const SizedBox(height: 8),

                        _recommendations.isEmpty
                            ? const EmptyStateWidget(
                                icon: Icons.movie_outlined,
                                title: 'Chưa có gợi ý cá nhân hóa',
                                subtitle: 'Hãy đánh giá vài bộ phim để mô hình AI SVD học sở thích của bạn!',
                              )
                            : ListView.builder(
                                shrinkWrap: true,
                                physics: const NeverScrollableScrollPhysics(),
                                padding: const EdgeInsets.symmetric(horizontal: 16.0),
                                itemCount: _recommendations.length,
                                itemBuilder: (context, index) {
                                  final movie = _recommendations[index];
                                  return _buildMovieTile(movie, rank: index + 1);
                                },
                              ),
                      ],
                    ),
                  ),
                ),
    );
  }

  /// Thẻ phim trong hàng "Tiếp tục xem" — poster + vị trí dừng + thanh tiến độ + nút xóa.
  Widget _buildContinueCard(WatchProgress item) {
    return SizedBox(
      width: 140,
      child: Padding(
        padding: const EdgeInsets.only(right: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            GestureDetector(
              onTap: () => _openDetail(
                Movie(
                  movieId: item.movieId,
                  title: item.title,
                  genres: item.genres,
                  posterPath: item.posterPath,
                  overview: '',
                  voteAverage: 0,
                  runtimeMinutes: item.runtimeMinutes,
                ),
              ),
              child: Stack(
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(10),
                    child: CachedNetworkImage(
                      imageUrl: item.posterPath,
                      width: 140,
                      height: 175,
                      fit: BoxFit.cover,
                      placeholder: (context, url) => Container(
                        width: 140,
                        height: 175,
                        color: AppColors.cardBackground,
                      ),
                      errorWidget: (context, url, error) => Container(
                        width: 140,
                        height: 175,
                        color: AppColors.cardBackground,
                        child: const Icon(Icons.movie_outlined, size: 40, color: Colors.grey),
                      ),
                    ),
                  ),
                  // Nút xóa nhanh ở góc trên phải
                  Positioned(
                    top: 6,
                    right: 6,
                    child: GestureDetector(
                      onTap: () async {
                        await _apiService.removeContinueWatching(widget.userId, item.movieId);
                        if (!mounted) return;
                        setState(() {
                          _continueWatching = _continueWatching
                              .where((e) => e.movieId != item.movieId)
                              .toList();
                        });
                      },
                      child: Container(
                        padding: const EdgeInsets.all(4),
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.65),
                          shape: BoxShape.circle,
                        ),
                        child: const Icon(Icons.close, size: 14, color: Colors.white70),
                      ),
                    ),
                  ),
                  // Progress badge & bar ở đáy poster
                  Positioned(
                    bottom: 0,
                    left: 0,
                    right: 0,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 8),
                          decoration: BoxDecoration(
                            color: Colors.black.withValues(alpha: 0.75),
                            borderRadius: const BorderRadius.vertical(bottom: Radius.circular(10)),
                          ),
                          child: Row(
                            children: [
                              const Icon(Icons.play_circle_fill, color: AppColors.primary, size: 14),
                              const SizedBox(width: 4),
                              Text(
                                item.positionLabel,
                                style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w500),
                              ),
                              const Spacer(),
                              Text(
                                '${(item.ratio * 100).round()}%',
                                style: const TextStyle(color: AppColors.primary, fontSize: 11, fontWeight: FontWeight.bold),
                              ),
                            ],
                          ),
                        ),
                        ClipRRect(
                          borderRadius: const BorderRadius.vertical(bottom: Radius.circular(10)),
                          child: LinearProgressIndicator(
                            value: item.ratio.clamp(0.0, 1.0),
                            backgroundColor: Colors.grey[800],
                            valueColor: const AlwaysStoppedAnimation<Color>(AppColors.primary),
                            minHeight: 3,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 6),
            Text(
              item.title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.bold,
                color: AppColors.textPrimary,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              item.genres.isNotEmpty ? item.genres.split(RegExp(r'[|,/]+')).first.trim() : 'Phim',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 11,
                color: AppColors.textSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMovieTile(Movie movie, {int? rank}) {
    return Card(
      color: AppColors.cardBackground,
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () => _openDetail(movie),
        child: Padding(
          padding: const EdgeInsets.all(12.0),
          child: Row(
            children: [
              if (rank != null) ...[
                Container(
                  width: 28,
                  alignment: Alignment.center,
                  child: Text(
                    '#$rank',
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      color: rank <= 3 ? AppColors.ratingStar : AppColors.textSecondary,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
              ],
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: CachedNetworkImage(
                  imageUrl: movie.posterPath,
                  width: 60,
                  height: 90,
                  fit: BoxFit.cover,
                  placeholder: (context, url) => Container(color: Colors.grey[300]),
                  errorWidget: (context, url, error) => Image.network(
                    'https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=500',
                    width: 60,
                    height: 90,
                    fit: BoxFit.cover,
                  ),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      movie.title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.bold,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      movie.genres,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 12, color: AppColors.primary),
                    ),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        const Icon(Icons.star, color: AppColors.ratingStar, size: 16),
                        const SizedBox(width: 4),
                        Text(
                          movie.voteAverage > 0 ? movie.voteAverage.toStringAsFixed(1) : '7.0',
                          style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: AppColors.textSecondary),
            ],
          ),
        ),
      ),
    );
  }
}
