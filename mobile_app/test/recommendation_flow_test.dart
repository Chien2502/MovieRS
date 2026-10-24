import 'dart:convert';
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:mobile_app/models/movie.dart';
import 'package:mobile_app/screens/detail_screen.dart';
import 'package:mobile_app/screens/home_screen.dart';
import 'package:mobile_app/screens/player_screen.dart';
import 'package:mobile_app/services/api_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => SharedPreferences.setMockInitialValues({}));
  test('Metadata số trống từ CSV không làm hỏng danh sách phim', () {
    final movie = Movie.fromJson({
      'movieId': 2,
      'vote_average': '',
      'runtime_minutes': '',
    });
    expect(movie.movieId, 2);
    expect(movie.voteAverage, 0);
    expect(movie.runtimeMinutes, 100);
  });
  http.Response response(Object data, [int code = 200]) => http.Response(
    json.encode(data),
    code,
    headers: {'content-type': 'application/json; charset=utf-8'},
  );

  test('Lỗi máy chủ khác danh sách rỗng; ghi thất bại trả false', () async {
    final api = ApiService(
      client: MockClient(
        (_) async => response({'detail': 'Mất kết nối dữ liệu'}, 503),
      ),
    );
    await expectLater(
      api.getRecommendations(200000),
      throwsA(isA<ApiException>()),
    );
    expect(await api.sendRating(200000, 1, 4), isFalse);
  });

  test('Danh sách cộng đồng gọi endpoint xếp hạng', () async {
    String? path;
    final api = ApiService(
      client: MockClient((request) async {
        path = request.url.path;
        return response({'results': []});
      }),
    );
    await api.getPopularMovies();
    expect(path, '/api/movies/popular');
  });

  test('Mỗi ý định ghi gửi một idempotency key riêng', () async {
    final keys = <String?>[];
    final api = ApiService(
      client: MockClient((request) async {
        keys.add(request.headers['Idempotency-Key']);
        return response({'changed': true});
      }),
    );
    expect(await api.sendRating(200000, 1, 4), isTrue);
    expect(await api.sendRating(200000, 1, 3), isTrue);
    expect(keys.every((key) => key != null && key.length >= 8), isTrue);
    expect(keys.toSet().length, 2);
  });

  test(
    'Đăng nhập lưu token và request sau gửi bearer; đăng xuất xóa phiên',
    () async {
      String? authorization;
      final api = ApiService(
        client: MockClient((request) async {
          if (request.url.path.endsWith('/login')) {
            return response({
              'user_id': 200000,
              'username': 'tester',
              'access_token': 'temporary-token',
              'expires_at': '2099-01-01T00:00:00Z',
            });
          }
          authorization = request.headers['Authorization'];
          return response({'user_id': 200000});
        }),
      );
      expect((await api.login('tester', 'abcdefgh')).isSuccess, isTrue);
      expect(await api.hasValidSession(), isTrue);
      expect(authorization, 'Bearer temporary-token');
      await api.logout();
      expect(await api.hasValidSession(), isFalse);
    },
  );

  testWidgets('Trang chủ giải thích khởi đầu và hiển thị lỗi có thể thử lại', (
    tester,
  ) async {
    final api = ApiService(
      client: MockClient((request) async {
        if (request.url.path.contains('/recommendations/')) {
          return response({
            'recommendations': [],
            'strategy': 'genre_popularity',
            'stage': 'cold_start',
            'history_count': 0,
            'candidate_count': 60,
          });
        }
        if (request.url.path.endsWith('/profile')) {
          return response({
            'genres': ['Drama'],
          });
        }
        if (request.url.path.endsWith('/popular')) {
          return response({'results': []});
        }
        return response([]);
      }),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: HomeScreen(userId: 200000, username: 'demo', apiService: api),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('Gợi ý theo thể loại'), findsOneWidget);
    expect(find.textContaining('0 phim đã tương tác'), findsOneWidget);
    expect(find.textContaining('AI SVD'), findsNothing);

    final failed = ApiService(
      client: MockClient(
        (_) async => response({'detail': 'Không tải được dữ liệu'}, 503),
      ),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: HomeScreen(
          key: const ValueKey('failed'),
          userId: 200000,
          username: 'demo',
          apiService: failed,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('Không tải được dữ liệu'), findsOneWidget);
    expect(find.text('Chưa có phim phù hợp'), findsNothing);
  });

  testWidgets(
    'Quay lại từ phim giữ trang chủ; chỉ tải lại khi ghi dữ liệu thành công',
    (tester) async {
      final paths = <String>[];
      final waitingRecommendation = Completer<http.Response>();
      var recommendationCalls = 0;
      final movie = {
        'movieId': 1,
        'title': 'Phim kiểm tra cache',
        'genres': 'Drama',
        'poster_path': '',
        'overview': 'Nội dung',
        'vote_average': 0,
      };
      final api = ApiService(
        client: MockClient((request) async {
          paths.add('${request.method} ${request.url.path}');
          if (request.url.path.startsWith('/api/recommendations/')) {
            recommendationCalls++;
            if (recommendationCalls == 2) return waitingRecommendation.future;
            return response({
              'recommendations': [movie],
              'strategy': 'popularity',
              'stage': 'cold_start',
              'history_count': 0,
              'candidate_count': 1,
            });
          }
          if (request.url.path.endsWith('/popular')) {
            return response({'results': []});
          }
          if (request.url.path.endsWith('/profile')) {
            return response({'genres': []});
          }
          if (request.url.path.endsWith('/favorites') ||
              request.url.path.endsWith('/ratings') ||
              request.url.path == '/api/watch/progress/200000') {
            return response([]);
          }
          return response({'changed': true});
        }),
      );

      await tester.pumpWidget(
        MaterialApp(
          home: HomeScreen(userId: 200000, username: 'demo', apiService: api),
        ),
      );
      await tester.pumpAndSettle();
      expect(recommendationCalls, 1);

      await tester.tap(find.text('Phim kiểm tra cache'));
      await tester.pumpAndSettle();
      await tester.pageBack();
      await tester.pumpAndSettle();
      expect(recommendationCalls, 1);
      expect(find.text('Dành cho bạn'), findsOneWidget);

      await tester.pumpWidget(
        MaterialApp(
          home: HomeScreen(
            userId: 200000,
            username: 'demo',
            refreshToken: 1,
            apiService: api,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(recommendationCalls, 1);

      await tester.tap(find.text('Phim kiểm tra cache'));
      await tester.pumpAndSettle();
      await tester.tap(find.byIcon(Icons.favorite_border));
      await tester.pumpAndSettle();
      await tester.pageBack();
      await tester.pump();
      expect(recommendationCalls, 2);
      expect(find.text('Dành cho bạn'), findsOneWidget);
      expect(
        paths.where((path) => path == 'GET /api/movies/popular').length,
        1,
      );

      waitingRecommendation.complete(
        response({
          'recommendations': [movie],
          'strategy': 'popularity',
          'stage': 'cold_start',
          'history_count': 0,
          'candidate_count': 1,
        }),
      );
      await tester.pumpAndSettle();
    },
  );

  testWidgets(
    'Đánh giá thất bại không thông báo đã lưu; yêu thích dùng một request',
    (tester) async {
      final posts = <String>[];
      final api = ApiService(
        client: MockClient((request) async {
          if (request.method == 'GET') return response([]);
          posts.add(request.url.path);
          return response({
            'detail': 'Thử lại',
          }, request.url.path.endsWith('/rating') ? 503 : 200);
        }),
      );
      final movie = Movie(
        movieId: 1,
        title: 'Phim kiểm thử',
        genres: 'Drama, Comedy',
        posterPath: '',
        overview: 'Mô tả',
        voteAverage: 0,
      );
      await tester.pumpWidget(
        MaterialApp(
          home: DetailScreen(movie: movie, userId: 200000, apiService: api),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byIcon(Icons.favorite_border));
      await tester.pumpAndSettle();
      expect(posts, ['/api/users/200000/favorites']);
      await tester.ensureVisible(find.text('Bạn đánh giá phim này thế nào?'));
      await tester.tap(find.byIcon(Icons.star).at(3));
      await tester.pumpAndSettle();
      expect(posts.last, '/api/interactions/rating');
      await tester.pump(const Duration(seconds: 3));
      await tester.pumpAndSettle();
      expect(
        find.text('Chưa lưu được đánh giá. Vui lòng thử lại.'),
        findsOneWidget,
      );
      expect(find.textContaining('Bạn đã đánh giá'), findsNothing);
    },
  );

  testWidgets(
    'Player khôi phục đúng vị trí và chờ lưu thành công trước khi thoát',
    (tester) async {
      final pending = Completer<http.Response>();
      var writes = 0;
      final positions = <int>[];
      final api = ApiService(
        client: MockClient((request) async {
          if (request.method == 'GET') {
            return response({
              'position_seconds': 30,
              'duration_seconds': 100,
              'ratio': 0.3,
              'status': 'in_progress',
            });
          }
          positions.add(
            (json.decode(request.body) as Map)['positionSeconds'] as int,
          );
          writes++;
          return writes == 1 ? pending.future : response({'status': 'success'});
        }),
      );
      final movie = Movie(
        movieId: 1,
        title: 'Phim mô phỏng',
        genres: 'Drama',
        posterPath: '',
        overview: '',
        voteAverage: 0,
      );
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () => Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => PlayerScreen(
                      movie: movie,
                      userId: 200000,
                      apiService: api,
                    ),
                  ),
                ),
                child: const Text('Mở mô phỏng'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Mở mô phỏng'));
      await tester.pumpAndSettle();
      expect(tester.widget<Slider>(find.byType(Slider)).value, 30);
      await tester.tap(find.byIcon(Icons.arrow_back));
      await tester.pump();
      expect(find.byType(PlayerScreen), findsOneWidget);
      pending.complete(response({'detail': 'Lỗi ghi'}, 503));
      await tester.pumpAndSettle();
      expect(find.textContaining('Chưa lưu được tiến độ'), findsOneWidget);
      await tester.tap(find.text('Thử lại'));
      await tester.pumpAndSettle();
      await tester.tap(find.byIcon(Icons.arrow_back));
      await tester.pumpAndSettle();
      expect(find.byType(PlayerScreen), findsNothing);
      expect(find.text('Mở mô phỏng'), findsOneWidget);
      expect(positions, everyElement(30));
    },
  );
}
