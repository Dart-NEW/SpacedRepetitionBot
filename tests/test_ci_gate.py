"""Intentional CI failure used to validate the quality gate."""


def test_ci_gate_tripwire() -> None:
    assert False, "Intentional CI failure to test the gate."
