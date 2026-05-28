import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../models/user.dart';
import '../services/cache_service.dart';

abstract class BaseRepository {
  Future<bool> healthCheck();
}

class UserRepository extends BaseRepository implements Auditable {
  final http.Client _client;
  final CacheService _cache;
  final String baseUrl;

  const UserRepository({
    required http.Client client,
    required CacheService cache,
    this.baseUrl = 'https://api.example.com',
  })  : _client = client,
        _cache = cache;

  @override
  Future<bool> healthCheck() async {
    final response = await _client.get(Uri.parse('$baseUrl/health'));
    return response.statusCode == 200;
  }

  Future<User?> findById(int id) async {
    final cached = _cache.get('user:$id');
    if (cached != null) {
      return User.fromJson(cached);
    }
    final response = await _client.get(Uri.parse('$baseUrl/users/$id'));
    if (response.statusCode == 200) {
      final user = User.fromJson(response.body);
      _cache.set('user:$id', response.body);
      return user;
    }
    return null;
  }

  Future<List<User>> findAll({int page = 0, int size = 20}) async {
    final response = await _client.get(
      Uri.parse('$baseUrl/users?page=$page&size=$size'),
    );
    return User.listFromJson(response.body);
  }

  String get endpoint => baseUrl;
}

class UserWidget extends StatefulWidget {
  final int userId;

  const UserWidget({super.key, required this.userId});

  @override
  State<UserWidget> createState() => _UserWidgetState();
}

class _UserWidgetState extends State<UserWidget> {
  User? _user;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadUser();
  }

  Future<void> _loadUser() async {
    final repo = UserRepository(
      client: http.Client(),
      cache: CacheService(),
    );
    final user = await repo.findById(widget.userId);
    setState(() {
      _user = user;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const CircularProgressIndicator();
    }
    return Text(_user?.name ?? 'Unknown');
  }
}