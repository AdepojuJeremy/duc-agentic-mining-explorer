from duc_agentic_mining.dedup import jaccard


def test_jaccard():
    assert jaccard("give drug x", "give drug x") == 1.0
    assert jaccard("give drug x", "unrelated surgery") < 0.5
