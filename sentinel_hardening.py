"""Production-oriented request and response helpers for SENTINEL.

Drop-in replacement for the existing backend helper functions:
    safe_text, _error_hint, call_with_retry, parse_prediction_response,
    call_svc, call_finbert, get_circuit_breaker

The module deliberately does not depend on Streamlit, so its behavior can be unit-tested.
"""
from __future__ import annotations

import html
import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests

RETRY_ATTEMPTS = 2
RETRY_BACKOFF_S = 0.5
CIRCUIT_COOLDOWN_S = 30.0
CIRCUIT_FAILURE_THRESHOLD = 3
CONNECT_TIMEOUT_S = 3.05
MAX_RESPONSE_BYTES = 1_000_000
BINARY_TOLERANCE = 1e-9
PROBABILITY_SUM_TOLERANCE = 0.03
FINBERT_PROBABILITY_KEYS = ("cold", "hot_rising", "hot_falling")
RETRYABLE_STATUSES = {408, 425, 429}


def safe_text(value: Any, limit: int = 500) -> str:
    """HTML-escape a value before including it in custom HTML/Markdown."""
    return html.escape(str(value)[:limit], quote=True)


def _error_hint(status: Optional[int], exc: Optional[BaseException]) -> str:
    """Return a short, actionable hint for a failed HTTP request."""
    if exc is not None:
        name = type(exc).__name__
        if isinstance(exc, requests.Timeout):
            return "Request timed out; check cold starts, model loading, and server capacity."
        if isinstance(exc, requests.ConnectionError):
            return "Connection failed; verify the URL, service health, and network egress."
        return f"{name}: transient request failure; inspect service logs if it persists."
    if status == 429:
        return "HTTP 429; endpoint is rate-limiting requests."
    if status == 502:
        return "HTTP 502; upstream container may be unhealthy or still starting."
    if status == 503:
        return "HTTP 503; endpoint may be overloaded or unavailable."
    if status == 504:
        return "HTTP 504; gateway timed out. Check model startup and request duration."
    if status is not None and 500 <= status < 600:
        return f"HTTP {status}; inspect endpoint logs for a server-side failure."
    return ""


class CircuitOpenError(RuntimeError):
    """Raised when a circuit breaker is cooling down after repeated failures."""


@dataclass(frozen=True)
class CircuitSnapshot:
    failures: int
    is_open: bool
    retry_in_s: float


class CircuitBreaker:
    """Thread-safe, process-local circuit breaker for one endpoint URL."""

    def __init__(self, threshold: int = CIRCUIT_FAILURE_THRESHOLD,
                 cooldown_s: float = CIRCUIT_COOLDOWN_S) -> None:
        if threshold < 1:
            raise ValueError("threshold must be >= 1")
        if cooldown_s <= 0:
            raise ValueError("cooldown_s must be > 0")
        self.threshold = threshold
        self.cooldown_s = cooldown_s
        self._failures = 0
        self._opened_until = 0.0
        self._half_open_probe = False
        self._lock = threading.Lock()

    def allow_request(self) -> tuple[bool, float]:
        """Return (allowed, seconds_until_retry)."""
        with self._lock:
            now = time.monotonic()
            if self._opened_until and now < self._opened_until:
                return False, self._opened_until - now
            if self._opened_until and now >= self._opened_until:
                # Permit one trial request after cooldown; concurrent callers wait.
                if self._half_open_probe:
                    return False, 1.0
                self._half_open_probe = True
                return True, 0.0
            return True, 0.0

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_until = 0.0
            self._half_open_probe = False

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            self._half_open_probe = False
            if self._failures >= self.threshold:
                self._opened_until = time.monotonic() + self.cooldown_s

    def snapshot(self) -> CircuitSnapshot:
        with self._lock:
            wait = max(0.0, self._opened_until - time.monotonic())
            return CircuitSnapshot(
                failures=self._failures,
                is_open=wait > 0,
                retry_in_s=wait,
            )


_BREAKERS: dict[str, CircuitBreaker] = {}
_BREAKERS_LOCK = threading.Lock()


def get_circuit_breaker(url: str) -> CircuitBreaker:
    """Get a shared breaker keyed by the exact endpoint URL."""
    key = str(url).rstrip("/")
    with _BREAKERS_LOCK:
        breaker = _BREAKERS.get(key)
        if breaker is None:
            breaker = CircuitBreaker()
            _BREAKERS[key] = breaker
        return breaker


def _is_retryable_status(status: int) -> bool:
    return status in RETRYABLE_STATUSES or 500 <= status < 600


def call_with_retry(
    url: str,
    method: str = "GET",
    retries: int = RETRY_ATTEMPTS,
    backoff: float = RETRY_BACKOFF_S,
    *,
    breaker: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """Request an endpoint with bounded retries and honest timing/attempt counts.

    Retries connection/time-out errors and transient HTTP statuses only. Client
    errors (4xx, except 408/425/429) are returned immediately. ``latency_ms`` is
    elapsed wall time for the complete operation, including backoff delays.
    """
    method = method.upper().strip()
    if method not in {"GET", "POST"}:
        return {
            "ok": False, "response": None, "latency_ms": 0,
            "last_attempt_latency_ms": 0, "attempts": 0,
            "error": f"Unsupported HTTP method: {method}", "status": None,
        }
    if retries < 0 or backoff < 0:
        raise ValueError("retries and backoff must be non-negative")

    cb = get_circuit_breaker(url) if breaker else None
    started_total = time.perf_counter()
    if cb is not None:
        allowed, wait_s = cb.allow_request()
        if not allowed:
            wait_rounded = max(1, math.ceil(wait_s))
            return {
                "ok": False, "response": None, "latency_ms": 0,
                "last_attempt_latency_ms": 0, "attempts": 0,
                "error": f"Circuit open; retry in about {wait_rounded}s.",
                "status": None, "circuit_open": True,
            }

    last_exc: Optional[BaseException] = None
    last_status: Optional[int] = None
    last_response: Optional[requests.Response] = None
    last_attempt_ms = 0
    attempts = 0
    request_fn = requests.get if method == "GET" else requests.post

    for attempt_index in range(retries + 1):
        attempts += 1
        attempt_started = time.perf_counter()
        last_exc = None
        last_status = None
        last_response = None
        try:
            response = request_fn(url, **kwargs)
            last_attempt_ms = int((time.perf_counter() - attempt_started) * 1000)
            last_response = response
            last_status = response.status_code
            if response.status_code == 200:
                if cb is not None:
                    cb.record_success()
                return {
                    "ok": True, "response": response,
                    "latency_ms": int((time.perf_counter() - started_total) * 1000),
                    "last_attempt_latency_ms": last_attempt_ms,
                    "attempts": attempts, "error": "", "status": 200,
                    "circuit_open": False,
                }
            should_retry = _is_retryable_status(response.status_code)
            if not should_retry:
                break
        except requests.RequestException as exc:
            last_attempt_ms = int((time.perf_counter() - attempt_started) * 1000)
            last_exc = exc
            should_retry = True

        if attempt_index < retries and should_retry:
            time.sleep(backoff * (2 ** attempt_index))
        else:
            break

    if cb is not None:
        if (last_status is not None and 400 <= last_status < 500
                and last_status not in RETRYABLE_STATUSES):
            # A client error proves the endpoint responded; don't count it as an outage.
            cb.record_success()
        else:
            cb.record_failure()

    total_ms = int((time.perf_counter() - started_total) * 1000)
    hint = _error_hint(last_status, last_exc)
    if last_status is not None:
        err_msg = f"HTTP {last_status}"
        if last_response is not None:
            body = (last_response.text or "").strip()
            if body:
                err_msg += f": {safe_text(body, 240)}"
    elif last_exc is not None:
        err_msg = f"{type(last_exc).__name__}: {safe_text(last_exc, 240)}"
    else:
        err_msg = "Request failed for an unknown reason."
    if hint:
        err_msg += f" — {hint}"
    return {
        "ok": False, "response": None,
        "latency_ms": total_ms,
        "last_attempt_latency_ms": last_attempt_ms,
        "attempts": attempts, "error": err_msg,
        "status": last_status, "circuit_open": False,
    }


def _response_error(response: requests.Response) -> str:
    if response.status_code != 200:
        body = safe_text((response.text or "").strip(), 300)
        return f"HTTP {response.status_code}" + (f": {body}" if body else "")
    content = getattr(response, "content", b"")
    if content and len(content) > MAX_RESPONSE_BYTES:
        return f"Response exceeded {MAX_RESPONSE_BYTES:,}-byte safety limit."
    return ""


def parse_prediction_response(response: requests.Response) -> tuple[bool, dict[str, Any], str]:
    """Parse a prediction payload and enforce the binary 0/1 output contract."""
    status_error = _response_error(response)
    if status_error:
        return False, {}, status_error
    try:
        payload = response.json()
    except (ValueError, requests.JSONDecodeError):
        return False, {}, "Endpoint returned invalid JSON."
    if not isinstance(payload, dict):
        return False, {}, "Endpoint response must be a JSON object."
    if "prediction" not in payload:
        return False, payload, "Endpoint response missing 'prediction' field."
    try:
        prediction = float(payload["prediction"])
    except (TypeError, ValueError, OverflowError):
        return False, payload, "'prediction' field must be numeric (0 or 1)."
    if not math.isfinite(prediction):
        return False, payload, "'prediction' field must be finite."
    if min(abs(prediction), abs(prediction - 1.0)) > BINARY_TOLERANCE:
        return False, payload, "'prediction' must be binary: 0 (COLD) or 1 (HOT)."
    payload["prediction"] = int(round(prediction))
    return True, payload, ""


def _result_template() -> dict[str, Any]:
    return {
        "ok": False, "val": None, "latency_ms": 0,
        "last_attempt_latency_ms": 0, "error": "", "data": {},
        "attempts": 0, "status": None,
    }


def call_svc(url: str, headline: str, model_code: int | float,
             timeout: int = 15) -> dict[str, Any]:
    result = _result_template()
    response_meta = call_with_retry(
        f"{url.rstrip('/')}/predict", method="GET",
        params={"headline": headline, "model_choice": model_code},
        timeout=(CONNECT_TIMEOUT_S, timeout),
    )
    for key in ("latency_ms", "last_attempt_latency_ms", "attempts", "status"):
        result[key] = response_meta.get(key)
    if not response_meta["ok"]:
        result["error"] = response_meta["error"]
        return result

    ok, payload, error = parse_prediction_response(response_meta["response"])
    result.update(ok=ok, data=payload, error=error)
    if ok:
        result["val"] = payload["prediction"]
    return result


def _validate_finbert_probabilities(payload: dict[str, Any]) -> tuple[bool, str]:
    probs = payload.get("probabilities")
    if not isinstance(probs, dict):
        return False, "FinBERT response must include a 'probabilities' JSON object."

    normalized: dict[str, float] = {}
    for key in FINBERT_PROBABILITY_KEYS:
        if key not in probs:
            return False, f"FinBERT probabilities missing '{key}'."
        try:
            value = float(probs[key])
        except (TypeError, ValueError, OverflowError):
            return False, f"FinBERT probability '{key}' must be numeric."
        if not math.isfinite(value) or value < 0.0 or value > 1.0:
            return False, f"FinBERT probability '{key}' must be finite and between 0 and 1."
        normalized[key] = value

    total = sum(normalized.values())
    if abs(total - 1.0) > PROBABILITY_SUM_TOLERANCE:
        return False, f"FinBERT class probabilities must sum to 1 (received {total:.4f})."
    payload["probabilities"] = normalized

    derived_hot = normalized["hot_rising"] + normalized["hot_falling"]
    if "prob_hot" in payload:
        try:
            reported_hot = float(payload["prob_hot"])
        except (TypeError, ValueError, OverflowError):
            return False, "FinBERT 'prob_hot' must be numeric."
        if not math.isfinite(reported_hot) or not 0.0 <= reported_hot <= 1.0:
            return False, "FinBERT 'prob_hot' must be finite and between 0 and 1."
        if abs(reported_hot - derived_hot) > PROBABILITY_SUM_TOLERANCE:
            return False, "FinBERT 'prob_hot' conflicts with hot_rising + hot_falling."
    else:
        payload["prob_hot"] = derived_hot
    return True, ""


def call_finbert(url: str, headline: str, summary: str, timeout: int = 20) -> dict[str, Any]:
    result = _result_template()
    response_meta = call_with_retry(
        f"{url.rstrip('/')}/dl_predict", method="POST",
        json={"headline": headline, "summary": summary},
        timeout=(CONNECT_TIMEOUT_S, timeout),
    )
    for key in ("latency_ms", "last_attempt_latency_ms", "attempts", "status"):
        result[key] = response_meta.get(key)
    if not response_meta["ok"]:
        result["error"] = response_meta["error"]
        return result

    ok, payload, error = parse_prediction_response(response_meta["response"])
    if not ok:
        result.update(data=payload, error=error)
        return result

    probs_ok, probs_error = _validate_finbert_probabilities(payload)
    if not probs_ok:
        result.update(ok=False, data=payload, error=probs_error)
        return result

    result.update(ok=True, val=payload["prediction"], data=payload, error="")
    return result
