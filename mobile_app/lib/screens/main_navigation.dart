import 'package:flutter/material.dart';
import '../constants/app_colors.dart';
import 'home_screen.dart';
import 'search_screen.dart';
import 'favorites_screen.dart';
import 'profile_screen.dart';

class MainNavigation extends StatefulWidget {
  final int userId;
  final String username;

  const MainNavigation({
    super.key,
    required this.userId,
    required this.username,
  });

  @override
  State<MainNavigation> createState() => _MainNavigationState();
}

class _MainNavigationState extends State<MainNavigation> {
  int _currentIndex = 0;
  final List<int> _refreshTokens = [0, 0, 0, 0];
  final List<bool> _visited = [true, false, false, false];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: IndexedStack(
        index: _currentIndex,
        children: [
          HomeScreen(
            userId: widget.userId,
            username: widget.username,
            refreshToken: _refreshTokens[0],
          ),
          _visited[1]
              ? SearchScreen(userId: widget.userId)
              : const SizedBox.shrink(),
          _visited[2]
              ? FavoritesScreen(
                  userId: widget.userId,
                  refreshToken: _refreshTokens[2],
                )
              : const SizedBox.shrink(),
          _visited[3]
              ? ProfileScreen(
                  userId: widget.userId,
                  username: widget.username,
                  refreshToken: _refreshTokens[3],
                )
              : const SizedBox.shrink(),
        ],
      ),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        onTap: (index) {
          if (index == _currentIndex) return;
          setState(() {
            _currentIndex = index;
            _visited[index] = true;
            _refreshTokens[index]++;
          });
        },
        backgroundColor: AppColors.cardBackground,
        selectedItemColor: AppColors.primary,
        unselectedItemColor: AppColors.textSecondary,
        type: BottomNavigationBarType.fixed,
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.home_rounded),
            label: 'Trang chủ',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.search_rounded),
            label: 'Tìm kiếm',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.favorite_rounded),
            label: 'Yêu thích',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.person_rounded),
            label: 'Hồ sơ',
          ),
        ],
      ),
    );
  }
}
