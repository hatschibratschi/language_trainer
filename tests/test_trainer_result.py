"""Round result: donut chart and the table of words not known."""

from parla.app import missed_html, result_html


def test_result_donut():
    out = result_html(4, 10)
    assert 'stroke-dasharray="40 100"' in out and ">40%<" in out and "4 von 10 gewusst" in out
    assert "💪" in out and "🎉" in result_html(9, 10) and "👍" in result_html(5, 10)
    assert ">0%<" in result_html(0, 0)


def test_missed_table():
    assert missed_html([]) == ""
    out = missed_html([["die <Tomate>", "il pomodoro"]])
    assert "<th>Deutsch</th><th>Italienisch</th>" in out
    assert "<td>die &lt;Tomate&gt;</td><td>il pomodoro</td>" in out
