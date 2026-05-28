API Based Tree-Sitter language pack parser for other systems

# Quick Start
```bash
cd parser
pip install -e ".[dev]"
pytest -v                        # run the test suite
uvicorn app.main:app --port 8200 # start the sidecar
```

Parses code files with the following formatting:

```python
class ParseRequest(BaseModel):
    source_text: str = Field(description="Raw source code to parse")
    file_path: str = Field(description="Original file path — used for metadata only, not file access")
    language: Language

class Language(StrEnum):
    Python = "Python"
    Kotlin = "Kotlin"
    Dart = "Dart"
    JavaScript = "JavaScript"
    TypeScript = "TypeScript"
    Cobol = "Cobol"
    C ="C"
    Cpp = "Cpp"
```

Using the following endpoints `/parse` `/parse/structured` producing the same response structure:

```python
class CodeReference(BaseModel):
    type: ReferenceType
    target: str
    qualifiedTarget: str | None = None


class CodeUnit(BaseModel):
    type: UnitType
    name: str
    language: Language
    sourceText: str
    filePath: str
    startLine: int
    endLine: int
    qualifiedName: str | None = None
    signature: str | None = None
    references: list[CodeReference] = Field(default_factory=list)
    parentName: str | None = None
    children: list[str] = Field(default_factory=list)


class CodeParsingResult(BaseModel):
    units: list[CodeUnit]
    filePath: str
    language: Language
    warnings: list[str] = Field(default_factory=list)


class UnitType(StrEnum):
    Module = "Module"
    Class = "Class"
    Function = "Function"
    ImportBlock = "ImportBlock"
    Declaration = "Declaration"


class ReferenceType(StrEnum):
    Imports = "Imports"
    Extends = "Extends"
    Implements = "Implements"
    Calls = "Calls"
    References = "References"
    Annotations = "Annotations"
    Overrides = "Overrides"
    UsesTypes = "UsesTypes"
```


# Quick test against the API

```bash
echo "Quick Test"

curl -X POST http://localhost:8200/parse/structured \
  -H "Content-Type: application/json" \
  --data @- <<EOF
{
  "source_text": "import 'package:flutter/material.dart';
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
}",
  "file_path": "/tmp/test.dart",
  "language": "Dart"
}
EOF
```