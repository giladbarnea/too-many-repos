from too_many_repos.tmrignore import tmrignore

def test_line_with_comment_in_the_end():
	assert not tmrignore.is_ignored('1'), "precondition to know for sure that 1 is ignored for the right reason"
	tmrignore.add('\d+ # comment')
	assert tmrignore.is_ignored('1')
	
def test_line_with_comment_in_the_beginning():
	assert not tmrignore.is_ignored('a'), "precondition to know for sure that 'a' is not ignored for the right reason"
	tmrignore.add('#.*')
	assert not tmrignore.is_ignored('a')