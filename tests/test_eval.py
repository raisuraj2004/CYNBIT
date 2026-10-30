from eval.run_eval import load_profiles, run_injection_checks
from core.retrieval import load_tracks
from core.security_cases import INJECTION_TEST_CASES


def test_evaluation_data_has_twenty_synthetic_profiles_and_labels():
    profiles = load_profiles()
    track_ids = {track.id for track in load_tracks()}
    assert len(profiles) == 20
    assert all(labels and labels <= track_ids for _, _, labels in profiles)


def test_evaluation_injection_checks_pass():
    passed, total = run_injection_checks(load_tracks())
    assert total == len(INJECTION_TEST_CASES)
    assert passed == total
