import ljd.ast.nodes as nodes


def insert_table_record(constructor, key, value):
	array = constructor.array.contents
	records = constructor.records.contents

	if isinstance(key, nodes.MULTRES):
		assert len(records) == 0 \
			or isinstance(records[-1], nodes.TableRecord)

		records.append(value)
		return

	while isinstance(key, nodes.Constant)			\
				and key.type == key.T_INTEGER	\
				and key.value >= 0:
		if key.value > len(array):
			break

		record = nodes.ArrayRecord()
		record.value = value

		if key.value == len(array):
			array.append(record)
		else:
			array[key.value] = record

		return

	record = nodes.TableRecord()
	record.key = key
	record.value = value

	if len(records) == 0:
		records.append(record)
		return

	last = records[-1]

	if isinstance(last, (nodes.FunctionCall, nodes.Vararg)):
		records.insert(-1, record)
	else:
		records.append(record)
