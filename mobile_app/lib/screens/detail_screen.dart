import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter_rating_bar/flutter_rating_bar.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/movie.dart';
import '../services/api_service.dart';
import '../constants/app_colors.dart';
import 'player_screen.dart';

class DetailScreen extends StatefulWidget {
  final Movie movie;
  final int userId;

  const DetailScreen({
    super.key,
    required this.movie,
    required this.userId,
  });

  @override
  State<DetailScreen> createState() => _DetailScreenState();
}

class _DetailScreenState extends State<DetailScreen> {
  final ApiService _apiService = ApiService();
  bool _isFavorite = false;
  double _userRating = 0.0;
  bool _isSubmitting = false;

  @override
  void initState() {
    super.initState();
    _checkInitialState();
  }

  Future<void> _checkInitialState() async {
    // Đồng bộ trạng thái yêu thích + đánh giá đã vote từ server (theo tài khoản)
    final results = await Future.wait([
      _apiService.getFavorites(widget.userId),
      _apiService.getRatingsHistory(widget.userId),
    ]);

    final favs = results[0] as List<Movie>;
    final ratings = results[1] as List<Map<String, dynamic>>;

    double userRating = 0.0;
    for (final r in ratings) {
      if (r['movieId'] == widget.movie.movieId) {
        userRating = (r['rating'] as num).toDouble();
        break;
      }
    }

    if (mounted) {
      setState(() {
        _isFavorite = favs.any((m) => m.movieId == widget.movie.movieId);
        _userRating = userRating;
      });
    }
  }

  void _toggleFavorite() async {
    setState(() {
      _isFavorite = !_isFavorite;
    });

    final ok = await _apiService.setFavorite(
      widget.userId,
      widget.movie.movieId,
      _isFavorite,
    );

    if (!ok && mounted) {
      setState(() {
        _isFavorite = !_isFavorite;
      });
    }

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(ok
              ? (_isFavorite ? 'Đã thêm vào Phim yêu thích ❤️' : 'Đã bỏ yêu thích 💔')
              : 'Không thể đồng bộ yêu thích lên máy chủ'),
          backgroundColor: ok ? (_isFavorite ? Colors.pinkAccent : Colors.grey) : Colors.redAccent,
          duration: const Duration(seconds: 2),
        ),
      );
    }
  }

  void _submitRating(double rating) async {
    setState(() {
      _userRating = rating;
      _isSubmitting = true;
    });

    final prefs = await SharedPreferences.getInstance();
    List<String> ratings = prefs.getStringList('ratings_history_${widget.userId}') ?? [];
    // Cập nhật thay vì thêm trùng: mỗi phim chỉ giữ 1 bản đánh giá mới nhất
    ratings.removeWhere((s) {
      try {
        return json.decode(s)['movieId'] == widget.movie.movieId;
      } catch (_) {
        return false;
      }
    });
    ratings.add(json.encode({
      'movieId': widget.movie.movieId,
      'title': widget.movie.title,
      'rating': rating,
      'timestamp': DateTime.now().toIso8601String(),
    }));
    await prefs.setStringList('ratings_history_${widget.userId}', ratings);

    await _apiService.sendRating(
      widget.userId,
      widget.movie.movieId,
      rating,
    );

    setState(() {
      _isSubmitting = false;
    });

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Đã gửi đánh giá $rating sao ⭐ cho hệ thống MLOps!'),
          backgroundColor: AppColors.success,
          duration: const Duration(seconds: 2),
        ),
      );
    }
  }

  void _openPlayer() async {
    final changed = await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => PlayerScreen(movie: widget.movie, userId: widget.userId),
      ),
    );
    // Xem xong (hoặc xem dở rồi quay lại) → làm mới trạng thái đã đánh giá
    if (changed == true && mounted) {
      await _checkInitialState();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            expandedHeight: 300,
            pinned: true,
            backgroundColor: AppColors.appBarBackground,
            flexibleSpace: FlexibleSpaceBar(
              title: Text(
                widget.movie.title,
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  shadows: [Shadow(blurRadius: 10, color: Colors.black)],
                ),
              ),
              background: Stack(
                fit: StackFit.expand,
                children: [
                  CachedNetworkImage(
                    imageUrl: widget.movie.posterPath,
                    fit: BoxFit.cover,
                    errorWidget: (context, url, error) => Image.network(
                      'https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=500',
                      fit: BoxFit.cover,
                    ),
                  ),
                  Container(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          Colors.white.withValues(alpha: 0.7),
                          Colors.transparent,
                          AppColors.background.withValues(alpha: 0.9),
                        ],
                        stops: const [0.0, 0.4, 1.0],
                      ),
                    ),
                  ),
                ],
              ),
            ),
            actions: [
              IconButton(
                icon: Icon(
                  _isFavorite ? Icons.favorite : Icons.favorite_border,
                  color: _isFavorite ? AppColors.favorite : AppColors.textSecondary,
                ),
                onPressed: _toggleFavorite,
              ),
            ],
          ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Thể loại
                  Wrap(
                    spacing: 8,
                    children: widget.movie.genres.split('|').map((genre) {
                      return Chip(
                        label: Text(genre.trim(), style: const TextStyle(color: AppColors.primary, fontSize: 12)),
                        backgroundColor: AppColors.cardBackground,
                      );
                    }).toList(),
                  ),

                  const SizedBox(height: 16),

                  // Nút Xem Phim — mở Player (mô phỏng) với cơ chế Resume
                  SizedBox(
                    width: double.infinity,
                    height: 48,
                    child: ElevatedButton.icon(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.primary,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                      ),
                      icon: const Icon(Icons.play_arrow, color: Colors.white),
                      label: const Text(
                        '▶ Xem Phim (Tiếp tục từ vị trí đã xem)',
                        style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                      ),
                      onPressed: _openPlayer,
                    ),
                  ),

                  const SizedBox(height: 24),

                  // Đánh Giá Của Bạn (Explicit Feedback Loop)
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: AppColors.cardBackground,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Column(
                      children: [
                        const Text(
                          'Đánh giá của bạn (Explicit Feedback)',
                          style: TextStyle(color: AppColors.textPrimary, fontWeight: FontWeight.bold, fontSize: 16),
                        ),
                        const SizedBox(height: 12),
                        RatingBar.builder(
                          initialRating: _userRating,
                          minRating: 1,
                          direction: Axis.horizontal,
                          allowHalfRating: true,
                          itemCount: 5,
                          itemPadding: const EdgeInsets.symmetric(horizontal: 4.0),
                          itemBuilder: (context, _) => const Icon(Icons.star, color: AppColors.ratingStar),
                          onRatingUpdate: _submitRating,
                        ),
                        if (_userRating > 0)
                          Padding(
                            padding: const EdgeInsets.only(top: 8),
                            child: Text(
                              'Bạn đã đánh giá $_userRating sao ⭐ (chạm để thay đổi)',
                              style: const TextStyle(color: AppColors.textSecondary, fontSize: 13),
                            ),
                          ),
                        if (_isSubmitting)
                          const Padding(
                            padding: EdgeInsets.all(8.0),
                            child: SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.primary),
                            ),
                          ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 24),

                  // Tóm tắt nội dung
                  const Text(
                    'Tóm Tắt Nội Dung',
                    style: TextStyle(color: AppColors.textPrimary, fontWeight: FontWeight.bold, fontSize: 18),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    widget.movie.overview,
                    style: const TextStyle(color: AppColors.textSecondary, height: 1.5, fontSize: 14),
                  ),

                  const SizedBox(height: 40),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
