import 'package:flutter/material.dart';
import '../models/movie.dart';
import '../services/api_service.dart';
import '../constants/app_colors.dart';
import '../widgets/empty_state.dart';
import 'detail_screen.dart';

class FavoritesScreen extends StatefulWidget {
  final int userId;

  const FavoritesScreen({super.key, required this.userId});

  @override
  State<FavoritesScreen> createState() => _FavoritesScreenState();
}

class _FavoritesScreenState extends State<FavoritesScreen> {
  final ApiService _apiService = ApiService();
  List<Movie> _favoriteMovies = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadFavorites();
  }

  Future<void> _loadFavorites() async {
    setState(() {
      _isLoading = true;
    });

    // Danh sách yêu thích đồng bộ từ server theo tài khoản
    final movies = await _apiService.getFavorites(widget.userId);

    if (mounted) {
      setState(() {
        _favoriteMovies = movies;
        _isLoading = false;
      });
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
          style: TextStyle(color: AppColors.textPrimary, fontWeight: FontWeight.bold),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: AppColors.primary),
            onPressed: _loadFavorites,
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator(color: AppColors.primary))
          : _favoriteMovies.isEmpty
              ? const EmptyStateWidget(
                  icon: Icons.favorite_border_rounded,
                  title: 'Chưa có phim yêu thích',
                  subtitle: 'Hãy bấm biểu tượng ❤️ trên trang chi tiết phim để lưu danh sách phim bạn yêu thích!',
                )
              : ListView.builder(
                  padding: const EdgeInsets.all(16),
                  itemCount: _favoriteMovies.length,
                  itemBuilder: (context, index) {
                    final movie = _favoriteMovies[index];
                    return Card(
                      color: AppColors.cardBackground,
                      margin: const EdgeInsets.only(bottom: 12),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      child: ListTile(
                        leading: ClipRRect(
                          borderRadius: BorderRadius.circular(6),
                          child: movie.posterPath.isNotEmpty
                              ? Image.network(
                                  movie.posterPath,
                                  width: 45,
                                  height: 65,
                                  fit: BoxFit.cover,
                                  errorBuilder: (context, error, stackTrace) =>
                                      Container(width: 45, height: 65, color: Colors.grey[300]),
                                )
                              : Container(width: 45, height: 65, color: Colors.grey[300]),
                        ),
                        title: Text(
                          movie.title,
                          style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.textPrimary),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        subtitle: Text(
                          movie.genres,
                          style: const TextStyle(color: AppColors.primary, fontSize: 12),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        trailing: const Icon(Icons.favorite, color: AppColors.favorite),
                        onTap: () async {
                          await Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (context) => DetailScreen(
                                movie: movie,
                                userId: widget.userId,
                              ),
                            ),
                          );
                          _loadFavorites();
                        },
                      ),
                    );
                  },
                ),
    );
  }
}
