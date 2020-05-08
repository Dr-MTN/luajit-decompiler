-- Using a literal in an or like this omits the condition before what
-- would normally be a conditional jump. This can choke slotfinder
-- if we're not careful, since it can't track back the source of
-- slot 1 in block 2 (slot1 = global 'b').
print(1234 or b)

-- Bytecode:
-- 0001    GGET     0   0      ; "print"
-- 0002    KSHORT   1 1234
--    « Something like ISF would usually go here »
-- 0003    JMP      2 => 0005
-- 0004    GGET     1   1      ; "b"
-- 0005 => CALL     0   1   2
-- 0006    RET0     0   1
