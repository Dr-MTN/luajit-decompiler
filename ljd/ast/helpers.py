import ljd.ast.nodes as nodes
import ljd.ast.traverse as traverse


def insert_table_record(constructor, key, value, replace, allow_duplicates=True):
    array = constructor.array.contents
    records = constructor.records.contents

    if isinstance(key, nodes.MULTRES):
        assert len(records) == 0 \
               or isinstance(records[-1], nodes.TableRecord)

        records.append(value)
        return True

    while isinstance(key, nodes.Constant) \
            and key.type == key.T_INTEGER \
            and key.value >= 0:
        index = key.value

        if index == 1 and len(array) == 0:
            record = nodes.ArrayRecord()
            record.value = nodes.Primitive()
            record.value.type = nodes.Primitive.T_NIL

            array.append(record)

        if index > len(array):
            break

        record = nodes.ArrayRecord()
        record.value = value

        if len(array) == 0 or index == len(array):
            array.append(record)
            return True
        elif replace:
            array[index] = record
            return True
        else:
            current_value = array[index].value
            if isinstance(current_value, nodes.Primitive) and current_value.type == nodes.Primitive.T_NIL:
                array[index] = record
                return True
            return False

    # Check for record duplicates
    # This isn't nearly as important as duplicate protection with arrays, since both values
    # end up in the table to the user can make sense of what happened. Nonetheless, we should still
    # reject stuff like this.
    if not allow_duplicates:
        for rec in records:
            if isinstance(rec, nodes.TableRecord):
                if is_equal(rec.key, key, strict=False):
                    return False

    record = nodes.TableRecord()
    record.key = key
    record.value = value

    if len(records) == 0:
        records.append(record)
        return True

    last = records[-1]

    if isinstance(last, (nodes.FunctionCall, nodes.Vararg)):
        records.insert(-1, record)
    else:
        records.append(record)

    return True


def has_same_table(node, table):
    class Checker(traverse.Visitor):
        def __init__(self, checker_table):
            super().__init__()
            self.found = False
            self.table = checker_table
            self.current_function_depth = 0

        def visit_table_element(self, checked_node):
            if is_equal(self.table, checked_node.table):
                self.found = True

        def visit_function_definition(self, node):
            self.current_function_depth += 1

        def leave_function_definition(self, node):
            self.current_function_depth -= 1

        def visit_identifier(self, node):
            if self.current_function_depth > 0 and node.type == node.T_UPVALUE:
                if getattr(self.table, "name", False) == node.name:  # Use False to avoid matches on None
                    self.found = True

        def _visit(self, checked_node):
            if not self.found:
                traverse.Visitor._visit(self, checked_node)

        def _visit_list(self, nodes_list):
            if not self.found:
                traverse.Visitor._visit_list(self, nodes_list)

    checker = Checker(table)
    traverse.traverse(checker, node)

    return checker.found


def is_equal(a, b, strict=True):
    if type(a) != type(b):
        return False

    if isinstance(a, nodes.Identifier):
        return a.type == b.type and a.slot == b.slot
    elif isinstance(a, nodes.TableElement):
        return is_equal(a.table, b.table, strict) \
               and is_equal(a.key, b.key, strict)
    elif isinstance(a, nodes.Constant):
        return a.type == b.type and a.value == b.value
    else:
        assert not strict
        return False
