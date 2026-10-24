import 'dart:async';
import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../models/movie.dart';
import '../services/api_service.dart';
import '../constants/app_colors.dart';

/// Trình phát mô phỏng để kiểm tra luồng phản hồi:
/// - Tải vị trí xem dở từ server → banner "Tiếp tục xem từ phút X".
/// - Phát mô phỏng bằng Timer (1 giây = 1 giây phim).
/// - Gửi heartbeat tiến độ mỗi 5 giây (PUT /api/watch/progress).
/// - Đạt 95% → ghi proxy hoàn thành, tách với sao người dùng chủ động nhập.
class PlayerScreen extends StatefulWidget {
  final Movie movie;
  final int userId;
  final ApiService? apiService;

  const PlayerScreen({
    super.key,
    required this.movie,
    required this.userId,
    this.apiService,
  });

  @override
  State<PlayerScreen> createState() => _PlayerScreenState();
}

class _PlayerScreenState extends State<PlayerScreen> {
  late final ApiService _apiService;

  late int _totalDuration; // tổng thời lượng (giây)
  int _position = 0;
  bool _isPlaying = true;
  bool _finished = false;
  bool _isSeeking = false;
  bool _wasPlayingBeforeSeek = false;
  bool _progressChanged = false;
  bool _isClosing = false;
  Future<bool> _pendingProgress = Future.value(true);
  String? _syncError;
  bool _resumeLoaded = false;

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
    _apiService = widget.apiService ?? ApiService();
    final runtimeMinutes = widget.movie.runtimeMinutes > 0
        ? widget.movie.runtimeMinutes
        : 100;
    _totalDuration = runtimeMinutes * 60;
    _loadResumePosition();
  }

  @override
  void dispose() {
    _tick?.cancel();
    if (!_isClosing) {
      _flushProgress(); // lưu vị trí cuối trước khi rời màn hình
    }
    super.dispose();
  }

  /// Tải vị trí xem dở từ server; nếu phim đang dở (5%–95%) thì seek đúng chỗ
  /// và hiện banner "Tiếp tục xem".
  Future<void> _loadResumePosition() async {
    try {
      final saved = await _apiService.getWatchProgress(
        widget.userId,
        widget.movie.movieId,
      );
      if (!mounted) return;

      if (saved != null) {
        final ratio = (saved['ratio'] ?? 0.0).toDouble();
        final position = ((saved['position_seconds'] ?? 0) as num).toInt();
        final savedDuration = ((saved['duration_seconds'] ?? 0) as num).toInt();

        if (savedDuration > 0) {
          _totalDuration = savedDuration;
        }

        if (ratio >= 0.05 && ratio < _finishRatio) {
          setState(() {
            _position = position.clamp(0, _totalDuration);
            _resumePosition = _position;
            _showResumeBanner = true;
          });
        }
      }
      _resumeLoaded = true;
      _startTicking();
    } catch (e) {
      if (mounted) {
        setState(() {
          _isPlaying = false;
          _syncError = e.toString();
        });
      }
    }
  }

  void _startTicking() {
    _tick?.cancel();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) => _onTick());
  }

  void _onTick() {
    if (!_isPlaying || _finished || _isSeeking) return;
    setState(() {
      _position = (_position + 1).clamp(0, _totalDuration);
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
  Future<bool> _sendProgress() {
    _progressChanged = true;
    final position = _position;
    _pendingProgress = _pendingProgress.then(
      (_) => _apiService.sendWatchProgress(
        widget.userId,
        widget.movie.movieId,
        position,
        _totalDuration,
      ),
    );
    return _pendingProgress;
  }

  void _flushProgress() {
    if (_position > 0 && !_finished) {
      _progressChanged = true;
      _sendProgress();
    }
  }

  void _onSeekStart(double value) {
    _wasPlayingBeforeSeek = _isPlaying;
    setState(() {
      _isSeeking = true;
      _isPlaying = false;
      _showResumeBanner = false;
    });
  }

  void _onSeekChanged(double value) {
    setState(() {
      _position = value.round().clamp(0, _totalDuration);
    });
  }

  Future<void> _onSeekEnd(double value) async {
    final newPosition = value.round().clamp(0, _totalDuration);
    setState(() {
      _position = newPosition;
      _isSeeking = false;
    });

    if (_position >= (_totalDuration * _finishRatio).round()) {
      await _onFinished();
      return;
    }

    await _sendProgress();

    if (!mounted) return;
    setState(() {
      _isPlaying = _wasPlayingBeforeSeek;
    });
  }

  Future<void> _onFinished() async {
    if (_finished) return;
    _finished = true;
    _tick?.cancel();
    _progressChanged = true;
    final ok = await _sendProgress();
    if (!mounted) return;
    if (!ok) {
      setState(() {
        _finished = false;
        _isPlaying = false;
        _syncError = 'Chưa lưu được tiến độ. Bấm thử lại để đồng bộ.';
      });
      _startTicking();
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text(
          'Đã ghi nhận hoàn thành mô phỏng. Bạn có thể đánh giá sao riêng.',
        ),
        backgroundColor: AppColors.success,
      ),
    );
    // Trả true để Home biết cần refresh hàng "Tiếp tục xem"
    Navigator.pop(context, true);
  }

  void _closePlayer() async {
    if (_isClosing) return;
    _isClosing = true;
    _tick?.cancel();
    final ok = _position == 0 || await _sendProgress();
    if (!mounted) return;
    if (!ok) {
      _isClosing = false;
      setState(() {
        _isPlaying = false;
        _syncError = 'Chưa lưu được tiến độ. Kiểm tra kết nối rồi thử lại.';
      });
      _startTicking();
      return;
    }
    Navigator.pop(context, _progressChanged);
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
    final progress = (_totalDuration == 0)
        ? 0.0
        : (_position / _totalDuration).clamp(0.0, 1.0);

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (didPop) return;
        _closePlayer();
      },
      child: Scaffold(
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
              errorWidget: (context, url, error) =>
                  Container(color: Colors.black),
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
                        onPressed: _closePlayer,
                      ),
                      Expanded(
                        child: Text(
                          'Mô phỏng: ${widget.movie.title}',
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
                  const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 24),
                    child: Text(
                      'Mô phỏng tương tác · Không phát video thật\nKéo thanh tiến độ để kiểm tra tiếp tục xem và phản hồi.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.white70),
                    ),
                  ),
                  if (_syncError != null)
                    Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        children: [
                          Text(
                            _syncError!,
                            style: const TextStyle(color: Colors.orangeAccent),
                          ),
                          TextButton(
                            onPressed: () async {
                              setState(() => _syncError = null);
                              if (_position >=
                                  (_totalDuration * _finishRatio).round()) {
                                await _onFinished();
                              } else if (!_resumeLoaded) {
                                await _loadResumePosition();
                              } else {
                                final ok = await _sendProgress();
                                if (!mounted) return;
                                setState(() {
                                  _syncError = ok
                                      ? null
                                      : 'Chưa đồng bộ được. Vui lòng thử lại.';
                                });
                              }
                            },
                            child: const Text('Thử lại'),
                          ),
                        ],
                      ),
                    ),

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
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 15,
                            ),
                          ),
                          const SizedBox(height: 12),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              ElevatedButton(
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: AppColors.primary,
                                ),
                                onPressed: _resumeFromSaved,
                                child: const Text(
                                  '▶ Tiếp tục xem',
                                  style: TextStyle(color: Colors.white),
                                ),
                              ),
                              const SizedBox(width: 12),
                              TextButton(
                                onPressed: _restartFromBeginning,
                                child: const Text(
                                  'Xem từ đầu',
                                  style: TextStyle(color: Colors.white70),
                                ),
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
                            _isPlaying
                                ? Icons.pause_circle_filled
                                : Icons.play_circle_fill,
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
                        SliderTheme(
                          data: SliderTheme.of(context).copyWith(
                            trackHeight: 6,
                            activeTrackColor: AppColors.primary,
                            inactiveTrackColor: Colors.white24,
                            thumbColor: Colors.white,
                            overlayColor: AppColors.primary.withValues(
                              alpha: 0.18,
                            ),
                            thumbShape: const RoundSliderThumbShape(
                              enabledThumbRadius: 8,
                            ),
                            overlayShape: const RoundSliderOverlayShape(
                              overlayRadius: 18,
                            ),
                          ),
                          child: Slider(
                            min: 0,
                            max: _totalDuration.toDouble(),
                            value: _position
                                .clamp(0, _totalDuration)
                                .toDouble(),
                            onChangeStart: _onSeekStart,
                            onChanged: _onSeekChanged,
                            onChangeEnd: (value) {
                              _onSeekEnd(value);
                            },
                          ),
                        ),
                        const SizedBox(height: 6),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              _format(_position),
                              style: const TextStyle(
                                color: Colors.white70,
                                fontSize: 12,
                              ),
                            ),
                            Text(
                              '${(progress * 100).round()}%',
                              style: const TextStyle(
                                color: Colors.white70,
                                fontSize: 12,
                              ),
                            ),
                            Text(
                              _format(_totalDuration),
                              style: const TextStyle(
                                color: Colors.white70,
                                fontSize: 12,
                              ),
                            ),
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
      ),
    );
  }
}
