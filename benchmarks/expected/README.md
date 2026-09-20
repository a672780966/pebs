# benchmarks/expected/（§20）

本目录是 §20 要求的 `expected/`，但**不是**第二份期望来源。

期望值的唯一真实来源是 `benchmarks/cases/*.yaml` 里的 `expect:` 块；
本目录是它的投影，便于人工审阅与外部工具读取。

- 生成/刷新：`python -m pytest tests/test_benchmark_expected.py -q`（校验）
  或直接调用 `pebs.benchmark.expected.write_expected()`
- 漂移检查：`tests/test_benchmark_expected.py` 会逐条比对投影与来源，漂移即失败
