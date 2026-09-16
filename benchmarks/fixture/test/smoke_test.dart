import 'package:bench_fixture/src/feature_01.dart';
import 'package:bench_fixture/src/feature_02.dart';
import 'package:bench_fixture/src/feature_03.dart';
import 'package:bench_fixture/src/feature_04.dart';
import 'package:bench_fixture/src/feature_05.dart';
import 'package:bench_fixture/src/feature_06.dart';
import 'package:bench_fixture/src/feature_07.dart';
import 'package:bench_fixture/src/feature_08.dart';
import 'package:bench_fixture/src/feature_09.dart';
import 'package:bench_fixture/src/feature_10.dart';
import 'package:test/test.dart';

void main() {
  test('all ten feature entrypoints are exported', () {
    expect(slugify, isNotNull);
    expect(isPalindrome, isNotNull);
    expect(chunk, isNotNull);
    expect(romanToInt, isNotNull);
    expect(camelToSnake, isNotNull);
    expect(wordCount, isNotNull);
    expect(clampInt, isNotNull);
    expect(binarySearch, isNotNull);
    expect(formatBytes, isNotNull);
    expect(parseDuration, isNotNull);
  });
}
