import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../models/movie.dart';
import '../services/api_service.dart';
import '../constants/app_colors.dart';
import '../widgets/empty_state.dart';
import '../widgets/error_state.dart';
import 'detail_screen.dart';

class FavoritesScreen extends StatefulWidget {
  final int userId;
  final int refreshToken;

  const FavoritesScreen({
    super.key,
    required this.userId,
    this.refreshToken = 0,
  });

  @override
  State<FavoritesScreen> createState() => _FavoritesScreenState();
}

class _FavoritesScreenState extends State<FavoritesScreen> {
  final ApiService _apiService = ApiService();
  List<Movie> _favoriteMovies = [];
  bool _isLoading = true;
  String? _error;
  int? _loadedVersion;

  @override
  void didUpdateWidget(covariant FavoritesScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.userId != widget.userId ||
        (oldWidget.refreshToken != widget.refreshToken &&
            _loadedVersion != ApiService.dataVersion(widget.userId))) {
      _loadFavorites();
    }
  }

  @override
  void initState() {
    super.initState();
    _loadFavorites();
  }

  Future<void> _loadFavorites() async {
    final version = ApiService.dataVersion(widget.userId);
    setState(() {
      _isLoading = true;
      _error = null;
    });

    // Danh sách yêu thích đồng bộ từ server theo tài khoản
    try {
      final movies = await _apiService.getFavorites(widget.userId);

      if (mounted) {
        setState(() {
          _favoriteMovies = movies;
          _isLoading = false;
          _loadedVersion = version;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.appBarBackground,
        title: const Text(
          'Phim Yêu Thích',
          style: TextStyle(
            color: AppColors.textPrimary,
            fontWeight: FontWeight.bold,
          ),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: AppColors.primary),
            onPressed: _loadFavorites,
          ),
        ],
      ),
      body: _isLoading
          ? const Center(
              child: CircularProgressIndicator(color: AppColors.primary),
            )
          : _error != null
          ? ErrorStateWidget(errorMessage: _error!, onRetry: _loadFavorites)
          : _favoriteMovies.isEmpty
          ? const EmptyStateWidget(
              icon: Icons.favorite_border_rounded,
              title: 'Chưa có phim yêu thích',
              subtitle:
                  'Hãy bấm biểu tượng ❤️ trên trang chi tiết phim để lưu danh sách phim bạn yêu thích!',
            )
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _favoriteMovies.length,
              itemBuilder: (context, index) {
                final movie = _favoriteMovies[index];
                return Card(
                  color: AppColors.cardBackground,
                  margin: const EdgeInsets.only(bottom: 12),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: ListTile(
                    leading: ClipRRect(
                      borderRadius: BorderRadius.circular(6),
                      child: movie.posterPath.isNotEmpty
                          ? CachedNetworkImage(
                              imageUrl: movie.posterPath,
                              width: 45,
                              height: 65,
                              fit: BoxFit.cover,
                              errorWidget: (context, url, error) => Container(
                                width: 45,
                                height: 65,
                                color: Colors.grey[300],
                              ),
                            )
                          : Container(
                              width: 45,
                              height: 65,
                              color: Colors.grey[300],
                            ),
                    ),
                    title: Text(
                      movie.title,
                      style: const TextStyle(
                        fontWeight: FontWeight.bold,
                        color: AppColors.textPrimary,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    subtitle: Text(
                      movie.genres,
                      style: const TextStyle(
                        color: AppColors.primary,
                        fontSize: 12,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    trailing: const Icon(
                      Icons.favorite,
                      color: AppColors.favorite,
                    ),
                    onTap: () async {
                      await Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (context) =>
                              DetailScreen(movie: movie, userId: widget.userId),
                        ),
                      );
                      if (mounted &&
                          _loadedVersion !=
                              ApiService.dataVersion(widget.userId)) {
                        _loadFavorites();
                      }
                    },
                  ),
                );
              },
            ),
    );
  }
}
