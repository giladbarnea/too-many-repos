from too_many_repos.gist import remove_empty_lines_and_rstrip


def test_remove_whitespace():
	lines = ['a\n', 'b', 'c ', '', ' d', ' ', ' e\n']
	actual = list(remove_empty_lines_and_rstrip(lines))
	expected = ['a', 'b', 'c', ' d', ' e']
	assert actual == expected
