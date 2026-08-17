import 'dart:async';
import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../models/movie.dart';
import '../services/api_service.dart';
import '../constants/app_colors.dart';

/// Màn hình xem phim mô phỏng (Simulated Player) theo chuẩn FPT Play/Netflix:
/// - Tải vị trí xem dở từ server → banner "Tiếp tục xem từ phút X".
/// - Phát mô phỏng bằng Timer (1 giây = 1 giây phim).
/// - Gửi heartbeat tiến độ mỗi 5 giây (PUT /api/watch/progress).
/// - Đạt 95% thời lượng → tự đánh dấu xem xong (server quy đổi rating 5.0
///   + online update để gợi ý cá nhân hóa ngay).
///
/// Nếu sau này có URL video thật, chỉ cần thay lõi Timer bằng video_player;
/// toàn bộ quy trình heartbeat/resume vẫn giữ nguyên.
class PlayerScreen extends StatefulWidget {
  final Movie movie;
  final int userId;

  const PlayerScreen({super.key, required this.movie, required this.userId});

  @override
  State<PlayerScreen> createState() => _PlayerScreenState();
}

class _PlayerScreenState extends State<PlayerScreen> {
  final ApiService _apiService = ApiService();

  late int _totalDuration; // tổng thời lượng (giây)
  int _position = 0;
  bool _isPlaying = true;
  bool _finished = false;

  // Banner resume: hiện khi có vị trí xem dở trong khoảng 5% – 95%
  bool _showResumeBanner = false;
  int _resumePosition = 0;

  Timer? _tick;
  int _heartbeatCount = 0;

  static const _finishRatio = 0.95; // ngưỡng "xem xong" (đồng bộ server)
  static const _heartbeatEveryTicks = 5; // gửi tiến độ mỗi 5 giây

  @override
  void initState() {
    super.initState();
    _totalDuration = widget.movie.runtimeMinutes * 60;
    _loadResumePosition();
  }

  @override
  void dispose() {
    _tick?.cancel();
    _flushProgress(); // lưu vị trí cuối trước khi rời màn hình
    super.dispose();
  }

  /// Tải vị trí xem dở từ server; nếu phim đang dở (5%–95%) thì seek đúng chỗ
  /// và hiện banner "Tiếp tục xem".
  Future<void> _loadResumePosition() async {
    final saved = await _apiService.getWatchProgress(widget.userId, widget.movie.movieId);
    if (saved == null) return;
    final ratio = (saved['ratio'] ?? 0.0).toDouble();
    final position = (saved['position_seconds'] ?? 0) as int;

    if (!mounted) return;
    if (ratio >= 0.05 && ratio < _finishRatio) {
      setState(() {
        _position = position;
        _resumePosition = position;
        _showResumeBanner = true;
      });
    }
    _startTicking();
  }

  void _startTicking() {
    _tick?.cancel();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) => _onTick());
  }

  void _onTick() {
    if (!_isPlaying || _finished) return;
    setState(() {
      _position++;
    });

    // Heartbeat: gửi tiến độ mỗi 5 giây (fire-and-forget)
    _heartbeatCount++;
    if (_heartbeatCount >= _heartbeatEveryTicks) {
      _heartbeatCount = 0;
      _sendProgress();
    }

    // Xem xong (>= 95%) → gửi lần cuối + thông báo
    if (_position >= (_totalDuration * _finishRatio).round()) {
      _onFinished();
    }
  }

  /// Gửi tiến độ hiện tại lên server (không chặn UI).
  void _sendProgress() {
    _apiService.sendWatchProgress(
      widget.userId,
      widget.movie.movieId,
      _position,
      _totalDuration,
    );
  }

  void _flushProgress() {
    if (_position > 0 && !_finished) {
      _apiService.sendWatchProgress(
        widget.userId,
        widget.movie.movieId,
        _position,
        _totalDuration,
      );
    }
  }

  Future<void> _onFinished() async {
    _finished = true;
    _tick?.cancel();
    await _apiService.sendWatchProgress(
      widget.userId,
      widget.movie.movieId,
      _totalDuration,
      _totalDuration,
    );
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('✅ Bạn đã xem xong — hệ thống đã ghi nhận và cập nhật gợi ý!'),
        backgroundColor: AppColors.success,
      ),
    );
    // Trả true để Home biết cần refresh hàng "Tiếp tục xem"
    Navigator.pop(context, true);
  }

  String _format(int seconds) {
    final m = seconds ~/ 60;
    final s = seconds % 60;
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  void _resumeFromSaved() {
    setState(() {
      _position = _resumePosition;
      _showResumeBanner = false;
    });
  }

  void _restartFromBeginning() {
    setState(() {
      _position = 0;
      _showResumeBanner = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final progress = (_totalDuration == 0) ? 0.0 : (_position / _totalDuration).clamp(0.0, 1.0);

    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        fit: StackFit.expand,
        children: [
          // Nền poster mờ
          CachedNetworkImage(
            imageUrl: widget.movie.posterPath,
            fit: BoxFit.cover,
            color: Colors.black.withValues(alpha: 0.65),
            colorBlendMode: BlendMode.darken,
            placeholder: (context, url) => Container(color: Colors.black),
            errorWidget: (context, url, error) => Container(color: Colors.black),
          ),

          // Lớp nội dung
          SafeArea(
            child: Column(
              children: [
                // AppBar đơn giản
                Row(
                  children: [
                    IconButton(
                      icon: const Icon(Icons.arrow_back, color: Colors.white),
                      onPressed: () => Navigator.pop(context),
                    ),
                    Expanded(
                      child: Text(
                        'Đang phát: ${widget.movie.title}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                          fontSize: 15,
                        ),
                      ),
                    ),
                  ],
                ),

                const Spacer(),

                // Banner Resume (FPT Play style)
                if (_showResumeBanner) ...[
                  Container(
                    margin: const EdgeInsets.all(16),
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.black.withValues(alpha: 0.75),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Column(
                      children: [
                        Text(
                          'Bạn đã xem đến phút ${_resumePosition ~/ 60} — tiếp tục nhé!',
                          textAlign: TextAlign.center,
                          style: const TextStyle(color: Colors.white, fontSize: 15),
                        ),
                        const SizedBox(height: 12),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            ElevatedButton(
                              style: ElevatedButton.styleFrom(backgroundColor: AppColors.primary),
                              onPressed: _resumeFromSaved,
                              child: const Text('▶ Tiếp tục xem', style: TextStyle(color: Colors.white)),
                            ),
                            const SizedBox(width: 12),
                            TextButton(
                              onPressed: _restartFromBeginning,
                              child: const Text('Xem từ đầu', style: TextStyle(color: Colors.white70)),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 8),
                ],

                // Điều khiển trung tâm: play/pause
                _finished
                    ? const SizedBox.shrink()
                    : IconButton(
                        iconSize: 72,
                        icon: Icon(
                          _isPlaying ? Icons.pause_circle_filled : Icons.play_circle_fill,
                          color: Colors.white.withValues(alpha: 0.9),
                        ),
                        onPressed: () {
                          setState(() => _isPlaying = !_isPlaying);
                        },
                      ),

                const SizedBox(height: 24),

                // Thanh tiến độ + thời gian
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Column(
                    children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(4),
                        child: LinearProgressIndicator(
                          value: progress,
                          minHeight: 6,
                          backgroundColor: Colors.white24,
                          color: AppColors.primary,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(_format(_position),
                              style: const TextStyle(color: Colors.white70, fontSize: 12)),
                          Text('${(progress * 100).round()}%',
                              style: const TextStyle(color: Colors.white70, fontSize: 12)),
                          Text(_format(_totalDuration),
                              style: const TextStyle(color: Colors.white70, fontSize: 12)),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
