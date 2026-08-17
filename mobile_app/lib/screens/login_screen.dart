import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../constants/app_colors.dart';
import '../constants/app_genres.dart';
import '../services/api_service.dart';
import 'main_navigation.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> with SingleTickerProviderStateMixin {
  final ApiService _apiService = ApiService();
  final TextEditingController _usernameController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  final Set<String> _selectedGenres = {};

  late final TabController _tabController;
  bool _isSubmitting = false;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    _tabController.dispose();
    super.dispose();
  }

  void _toggleGenre(String genre) {
    setState(() {
      if (_selectedGenres.contains(genre)) {
        _selectedGenres.remove(genre);
      } else {
        _selectedGenres.add(genre);
      }
    });
  }

  void _showMessage(String message, {bool isError = false}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: isError ? Colors.redAccent : AppColors.success,
      ),
    );
  }

  Future<void> _saveSession(AuthResult result) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt('userId', result.userId!);
    await prefs.setString('username', result.username!);
    await prefs.setStringList('selected_genres', _selectedGenres.toList());
  }

  Future<void> _submitLogin() async {
    final username = _usernameController.text.trim();
    final password = _passwordController.text;

    if (username.isEmpty || password.isEmpty) {
      _showMessage('Vui lòng nhập tên đăng nhập và mật khẩu!', isError: true);
      return;
    }

    setState(() => _isSubmitting = true);
    final result = await _apiService.login(username, password);
    if (!mounted) return;

    if (result.isSuccess) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setInt('userId', result.userId!);
      await prefs.setString('username', result.username!);
      if (!mounted) return;
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (context) => MainNavigation(userId: result.userId!, username: result.username!)),
      );
    } else {
      setState(() => _isSubmitting = false);
      _showMessage(result.error ?? 'Đăng nhập thất bại', isError: true);
    }
  }

  Future<void> _submitRegister() async {
    final username = _usernameController.text.trim();
    final password = _passwordController.text;

    if (username.isEmpty || password.isEmpty) {
      _showMessage('Vui lòng nhập tên đăng nhập và mật khẩu!', isError: true);
      return;
    }
    if (_selectedGenres.isEmpty) {
      _showMessage('Vui lòng chọn ít nhất 1 thể loại phim yêu thích!', isError: true);
      return;
    }

    setState(() => _isSubmitting = true);
    final result = await _apiService.register(username, password, _selectedGenres.toList());
    if (!mounted) return;

    if (result.isSuccess) {
      await _saveSession(result);
      if (!mounted) return;
      _showMessage('Đăng ký thành công! Chào mừng ${result.username} 🎉');
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (context) => MainNavigation(userId: result.userId!, username: result.username!)),
      );
    } else {
      setState(() => _isSubmitting = false);
      _showMessage(result.error ?? 'Đăng ký thất bại', isError: true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.appBarBackground,
        elevation: 0,
        title: const Text(
          'MovieRS',
          style: TextStyle(color: AppColors.primary, fontWeight: FontWeight.bold),
        ),
        centerTitle: true,
      ),
      body: SafeArea(
        child: Column(
          children: [
            TabBar(
              controller: _tabController,
              indicatorColor: AppColors.primary,
              labelColor: AppColors.primary,
              unselectedLabelColor: AppColors.textSecondary,
              tabs: const [
                Tab(text: 'Đăng nhập'),
                Tab(text: 'Đăng ký'),
              ],
            ),
            Expanded(
              child: TabBarView(
                controller: _tabController,
                children: [
                  _buildLoginTab(),
                  _buildRegisterTab(),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLoginTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(height: 8),
          const Text(
            'Chào mừng trở lại! 👋',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: AppColors.textPrimary),
          ),
          const SizedBox(height: 4),
          const Text(
            'Đăng nhập để hệ thống AI gợi ý phim theo đúng sở thích của bạn.',
            style: TextStyle(fontSize: 13, color: AppColors.textSecondary),
          ),
          const SizedBox(height: 24),
          _buildTextField(_usernameController, 'Tên đăng nhập', Icons.person_outline),
          const SizedBox(height: 14),
          _buildTextField(_passwordController, 'Mật khẩu', Icons.lock_outline, obscure: true),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            height: 50,
            child: ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.primary,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
              onPressed: _isSubmitting ? null : _submitLogin,
              child: _isSubmitting
                  ? const SizedBox(
                      width: 22, height: 22,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : const Text(
                      'Đăng nhập',
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
                    ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRegisterTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Tạo tài khoản mới ✨',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: AppColors.textPrimary),
          ),
          const SizedBox(height: 4),
          const Text(
            'Chọn 3-5 thể loại để hệ thống AI tạo gợi ý ban đầu phù hợp với bạn (Giải quyết Cold-Start):',
            style: TextStyle(fontSize: 13, color: AppColors.textSecondary),
          ),
          const SizedBox(height: 16),
          _buildTextField(_usernameController, 'Tên đăng nhập', Icons.person_outline),
          const SizedBox(height: 14),
          _buildTextField(_passwordController, 'Mật khẩu (tối thiểu 4 ký tự)', Icons.lock_outline, obscure: true),
          const SizedBox(height: 20),
          Wrap(
            spacing: 10,
            runSpacing: 12,
            children: appGenres.map((genre) {
              final isSelected = _selectedGenres.contains(genre);
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
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                onSelected: (_) => _toggleGenre(genre),
              );
            }).toList(),
          ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            height: 50,
            child: ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.primary,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
              onPressed: _isSubmitting ? null : _submitRegister,
              child: _isSubmitting
                  ? const SizedBox(
                      width: 22, height: 22,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : Text(
                      'Đăng ký (${_selectedGenres.length} thể loại)',
                      style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
                    ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTextField(
    TextEditingController controller,
    String hint,
    IconData icon, {
    bool obscure = false,
  }) {
    return TextField(
      controller: controller,
      obscureText: obscure,
      style: const TextStyle(color: AppColors.textPrimary),
      decoration: InputDecoration(
        hintText: hint,
        hintStyle: const TextStyle(color: AppColors.textSecondary),
        prefixIcon: Icon(icon, color: AppColors.primary),
        filled: true,
        fillColor: AppColors.cardBackground,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide.none,
        ),
      ),
    );
  }
}
