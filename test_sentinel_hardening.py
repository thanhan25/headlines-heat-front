"""Small offline tests for SENTINEL's hardened response/request helpers."""
import json
import unittest
from unittest.mock import Mock, patch

import requests

from sentinel_hardening import (
    CircuitBreaker,
    _validate_finbert_probabilities,
    _validate_lstm_probabilities,
    call_lstm,
    call_with_retry,
    parse_prediction_response,
)


def response(status=200, payload=None, text=None):
    r = Mock(spec=requests.Response)
    r.status_code = status
    r.content = (text or json.dumps(payload if payload is not None else {})).encode()
    r.text = text if text is not None else json.dumps(payload if payload is not None else {})
    if text is not None:
        r.json.side_effect = ValueError("bad json")
    else:
        r.json.return_value = payload
    return r


class SentinelHardeningTests(unittest.TestCase):
    def test_binary_prediction_accepted(self):
        ok, payload, error = parse_prediction_response(response(payload={"prediction": 1.0}))
        self.assertTrue(ok, error)
        self.assertEqual(payload["prediction"], 1)

    def test_non_binary_prediction_rejected(self):
        ok, _, error = parse_prediction_response(response(payload={"prediction": 1.7}))
        self.assertFalse(ok)
        self.assertIn("binary", error)

    def test_non_finite_prediction_rejected(self):
        ok, _, error = parse_prediction_response(response(payload={"prediction": float("nan")}))
        self.assertFalse(ok)
        self.assertIn("finite", error)

    def test_finbert_probability_contract(self):
        payload = {"probabilities": {"cold": 0.2, "hot_rising": 0.5, "hot_falling": 0.3}}
        ok, error = _validate_finbert_probabilities(payload)
        self.assertTrue(ok, error)
        self.assertAlmostEqual(payload["prob_hot"], 0.8)

    def test_finbert_probability_sum_rejected(self):
        payload = {"probabilities": {"cold": 0.2, "hot_rising": 0.2, "hot_falling": 0.2}}
        ok, error = _validate_finbert_probabilities(payload)
        self.assertFalse(ok)
        self.assertIn("sum to 1", error)

    def test_lstm_probability_contract(self):
        payload = {
            "prediction": 1,
            "label": "hot",
            "prob_hot": 0.6883,
            "prob_cold": 0.3117,
            "probabilities": {"cold": 0.3117, "hot": 0.6883},
            "sequence_length": 83,
            "matched_tokens": 1,
        }
        ok, error = _validate_lstm_probabilities(payload)
        self.assertTrue(ok, error)
        self.assertAlmostEqual(payload["prob_hot"], 0.6883)
        self.assertAlmostEqual(payload["prob_cold"], 0.3117)

    def test_call_lstm_parses_valid_response(self):
        good = response(payload={
            "prediction": 1,
            "label": "hot",
            "prob_hot": 0.6883,
            "prob_cold": 0.3117,
            "probabilities": {"cold": 0.3117, "hot": 0.6883},
            "sequence_length": 83,
            "matched_tokens": 1,
        })
        with patch("sentinel_hardening.requests.post", return_value=good):
            res = call_lstm("https://lstm.example.invalid", "earnings surge")
        self.assertTrue(res["ok"])
        self.assertEqual(res["val"], 1)
        self.assertEqual(res["data"]["matched_tokens"], 1)

    def test_retry_then_success_reports_actual_attempts(self):
        good = response(payload={"prediction": 0})
        with patch("sentinel_hardening.requests.get", side_effect=[requests.Timeout("slow"), good]), \
             patch("sentinel_hardening.time.sleep"):
            result = call_with_retry("https://example.invalid/predict", retries=1, backoff=0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["attempts"], 2)
        self.assertGreaterEqual(result["latency_ms"], 0)

    def test_client_error_is_not_retried(self):
        bad = response(status=400, text="bad request")
        with patch("sentinel_hardening.requests.get", return_value=bad) as mock_get:
            result = call_with_retry("https://example.invalid/predict", retries=2, backoff=0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["attempts"], 1)
        mock_get.assert_called_once()

    def test_circuit_opens_after_threshold(self):
        cb = CircuitBreaker(threshold=2, cooldown_s=10)
        cb.record_failure()
        self.assertFalse(cb.snapshot().is_open)
        cb.record_failure()
        self.assertTrue(cb.snapshot().is_open)
        allowed, wait = cb.allow_request()
        self.assertFalse(allowed)
        self.assertGreater(wait, 0)
        cb.record_success()
        self.assertFalse(cb.snapshot().is_open)


if __name__ == "__main__":
    unittest.main(verbosity=2)