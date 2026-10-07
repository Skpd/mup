// Maps server -> client head (and sub) codes to the client code handling them.
//
// The receive dispatcher switches on the head code through a byte index table and a jump table:
//   cmp esi, <max head>; ja <loop>; mov cl, byte [esi + <index table>]; jmp [ecx*4 + <jump table>]
// Codes with sub codes do the same on the sub code byte read from the packet:
//   mov al, byte [ebp + <offset>]; cmp eax, <max sub>; ja ...; mov dl, byte [eax + <index table>]; jmp [edx*4 + <jump table>]
// For every case this walks the code until it jumps back to the receive loop and lists the calls made.
//
// args: <output file> <switch jmp address> <receive loop address>
//@category mu

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeMap;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.scalar.Scalar;

public class ReceiveDispatch extends GhidraScript {
    private Address loop;
    private Set<Address> caseStarts = new HashSet<>();

    static class Switch {
        Address jmp;
        int readOffset = -1;  // packet byte the switch value comes from, -1 for the head switch
        int max;
        int base;  // switch value = case index + base
        TreeMap<Integer, Address> cases = new TreeMap<>();
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Address headJmp = toAddr(args[1]);
        loop = toAddr(args[2]);

        Switch head = parseSwitch(headJmp);
        caseStarts.addAll(head.cases.values());

        try (PrintWriter out = new PrintWriter(new FileWriter(args[0]))) {
            for (var e : head.cases.entrySet()) {
                if (e.getValue().equals(loop)) {
                    continue;
                }
                describeCase(out, String.format("%02X", e.getKey()), e.getValue(), 1);
            }
        }
    }

    private void describeCase(PrintWriter out, String code, Address start, int depth) throws Exception {
        String indent = "  ".repeat(depth - 1);
        List<Address> calls = new ArrayList<>();
        Switch sub = walk(start, calls);

        out.printf("%s%s @ %s calls %s%n", indent, code, start, names(calls));
        if (sub != null) {
            out.printf("%s  sub switch on packet[%d], %02X..%02X%n", indent, sub.readOffset, sub.base, sub.base + sub.max);
            caseStarts.addAll(sub.cases.values());
            for (var e : sub.cases.entrySet()) {
                if (!e.getValue().equals(loop) && !isDefault(sub, e.getValue())) {
                    describeCase(out, code + " " + String.format("%02X", e.getKey()), e.getValue(), depth + 1);
                }
            }
        }
    }

    // the most common target of a sub switch is its default case
    private boolean isDefault(Switch s, Address a) {
        TreeMap<Address, Integer> counts = new TreeMap<>();
        for (Address t : s.cases.values()) {
            counts.merge(t, 1, Integer::sum);
        }
        Address most = null;
        for (var e : counts.entrySet()) {
            if (most == null || e.getValue() > counts.get(most)) {
                most = e.getKey();
            }
        }
        return a.equals(most) && counts.get(most) > 1;
    }

    private String names(List<Address> calls) {
        Set<String> out = new LinkedHashSet<>();
        for (Address a : calls) {
            Function f = getFunctionAt(a);
            out.add(f != null ? f.getName() + "@" + a : a.toString());
        }
        return out.toString();
    }

    // Follows the case code until it gets back to the receive loop, another case or a nested switch.
    private Switch walk(Address start, List<Address> calls) throws Exception {
        Deque<Address> todo = new ArrayDeque<>();
        Set<Address> seen = new HashSet<>();
        todo.push(start);
        Switch nested = null;

        while (!todo.isEmpty()) {
            Address a = todo.pop();
            while (a != null && seen.add(a)) {
                if (a.equals(loop) || (!a.equals(start) && caseStarts.contains(a))) {
                    break;
                }
                Instruction ins = getInstructionAt(a);
                if (ins == null) {
                    break;
                }

                if (ins.getFlowType().isCall()) {
                    for (Address t : ins.getFlows()) {
                        calls.add(t);
                    }
                } else if (ins.getFlowType().isJump() && ins.getFlowType().isComputed()) {
                    if (nested == null) {
                        nested = parseSwitch(a);
                    }
                    break;
                } else if (ins.getFlowType().isJump()) {
                    for (Address t : ins.getFlows()) {
                        todo.push(t);
                    }
                    if (ins.getFlowType().isUnConditional()) {
                        break;
                    }
                } else if (ins.getFlowType().isTerminal()) {
                    break;
                }
                a = ins.getFallThrough();
            }
        }
        return nested;
    }

    // Reads the index and jump tables of a switch ending with the computed jump at jmpAddr.
    private Switch parseSwitch(Address jmpAddr) throws Exception {
        Switch s = new Switch();
        s.jmp = jmpAddr;
        Instruction jmp = getInstructionAt(jmpAddr);
        Address jumpTable = toAddr(scalarIn(jmp));

        // xor ecx, ecx; mov cl, byte [eax + index table]; jmp [ecx*4 + jump table]
        Address indexTable = null;
        Instruction ins = jmp.getPrevious();
        if (ins.getMnemonicString().equals("MOV") && ins.toString().contains("byte ptr")) {
            indexTable = toAddr(scalarIn(ins));
        }

        for (int i = 0; i < 12 && ins != null; i++, ins = ins.getPrevious()) {
            String m = ins.getMnemonicString();
            if (m.equals("CMP") && ins.getScalar(1) != null && s.max == 0) {
                s.max = (int) ins.getScalar(1).getUnsignedValue();
            } else if ((m.equals("ADD") || m.equals("SUB")) && ins.getScalar(1) != null && s.max != 0) {
                long v = ins.getScalar(1).getSignedValue();
                s.base = (int) (m.equals("ADD") ? -v : v);
            } else if (m.equals("MOV") && ins.toString().contains("byte ptr [EBP + ")) {
                s.readOffset = (int) scalarIn(ins);
                break;
            }
        }

        for (int v = 0; v <= s.max; v++) {
            int index = indexTable != null ? getByte(indexTable.add(v)) & 0xFF : v;
            s.cases.put(v + s.base, toAddr(getInt(jumpTable.add(index * 4L)) & 0xFFFFFFFFL));
        }
        return s;
    }

    // largest constant in the operands: the table address, or the displacement in [reg + offset]
    private long scalarIn(Instruction ins) {
        long max = -1;
        for (int i = 0; i < ins.getNumOperands(); i++) {
            for (Object o : ins.getOpObjects(i)) {
                if (o instanceof Scalar s) {
                    max = Math.max(max, s.getUnsignedValue());
                }
            }
        }
        return max;
    }
}
