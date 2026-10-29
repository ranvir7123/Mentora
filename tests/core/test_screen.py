from app.core.screen import (CLOSED_LESSON, CUES, EMPTY_HOME, HIDDEN_POINTER, AskView, Factory, GoalView,
                             HomeState, Learner, LessonState, PointerState, Tips)


def test_defaults_have_every_key():
    for default, shape in ((EMPTY_HOME, HomeState), (CLOSED_LESSON, LessonState), (HIDDEN_POINTER, PointerState)):
        assert set(default) == set(shape.__annotations__)


def test_nested_defaults_have_every_key():
    for default, shape in ((EMPTY_HOME["learner"], Learner), (EMPTY_HOME["tips"], Tips),
                           (EMPTY_HOME["factory"], Factory), (CLOSED_LESSON["goal"], GoalView),
                           (CLOSED_LESSON["ask"], AskView)):
        assert set(default) == set(shape.__annotations__)


def test_cue_names_are_fixed():
    assert CUES == ("click", "right", "not_yet", "complete", "hop")
