import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../models/movie.dart';
import '../constants/app_colors.dart';

class MovieCard extends StatelessWidget {
  final Movie movie;
  final VoidCallback onTap;
  final double width;
  final double height;

  const MovieCard({
    super.key,
    required this.movie,
    required this.onTap,
    this.width = 130,
    this.height = 190,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: width,
        margin: const EdgeInsets.only(right: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: CachedNetworkImage(
                imageUrl: movie.posterPath,
                width: width,
                height: height,
                fit: BoxFit.cover,
                placeholder: (context, url) => Container(
                  width: width,
                  height: height,
                  color: AppColors.cardBackground,
                ),
                errorWidget: (context, url, error) => Image.network(
                  'https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=500',
                  width: width,
                  height: height,
                  fit: BoxFit.cover,
                ),
              ),
            ),
            const SizedBox(height: 8),
            Text(
              movie.title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontWeight: FontWeight.bold,
                fontSize: 14,
                height: 1.2,
                color: AppColors.textPrimary,
              ),
            ),
            const SizedBox(height: 2),
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.star, color: AppColors.ratingStar, size: 14),
                const SizedBox(width: 4),
                Text(
                  movie.voteAverage > 0 ? movie.voteAverage.toStringAsFixed(1) : '7.0',
                  style: const TextStyle(
                    fontSize: 12,
                    height: 1.2,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
