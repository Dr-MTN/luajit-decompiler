#
# Copyright (C) 2013 Andrian Nord. See Copyright Notice in main.py
#

import re
import sys
import traceback

import ljd.ast.nodes as nodes
import ljd.ast.traverse as traverse
import ljd
from ljd.bytecode.instructions import SLOT_FALSE, SLOT_TRUE

compact_table_constructors = False
comment_empty_blocks = True
show_slot_ids = False
show_line_info = False

CMD_START_STATEMENT = 0
CMD_END_STATEMENT = 1
CMD_END_LINE = 3
CMD_START_BLOCK = 4
CMD_END_BLOCK = 5
CMD_WRITE = 6

OPERATOR_TYPES = (nodes.BinaryOperator, nodes.UnaryOperator)

STATEMENT_NONE = -1

STATEMENT_ASSIGNMENT = 0
STATEMENT_FUNCTION_CALL = 1
STATEMENT_RETURN = 2
STATEMENT_BREAK = 3

STATEMENT_IF = 4

STATEMENT_ITERATOR_FOR = 5
STATEMENT_NUMERIC_FOR = 6
STATEMENT_REPEAT_UNTIL = 7
STATEMENT_WHILE = 8

STATEMENT_FUNCTION = 9

VALID_IDENTIFIER = re.compile(r'^[a-zA-Z_][\w]*$')

RESERVED_WORDS = [
    "and",
    "break",
    "do",
    "else",
    "elseif",
    "end",
    "false",
    "for",
    "function",
    "if",
    "in",
    "local",
    "nil",
    "not",
    "or",
    "repeat",
    "return",
    "then",
    "true",
    "until",
    "while"
]

LIST_TYPES = (nodes.VariablesList,
              nodes.IdentifiersList,
              nodes.ExpressionsList,
              nodes.StatementsList)


class _State:
    def __init__(self):
        self.current_statement = STATEMENT_NONE
        self.function_name = None
        self.function_local = False
        self.function_method = False


class Visitor(traverse.Visitor):
    def __init__(self):
        traverse.Visitor.__init__(self)

        self.print_queue = []

        self._path = []
        self._visited_nodes = [set()]
        self._states = [_State()]

        self.line_token_map = {}

    # ##

    def _start_statement(self, statement):
        assert self._state().current_statement == STATEMENT_NONE
        self._state().current_statement = statement
        self.print_queue.append((CMD_START_STATEMENT, statement))

    def _end_statement(self, statement):
        assert statement == self._state().current_statement
        self._state().current_statement = STATEMENT_NONE
        self.print_queue.append((CMD_END_STATEMENT, statement))

    def _end_line(self):
        self.print_queue.append((CMD_END_LINE,))

    def _start_block(self):
        self.print_queue.append((CMD_START_BLOCK,))

    def _end_block(self):
        self.print_queue.append((CMD_END_BLOCK,))

    def _write(self, fmt, *args, **kargs):
        self.print_queue.append((CMD_WRITE, fmt, args, kargs))

    def _state(self):
        return self._states[-1]

    def _push_state(self):
        return self._states.append(_State())

    def _pop_state(self):
        return self._states.pop()

    # ##

    def _write_slot(self, node):
        slot = None
        slot_ids = None

        if isinstance(node, nodes.Identifier):
            slot = node.slot

            if node.id != -1:
                slot_ids = node.id
            else:
                slot_ids = getattr(node, "_ids", None)
        else:
            slot = getattr(node, "_slot", None)
            slot_id = getattr(node, "_slot_id", None)

        assert slot is not None

        name = "slot" + str(slot)

        if show_slot_ids:
            if slot_ids and slot_ids != -1:
                name += "#"
                if isinstance(slot_ids, list):
                    name += "{"
                    for i, slot_id in enumerate(slot_ids):
                        if i > 0:
                            name += "|"
                        name += str(slot_id)
                    name += "}"
                else:
                    name += str(slot_ids)

        self._write(name)

    # ##

    def visit_function_definition(self, node):
        is_statement = self._state().function_name is not None
        is_method = self._state().function_method

        if is_statement:
            self._start_statement(STATEMENT_FUNCTION)

            lineinfo = show_line_info and getattr(node, "_lineinfo", None)
            if lineinfo:
                self._write("-- Lines {0}-{1}".format(lineinfo[0], lineinfo[0] + lineinfo[1]))
                self._end_line()

            if self._state().function_local:
                self._write("local ")

            self._write("function ")

            fn = self._state().function_name
            if is_method:
                self._visit(fn.table)
                self._write(":")
                self._write(fn.key)
            else:
                self._visit(fn)

            self._write("(")

            self._state().function_name = None
        else:
            self._write("function (")

        args = node.arguments

        # If this is a method, remove the "self" argument
        if is_method:
            # AFAIK we don't ever use the args again, and if we
            #  use a new args object then the original one gets written later on
            orig = args.contents
            args.contents = orig[1:]

            assert orig[0].name == "self"

            # Same as above with function_name, set this to false afterwards
            # This is because it is only set in visit_assignment if it is a
            # simple assignment. If we have two functions one after the other,
            # and the first is a method while the other is not but uses
            # a complex assignment, then this variable will not be reset and
            # the above assertion will fail, as the writer thinks it is a method.
            # See https://gitlab.com/znixian/luajit-decompiler/issues/13
            self._state().function_method = False

        self._visit(args)

        self._write(")")

        self._end_line()

        # If there were unrecoverable errors in the function (namely invalid bytecodes), an error will
        # be set for the entire function. Print it out as a comment, along with an error to crash the
        # program should the generated source be recompiled.
        if node.error:
            self._start_block()
            self._write('error("Decompilation failed")')
            self._end_line()
            self._write("-- Exception in function building!")
            self._end_line()
            for entry in traceback.format_exception(value=node.error, tb=node.error.__traceback__, etype=None):
                for line in entry.strip().split("\n"):
                    self._write("-- " + line)
                    self._end_line()
            self._end_block()

        # Syntactic Sugar: Cull empty returns at the ends of functions
        if len(node.statements.contents) > 1:
            end_node = node.statements.contents[-1]
            if isinstance(end_node, nodes.Return) and len(end_node.returns.contents) == 0:
                node.statements.contents.pop(-1)

        self._visit(node.statements)

        self._write("end")

        if is_statement:
            self._end_statement(STATEMENT_FUNCTION)

    # ##

    def visit_table_constructor(self, node):
        self._write("{")

        # These are both delt with in the contents array, no need to visit them separately
        self._skip(node.array)
        self._skip(node.records)

        contents = node.array.contents + node.records.contents

        if len(node.array.contents) > 0:
            # Since we're using array+records in that order, the first
            #  array item is also the first combined item.
            first = contents.pop(0).value

            if not isinstance(first, nodes.Primitive) or first.type != first.T_NIL:
                record = nodes.TableRecord()
                record.key = nodes.Constant()
                record.key.type = nodes.Constant.T_INTEGER
                record.key.value = 0
                record.value = first

                contents.insert(0, record)

        if compact_table_constructors and len(contents) == 1:
            self._visit(contents[0])
        elif len(contents) > 0:
            self._end_line()

            self._start_block()

            all_records = nodes.RecordsList()
            all_records.contents = contents

            self._visit(all_records)

            self._end_block()

        self._write("}")

    def visit_table_record(self, node):
        if self._is_valid_name(node.key):
            self._write(node.key.value)

            self._skip(node.key)

            self._write(" = ")
        else:
            self._write("[")

            self._visit(node.key)

            self._write("] = ")

        self._visit(node.value)

    # visit_array_record is a passthough

    # ##

    def visit_assignment(self, node):
        is_local = node.type == node.T_LOCAL_DEFINITION

        dsts = node.destinations.contents
        srcs = node.expressions.contents

        num_dsts = len(dsts)
        num_srcs = len(srcs)

        src_is_function = False
        if num_dsts == 1 and num_srcs == 1:
            dst = dsts[0]
            src = srcs[0]

            src_is_function = isinstance(src, nodes.FunctionDefinition)
            dst_is_simple = self._is_acceptable_func_dst(dst)

            if src_is_function:
                if dst_is_simple:
                    self._state().function_name = dst
                    self._state().function_local = is_local
                    self._state().function_method = self._is_method(dst, src)

                    self._visit(src)

                    self._skip(node.destinations)
                    self._skip(node.expressions)

                    return

        if is_local:
            self._write("local ")

        if src_is_function:
            self._start_statement(STATEMENT_FUNCTION)
        else:
            self._start_statement(STATEMENT_ASSIGNMENT)

        self._visit(node.destinations)

        self._write(" = ")

        self._visit(node.expressions)

        if src_is_function:
            self._end_statement(STATEMENT_FUNCTION)
        else:
            self._end_statement(STATEMENT_ASSIGNMENT)

    def _is_variable(self, node):
        if isinstance(node, nodes.Identifier):
            return True

        return self._is_global(node)

    def _is_global(self, node):
        if isinstance(node, nodes.TableElement):
            return self._is_builtin(node.table)

        return False

    def _is_acceptable_func_dst(self, dst):
        # If this is an identifier, we're fine
        if isinstance(dst, nodes.Identifier):
            return True

        # Otherwise, it must be a table element
        if not isinstance(dst, nodes.TableElement):
            return False

        # It's key must be a constant
        if not isinstance(dst.key, nodes.Constant):
            return False

        # Ensure the key is a string
        if dst.key.type != nodes.Constant.T_STRING:
            return False

        # Ensure the key is alphanumeric, and the first character is a letter
        key = dst.key.value
        if key[0].isdigit():
            # TODO I don't think the code in this generator checks this - so you can end up with a.1234.b
            return False

        for char in key:
            if not char.isalnum() and char != "_":
                return False

        # Finally, recurse up the chain
        return self._is_acceptable_func_dst(dst.table)

    def _is_method(self, dst, func):
        if not func.arguments.contents:
            return False

        selfarg = func.arguments.contents[0]

        # This chokes on functions with their first argument being the vararg symbol
        #  otherwise, since they don't have a `name` property
        #  ex. `function myfunc(...)`
        if not isinstance(selfarg, nodes.Identifier):
            return False

        if selfarg.name != "self":
            return False

        # Ensure the destination is on a table
        if not isinstance(dst, nodes.TableElement):
            return False

        return True

    @staticmethod
    def _is_builtin(node):
        if not isinstance(node, nodes.Identifier):
            return False

        return node.type == nodes.Identifier.T_BUILTIN

    @staticmethod
    def _is_valid_name(key):
        if not isinstance(key, nodes.Constant) or key.type != key.T_STRING:
            return False

        if not VALID_IDENTIFIER.match(key.value):
            return False

        return key.value not in RESERVED_WORDS

    # ##

    def visit_binary_operator(self, node):
        is_left_op = isinstance(node.left, OPERATOR_TYPES)
        is_right_op = isinstance(node.right, OPERATOR_TYPES)

        # If the subexpressions are less in order then this expression,
        # they should go with parentheses

        left_parentheses = False
        right_parentheses = False

        binop = nodes.BinaryOperator

        # Rules for braces:
        #  * A group MUST be braced if it is of a lower precedence (eg, if a * has a +, then the + must be braced)
        #  * Braces are unnecessary if the group has a higher precedence
        #  * If a group is of the same precedence, it must be braced if it is not on the associative side - so
        #     `(a * b) / (c * d)` comes out to `a * b / (c * d)`

        if is_left_op:
            if node.is_right_associative():
                left_parentheses = node.left.precedence() <= node.precedence()
            else:
                left_parentheses = node.left.precedence() < node.precedence()

        if is_right_op:
            if node.is_right_associative():
                right_parentheses = node.right.precedence() < node.precedence()
            else:
                right_parentheses = node.right.precedence() <= node.precedence()

                # If this is either `a + (b + c)`, `a + (b - c)`, `a * (b * c)`, or `a * (b / c)`, we
                #  can drop the braces:
                if node.type == binop.T_ADD and binop.T_ADD <= node.right.type <= binop.T_SUBTRACT:
                    right_parentheses = False

                elif node.type == binop.T_MULTIPLY and binop.T_MULTIPLY <= node.right.type <= binop.T_DIVISION:
                    right_parentheses = False

        if left_parentheses:
            self._write("(")

        self._visit(node.left)

        if left_parentheses:
            self._write(")")

        if node.type == nodes.BinaryOperator.T_LOGICAL_OR:
            self._write(" or ")
        elif node.type == nodes.BinaryOperator.T_LOGICAL_AND:
            self._write(" and ")

        elif node.type == nodes.BinaryOperator.T_LESS_THEN:
            self._write(" < ")
        elif node.type == nodes.BinaryOperator.T_GREATER_THEN:
            self._write(" > ")
        elif node.type == nodes.BinaryOperator.T_LESS_OR_EQUAL:
            self._write(" <= ")
        elif node.type == nodes.BinaryOperator.T_GREATER_OR_EQUAL:
            self._write(" >= ")

        elif node.type == nodes.BinaryOperator.T_NOT_EQUAL:
            self._write(" ~= ")
        elif node.type == nodes.BinaryOperator.T_EQUAL:
            self._write(" == ")

        elif node.type == nodes.BinaryOperator.T_CONCAT:
            self._write(" .. ")

        elif node.type == nodes.BinaryOperator.T_ADD:
            self._write(" + ")
        elif node.type == nodes.BinaryOperator.T_SUBTRACT:
            self._write(" - ")

        elif node.type == nodes.BinaryOperator.T_DIVISION:
            self._write(" / ")
        elif node.type == nodes.BinaryOperator.T_MULTIPLY:
            self._write(" * ")
        elif node.type == nodes.BinaryOperator.T_MOD:
            self._write(" % ")

        else:
            assert node.type == nodes.BinaryOperator.T_POW
            self._write("^")

        if right_parentheses:
            self._write("(")

        self._visit(node.right)

        if right_parentheses:
            self._write(")")

    def visit_unary_operator(self, node):
        if node.type == nodes.UnaryOperator.T_LENGTH_OPERATOR:
            self._write("#")
        elif node.type == nodes.UnaryOperator.T_MINUS:
            self._write("-")
        elif node.type == nodes.UnaryOperator.T_NOT:
            if hasattr(node.operand, "slot"):
                if not node.operand.slot == SLOT_FALSE:
                    self._write("not ")
                else:
                    node.operand.slot = SLOT_TRUE
            else:
                self._write("not ")
        elif ljd.CURRENT_VERSION > 2.0:
            # TODO
            if node.type == nodes.UnaryOperator.T_TOSTRING:
                self._write("tostring")
            elif node.type == nodes.UnaryOperator.T_TONUMBER:
                self._write("tonumber")

        has_subexp = isinstance(node.operand, OPERATOR_TYPES)
        need_parentheses = has_subexp and node.operand.type < node.type

        if need_parentheses:
            self._write("(")

        self._visit(node.operand)

        if need_parentheses:
            self._write(")")

    # ##

    def visit_statements_list(self, node):
        if len(self._states) > 1:
            self._start_block()

        self._push_state()

        if comment_empty_blocks and len(self._path) > 1:
            add_comment = False
            if len(node.contents) == 0:
                add_comment = isinstance(self._path[-2], (nodes.IteratorFor, nodes.If, nodes.ElseIf))
            elif len(node.contents) == 1:
                add_comment = isinstance(node.contents[0], nodes.NoOp)

            if add_comment:
                self._write("-- Nothing")
                self._end_line()

    def leave_statements_list(self, node):
        self._pop_state()

        if len(self._states) > 1:
            self._end_block()

    def _visit_comma_separated_list(self, node):
        if not node.contents:
            return

        for subnode in node.contents[:-1]:
            self._visit(subnode)
            self._write(", ")

        self._visit(node.contents[-1])

    visit_identifiers_list = _visit_comma_separated_list

    def visit_records_list(self, node):
        if not node.contents:
            return

        for subnode in node.contents[:-1]:
            self._visit(subnode)

            self._write(",")
            self._end_line()

        self._visit(node.contents[-1])
        self._end_line()

    visit_variables_list = _visit_comma_separated_list
    visit_expressions_list = _visit_comma_separated_list

    # ##

    def visit_identifier(self, node):
        if node.type == nodes.Identifier.T_SLOT:
            if node.slot == SLOT_FALSE:
                self._write("false")
            elif node.slot == SLOT_TRUE:
                self._write("true")
            else:
                self._write_slot(node)
        elif not node.name and node.type == nodes.Identifier.T_UPVALUE:
            placeholder_identifier = "uv{0}"
            self._write(placeholder_identifier, node.slot)
        else:
            self._write(node.name)

    def visit_multres(self, node):
        self._write("MULTRES")

    def visit_table_element(self, node):
        key = node.key
        base = node.table

        is_valid_name = self._is_valid_name(key)

        if self._is_global(node):
            assert is_valid_name

            self._skip(base)
            self._skip(key)

            self._write(key.value)

            return

        base_is_constructor = isinstance(base, nodes.TableConstructor) \
                              or isinstance(base, OPERATOR_TYPES) \
                              or (isinstance(base, nodes.Constant) and base.type == nodes.Constant.T_STRING)

        if base_is_constructor:
            self._write("(")

        self._visit(base)

        if base_is_constructor:
            self._write(")")

        if is_valid_name:
            self._write(".")
            self._write(key.value)
            self._skip(key)
        else:
            self._write("[")
            self._visit(key)
            self._write("]")

    def visit_vararg(self, node):
        self._write("...")

    def visit_function_call(self, node):
        is_statement = self._state().current_statement == STATEMENT_NONE

        if is_statement:
            self._start_statement(STATEMENT_FUNCTION_CALL)

        func = node.function

        # We are going to modify this list so we can remove the first argument
        args = node.arguments.contents

        if node.is_method:
            func = node.function
            base = func.table
            base_is_constructor = isinstance(base, nodes.TableConstructor) \
                                  or isinstance(base, OPERATOR_TYPES) \
                                  or (isinstance(base, nodes.Constant) and base.type == nodes.Constant.T_STRING)

            if base_is_constructor:
                self._write("(")

            self._visit(base)

            if base_is_constructor:
                self._write(")")

            self._write(":")

            assert self._is_valid_name(func.key)

            self._write(func.key.value)
            self._skip(func.key)

            self._skip(node.function)

            self._write("(")
            self._visit(node.arguments)
            self._write(")")

            self._skip(node.arguments)
        else:
            self._visit(node.function)

            self._write("(")
            self._visit(node.arguments)
            self._write(")")

        if is_statement:
            self._end_statement(STATEMENT_FUNCTION_CALL)

    # ##

    def visit_if(self, node):
        self._start_statement(STATEMENT_IF)

        self._write("if ")

        self._visit(node.expression)

        self._write(" then")

        self._end_line()

        self._visit(node.then_block)

        self._visit_list(node.elseifs)

        if len(node.else_block.contents) > 0:
            self._write("else")

            self._end_line()

            self._visit(node.else_block)
        else:
            self._skip(node.else_block)

        self._write("end")

        self._end_statement(STATEMENT_IF)

    def visit_elseif(self, node):
        self._write("elseif ")

        self._visit(node.expression)

        self._write(" then")

        self._end_line()

        self._visit(node.then_block)

    # ##

    def visit_block(self, node):
        self._write("--- BLOCK #{0} {1}-{2}, warpins: {3} ---",
                    node.index,
                    node.first_address, node.last_address,
                    node.warpins_count)

        self._end_line()

        self._visit_list(node.contents)

        self._write("--- END OF BLOCK #{0} ---", node.index)

        self._end_line()

        self._end_line()
        self._visit(node.warp)
        self._end_line()

        self._end_line()

    def visit_unconditional_warp(self, node):
        if node.type == nodes.UnconditionalWarp.T_FLOW:
            self._write("FLOW")
        elif node.type == nodes.UnconditionalWarp.T_JUMP:
            self._write("UNCONDITIONAL JUMP")

        self._write("; TARGET BLOCK #{0}", node.target.index)

        self._end_line()

    def visit_conditional_warp(self, node):
        if hasattr(node, "_slot"):
            self._write_slot(node)
            self._write(" = ")

        self._write("if ")

        self._visit(node.condition)

        self._write(" then")
        self._end_line()

        self._write("JUMP TO BLOCK #{0}", node.true_target.index)

        self._end_line()
        self._write("else")
        self._end_line()

        self._write("JUMP TO BLOCK #{0}", node.false_target.index)

        self._end_line()

        self._write("end")
        self._end_line()

    def visit_iterator_warp(self, node):
        self._write("for ")

        self._visit(node.variables)

        self._write(" in ")

        self._visit(node.controls)

        self._end_line()
        self._write("LOOP BLOCK #{0}", node.body.index)

        self._end_line()
        self._write("GO OUT TO BLOCK #{0}", node.way_out.index)

        self._end_line()

    def visit_numeric_loop_warp(self, node):
        self._write("for ")

        self._visit(node.index)

        self._write("=")

        self._visit(node.controls)

        self._end_line()
        self._write("LOOP BLOCK #{0}", node.body.index)

        self._end_line()
        self._write("GO OUT TO BLOCK #{0}", node.way_out.index)

    # ##

    def visit_return(self, node):
        self._start_statement(STATEMENT_RETURN)

        if len(node.returns.contents) > 0:
            self._write("return ")
        else:
            self._write("return")

        self._visit(node.returns)

        self._end_statement(STATEMENT_RETURN)

    def visit_break(self, node):
        self._start_statement(STATEMENT_BREAK)

        self._write("break")

        self._end_statement(STATEMENT_BREAK)

    # ##

    def visit_while(self, node):
        self._start_statement(STATEMENT_WHILE)

        self._write("while ")
        self._visit(node.expression)
        self._write(" do")

        self._end_line()

        self._visit(node.statements)

        self._write("end")
        self._end_statement(STATEMENT_WHILE)

    def visit_repeat_until(self, node):
        self._start_statement(STATEMENT_REPEAT_UNTIL)

        self._write("repeat")
        self._end_line()

        self._visit(node.statements)

        self._write("until ")
        self._visit(node.expression)

        self._end_statement(STATEMENT_REPEAT_UNTIL)

    def visit_numeric_for(self, node):
        self._start_statement(STATEMENT_NUMERIC_FOR)

        self._write("for ")
        self._visit(node.variable)
        self._write(" = ")

        # Manually visit the expressions so we have the option to skip the default increment
        self._skip(node.expressions)

        expressions = node.expressions.contents
        assert len(expressions) == 3
        if isinstance(expressions[2], nodes.Constant) and expressions[2].value == 1:
            expressions = expressions[:-1]

        for subnode in expressions[:-1]:
            self._visit(subnode)
            self._write(", ")

        self._visit(expressions[-1])

        self._write(" do")

        self._end_line()

        self._visit(node.statements)

        self._write("end")
        self._end_statement(STATEMENT_NUMERIC_FOR)

    def visit_iterator_for(self, node):
        self._start_statement(STATEMENT_ITERATOR_FOR)

        self._write("for ")
        self._visit(node.identifiers)
        self._write(" in ")
        self._visit(node.expressions)
        self._write(" do")

        self._end_line()

        self._visit(node.statements)

        self._write("end")
        self._end_statement(STATEMENT_ITERATOR_FOR)

    # ##

    def visit_constant(self, node):
        if node.type != nodes.Constant.T_STRING:
            self._write(node.value)
            return

        lines = node.value.count("\n")

        if lines > 2:
            self._write("[[")

            self._write("\n")

            self._write(node.value)

            self._write("]]")
        else:
            text = node.value

            text = text.replace("\\", "\\\\")
            text = text.replace("\t", "\\t")
            text = text.replace("\n", "\\n")
            text = text.replace("\r", "\\r")
            text = text.replace("\"", "\\\"")

            self._write('"' + text + '"')

    def visit_primitive(self, node):
        if node.type == nodes.Primitive.T_FALSE:
            self._write("false")
        elif node.type == nodes.Primitive.T_TRUE:
            self._write("true")
        else:
            self._write("nil")

    def _visit_node(self, handler, node):
        self._path.append(node)

        traverse.Visitor._visit_node(self, handler, node)

    def _leave_node(self, handler, node):
        self._path.pop()

        traverse.Visitor._leave_node(self, handler, node)

    def _skip(self, node):
        self._visited_nodes[-1].add(node)

    def _visit(self, node):
        assert node is not None

        if node in self._visited_nodes[-1]:
            return

        self._visited_nodes[-1].add(node)

        # TODO: add check
        # "It looks like you forgot about some node changes..."

        self._visited_nodes.append(set())

        if hasattr(node, "_decompilation_error_here"):
            self._end_line()
            self._write("-- Decompilation error in this vicinity:")
            self._end_line()

        if hasattr(node, "_line") and node._line:
            line = node._line
            self.line_token_map[line] = len(self.print_queue)

        traverse.Visitor._visit(self, node)

        self._visited_nodes.pop()


def write(fd, ast, generate_linemap=False):
    assert isinstance(ast, nodes.FunctionDefinition)

    visitor = Visitor()

    traverse.traverse(visitor, ast.statements)

    line_map = {}
    token_map = _process_queue(fd, visitor.print_queue, visitor.line_token_map.values() if generate_linemap else None)

    if generate_linemap:
        for inline, tok in visitor.line_token_map.items():
            line_map[inline] = token_map[tok]

        return line_map


def wrapped_write(fd, *objects, sep=' ', end='\n', file=sys.stdout):
    # TODO find out why this was added (asking Aussiemon might be a good place to start)
    # For now, just write it without reencoding
    # Also, it made the output platform-dependant, rather than being identical across platforms
    fd.write(*objects)

    # enc = fd.encoding
    # if enc == 'UTF-8':
    #     fd.write(*objects)
    # else:
    #     f = lambda obj: str(obj).encode(enc, errors='backslashreplace').decode(enc)
    #     fd.write(*map(f, objects))


def _get_next_significant(queue, i):
    i += 1

    while i < len(queue):
        cmd = queue[i]

        if cmd[0] not in (CMD_END_LINE, CMD_WRITE):
            break

        i += 1

    if i < len(queue):
        return queue[i]
    else:
        return CMD_END_BLOCK,


def _process_queue(fd, queue, wanted_tokens):
    indent = 0

    line_broken = True

    token_map = {}
    line_num = 1

    for i, cmd in enumerate(queue):
        assert isinstance(cmd, tuple)

        if wanted_tokens and i in wanted_tokens:
            token_map[i] = line_num

        if cmd[0] == CMD_START_STATEMENT:
            # assert line_broken
            pass
        elif cmd[0] == CMD_END_STATEMENT:
            wrapped_write(fd, "\n")
            line_num += 1
            line_broken = True

            next_cmd = _get_next_significant(queue, i)

            if next_cmd[0] not in (CMD_END_BLOCK, CMD_START_BLOCK):
                assert next_cmd[0] == CMD_START_STATEMENT

                if next_cmd[1] != cmd[1] \
                        or cmd[1] >= STATEMENT_IF \
                        or next_cmd[1] >= STATEMENT_IF:
                    wrapped_write(fd, "\n")
                    line_num += 1
        elif cmd[0] == CMD_END_LINE:
            wrapped_write(fd, "\n")
            line_num += 1
            line_broken = True
        elif cmd[0] == CMD_START_BLOCK:
            indent += 1
        elif cmd[0] == CMD_END_BLOCK:
            indent -= 1

            assert indent >= 0
        else:
            assert cmd[0] == CMD_WRITE

            if line_broken:
                wrapped_write(fd, indent * '\t')
                line_broken = False

            _id, fmt, args, kargs = cmd

            if len(args) + len(kargs) > 0:
                text = fmt.format(*args, **kargs)
            elif isinstance(fmt, str):
                text = fmt
            else:
                text = str(fmt)

            wrapped_write(fd, text)

    return token_map
