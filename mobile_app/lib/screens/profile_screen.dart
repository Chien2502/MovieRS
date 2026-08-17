import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../constants/app_colors.dart';
import '../constants/app_genres.dart';
import '../services/api_service.dart';
import 'login_screen.dart';

class ProfileScreen extends StatefulWidget {
  final int userId;
  final String username;

  const ProfileScreen({super.key, required this.userId, required this.username});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  final ApiService _apiService = ApiService();
  List<String> _selectedGenres = [];
  int _ratingsCount = 0;
  int _favoritesCount = 0;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadProfileData();
  }

  Future<void> _loadProfileData() async {
    final prefs = await SharedPreferences.getInstance();
    final localGenres = prefs.getStringList('selected_genres') ?? [];

    final profile = await _apiService.getProfile(widget.userId);

    if (mounted) {
      setState(() {
        _selectedGenres = profile != null
            ? List<String>.from(profile['genres'] ?? [])
            : localGenres;
        _ratingsCount = profile?['ratings_count'] ?? 0;
        _favoritesCount = profile?['favorites_count'] ?? 0;
        _isLoading = false;
      });
    }
  }

  Future<void> _editGenres() async {
    final Set<String> draft = {..._selectedGenres};

    final saved = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) {
          return AlertDialog(
            backgroundColor: AppColors.cardBackground,
            title: const Text(
              'Chọn thể loại yêu thích',
              style: TextStyle(color: AppColors.textPrimary, fontSize: 17),
            ),
            content: SizedBox(
              width: double.maxFinite,
              child: Wrap(
                spacing: 8,
                runSpacing: 10,
                children: appGenres.map((genre) {
                  final isSelected = draft.contains(genre);
                  return FilterChip(
                    label: Text(genre),
                    labelStyle: TextStyle(
                      color: isSelected ? Colors.white : AppColors.textPrimary,
                      fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                    ),
                    selected: isSelected,
                    selectedColor: AppColors.primary,
                    backgroundColor: AppColors.cardBackground,
                    checkmarkColor: Colors.white,
                    onSelected: (_) {
                      setDialogState(() {
                        if (isSelected) {
                          draft.remove(genre);
                        } else {
                          draft.add(genre);
                        }
                      });
                    },
                  );
                }).toList(),
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Hủy', style: TextStyle(color: AppColors.textSecondary)),
              ),
              TextButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('Lưu', style: TextStyle(color: AppColors.primary)),
              ),
            ],
          );
        },
      ),
    );

    if (saved != true || draft.isEmpty) {
      if (draft.isEmpty && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Vui lòng chọn ít nhất 1 thể loại!'),
            backgroundColor: Colors.redAccent,
          ),
        );
      }
      return;
    }

    final ok = await _apiService.savePreferences(widget.userId, draft.toList());
    if (!mounted) return;

    if (ok) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setStringList('selected_genres', draft.toList());
      if (!mounted) return;
      setState(() => _selectedGenres = draft.toList());
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Đã cập nhật sở thích phim ✓'), backgroundColor: AppColors.success),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Không thể cập nhật lên máy chủ'), backgroundColor: Colors.redAccent),
      );
    }
  }

  void _logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('userId');
    await prefs.remove('username');
    await prefs.remove('onboarded');

    if (!mounted) return;

    Navigator.pushAndRemoveUntil(
      context,
      MaterialPageRoute(builder: (context) => const LoginScreen()),
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.appBarBackground,
        title: const Text(
          'Hồ Sơ Người Dùng',
          style: TextStyle(color: AppColors.textPrimary, fontWeight: FontWeight.bold),
        ),
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator(color: AppColors.primary))
          : SingleChildScrollView(
              padding: const EdgeInsets.all(20.0),
              child: Column(
                children: [
                  const SizedBox(height: 10),
                  Center(
                    child: Stack(
                      alignment: Alignment.center,
                      children: [
                        Container(
                          width: 90,
                          height: 90,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: AppColors.primary.withValues(alpha: 0.2),
                            border: Border.all(color: AppColors.primary, width: 2),
                          ),
                        ),
                        const Icon(Icons.person_rounded, size: 50, color: AppColors.primary),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    widget.username,
                    style: const TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'User ID: #${widget.userId} · Tài khoản MLOps',
                    style: const TextStyle(color: AppColors.textSecondary, fontSize: 13),
                  ),
                  const SizedBox(height: 24),

                  // Thống kê tương tác (từ server)
                  Row(
                    children: [
                      _buildStatCard('⭐ Ratings', '$_ratingsCount', AppColors.ratingStar),
                      const SizedBox(width: 12),
                      _buildStatCard('❤️ Yêu thích', '$_favoritesCount', AppColors.favorite),
                    ],
                  ),

                  const SizedBox(height: 24),

                  // Thể loại đã chọn (Cold-Start)
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: AppColors.cardBackground,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            const Text(
                              '🎭 Thể loại đã chọn (Cold-Start)',
                              style: TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.bold,
                                color: AppColors.textPrimary,
                              ),
                            ),
                            IconButton(
                              icon: const Icon(Icons.edit_outlined, color: AppColors.primary, size: 20),
                              onPressed: _editGenres,
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        _selectedGenres.isEmpty
                            ? const Text('Chưa chọn thể loại nào.', style: TextStyle(color: AppColors.textSecondary))
                            : Wrap(
                                spacing: 8,
                                runSpacing: 8,
                                children: _selectedGenres.map((g) {
                                  return Chip(
                                    label: Text(g, style: const TextStyle(fontSize: 12, color: Colors.white)),
                                    backgroundColor: AppColors.primary,
                                  );
                                }).toList(),
                              ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 32),

                  // Nút Đăng xuất
                  SizedBox(
                    width: double.infinity,
                    height: 48,
                    child: ElevatedButton.icon(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.redAccent.withValues(alpha: 0.15),
                        foregroundColor: Colors.redAccent,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                          side: const BorderSide(color: Colors.redAccent, width: 1),
                        ),
                      ),
                      icon: const Icon(Icons.logout),
                      label: const Text('Đăng xuất', style: TextStyle(fontWeight: FontWeight.bold)),
                      onPressed: _logout,
                    ),
                  ),
                ],
              ),
            ),
    );
  }

  Widget _buildStatCard(String label, String value, Color color) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 12),
        decoration: BoxDecoration(
          color: AppColors.cardBackground,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          children: [
            Text(
              value,
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: color),
            ),
            const SizedBox(height: 4),
            Text(
              label,
              style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
            ),
          ],
        ),
      ),
    );
  }
}
