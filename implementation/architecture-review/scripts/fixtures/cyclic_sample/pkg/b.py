from pkg.a import do_a


def do_b():
    return "b"


def do_b_calls_a():
    return do_a()
