import threading
from collections import defaultdict
from collections.abc import Sequence


class Counter:
    def __init__(self, name: str, documentation: str, labelnames: Sequence[str] = ()):
        self.name = name
        self.documentation = documentation
        self.labelnames = tuple(labelnames)
        self._values: dict[tuple[str, ...], float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        label_values = tuple((labels or {}).get(lbl, "") for lbl in self.labelnames)
        with self._lock:
            self._values[label_values] += value

    def render(self) -> list[str]:
        lines = [
            f"# HELP {self.name} {self.documentation}",
            f"# TYPE {self.name} counter",
        ]
        with self._lock:
            for label_values, value in self._values.items():
                if self.labelnames:
                    label_str = ",".join(
                        f'{name}="{val}"'
                        for name, val in zip(self.labelnames, label_values, strict=False)
                    )
                    lines.append(f"{self.name}{{{label_str}}} {value}")
                else:
                    lines.append(f"{self.name} {value}")
        return lines


class Gauge:
    def __init__(self, name: str, documentation: str, labelnames: Sequence[str] = ()):
        self.name = name
        self.documentation = documentation
        self.labelnames = tuple(labelnames)
        self._values: dict[tuple[str, ...], float] = defaultdict(float)
        self._lock = threading.Lock()

    def set(self, value: float, labels: dict[str, str] | None = None) -> None:
        label_values = tuple((labels or {}).get(lbl, "") for lbl in self.labelnames)
        with self._lock:
            self._values[label_values] = value

    def render(self) -> list[str]:
        lines = [
            f"# HELP {self.name} {self.documentation}",
            f"# TYPE {self.name} gauge",
        ]
        with self._lock:
            for label_values, value in self._values.items():
                if self.labelnames:
                    label_str = ",".join(
                        f'{name}="{val}"'
                        for name, val in zip(self.labelnames, label_values, strict=False)
                    )
                    lines.append(f"{self.name}{{{label_str}}} {value}")
                else:
                    lines.append(f"{self.name} {value}")
        return lines


class Histogram:
    def __init__(
        self,
        name: str,
        documentation: str,
        labelnames: Sequence[str] = (),
        buckets: Sequence[float] = (
            0.005,
            0.01,
            0.025,
            0.05,
            0.075,
            0.1,
            0.25,
            0.5,
            0.75,
            1.0,
            2.5,
            5.0,
            7.5,
            10.0,
        ),
    ):
        self.name = name
        self.documentation = documentation
        self.labelnames = tuple(labelnames)
        self.buckets = tuple(sorted(buckets)) + (float("inf"),)

        # Key: label_values, Value: dict of bucket_upper_bound -> count
        self._buckets: dict[tuple[str, ...], dict[float, int]] = defaultdict(
            lambda: {b: 0 for b in self.buckets}
        )
        self._sums: dict[tuple[str, ...], float] = defaultdict(float)
        self._counts: dict[tuple[str, ...], int] = defaultdict(int)
        self._lock = threading.Lock()

    def observe(self, value: float, labels: dict[str, str] | None = None) -> None:
        label_values = tuple((labels or {}).get(lbl, "") for lbl in self.labelnames)
        with self._lock:
            self._sums[label_values] += value
            self._counts[label_values] += 1
            for b in self.buckets:
                if value <= b:
                    self._buckets[label_values][b] += 1

    def render(self) -> list[str]:
        lines = [
            f"# HELP {self.name} {self.documentation}",
            f"# TYPE {self.name} histogram",
        ]
        with self._lock:
            for label_values in self._counts.keys():
                label_pairs = []
                if self.labelnames:
                    label_pairs = [
                        f'{name}="{val}"'
                        for name, val in zip(self.labelnames, label_values, strict=False)
                    ]

                # Render buckets
                cumulative = 0
                for b in self.buckets:
                    count = self._buckets[label_values][b]
                    cumulative += count
                    le_str = "+Inf" if b == float("inf") else str(b)
                    bucket_labels = label_pairs + [f'le="{le_str}"']
                    labels_str = f"{{{','.join(bucket_labels)}}}"
                    lines.append(f"{self.name}_bucket{labels_str} {cumulative}")

                # Render sum and count
                labels_str = f"{{{','.join(label_pairs)}}}" if label_pairs else ""
                lines.append(f"{self.name}_sum{labels_str} {self._sums[label_values]}")
                lines.append(f"{self.name}_count{labels_str} {self._counts[label_values]}")
        return lines


class MetricsRegistry:
    def __init__(self) -> None:
        self.http_requests_total = Counter(
            "http_requests_total",
            "Total number of HTTP requests.",
            ["method", "path", "status"],
        )
        self.http_request_duration_seconds = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency in seconds.",
            ["method", "path"],
        )
        self.eval_runs_total = Counter(
            "eval_runs_total",
            "Total number of evaluation runs.",
            ["decision", "runner", "environment"],
        )
        self.eval_run_duration_seconds = Histogram(
            "eval_run_duration_seconds",
            "Duration of evaluation runs in seconds.",
            ["runner", "environment"],
        )
        self.policy_violations_total = Counter(
            "policy_violations_total",
            "Total number of static or dynamic policy violations.",
            ["rule_type", "environment"],
        )
        self.scenarios_total = Counter(
            "scenarios_total",
            "Total number of evaluated scenarios.",
            ["category"],
        )
        self.scenarios_failed_total = Counter(
            "scenarios_failed_total",
            "Total number of failed scenarios.",
            ["category"],
        )

    def render(self) -> str:
        all_lines = []
        all_lines.extend(self.http_requests_total.render())
        all_lines.extend(self.http_request_duration_seconds.render())
        all_lines.extend(self.eval_runs_total.render())
        all_lines.extend(self.eval_run_duration_seconds.render())
        all_lines.extend(self.policy_violations_total.render())
        all_lines.extend(self.scenarios_total.render())
        all_lines.extend(self.scenarios_failed_total.render())
        return "\n".join(all_lines) + "\n"


metrics = MetricsRegistry()
