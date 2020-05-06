import ljd.ast.nodes as nodes

_printers = {}
_indent_unit = '\t'


def dump(name, obj, level=0, **kwargs):
    indent = level * _indent_unit

    if name is not None:
        prefix = indent + name + " = "
    else:
        prefix = indent

    if isinstance(obj, (int, float, str)):
        print(prefix + str(obj))
    elif isinstance(obj, list):
        if len(obj) == 0:
            print(prefix + "[]")
            return

        print(prefix + "[")

        for value in obj:
            dump(None, value, level + 1)

        print(indent + "]")
    elif isinstance(obj, dict):
        print(prefix + "{")

        for key, value in obj.items():
            dump(key, value, level + 1)

        print(indent + "}")
    elif type(obj) in _printers:
        _printers[type(obj)](obj, prefix, level, **kwargs)
    else:
        _print_default(obj, prefix, level)


def _print_default(obj, prefix, level, exclude_blocks=False, extra_attrs=None):
    header_keys = _header(prefix, obj, attrs=extra_attrs)

    for key in dir(obj):
        if key.startswith("__") or key in header_keys:
            continue

        val = getattr(obj, key)

        # Exclude methods, they're of no use
        if callable(val):
            continue

        # Definitely don't show the blocks, otherwise it explodes the output
        if exclude_blocks and isinstance(val, nodes.Block):
            print(_indent_unit * (level + 1) + key + " = Block[index=%d]" % val.index)
            continue

        dump(key, val, level + 1)


def _header(prefix, obj, attrs=None, suffix="", **values):
    if attrs is None:
        attrs = ["_addr", "_line"]

    for name in attrs:
        if not hasattr(obj, name):
            continue
        pretty_name = name.lstrip("_")
        values[pretty_name] = getattr(obj, name)

    if len(values) == 0:
        attr_block = ""
    else:
        attr_block = "[%s]" % ", ".join(["%s=%s" % (k, v) for k, v in values.items()])

    if suffix != "":
        suffix = ": " + str(suffix)

    print(prefix + type(obj).__name__ + attr_block + suffix)

    return attrs


def _printer(klass):
    def wrapper(func):
        _printers[klass] = func
        return func

    return wrapper


# TODO add some way to show the _addr elements of all these

@_printer(nodes.Identifier)
def _print_str(obj, prefix, level):
    print(prefix + str(obj))


@_printer(nodes.Constant)
def _print_const(obj: nodes.Constant, prefix, level):
    s = '"' + obj.value + '"' if obj.type == nodes.Constant.T_STRING else obj.value
    _header(prefix, obj, suffix=s)


@_printer(nodes.Assignment)
def _print_assn(obj: nodes.Assignment, prefix, level):
    print(prefix + "Assignment[type=%s]" % ["T_LOCAL_DEFINITION", "T_NORMAL"][obj.type])
    dump("dest", obj.destinations, level + 1, omit_single=True)
    dump("expr", obj.expressions, level + 1, omit_single=True)


@_printer(nodes.VariablesList)
@_printer(nodes.ExpressionsList)
@_printer(nodes.StatementsList)
def _print_list(obj: nodes.VariablesList, prefix: str, level, omit_single=False):
    name = prefix[:-2].strip()  # chop out the = and strip it to recover the name

    if len(obj.contents) == 0:
        print(prefix + type(obj).__name__ + "[empty]")
    elif len(obj.contents) == 1:
        if omit_single:
            dump(name, obj.contents[0], level)
        else:
            print(prefix + type(obj).__name__ + "[single]: ", end='')
            dump(None, obj.contents[0], 0)
    else:
        print(prefix + type(obj).__name__ + "[")
        for value in obj.contents:
            dump(None, value, level + 1)
        print(_indent_unit * level + "]")


@_printer(nodes.TableElement)
def _print_table_elem(obj: nodes.TableElement, prefix, level):
    print(prefix + "TableElement")
    dump("table", obj.table, level + 1)
    dump("key", obj.key, level + 1)


@_printer(nodes.UnconditionalWarp)
@_printer(nodes.ConditionalWarp)
@_printer(nodes.IteratorWarp)
@_printer(nodes.NumericLoopWarp)
@_printer(nodes.EndWarp)
def _print_warp(obj, prefix, level):
    _print_default(obj, prefix, level, exclude_blocks=True)


@_printer(nodes.Block)
def _print_block(obj, prefix, level):
    _print_default(obj, prefix, level, extra_attrs=["index", "first_address", "last_address"])
