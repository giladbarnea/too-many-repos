from typing import Literal, Union, Optional

from too_many_repos.log import logger
from too_many_repos.tmrconfig import is_valid, cast_type

NoneType = type(None)

VALID_INTS = {'1', '0', '5', }
VALID_FLOATS = VALID_INTS | {'5.5', }
VALID_TRUE = {'true', 'yes'}
VALID_FALSE = {'false', 'no'}
VALID_BOOLS = VALID_TRUE | VALID_FALSE
VALID_STRS = {'r', }
VALID_NONE = {None, 'none'}

VALID_CASES = {
	bool:     VALID_BOOLS,
	int:      VALID_INTS,
	float:    VALID_FLOATS,
	str:      VALID_STRS,
	None:     VALID_NONE,
	NoneType: VALID_NONE,
	}

VALID_CASES.update({
	True:  VALID_CASES[bool] - VALID_FALSE,
	False: VALID_CASES[bool] - VALID_TRUE,
	5:     {'5'},
	5.5:   {'5.5'},
	5.0:   {'5'},
	'r':   {'r'},
	})

VALID_CASES.update({
	Literal[True]:     VALID_CASES[True],
	Literal[False]:    VALID_CASES[False],
	Literal['r']:      {'r'},
	Literal['r', 'w']: {'r', 'w'},
	})

for type_ in (int, float, bool, str):
	VALID_CASES[Optional[type_]] = VALID_CASES[type_] | VALID_CASES[None]

VALID_CASES.update({
	Union[Literal['r'], Literal['w']]:         {'r', 'w'},
	Union[Literal['r'], Literal[5]]:           {'r', '5'},
	Union[Literal['r'], Literal[5], None]:     {'r', '5'} | VALID_CASES[None],
	Union[Optional[Literal['r']], Literal[5]]: {'r', '5'} | VALID_CASES[None],
	Union[Literal['r'], Literal[True]]:        {'r'} | VALID_CASES[True],

	})

INVALID_CASES = {
	bool:     VALID_NONE | VALID_STRS | VALID_FLOATS,
	int:      VALID_NONE | VALID_STRS | VALID_BOOLS | {'5.5'},
	float:    VALID_NONE | VALID_STRS | VALID_BOOLS,
	str:      VALID_NONE | VALID_BOOLS | VALID_FLOATS,
	None:     VALID_BOOLS | VALID_FLOATS | VALID_STRS,
	NoneType: VALID_BOOLS | VALID_FLOATS | VALID_STRS,
	}

for type_ in (int, float, bool, str):
	INVALID_CASES[Optional[type_]] = INVALID_CASES[type_] - VALID_NONE

INVALID_CASES.update({
	True:  INVALID_CASES[bool] | VALID_FALSE,
	False: INVALID_CASES[bool] | VALID_TRUE,
	5:     INVALID_CASES[int] | {'6'},
	5.5:   INVALID_CASES[float] | {'5.6'},
	'r':   INVALID_CASES[str] | {'w'},
	'w':   INVALID_CASES[str] | {'r'},
	})

INVALID_CASES.update({
	Literal[True]:                     INVALID_CASES[True],
	Literal[False]:                    INVALID_CASES[False],
	Literal['w']:                      {'r'} | INVALID_CASES[str],
	Literal['w', 'r']:                 {'x'},
	Union[Literal['r'], Literal['w']]: {'x'} | INVALID_CASES[str],
	Union[Literal['r'], Literal[5]]:   {'x', '4'} | INVALID_CASES[str] - VALID_CASES[5],
	})


def test_is_valid():
	for type_, values in VALID_CASES.items():
		for val in values:
			assert is_valid(val, type_) is True

	for type_, values in INVALID_CASES.items():
		for val in values:
			assert is_valid(val, type_) is False


def test_cast_type():
	for type_, values in VALID_CASES.items():
		for val in values:
			cast = cast_type(val, type_)
			if type_ is None:
				assert cast is None
			else:
				type_of_cast = type(cast)
				logger.debug(f'[{"good" if type_of_cast is type_ else "warn"}]cast_type({repr(val)}, {repr(type_)}) → {repr(cast)}[/]')
	# assert is_valid(val, type_) is True
