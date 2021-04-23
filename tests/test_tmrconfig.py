from too_many_repos.tmrconfig import is_valid
from typing import Literal, Union, Optional
NoneType = type(None)

def test_is_valid():
	# * type_ is not value / instance (e.g. bool, NoneType)
	### True
	assert is_valid("true", bool) is True
	assert is_valid("false", bool) is True
	assert is_valid("yes", bool) is True
	assert is_valid("no", bool) is True
	assert is_valid(None, NoneType) is True
	assert is_valid("None", NoneType) is True
	assert is_valid("r", str) is True
	assert is_valid("5", int) is True
	assert is_valid("0", int) is True
	assert is_valid("1", int) is True
	assert is_valid("5", float) is True
	assert is_valid("0", float) is True
	assert is_valid("1", float) is True
	assert is_valid("5.5", float) is True

	### False
	## type_ = NoneType
	assert is_valid("r", NoneType) is False
	assert is_valid("5", NoneType) is False
	assert is_valid("0", NoneType) is False
	assert is_valid("1", NoneType) is False
	assert is_valid("5.5", NoneType) is False
	assert is_valid("false", NoneType) is False

	## type_ = int
	assert is_valid("r", int) is False
	assert is_valid("5.5", int) is False
	assert is_valid("false", int) is False
	assert is_valid("none", int) is False

	## type_ = float
	assert is_valid("r", float) is False
	assert is_valid("false", float) is False
	assert is_valid("none", float) is False

	## type_ = bool
	assert is_valid("r", bool) is False
	assert is_valid("5", bool) is False
	assert is_valid("0", bool) is False
	assert is_valid("1", bool) is False
	assert is_valid("5.5", bool) is False

	## type_ = str
	assert is_valid("5", str) is False
	assert is_valid("0", str) is False
	assert is_valid("1", str) is False
	assert is_valid("5.5", str) is False
	assert is_valid("false", str) is False
	assert is_valid("no", str) is False
	assert is_valid("yes", str) is False
	assert is_valid("none", str) is False

	# * type_ is a value / instance (e.g None, 'r', 5)
	### True
	assert is_valid(None, None) is True
	assert is_valid("None", None) is True
	assert is_valid("r", "r") is True
	assert is_valid("5", 5) is True
	assert is_valid("5.5", 5.5) is True
	assert is_valid("true", True) is True
	assert is_valid("yes", True) is True
	assert is_valid("false", False) is True
	assert is_valid("no", False) is True

	### False
	## type_ = None
	assert is_valid("r", None) is False
	assert is_valid("5", None) is False
	assert is_valid("0", None) is False
	assert is_valid("1", None) is False
	assert is_valid("5.5", None) is False
	assert is_valid("false", None) is False

	## type_ = 5
	assert is_valid("r", 5) is False
	assert is_valid("false", 5) is False
	assert is_valid("none", 5) is False
	assert is_valid("5.5", 5) is False

	## type_ = 5.5
	assert is_valid("r", 5.5) is False
	assert is_valid("false", 5.5) is False
	assert is_valid("none", 5.5) is False
	assert is_valid("5", 5.5) is False

	## type_ = True
	assert is_valid("r", True) is False
	assert is_valid("false", True) is False
	assert is_valid("no", True) is False
	assert is_valid("none", True) is False
	assert is_valid("5", True) is False
	assert is_valid("0", True) is False
	assert is_valid("1", True) is False
	assert is_valid("5.5", True) is False

	## type_ = False
	assert is_valid("r", False) is False
	assert is_valid("true", False) is False
	assert is_valid("yes", False) is False
	assert is_valid("none", False) is False
	assert is_valid("5", False) is False
	assert is_valid("0", False) is False
	assert is_valid("1", False) is False
	assert is_valid("5.5", False) is False

	## type_ = "r"
	assert is_valid("w", "r") is False
	assert is_valid("false", "r") is False
	assert is_valid("true", "r") is False
	assert is_valid("yes", "r") is False
	assert is_valid("no", "r") is False
	assert is_valid("none", "r") is False
	assert is_valid("5", "r") is False
	assert is_valid("5.5", "r") is False
	assert is_valid("0", "r") is False
	assert is_valid("1", "r") is False



	# * type_ is a typing.<Foo>
	# * Optional
	### True
	assert is_valid(None, Optional[int]) is True
	assert is_valid("5", Optional[int]) is True
	assert is_valid(None, Optional[str]) is True
	assert is_valid("hi", Optional[str]) is True
	assert is_valid(None, Optional[float]) is True
	assert is_valid("5", Optional[float]) is True
	assert is_valid("5.5", Optional[float]) is True
	assert is_valid(None, Optional[bool]) is True
	assert is_valid("true", Optional[bool]) is True
	assert is_valid("False", Optional[bool]) is True
	assert is_valid("yes", Optional[bool]) is True
	assert is_valid("No", Optional[bool]) is True

	### False
	assert is_valid("true", Optional[int]) is False
	assert is_valid("5.5", Optional[int]) is False
	assert is_valid("true", Optional[str]) is False
	assert is_valid("true", Optional[float]) is False
	assert is_valid("5", Optional[bool]) is False

	# * Literal
	### True
	assert is_valid("hello", Literal["hello"]) is True
	assert is_valid("5", Literal["5"]) is True
	assert is_valid("5.5", Literal["5.5"]) is True
	assert is_valid("true", Literal[True]) is True
	assert is_valid("yes", Literal[True]) is True
	assert is_valid("false", Literal[False]) is True
	assert is_valid("no", Literal[False]) is True
	assert is_valid("r", Literal["r"]) is True

	### False
	assert is_valid("olleh", Literal["hello"]) is False
	assert is_valid("5.5", Literal["5"]) is False
	assert is_valid("false", Literal[True]) is False
	assert is_valid("no", Literal[True]) is False
	assert is_valid("true", Literal[False]) is False
	assert is_valid("yes", Literal[False]) is False
	assert is_valid("5", Literal[False]) is False
	assert is_valid("none", Literal[False]) is False
	assert is_valid("w", Literal["r"]) is False
