import 'package:flutter/material.dart';

class AppColors {
  // Backgrounds (Light theme: nền trắng, thẻ xám)
  static const Color background = Colors.white;
  static const Color cardBackground = Color(0xFFF1F3F5); // Xám nhạt cho thẻ
  static const Color appBarBackground = Colors.white;

  // Primary & Accents (Button màu xám)
  static const Color primary = Color(0xFF616161); // Xám cho button
  static const Color accent = Color(0xFFBDBDBD);
  static const Color favorite = Colors.redAccent;
  static const Color ratingStar = Colors.amber;

  // Text colors
  static const Color textPrimary = Color(0xFF1F2937); // Đậm trên nền trắng
  static const Color textSecondary = Color(0xFF6B7280);
  static const Color textMuted = Color(0xFF9CA3AF);

  // Statuses
  static const Color error = Colors.redAccent;
  static const Color success = Colors.green;
}
