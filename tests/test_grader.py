from app.grader import grade_text


def test_grade_sample_parlay() -> None:
    text = 'Jokic 25+ pts\nDenver ML\nMurray over 1.5 threes'
    result = grade_text(text)
    assert result.overall == 'lost'
    assert result.legs[0].settlement == 'win'
    assert result.legs[1].settlement == 'win'
    assert result.legs[2].settlement == 'loss'
